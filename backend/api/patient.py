"""患者端接口：报告、病历、主治医生、个人资料、AI 模型配置

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, require_auth, require_role
from core.helpers import get_filtered_reports
from database import (
    CustomModel, DetectionHistory, DoctorPatientRelation, DoctorProfile,
    MedicalRecord, Message, PatientProfile, User, UserAIModel, db,
)
from utils.logger import logger

bp = Blueprint('patient', __name__)

@bp.route("/api/user-ai-models", methods=["GET"])
@require_auth
def get_user_ai_models():
    """获取当前用户的AI模型配置列表"""
    username = request.headers.get('X-Username', 'unknown')
    provider = request.args.get('provider', '')
    
    query = UserAIModel.query.filter_by(created_by=username)
    if provider:
        query = query.filter_by(provider=provider)
    
    models = query.order_by(UserAIModel.created_at.desc()).all()
    
    return jsonify({
        "success": True,
        "data": [m.to_dict() for m in models]
    })

# ==================== 患者接口 ====================

@bp.route("/api/patient/reports", methods=["GET"])
@require_role('admin', 'patient')
def patient_get_reports():
    """获取患者自己的检测报告
    
    权限: admin, patient
    
    Query参数:
        page: 页码 (默认1)
        per_page: 每页数量 (默认20, 最大100)
    
    返回报告列表，包含:
        - 医生姓名
        - 诊断结论
        - 检测结果
        - 医疗建议
    
    需求: 4.1, 4.2, 12.4, 2.2, 14.3
    """
    user = get_current_user()
    
    # 使用数据隔离过滤函数
    query = get_filtered_reports(user)
    
    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # 限制最大每页数量
    
    # 按时间倒序排列并分页
    query = query.order_by(DetectionHistory.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    data = []
    for report in pagination.items:
        report_dict = report.to_dict()
        # to_dict() 已经包含了 doctor_name, patient_name, diagnosis, medical_advice 等字段
        data.append(report_dict)
    
    return jsonify({
        "data": data,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages
    })

@bp.route("/api/patient/reports/<int:report_id>", methods=["GET"])
@require_role('admin', 'patient')
def patient_get_report_detail(report_id):
    """获取单个报告详情
    
    权限: admin, patient
    
    验证:
        - 患者只能查看自己的报告（admin除外）
    
    返回完整的报告信息和医疗建议
    
    需求: 4.1, 4.2
    """
    user = get_current_user()
    
    # 查找报告
    report = db.session.get(DetectionHistory, report_id)
    if not report:
        return jsonify({"error": "报告不存在"}), 404
    
    # 权限验证: 患者只能查看自己的报告（admin除外）
    if user.role == 'patient' and report.patient_id != user.id:
        return jsonify({"error": "无权查看此报告"}), 403
    
    # 返回完整报告信息
    return jsonify({
        "success": True,
        "report": report.to_dict()
    }), 200

# -------------------- 患者端 API --------------------

@bp.route("/api/patient/profile", methods=["GET"])
@require_role('patient')
def get_patient_profile():
    """获取患者个人信息"""
    user = get_current_user()
    profile = PatientProfile.query.filter_by(user_id=user.id).first()
    
    # 如果没有档案，返回空档案数据
    profile_data = profile.to_dict() if profile else {
        "id": None,
        "user_id": user.id,
        "patient_number": None,
        "gender": None,
        "birth_date": None,
        "id_card": None,
        "address": None,
        "emergency_contact": None,
        "emergency_phone": None,
        "allergies": None,
        "medical_history": None,
        "created_at": None
    }
    
    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone
        },
        "profile": profile_data
    })

@bp.route("/api/patient/medical-records", methods=["GET"])
@require_role('patient')
def get_patient_medical_records():
    """获取患者病历列表"""
    user = get_current_user()
    records = MedicalRecord.query.filter_by(patient_id=user.id).order_by(MedicalRecord.visit_date.desc()).all()
    
    return jsonify({
        "success": True,
        "records": [record.to_dict() for record in records]
    })

@bp.route("/api/patient/doctors", methods=["GET"])
@require_role('patient')
def get_patient_doctors():
    """获取患者的主治医师列表"""
    user = get_current_user()
    relations = DoctorPatientRelation.query.filter_by(patient_id=user.id).all()
    
    doctors = []
    for relation in relations:
        doctor = db.session.get(User, relation.doctor_id)
        profile = DoctorProfile.query.filter_by(user_id=doctor.id).first()
        if doctor and profile:
            doctors.append({
                "id": doctor.id,
                "full_name": doctor.full_name,
                "department": profile.department,
                "title": profile.title,
                "hospital": profile.hospital,
                "license_number": profile.license_number,
                "specialty": profile.specialty,
                "phone": doctor.phone,
                "is_primary": relation.is_primary
            })
    
    return jsonify({
        "success": True,
        "doctors": doctors
    })

@bp.route("/api/patient/detection-reports", methods=["GET"])
@require_role('patient')
def get_patient_detection_reports():
    """获取患者的AI检测报告列表"""
    user = get_current_user()
    
    # 获取该患者的所有检测历史
    reports = DetectionHistory.query.filter_by(patient_id=user.id).order_by(DetectionHistory.timestamp.desc()).all()
    
    reports_data = []
    for report in reports:
        # 使用to_dict()获取完整数据
        report_dict = report.to_dict()
        
        # 获取模型显示名称
        model_display_name = report_dict['model']
        if report_dict['model']:
            # 查找自定义模型名称（直接使用model字段匹配model_key）
            custom_model = CustomModel.query.filter_by(model_key=report_dict['model']).first()
            if custom_model:
                model_display_name = custom_model.name
            elif report_dict['model'].startswith('yolov8'):
                model_display_name = 'YOLOv8'
            elif report_dict['model'].startswith('yolo11'):
                model_display_name = 'YOLO11'
            elif report_dict['model'].startswith('yolo26'):
                model_display_name = 'YOLO26'
        
        reports_data.append({
            "id": report_dict['id'],
            "timestamp": report_dict['timestamp'],
            "model": report_dict['model'],
            "model_name": model_display_name,
            "count": report_dict['count'],
            "confidence": report_dict['confidence'],
            "fracture_types": report_dict['fracture_types'],
            "detections": report_dict['detections'],
            "original_image": report_dict['original_image'],
            "result_image": report_dict['result_image'],
            "doctor_name": report_dict['doctor_name'] or "AI自动检测",
            "diagnosis": report_dict['diagnosis'],
            "medical_advice": report_dict['medical_advice'],
            "has_medical_advice": report_dict['has_medical_advice']
        })
    
    return jsonify({
        "success": True,
        "reports": reports_data
    })

@bp.route("/api/patient/messages", methods=["GET"])
@require_role('patient')
def get_patient_messages():
    """获取患者的消息通知列表"""
    user = get_current_user()
    
    # 获取系统消息和医生发送的消息
    messages = Message.query.filter(
        (Message.receiver_id == user.id) | (Message.receiver_id == None)
    ).order_by(Message.created_at.desc()).all()
    
    messages_data = []
    for msg in messages:
        sender = db.session.get(User, msg.sender_id) if msg.sender_id else None
        messages_data.append({
            "id": msg.id,
            "title": msg.title,
            "content": msg.content,
            "sender_name": sender.full_name if sender else "系统",
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "is_read": msg.is_read
        })
    
    return jsonify({
        "success": True,
        "messages": messages_data
    })

@bp.route("/api/patient/messages/<int:message_id>/read", methods=["PUT"])
@require_role('patient')
def mark_message_read(message_id):
    """标记消息为已读"""
    user = get_current_user()
    
    # 查询消息 - 可以是发给该用户的，也可以是系统广播消息(receiver_id为None)
    message = Message.query.filter(
        (Message.id == message_id) & 
        ((Message.receiver_id == user.id) | (Message.receiver_id == None))
    ).first()
    
    if not message:
        return jsonify({"error": "消息不存在"}), 404
    
    message.is_read = True
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "已标记为已读"
    })

@bp.route("/api/patient/profile/update", methods=["PUT"])
@require_role('patient')
def update_patient_profile():
    """患者更新个人信息"""
    user = get_current_user()
    data = request.json
    
    try:
        # 更新User表信息
        if 'full_name' in data:
            user.full_name = data['full_name']
        if 'phone' in data:
            user.phone = data['phone']
        if 'email' in data:
            user.email = data['email']
        
        # 更新PatientProfile信息
        profile = PatientProfile.query.filter_by(user_id=user.id).first()
        if not profile:
            profile = PatientProfile(user_id=user.id)
            db.session.add(profile)
        
        if 'gender' in data:
            profile.gender = data['gender']
        if 'birth_date' in data:
            profile.birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date() if data['birth_date'] else None
        if 'id_card' in data:
            profile.id_card = data['id_card']
        if 'address' in data:
            profile.address = data['address']
        if 'emergency_contact' in data:
            profile.emergency_contact = data['emergency_contact']
        if 'emergency_phone' in data:
            profile.emergency_phone = data['emergency_phone']
        if 'allergies' in data:
            profile.allergies = data['allergies']
        if 'medical_history' in data:
            profile.medical_history = data['medical_history']
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "个人信息更新成功"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新患者信息失败: {e}")
        return jsonify({"error": "更新失败"}), 500
