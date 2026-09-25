"""用户额度（单会话 / 每日）

与 `core/ratelimit.py` 是**时间尺度不同的两层**，不是替代关系：

    @limit('ai_chat', key='user')   分钟级 —— 防突发流量（滑动窗口）
    quota.check_and_consume(...)    会话级 —— 单个会话的对话轮数上限
                                    每日级 —— 单用户每天的对话次数上限

为什么另起一层而不是把阈值调大：分钟级限流只能约束"多快"，约束不了"总量"。
一次 Agent 请求最坏触发 5 次 LLM 调用（编排最多 5 轮），按 5 次/分钟放行
意味着一个用户一小时能烧掉 25 次推演；分钟阈值调大则突发流量失去防护。
两个尺度必须分开表达。

**日期边界用本地日期**，不是 UTC：本仓已经吃过一次这个坑（阶段 8 踩坑第 9 条，
服务端 utcnow() 与 SQL now() 差 8 小时）。用 UTC 的话额度会在北京时间早上 8 点
重置，而界面上「今日剩余 N 次」会与用户的直觉对不上。

**降级策略与 ratelimit 一致**：Redis 不可用时退回进程内计数并**放行**
（fail-open）。理由同 ratelimit.py 的注释：医疗场景下宁可被刷，也不能让
患者用不了助手。降级期多进程不共享、重启清零，用 WARNING 明示。

**不退款**：额度在请求准入时消费。LLM 成本在准入之后随即发生；而并发请求下
退款会被当成放大器（先占额度过检查、失败后再退，等于无限额）。偶尔误扣
（例如 provider 全挂、回答走了预设话术）是可接受的代价 —— 这条写成注释是
为了避免后人把它当 bug 修掉。
"""
import datetime
import threading

from core.cache import get_redis, report_failure
from core.state import QUOTA_CONFIG
from utils.logger import logger

# 判定 + 消费两把计数器，必须原子完成：拆成多条命令会在并发请求的
# 「检查」与「写入」之间产生竞态，让用户超额（与 ratelimit 的 Lua 同一理由）
_QUOTA_LUA = """
local session_key = KEYS[1]
local daily_key   = KEYS[2]
local session_max = tonumber(ARGV[1])
local daily_max   = tonumber(ARGV[2])
local session_ttl = tonumber(ARGV[3])
local daily_ttl   = tonumber(ARGV[4])

local s = tonumber(redis.call('GET', session_key) or '0')
local d = tonumber(redis.call('GET', daily_key) or '0')

if s >= session_max then
    -- 会话额度拒绝时 retry_after 恒为 0：它只能靠新建会话解除，等不会等到
    return {0, 1, s, d, 0}
end
if d >= daily_max then
    return {0, 2, s, d, daily_ttl}
end

local ns = redis.call('INCR', session_key)
if ns == 1 then redis.call('EXPIRE', session_key, session_ttl) end
local nd = redis.call('INCR', daily_key)
if nd == 1 then redis.call('EXPIRE', daily_key, daily_ttl) end
return {1, 0, ns, nd, 0}
"""

_script = None
_lock = threading.Lock()
# 降级用的进程内计数：{key: [count, expire_at]}
_memory = {}


def _get_script(client):
    global _script
    if _script is None:
        _script = client.register_script(_QUOTA_LUA)
    return _script


def local_day(now=None):
    """本地日期串（额度按这个分区）"""
    return (now or datetime.datetime.now()).strftime('%Y-%m-%d')


def seconds_to_local_midnight(now=None):
    """距本地 00:00 的剩余秒数（+60 冗余，避免边界上刚好丢键）"""
    now = now or datetime.datetime.now()
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds()) + 60


def session_key(user_id, session_id):
    return f'quota:session:{user_id}:{session_id}'


def daily_key(user_id, day=None):
    # 键名自带 user_id：同一 session_id 在不同用户下必须互不影响
    return f'quota:daily:{user_id}:{day or local_day()}'


class QuotaResult:
    """一次额度判定的结果"""

    def __init__(self, allowed, scope=None, daily_used=0, session_used=0,
                 retry_after=0):
        self.allowed = allowed
        self.scope = scope            # None | 'session' | 'daily'
        self.daily_used = daily_used
        self.session_used = session_used
        self.retry_after = retry_after

    @property
    def daily_limit(self):
        return QUOTA_CONFIG['daily_max']

    @property
    def session_limit(self):
        return QUOTA_CONFIG['session_max']

    @property
    def daily_remaining(self):
        return max(0, self.daily_limit - self.daily_used)

    @property
    def session_remaining(self):
        return max(0, self.session_limit - self.session_used)

    @property
    def error_code(self):
        return {'session': 'QUOTA_001', 'daily': 'QUOTA_002'}.get(self.scope)

    @property
    def message(self):
        if self.scope == 'session':
            return (f'本次会话已达上限（{self.session_limit} 次），'
                    f'新建会话可继续')
        if self.scope == 'daily':
            return (f'今日对话额度已用完（{self.daily_limit} 次），'
                    f'明日 00:00 重置')
        return ''


def check_and_consume(user_id, session_id):
    """判定并消费一次额度，返回 QuotaResult

    两层**一起判定**，且只在都通过时才消费 —— 否则会话已超限的请求会把
    当日额度也扣掉，用户什么都没得到却损失了当天总量。
    """
    if not QUOTA_CONFIG['enabled'] or user_id is None or not session_id:
        return QuotaResult(True)

    session_max = QUOTA_CONFIG['session_max']
    daily_max = QUOTA_CONFIG['daily_max']
    skey = session_key(user_id, session_id)
    dkey = daily_key(user_id)
    dttl = seconds_to_local_midnight()

    client = get_redis()
    if client is not None:
        try:
            allowed, scope_code, s, d, retry = _get_script(client)(
                keys=[skey, dkey],
                args=[session_max, daily_max, QUOTA_CONFIG['session_ttl'], dttl])
            scope = {0: None, 1: 'session', 2: 'daily'}[int(scope_code)]
            return QuotaResult(bool(int(allowed)), scope, int(d), int(s),
                               int(retry) if not int(allowed) else 0)
        except Exception as e:
            # Redis 运行中挂掉：缓存的客户端是死的，必须降级而不是把异常
            # 抛给请求（同 ratelimit.check_rate_limit 的处理）
            report_failure(e)
    return _consume_memory(skey, dkey, session_max, daily_max, dttl)


def _consume_memory(skey, dkey, session_max, daily_max, daily_ttl):
    """降级实现：进程内计数（多 worker 不共享、重启清零）"""
    now = datetime.datetime.now().timestamp()
    with _lock:
        for k in [k for k, v in _memory.items() if v[1] <= now]:
            del _memory[k]
        s = _memory.get(skey, [0, now + QUOTA_CONFIG['session_ttl']])[0]
        d = _memory.get(dkey, [0, now + daily_ttl])[0]
        if s >= session_max:
            return QuotaResult(False, 'session', d, s, 0)
        if d >= daily_max:
            return QuotaResult(False, 'daily', d, s, int(daily_ttl))
        _memory[skey] = [s + 1, now + QUOTA_CONFIG['session_ttl']]
        _memory[dkey] = [d + 1, now + daily_ttl]
        return QuotaResult(True, None, d + 1, s + 1, 0)


def is_exempt(user):
    """该用户是否豁免额度（默认 admin，与 RATE_LIMIT_BYPASS_ROLES 语义一致）"""
    try:
        from flask import current_app
        roles = set(current_app.config.get('QUOTA_BYPASS_ROLES') or [])
    except RuntimeError:
        roles = set()
    return bool(user) and getattr(user, 'role', None) in roles


def denial_response(result):
    """额度用尽时的 429 响应

    **不复用 RATE_LIMIT_EXCEEDED**：那个码的语义是「太快」，这个的语义是
    「用完了」—— 前端的提示（稍后再试 / 新建会话 / 明日重置）与自动测试的
    判据都该分得开。
    """
    from flask import jsonify
    from core.helpers import log_operation

    log_operation(description=f'额度用尽: {result.scope}',
                  success=False, error_msg=result.message)
    payload = {
        'error': result.message,
        'error_code': result.error_code,
        'timestamp': datetime.datetime.utcnow().isoformat(),
    }
    if result.scope == 'daily' and result.retry_after:
        payload['retry_after'] = result.retry_after
    resp = jsonify(payload)
    resp.status_code = 429
    if payload.get('retry_after'):
        resp.headers['Retry-After'] = str(payload['retry_after'])
    return resp


def attach_headers(response, result):
    """在响应上附加额度信息头（兼容 (body, status) 元组返回）

    前端据此显示「今日剩余 N 次」；验证脚本也靠它断言额度真的在扣。
    """
    target = response[0] if isinstance(response, tuple) else response
    if hasattr(target, 'headers'):
        target.headers['X-Quota-Daily-Remaining'] = str(result.daily_remaining)
        target.headers['X-Quota-Daily-Limit'] = str(result.daily_limit)
        target.headers['X-Quota-Session-Remaining'] = str(result.session_remaining)
        target.headers['X-Quota-Session-Limit'] = str(result.session_limit)
    return response


def reset_memory():
    """清空降级计数（仅验证脚本用）"""
    with _lock:
        _memory.clear()
