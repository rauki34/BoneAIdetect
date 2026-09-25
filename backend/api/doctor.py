"""医生端接口：患者管理、病历、检查、报告

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import json
import random
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from core.auth import get_current_user, require_auth, require_role
from core.helpers import get_filtered_reports, log_operation
from core.validators import calculate_age
from database import (
    DetectionHistory, DoctorPatientRelation, DoctorProfile, Examination,
    MedicalRecord, Patient, PatientProfile, User, db,
)
from utils.logger import logger

bp = Blueprint('doctor', __name__)

# ==================== 患者管理相关 ====================

@bp.route('/api/patients', methods=['GET', 'POST'])
@require_auth
def patients():
    """患者管理"""
    if request.method == 'GET':
        # 获取患者列表
        patients = Patient.query.all()
        return jsonify({"success": True, "data": [p.to_dict() for p in patients]})
    
    elif request.method == 'POST':
        # 添加新患者
        data = request.get_json(silent=True) or {}
        user = get_current_user()
        
        patient = Patient(
            name=data.get('name'),
            age=data.get('age'),
            gender=data.get('gender'),
            medical_history=data.get('medical_history'),
            contact_info=data.get('contact_info')
        )
        
        db.session.add(patient)
        db.session.commit()
        
        # 记录操作日志
        log_operation(user.username, 'POST', '/api/patients', f'添加患者: {patient.name}')
        
        return jsonify({"success": True, "data": patient.to_dict(), "message": "患者添加成功"})

@bp.route('/api/patients/<int:patient_id>', methods=['GET', 'PUT', 'DELETE'])
@require_auth
def patient_detail(patient_id):
    """患者详情"""
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"success": False, "message": "患者不存在"})
    
    if request.method == 'GET':
        return jsonify({"success": True, "data": patient.to_dict()})
    
    elif request.method == 'PUT':
        # 更新患者信息
        data = request.get_json(silent=True) or {}
        user = get_current_user()
        
        if 'name' in data:
            patient.name = data['name']
        if 'age' in data:
            patient.age = data['age']
        if 'gender' in data:
            patient.gender = data['gender']
        if 'medical_history' in data:
            patient.medical_history = data['medical_history']
        if 'contact_info' in data:
            patient.contact_info = data['contact_info']
        
        db.session.commit()
        
        # 记录操作日志
        log_operation(user.username, 'PUT', f'/api/patients/{patient_id}', f'更新患者: {patient.name}')
        
        return jsonify({"success": True, "data": patient.to_dict(), "message": "患者信息更新成功"})
    
    elif request.method == 'DELETE':
        # 删除患者
        user = get_current_user()
        patient_name = patient.name
        
        # 先删除相关的检查记录
        Examination.query.filter_by(patient_id=patient_id).delete()
        
        db.session.delete(patient)
        db.session.commit()
        
        # 记录操作日志
        log_operation(user.username, 'DELETE', f'/api/patients/{patient_id}', f'删除患者: {patient_name}')
        
        return jsonify({"success": True, "message": "患者删除成功"})

# ==================== 检查记录相关 ====================

@bp.route('/api/examinations', methods=['GET', 'POST'])
@require_auth
def examinations():
    """检查记录管理"""
    if request.method == 'GET':
        # 获取检查记录列表
        patient_id = request.args.get('patient_id')
        if patient_id:
            examinations = Examination.query.filter_by(patient_id=patient_id).all()
        else:
            examinations = Examination.query.all()
        return jsonify({"success": True, "data": [e.to_dict() for e in examinations]})
    
    elif request.method == 'POST':
        # 添加新检查记录
        data = request.get_json(silent=True) or {}
        user = get_current_user()
        
        # 检查患者是否存在
        patient = db.session.get(Patient, data.get('patient_id'))
        if not patient:
            return jsonify({"success": False, "message": "患者不存在"})
        
        examination = Examination(
            patient_id=data.get('patient_id'),
            exam_date=datetime.fromisoformat(data.get('exam_date')) if data.get('exam_date') else datetime.utcnow(),
            image_path=data.get('image_path'),
            detection_result=json.dumps(data.get('detection_result', {})) if data.get('detection_result') else None,
            report=data.get('report'),
            follow_up_date=datetime.fromisoformat(data.get('follow_up_date')) if data.get('follow_up_date') else None,
            created_by=user.username
        )
        
        db.session.add(examination)
        db.session.commit()
        
        # 记录操作日志
        log_operation(user.username, 'POST', '/api/examinations', f'添加检查记录: 患者{patient.name}')
        
        return jsonify({"success": True, "data": examination.to_dict(), "message": "检查记录添加成功"})

@bp.route('/api/examinations/<int:exam_id>', methods=['GET', 'PUT', 'DELETE'])
@require_auth
def examination_detail(exam_id):
    """检查记录详情"""
    examination = db.session.get(Examination, exam_id)
    if not examination:
        return jsonify({"success": False, "message": "检查记录不存在"})
    
    if request.method == 'GET':
        return jsonify({"success": True, "data": examination.to_dict()})
    
    elif request.method == 'PUT':
        # 更新检查记录
        data = request.get_json(silent=True) or {}
        user = get_current_user()
        
        if 'exam_date' in data:
            examination.exam_date = datetime.fromisoformat(data['exam_date'])
        if 'image_path' in data:
            examination.image_path = data['image_path']
        if 'detection_result' in data:
            examination.detection_result = json.dumps(data['detection_result'])
        if 'report' in data:
            examination.report = data['report']
        if 'follow_up_date' in data:
            examination.follow_up_date = datetime.fromisoformat(data['follow_up_date']) if data.get('follow_up_date') else None
        
        db.session.commit()
        
        # 记录操作日志
        log_operation(user.username, 'PUT', f'/api/examinations/{exam_id}', f'更新检查记录: 患者{examination.patient.name}')
        
        return jsonify({"success": True, "data": examination.to_dict(), "message": "检查记录更新成功"})
    
    elif request.method == 'DELETE':
        # 删除检查记录
        user = get_current_user()
        patient_name = examination.patient.name
        
        db.session.delete(examination)
        db.session.commit()
        
        # 记录操作日志
        log_operation(user.username, 'DELETE', f'/api/examinations/{exam_id}', f'删除检查记录: 患者{patient_name}')
        
        return jsonify({"success": True, "message": "检查记录删除成功"})

# ==================== 医生接口 ====================

@bp.route("/api/doctor/patients", methods=["GET"])
@require_role('admin', 'doctor')
def doctor_get_patients():
    """获取患者列表（供医生选择患者）
    
    Query参数:
        search: 按 full_name 或 username 搜索
    
    返回字段: id, username, full_name, phone, gender, birth_date
    """
    search = request.args.get('search', '').strip()
    
    query = User.query.filter_by(role='patient')
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                User.full_name.ilike(search_pattern),
                User.username.ilike(search_pattern)
            )
        )
    
    patients = query.order_by(User.created_at.desc()).all()
    
    data = []
    for p in patients:
        # 获取患者档案信息
        profile = PatientProfile.query.filter_by(user_id=p.id).first()
        data.append({
            "id": p.id,
            "username": p.username,
            "full_name": p.full_name,
            "phone": p.phone,
            "gender": profile.gender if profile else None,
            "birth_date": profile.birth_date.strftime('%Y-%m-%d') if profile and profile.birth_date else None
        })
    
    return jsonify({"data": data})

@bp.route("/api/doctor/reports", methods=["POST"])
@require_role('admin', 'doctor')
def doctor_create_report():
    """创建检测报告并关联患者（更新已有DetectionHistory记录）
    
    请求体:
        patient_id: 患者ID（必填）
        detection_id: DetectionHistory的ID（必填）
        diagnosis: 诊断结论（可选）
        follow_up_notes: 随访备注（可选）
    
    验证:
        - detection_id对应的记录必须存在
        - patient_id对应的用户必须存在且role='patient'
        - doctor只能更新自己创建的记录（admin除外）
    
    需求: 3.3, 8.2, 8.3, 8.4, 12.1, 12.2
    """
    user = get_current_user()
    data = request.json or {}

    patient_id = data.get('patient_id')
    detection_id = data.get('detection_id')
    diagnosis = data.get('diagnosis', '').strip() if data.get('diagnosis') else None
    follow_up_notes = data.get('follow_up_notes', '').strip() if data.get('follow_up_notes') else None

    # 验证必填字段
    if patient_id is None:
        return jsonify({"error": "patient_id 不能为空"}), 400
    if detection_id is None:
        return jsonify({"error": "detection_id 不能为空"}), 400

    # 验证 detection_id 对应的记录存在
    history = db.session.get(DetectionHistory, detection_id)
    if not history:
        return jsonify({"error": "检测记录不存在"}), 404

    # 验证 patient_id 对应的用户存在且 role='patient'
    patient = db.session.get(User, patient_id)
    if not patient:
        return jsonify({"error": "患者不存在"}), 404
    if patient.role != 'patient':
        return jsonify({"error": "指定用户不是患者角色"}), 400

    # doctor 只能更新自己创建的记录（admin 不受限制）
    if user.role == 'doctor' and history.username != user.username:
        return jsonify({"error": "无权更新其他医生创建的记录"}), 403

    # 更新记录
    history.patient_id = patient_id
    if diagnosis is not None:
        history.diagnosis = diagnosis
    if follow_up_notes is not None:
        history.follow_up_notes = follow_up_notes

    db.session.commit()

    log_operation(f"医生创建/更新报告:detection_id={detection_id},patient_id={patient_id}")

    return jsonify({
        "success": True,
        "message": "报告已创建并关联患者",
        "report": history.to_dict()
    }), 200

@bp.route("/api/doctor/reports", methods=["GET"])
@require_role('admin', 'doctor')
def doctor_get_reports():
    """获取医生创建的所有报告（使用数据隔离）
    
    Query参数:
        patient_id: 按患者ID筛选（可选）
        date_from: 开始日期，格式YYYY-MM-DD（可选）
        date_to: 结束日期，格式YYYY-MM-DD（可选）
        page: 页码 (默认1)
        per_page: 每页数量 (默认20, 最大100)
    
    返回报告列表，包含患者姓名（通过patient_id关联User获取full_name）
    
    需求: 3.2, 3.9, 2.2, 14.3
    """
    user = get_current_user()

    # 使用数据隔离过滤函数
    query = get_filtered_reports(user)

    # 按患者筛选
    patient_id = request.args.get('patient_id')
    if patient_id:
        try:
            patient_id = int(patient_id)
            query = query.filter(DetectionHistory.patient_id == patient_id)
        except ValueError:
            return jsonify({"error": "patient_id 必须是整数"}), 400

    # 按日期范围筛选
    date_from = request.args.get('date_from')
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(DetectionHistory.timestamp >= date_from_dt)
        except ValueError:
            return jsonify({"error": "date_from 格式必须为 YYYY-MM-DD"}), 400

    date_to = request.args.get('date_to')
    if date_to:
        try:
            from datetime import timedelta
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(DetectionHistory.timestamp < date_to_dt)
        except ValueError:
            return jsonify({"error": "date_to 格式必须为 YYYY-MM-DD"}), 400

    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # 限制最大每页数量

    # 排序并分页
    query = query.order_by(DetectionHistory.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    data = []
    for report in pagination.items:
        report_dict = report.to_dict()
        # 确保包含患者姓名（通过patient_id关联User获取full_name）
        if report.patient_id and not report_dict.get('patient_name'):
            patient = db.session.get(User, report.patient_id)
            if patient:
                report_dict['patient_name'] = patient.full_name or patient.username
        data.append(report_dict)

    return jsonify({
        "data": data,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages
    })

@bp.route("/api/doctor/reports/<int:report_id>", methods=["PUT"])
@require_role('admin', 'doctor')
def doctor_update_report(report_id):
    """编辑检测报告（更新诊断和随访备注）
    
    请求体:
        diagnosis: 诊断结论（可选）
        follow_up_notes: 随访备注（可选）
    
    验证:
        - report_id对应的记录必须存在
        - doctor只能编辑自己创建的报告（admin除外）
    
    需求: 3.4, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
    """
    user = get_current_user()
    data = request.json or {}
    
    # 查找报告
    report = db.session.get(DetectionHistory, report_id)
    if not report:
        return jsonify({"error": "报告不存在"}), 404
    
    # 权限验证: doctor只能编辑自己创建的报告（admin除外）
    if user.role == 'doctor' and report.username != user.username:
        return jsonify({"error": "无权编辑其他医生创建的报告"}), 403
    
    # 更新字段
    diagnosis = data.get('diagnosis')
    follow_up_notes = data.get('follow_up_notes')
    
    if diagnosis is not None:
        report.diagnosis = diagnosis.strip() if diagnosis else None
    
    if follow_up_notes is not None:
        report.follow_up_notes = follow_up_notes.strip() if follow_up_notes else None
    
    # 记录修改时间戳（使用updated_at字段，如果没有则使用timestamp）
    report.timestamp = datetime.utcnow()
    
    db.session.commit()
    
    # 记录操作日志
    log_operation(f"医生编辑报告:report_id={report_id}")
    
    return jsonify({
        "success": True,
        "message": "报告已更新",
        "report": report.to_dict()
    }), 200

# -------------------- 医生端 API --------------------

@bp.route("/api/doctor/dashboard", methods=["GET"])
@require_role('doctor')
def get_doctor_dashboard():
    """获取医生工作台数据"""
    user = get_current_user()
    profile = DoctorProfile.query.filter_by(user_id=user.id).first()
    
    # 获取我的患者
    relations = DoctorPatientRelation.query.filter_by(doctor_id=user.id).all()
    patient_ids = [r.patient_id for r in relations]
    patients = User.query.filter(User.id.in_(patient_ids)).all()
    
    patient_list = []
    for patient in patients:
        p_profile = PatientProfile.query.filter_by(user_id=patient.id).first()
        relation = next((r for r in relations if r.patient_id == patient.id), None)
        patient_list.append({
            "id": patient.id,
            "full_name": patient.full_name,
            "patient_number": p_profile.patient_number if p_profile else '',
            "gender": p_profile.gender if p_profile else '',
            "age": calculate_age(p_profile.birth_date) if p_profile and p_profile.birth_date else 0,
            "phone": patient.phone,
            "status": relation.status if relation else 'active'
        })
    
    # 获取病历记录
    records = MedicalRecord.query.filter_by(doctor_id=user.id).order_by(MedicalRecord.visit_date.desc()).limit(50).all()
    
    # 获取今日病历数
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    today_records = MedicalRecord.query.filter(
        MedicalRecord.doctor_id == user.id,
        MedicalRecord.visit_date >= today_start,
        MedicalRecord.visit_date < today_end
    ).all()
    
    # 获取今日检测数（该医生关联患者的检测记录）
    patient_ids_for_detect = [p['id'] for p in patient_list]
    today_detections = DetectionHistory.query.filter(
        DetectionHistory.patient_id.in_(patient_ids_for_detect),
        DetectionHistory.timestamp >= today_start,
        DetectionHistory.timestamp < today_end
    ).all() if patient_ids_for_detect else []
    
    # 生成待办事项（基于未完成的病历和检测）
    tasks = []
    # 1. 需要跟进的患者（最近7天有检测但没有诊断结论的）
    week_ago = today_start - timedelta(days=7)
    recent_detections = DetectionHistory.query.filter(
        DetectionHistory.patient_id.in_(patient_ids_for_detect),
        DetectionHistory.timestamp >= week_ago,
        DetectionHistory.diagnosis.is_(None)
    ).all() if patient_ids_for_detect else []
    
    for det in recent_detections[:3]:  # 最多显示3个
        patient = db.session.get(User, det.patient_id)
        if patient:
            tasks.append({
                "id": f"det_{det.id}",
                "content": f"为 {patient.full_name} 完善检测诊断结论",
                "type": "warning"
            })
    
    # 2. 需要复诊的患者（复诊日期在今天之前的）
    follow_up_patients = MedicalRecord.query.filter(
        MedicalRecord.doctor_id == user.id,
        MedicalRecord.follow_up_date < datetime.utcnow(),
        MedicalRecord.follow_up_date.isnot(None)
    ).order_by(MedicalRecord.follow_up_date.desc()).limit(2).all()
    
    for rec in follow_up_patients:
        patient = db.session.get(User, rec.patient_id)
        if patient:
            tasks.append({
                "id": f"follow_{rec.id}",
                "content": f"{patient.full_name} 复诊跟进",
                "type": "primary"
            })
    
    return jsonify({
        "success": True,
        "doctor": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "phone": user.phone,
            "email": user.email,
            "department": profile.department if profile else '',
            "title": profile.title if profile else '',
            "hospital": profile.hospital if profile else '',
            "license_number": profile.license_number if profile else '',
            "specialty": profile.specialty if profile else ''
        },
        "patients": patient_list,
        "records": [r.to_dict() for r in records],
        "today_records": [r.to_dict() for r in today_records],
        "today_detections": [d.to_dict() for d in today_detections],
        "tasks": tasks
    })

@bp.route("/api/doctor/patients", methods=["POST"])
@require_role('doctor')
def doctor_add_patient():
    """医生添加患者"""
    doctor = get_current_user()
    data = request.json
    
    # 生成随机用户名和密码
    import random
    import string
    username = f"P{datetime.now().strftime('%Y%m%d%H%M%S')}"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    try:
        # 创建用户
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            role='patient',
            full_name=data.get('full_name'),
            phone=data.get('phone')
        )
        db.session.add(new_user)
        db.session.flush()
        
        # 创建患者档案
        patient_number = f"P{datetime.now().strftime('%Y%m%d')}{new_user.id:04d}"
        birth_date = data.get('birth_date')
        profile = PatientProfile(
            user_id=new_user.id,
            patient_number=patient_number,
            id_card=data.get('id_card', ''),
            gender=data.get('gender', '男'),
            birth_date=datetime.strptime(birth_date, '%Y-%m-%d').date() if birth_date else None,
            address=data.get('address', ''),
            emergency_contact=data.get('emergency_contact', ''),
            emergency_phone=data.get('emergency_phone', ''),
            allergies=data.get('allergies', ''),
            medical_history=data.get('medical_history', ''),
            created_by=doctor.id
        )
        db.session.add(profile)
        
        # 建立医生-患者关系
        relation = DoctorPatientRelation(
            doctor_id=doctor.id,
            patient_id=new_user.id,
            is_primary=True,
            status='active'
        )
        db.session.add(relation)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "患者添加成功",
            "username": username,
            "password": password,
            "patient_number": patient_number
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"添加患者失败: {e}")
        return jsonify({"error": "添加失败"}), 500

@bp.route("/api/doctor/patients/<int:patient_id>/archive", methods=["PUT"])
@require_role('doctor')
def archive_patient(patient_id):
    """归档/取消归档患者"""
    doctor = get_current_user()
    data = request.json
    status = data.get('status', 'archived')  # 'archived' 或 'active'
    
    try:
        # 查找医生-患者关系
        relation = DoctorPatientRelation.query.filter_by(
            doctor_id=doctor.id,
            patient_id=patient_id
        ).first()
        
        if not relation:
            return jsonify({"error": "未找到该患者关联"}), 404
        
        # 更新状态
        relation.status = status
        db.session.commit()
        
        action = "归档" if status == 'archived' else "恢复"
        return jsonify({
            "success": True,
            "message": f"患者已{action}"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"归档患者失败: {e}")
        return jsonify({"error": "操作失败"}), 500

@bp.route("/api/doctor/all-patients", methods=["GET"])
@require_role('doctor')
def get_all_patients():
    """获取所有患者列表（用于创建病历时选择）"""
    try:
        patients = User.query.filter_by(role='patient').all()
        patient_list = []
        for patient in patients:
            profile = PatientProfile.query.filter_by(user_id=patient.id).first()
            if profile:  # 只返回有档案的患者
                patient_list.append({
                    "id": patient.id,
                    "full_name": patient.full_name,
                    "patient_number": profile.patient_number,
                    "gender": profile.gender,
                    "age": calculate_age(profile.birth_date) if profile.birth_date else 0,
                    "phone": patient.phone
                })
        
        return jsonify({
            "success": True,
            "patients": patient_list
        })
    except Exception as e:
        logger.error(f"获取患者列表失败: {e}")
        return jsonify({"error": "获取失败"}), 500

@bp.route("/api/doctor/medical-records", methods=["POST"])
@require_role('doctor')
def doctor_create_record():
    """医生创建病历"""
    doctor = get_current_user()
    data = request.json
    
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify({"error": "请选择患者"}), 400
    
    try:
        # 检查是否已存在医生-患者关系，如果不存在则创建
        relation = DoctorPatientRelation.query.filter_by(
            doctor_id=doctor.id,
            patient_id=patient_id
        ).first()
        
        if not relation:
            # 检查患者是否已有主治医生
            existing_primary = DoctorPatientRelation.query.filter_by(
                patient_id=patient_id,
                is_primary=True
            ).first()
            
            # 创建新的医生-患者关系，如果没有主治医生则设为 primary
            relation = DoctorPatientRelation(
                doctor_id=doctor.id,
                patient_id=patient_id,
                is_primary=not existing_primary,  # 如果没有主治医生，则设为 primary
                status='active'
            )
            db.session.add(relation)
        
        # 生成病历号
        record_number = f"R{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        record = MedicalRecord(
            record_number=record_number,
            patient_id=patient_id,
            doctor_id=doctor.id,
            symptoms=data.get('symptoms', ''),
            diagnosis=data.get('diagnosis', ''),
            treatment=data.get('treatment', ''),
            advice=data.get('advice', ''),
            follow_up_date=datetime.strptime(data.get('follow_up_date'), '%Y-%m-%d') if data.get('follow_up_date') else None,
            status='active'
        )
        db.session.add(record)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "病历创建成功",
            "record_number": record_number
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建病历失败: {e}")
        return jsonify({"error": "创建失败"}), 500

@bp.route("/api/doctor/medical-records/<int:record_id>", methods=["PUT"])
@require_role('doctor')
def doctor_update_record(record_id):
    """医生更新病历"""
    doctor = get_current_user()
    data = request.json
    
    try:
        record = MedicalRecord.query.filter_by(id=record_id, doctor_id=doctor.id).first()
        if not record:
            return jsonify({"error": "病历不存在或无权限编辑"}), 404
        
        # 更新病历字段
        record.symptoms = data.get('symptoms', record.symptoms)
        record.diagnosis = data.get('diagnosis', record.diagnosis)
        record.treatment = data.get('treatment', record.treatment)
        record.advice = data.get('advice', record.advice)
        if data.get('follow_up_date'):
            record.follow_up_date = datetime.strptime(data.get('follow_up_date'), '%Y-%m-%d')
        else:
            record.follow_up_date = None
        record.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "病历更新成功"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新病历失败: {e}")
        return jsonify({"error": "更新失败"}), 500

# -------------------- 编辑个人信息 API --------------------

@bp.route("/api/profile/update", methods=["PUT"])
@require_auth
def update_profile():
    """更新当前登录用户的个人信息"""
    user = get_current_user()
    data = request.json
    
    try:
        # 更新用户基本信息
        if 'full_name' in data:
            user.full_name = data['full_name'].strip()
        if 'phone' in data:
            phone = data['phone'].strip()
            if phone and not re.match(r'^1[3-9]\d{9}$', phone):
                return jsonify({"error": "手机号格式不正确"}), 400
            user.phone = phone
        if 'email' in data:
            email = data['email'].strip()
            if email:
                # 检查邮箱是否被其他用户使用
                existing = User.query.filter(User.email == email, User.id != user.id).first()
                if existing:
                    return jsonify({"error": "邮箱已被其他用户使用"}), 409
            user.email = email
        
        # 根据角色更新特定信息
        if user.role == 'doctor':
            profile = DoctorProfile.query.filter_by(user_id=user.id).first()
            if not profile:
                profile = DoctorProfile(user_id=user.id)
                db.session.add(profile)
            
            if 'department' in data:
                profile.department = data['department'].strip()
            if 'title' in data:
                profile.title = data['title'].strip()
            if 'hospital' in data:
                profile.hospital = data['hospital'].strip()
            if 'license_number' in data:
                profile.license_number = data['license_number'].strip()
            if 'specialty' in data:
                profile.specialty = data['specialty'].strip()
                
        elif user.role == 'patient':
            profile = PatientProfile.query.filter_by(user_id=user.id).first()
            if not profile:
                profile = PatientProfile(user_id=user.id)
                db.session.add(profile)
            
            if 'id_card' in data:
                profile.id_card = data['id_card'].strip()
            if 'gender' in data:
                profile.gender = data['gender']
            if 'birth_date' in data:
                birth_date = data['birth_date']
                if birth_date:
                    profile.birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            if 'address' in data:
                profile.address = data['address'].strip()
            if 'emergency_contact' in data:
                profile.emergency_contact = data['emergency_contact'].strip()
            if 'emergency_phone' in data:
                profile.emergency_phone = data['emergency_phone'].strip()
            if 'allergies' in data:
                profile.allergies = data['allergies'].strip()
            if 'medical_history' in data:
                profile.medical_history = data['medical_history'].strip()
        
        db.session.commit()
        log_operation(f"用户更新个人信息:{user.username}")
        
        return jsonify({
            "success": True,
            "message": "个人信息更新成功"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新个人信息失败: {e}")
        return jsonify({"error": "更新失败"}), 500
