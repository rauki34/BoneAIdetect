"""请求限流（分层）

**按防护目标选择限流维度**，而不是一刀切：

    @limit('login',   key='ip')    认证层 —— 防爆破
    @limit('ai_chat', key='user')  成本层 —— 控 token 开销
    @limit('api_general')          通用层 —— 防滥用

为什么认证层必须按 IP：攻击者用的是随机用户名，按账号限流拦不住；
若沿用旧的「必须已登录才限流」逻辑，登录接口根本无法被保护。

实现说明：
- 算法：滑动窗口（无固定窗口的边界突刺问题）
- 存储：进程内 dict + 锁，**多 worker 部署不共享、重启即清零**
- 阶段 6 将迁至 Redis ZSET，本模块对外接口保持不变
"""
import time
from datetime import datetime
from functools import wraps

from flask import current_app, jsonify, request

from core.auth import get_current_user
from core.helpers import log_operation
from core.state import RATE_LIMIT_CONFIG, rate_limit_lock, rate_limit_storage
from utils.logger import logger


def client_ip():
    """取真实客户端 IP

    X-Forwarded-For 由客户端可伪造，仅当部署在**可信反向代理**之后、
    且由 TRUST_PROXY=True 显式开启时才采信；否则一律用 remote_addr。
    """
    try:
        if current_app.config.get('TRUST_PROXY'):
            forwarded = request.headers.get('X-Forwarded-For')
            if forwarded:
                return forwarded.split(',')[0].strip()
    except RuntimeError:
        pass
    return request.remote_addr or 'unknown'


def resolve_identity(key):
    """按维度解析限流标识"""
    if key == 'ip':
        return f'ip:{client_ip()}'
    if key == 'user':
        user = get_current_user()
        return f'user:{user.id}' if user else f'ip:{client_ip()}'
    if key == 'user_or_ip':
        user = get_current_user()
        return f'user:{user.id}' if user else f'ip:{client_ip()}'
    raise ValueError(f'未知的限流维度: {key}（可选 ip / user / user_or_ip）')


def check_rate_limit(ident, limit_type='api_general'):
    """滑动窗口限流检查

    Args:
        ident: 限流标识（如 'ip:127.0.0.1' / 'user:3'）
        limit_type: RATE_LIMIT_CONFIG 中的键

    Returns:
        (是否允许, 剩余次数, 重试等待秒数)
    """
    cfg = RATE_LIMIT_CONFIG.get(limit_type, RATE_LIMIT_CONFIG['api_general'])
    max_requests = cfg['max_requests']
    window = cfg['time_window']

    with rate_limit_lock:
        now = time.time()
        key = f'{ident}:{limit_type}'

        # 淘汰窗口外的记录
        hits = [t for t in rate_limit_storage[key] if now - t < window]
        rate_limit_storage[key] = hits

        if len(hits) >= max_requests:
            # 最早那次请求滑出窗口时即可恢复
            retry_after = int(window - (now - hits[0])) + 1
            return False, 0, max(retry_after, 1)

        hits.append(now)
        return True, max_requests - len(hits), 0


def limit(limit_type, key='user', bypass_roles=None):
    """限流装饰器

    Args:
        limit_type: RATE_LIMIT_CONFIG 中的键
        key: 限流维度，'ip' | 'user' | 'user_or_ip'
        bypass_roles: 不限流的角色；默认取配置的 RATE_LIMIT_BYPASS_ROLES
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if bypass_roles is not None:
                roles = set(bypass_roles)
            else:
                try:
                    roles = set(current_app.config.get(
                        'RATE_LIMIT_BYPASS_ROLES') or [])
                except RuntimeError:
                    roles = set()

            if roles:
                user = get_current_user()
                if user and user.role in roles:
                    return f(*args, **kwargs)

            ident = resolve_identity(key)

            try:
                allowed, remaining, retry_after = check_rate_limit(
                    ident, limit_type)
            except Exception as e:
                # fail-open：限流组件故障不应导致业务不可用
                # （医疗场景下，宁可被刷也不能让医护无法工作）
                logger.error('限流检查异常，放行本次请求: %s', e, exc_info=True)
                return f(*args, **kwargs)

            if not allowed:
                log_operation(
                    description=f'限流触发: {ident}, 类型={limit_type}',
                    success=False,
                    error_msg='请求频率超过限制',
                )
                resp = jsonify({
                    'error': '请求过于频繁，请稍后再试',
                    'error_code': 'RATE_LIMIT_EXCEEDED',
                    'retry_after': retry_after,
                    'timestamp': datetime.utcnow().isoformat(),
                })
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry_after)
                return resp

            return _attach_headers(f(*args, **kwargs), remaining, limit_type)

        return wrapper
    return decorator


def _attach_headers(response, remaining, limit_type):
    """在响应上附加限流信息头（兼容 (body, status) 元组返回）"""
    target = response[0] if isinstance(response, tuple) else response
    if hasattr(target, 'headers'):
        target.headers['X-RateLimit-Remaining'] = str(remaining)
        target.headers['X-RateLimit-Limit'] = str(
            RATE_LIMIT_CONFIG[limit_type]['max_requests'])
    return response


# 兼容旧名（原装饰器名为 rate_limit，且语义为按用户限流）
rate_limit = limit
