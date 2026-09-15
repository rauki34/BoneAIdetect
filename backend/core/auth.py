"""认证与权限装饰器

从 app.py 抽出。当前为 JWT + X-Username 双模式过渡期实现，
全量切换后移除兜底分支。
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
    """获取当前登录用户

    过渡期采用**双模式**认证，新旧并存以便灰度切换：
      1. JWT（Authorization: Bearer <token>）—— 新方式，有签名校验
      2. X-Username 请求头 —— 旧方式，**无任何校验，可被任意伪造**

    旧方式仅用于兼容尚未升级的客户端，会打出 WARNING 日志。
    待观察期内不再出现该日志后，删除下方"方式二"分支。
    """
    # --- 方式一：JWT ---
    try:
        # optional=True：无 token 时返回 None 而不报错；
        # 但 token 存在且非法时会抛异常，需一并吞掉走旧方式兜底
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        identity = None

    if identity:
        return User.query.filter_by(username=identity).first()

    # --- 方式二：旧 X-Username（TODO: 全量切换后删除）---
    username = request.headers.get('X-Username')
    if username:
        logger.warning(
            '检测到已废弃的 X-Username 认证: %s'
            '（该方式无签名校验、可被伪造，将在后续版本移除）',
            username,
        )
        return User.query.filter_by(username=username).first()

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
