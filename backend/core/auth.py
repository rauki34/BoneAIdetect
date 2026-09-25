"""认证与权限装饰器

**只认 JWT**（阶段 3 引入，过渡期的 X-Username 兜底已于 2026-09-25 移除）。

那段兜底曾经是必要的：改造期间前端还有页面没换成 JWT，留着它才能灰度切换。
代价是 `curl -H "X-Username: admin"` 就能冒充任何人 —— 所以它必须有个删除期限，
而"等全量切换后删除"这种说法**没有期限**，于是它活了两个阶段（见
BASELINE 二·补九 第 8 条：`TODO` 不写日期就等于不写）。

移除时顺带发现另外 5 处**直接读这个请求头**的地方（审计日志的操作人、
`/api/user-ai-models` 的数据过滤键、检测/训练记录的归属），它们比认证兜底更隐蔽：
即使认证改成了 JWT，那些地方仍然让调用方自己声明"我是谁"。现已统一改为
`get_current_user()`。
"""
from datetime import datetime
from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from core.helpers import log_operation
from database import User
from utils.logger import logger

# ==================== 权限验证装饰器 ====================

def get_current_user():
    """获取当前登录用户（JWT）

    `optional=True`：无 token 时返回 None 而不报错（各视图自己决定要不要拦）；
    但 token 存在且非法时会抛异常，这里一并吞掉返回 None —— 交给
    `@require_auth` / `@require_role` 给出 401，而不是让异常冒到错误处理器。
    """
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        identity = None

    if identity:
        return User.query.filter_by(username=identity).first()

    return None

def require_auth(f):
    """要求登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            log_operation("认证失败:未登录或登录已过期", success=False, error_msg="未登录")
            return jsonify({
                "error": "未登录或登录已过期",
                "error_code": "AUTH_001",
                "timestamp": datetime.utcnow().isoformat()
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """要求管理员权限的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            log_operation("认证失败:未登录或登录已过期", success=False, error_msg="未登录")
            return jsonify({
                "error": "未登录或登录已过期",
                "error_code": "AUTH_001",
                "timestamp": datetime.utcnow().isoformat()
            }), 401
        if user.role != 'admin':
            log_operation(f"权限验证失败:用户{user.username}尝试访问管理员功能", success=False, error_msg="需要管理员权限")
            return jsonify({
                "error": "需要管理员权限",
                "error_code": "AUTH_002",
                "timestamp": datetime.utcnow().isoformat()
            }), 403
        return f(*args, **kwargs)
    return decorated_function

def require_role(*allowed_roles):
    """通用角色验证装饰器,支持多角色验证
    
    Args:
        *allowed_roles: 允许访问的角色列表,如 'admin', 'doctor', 'patient'
    
    Returns:
        装饰器函数
    
    Example:
        @require_role('admin', 'doctor')
        def some_endpoint():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                log_operation("认证失败:未登录或登录已过期", success=False, error_msg="未登录")
                return jsonify({
                    "error": "未登录或登录已过期",
                    "error_code": "AUTH_001",
                    "timestamp": datetime.utcnow().isoformat()
                }), 401
            if user.role not in allowed_roles:
                log_operation(f"权限验证失败:用户{user.username}(角色:{user.role})尝试访问需要{allowed_roles}角色的功能", success=False, error_msg="权限不足")
                return jsonify({
                    "error": "权限不足",
                    "error_code": "AUTH_002",
                    "timestamp": datetime.utcnow().isoformat()
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
