"""通用辅助函数

从 app.py 抽出，供各蓝图共用。
"""
from flask import request

from database import DetectionHistory, OperationLog, db
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


# ==================== 数据隔离过滤函数 ====================

def get_filtered_reports(user):
    """根据用户角色过滤报告
    
    Args:
        user: 当前用户对象
    
    Returns:
        Query: 过滤后的DetectionHistory查询对象，使用eager loading避免N+1查询
    
    规则:
        - admin: 返回所有报告
        - doctor: 只返回该医生创建的报告
        - patient: 只返回关联到该患者的报告
        - 其他: 返回空查询
    
    需求: 13.4
    """
    # 使用joinedload进行eager loading，避免N+1查询问题
    from sqlalchemy.orm import joinedload
    
    if user.role == 'admin':
        return DetectionHistory.query.options(
            joinedload(DetectionHistory.doctor),
            joinedload(DetectionHistory.patient)
        )
    elif user.role == 'doctor':
        return DetectionHistory.query.options(
            joinedload(DetectionHistory.doctor),
            joinedload(DetectionHistory.patient)
        ).filter_by(username=user.username)
    elif user.role == 'patient':
        return DetectionHistory.query.options(
            joinedload(DetectionHistory.doctor),
            joinedload(DetectionHistory.patient)
        ).filter_by(patient_id=user.id)
    else:
        # 未知角色,返回空查询
        return DetectionHistory.query.filter(False)
