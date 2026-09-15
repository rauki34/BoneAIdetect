"""通用辅助函数

从 app.py 抽出，供各蓝图共用。
"""
from flask import request

from database import db, OperationLog
from utils.logger import logger

# ==================== 操作日志接口（借鉴pear-admin-flask）====================

def log_operation(description, success=True, error_msg=None):
    """记录操作日志的辅助函数"""
    try:
        # 获取请求上下文中的信息
        try:
            username = request.headers.get('X-Username', 'anonymous') if request else 'system'
            method = request.method if request else 'SYSTEM'
            url = request.path if request else ''
            ip = request.remote_addr if request else ''
            user_agent = request.headers.get('User-Agent', '') if request else ''
        except RuntimeError:
            # 不在请求上下文中
            username = 'system'
            method = 'SYSTEM'
            url = ''
            ip = ''
            user_agent = ''
        
        log = OperationLog(
            username=username,
            method=method,
            url=url,
            ip=ip,
            user_agent=user_agent,
            description=description,
            success=success,
            error_msg=error_msg
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"记录日志失败: {e}")
        try:
            db.session.rollback()
        except:
            pass
