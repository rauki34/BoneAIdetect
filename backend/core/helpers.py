"""通用辅助函数

从 app.py 抽出，供各蓝图共用。
"""
import sys

from flask import request

from database import (
    DetectionHistory, DoctorPatientRelation, OperationLog, UserAIModel, db,
)
from utils.logger import logger


def can_access_patient(user, patient_id):
    """当前用户是否有权访问该患者的数据

    admin 旁路；doctor 需存在医患关联；患者本人只能访问自己。
    凡是接受 patient_id 参数的接口都应经此校验，避免通过猜 id 越权。
    """
    if user is None or patient_id is None:
        return False
    if user.role == 'admin':
        return True
    try:
        patient_id = int(patient_id)
    except (TypeError, ValueError):
        return False
    if user.role == 'doctor':
        return DoctorPatientRelation.query.filter_by(
            doctor_id=user.id, patient_id=patient_id,
        ).first() is not None
    if user.role == 'patient':
        return user.id == patient_id
    return False



# ==================== 操作日志接口（借鉴pear-admin-flask）====================

def log_operation(description, success=True, error_msg=None, username=None):
    """记录操作日志的辅助函数

    `username` 用于显式指定操作人，覆盖从请求头推断的结果。

    需要它的场景是 Celery worker（阶段 8）：入库这类长任务搬到 worker 后
    已经没有请求上下文，本函数会退回记 `system` —— 医疗场景下审计记录丢掉
    操作人是合规性倒退。因此 HTTP 端把 `user.username` 一并投递给任务，
    worker 再显式传进来。
    """
    try:
        # 获取请求上下文中的信息
        try:
            # 操作人取**已认证身份**，不读请求头：X-Username 无签名校验，
            # 用它记审计等于让调用方自己填"谁干的"（可以冒名）。
            if not username:
                from core.auth import get_current_user   # 延迟导入：core.auth 反向依赖本模块
                user = get_current_user()
                username = user.username if user else 'anonymous'
            method = request.method if request else 'SYSTEM'
            url = request.path if request else ''
            ip = request.remote_addr if request else ''
            user_agent = request.headers.get('User-Agent', '') if request else ''
        except RuntimeError:
            # 不在请求上下文中
            username = username or 'system'
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


class Logger:
    """日志记录器，同时输出到控制台和文件"""
    def __init__(self, log_file):
        self.log_file = log_file
        self.terminal = sys.stdout
        self.log = open(log_file, 'w', encoding='utf-8')
        
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
        
    def flush(self):
        self.terminal.flush()
        self.log.flush()
        
    def close(self):
        self.log.close()

def save_user_ai_model(provider, model_id, api_key, api_url, username):
    """保存用户AI模型配置"""
    try:
        # 查找是否已存在
        existing = UserAIModel.query.filter_by(
            provider=provider,
            model_id=model_id,
            created_by=username
        ).first()
        
        if existing:
            # 更新现有记录
            existing.api_key = api_key
            existing.api_url = api_url
        else:
            # 创建新记录
            model = UserAIModel(
                provider=provider,
                model_id=model_id,
                api_key=api_key,
                api_url=api_url,
                created_by=username
            )
            db.session.add(model)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"保存用户AI模型失败: {e}")
        db.session.rollback()
