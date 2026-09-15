"""请求限流

从 app.py 抽出。基于进程内滑动窗口，多 worker 部署时不共享，
应迁至 Redis（见 BASELINE 待办）。
"""
import time
from datetime import datetime
from functools import wraps

from flask import jsonify

from core.auth import get_current_user
from core.helpers import log_operation
from core.state import RATE_LIMIT_CONFIG, rate_limit_lock, rate_limit_storage

def check_rate_limit(user_id, limit_type='api_general'):
    """检查用户是否超过限流
    
    Args:
        user_id: 用户ID
        limit_type: 限流类型 ('ai_chat' 或 'api_general')
    
    Returns:
        tuple: (是否允许, 剩余请求数)
    
    需求: 7.3
    """
    config = RATE_LIMIT_CONFIG.get(limit_type, RATE_LIMIT_CONFIG['api_general'])
    max_requests = config['max_requests']
    time_window = config['time_window']
    
    with rate_limit_lock:
        current_time = time.time()
        key = f"{user_id}:{limit_type}"
        
        # 获取用户的请求记录
        requests = rate_limit_storage[key]
        
        # 移除过期的请求记录
        requests = [req_time for req_time in requests if current_time - req_time < time_window]
        rate_limit_storage[key] = requests
        
        # 检查是否超过限制
        if len(requests) >= max_requests:
            return False, 0
        
        # 记录本次请求
        requests.append(current_time)
        remaining = max_requests - len(requests)
        
        return True, remaining

def rate_limit(limit_type='api_general'):
    """限流装饰器
    
    Args:
        limit_type: 限流类型
    
    需求: 7.3
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "未登录"}), 401
            
            allowed, remaining = check_rate_limit(user.id, limit_type)
            
            if not allowed:
                # 记录限流日志
                log_operation(
                    description=f"限流触发: 用户{user.username}, 类型{limit_type}",
                    success=False,
                    error_msg="请求频率超过限制"
                )
                
                return jsonify({
                    "error": "请求过于频繁,请稍后再试",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "timestamp": datetime.utcnow().isoformat()
                }), 429
            
            # 在响应头中添加限流信息
            response = f(*args, **kwargs)
            if isinstance(response, tuple):
                response_obj, status_code = response[0], response[1]
            else:
                response_obj, status_code = response, 200
            
            # 添加限流头
            if hasattr(response_obj, 'headers'):
                response_obj.headers['X-RateLimit-Remaining'] = str(remaining)
                response_obj.headers['X-RateLimit-Limit'] = str(RATE_LIMIT_CONFIG[limit_type]['max_requests'])
            
            return response_obj, status_code
        
        return decorated_function
    return decorator
