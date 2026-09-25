"""管理后台接口：用户、日志、设置、公告、统计

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import json
import random
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from core.auth import get_current_user, require_auth, require_role
from core.helpers import log_operation, save_user_ai_model
from core.validators import (
    validate_email, validate_password, validate_phone,
    validate_role, validate_username,
)
from database import (
    Announcement, AnnouncementRead, CustomModel, DetectionHistory,
    DoctorProfile, DoctorRegistration, Examination, MedicalRecord,
    OperationLog, Patient, PatientProfile, SystemSettings, User, db,
)
from utils.logger import logger

bp = Blueprint('admin', __name__)

# ==================== 系统设置接口 ====================

@bp.route("/api/settings", methods=["GET"])
@require_auth
def get_settings():
    default_model_setting = SystemSettings.query.filter_by(key='default_model').first()
    default_model = default_model_setting.value if default_model_setting else 'yolov8s'
    
    confidence_setting = SystemSettings.query.filter_by(key='confidence_threshold').first()
    confidence_threshold = float(confidence_setting.value) if confidence_setting else 0.25
    
    # AI服务配置
    ai_provider_setting = SystemSettings.query.filter_by(key='ai_provider').first()
    ai_provider = ai_provider_setting.value if ai_provider_setting else 'local'
    
    ai_api_key_setting = SystemSettings.query.filter_by(key='ai_api_key').first()
    ai_api_key = ai_api_key_setting.value if ai_api_key_setting else ''
    
    ai_api_url_setting = SystemSettings.query.filter_by(key='ai_api_url').first()
    ai_api_url = ai_api_url_setting.value if ai_api_url_setting else ''
    
    ai_model_setting = SystemSettings.query.filter_by(key='ai_model').first()
    ai_model = ai_model_setting.value if ai_model_setting else 'gpt-4'
    
    # 获取所有已发布的模型（只返回管理员发布的自定义模型）
    # 基础模型（yolov8, yolo11, yolo26）仅供训练使用，不显示给医生用于检测
    available_models = []

    # 只返回已发布的自定义模型
    custom_models = CustomModel.query.filter_by(status='published').all()
    for model in custom_models:
        available_models.append({
            'key': model.model_key,
            'name': model.name,
            'type': 'custom'
        })
    
    return jsonify({
        "default_model": default_model,
        "available_models": available_models,
        "confidence_threshold": confidence_threshold,
        "ai_provider": ai_provider,
        "ai_api_key": ai_api_key,
        "ai_api_url": ai_api_url,
        "ai_model": ai_model
    })

@bp.route("/api/settings", methods=["POST"])
@require_role('admin')
def update_settings():
    data = request.json
    
    if 'default_model' in data:
        setting = SystemSettings.query.filter_by(key='default_model').first()
        if setting:
            setting.value = data['default_model']
        else:
            setting = SystemSettings(key='default_model', value=data['default_model'])
        db.session.add(setting)
    
    if 'confidence_threshold' in data:
        setting = SystemSettings.query.filter_by(key='confidence_threshold').first()
        if setting:
            setting.value = str(data['confidence_threshold'])
        else:
            setting = SystemSettings(key='confidence_threshold', value=str(data['confidence_threshold']))
        db.session.add(setting)
    
    # AI服务配置
    if 'ai_provider' in data:
        setting = SystemSettings.query.filter_by(key='ai_provider').first()
        if setting:
            setting.value = data['ai_provider']
        else:
            setting = SystemSettings(key='ai_provider', value=data['ai_provider'])
        db.session.add(setting)
    
    if 'ai_api_key' in data:
        setting = SystemSettings.query.filter_by(key='ai_api_key').first()
        if setting:
            setting.value = data['ai_api_key']
        else:
            setting = SystemSettings(key='ai_api_key', value=data['ai_api_key'])
        db.session.add(setting)
    
    if 'ai_api_url' in data:
        setting = SystemSettings.query.filter_by(key='ai_api_url').first()
        if setting:
            setting.value = data['ai_api_url']
        else:
            setting = SystemSettings(key='ai_api_url', value=data['ai_api_url'])
        db.session.add(setting)
    
    if 'ai_model' in data:
        setting = SystemSettings.query.filter_by(key='ai_model').first()
        if setting:
            setting.value = data['ai_model']
        else:
            setting = SystemSettings(key='ai_model', value=data['ai_model'])
        db.session.add(setting)
    
    db.session.commit()
    
    # 保存用户AI模型配置（用于下拉框选择）
    if 'ai_provider' in data and 'ai_model' in data:
        username = request.headers.get('X-Username', 'unknown')
        save_user_ai_model(
            provider=data['ai_provider'],
            model_id=data['ai_model'],
            api_key=data.get('ai_api_key', ''),
            api_url=data.get('ai_api_url', ''),
            username=username
        )
    
    return jsonify({"success": True, "message": "设置已保存"})

# ==================== 用户管理接口（仅管理员） ====================

@bp.route("/api/users", methods=["GET"])
@require_role('admin')
def get_users():
    """获取所有用户列表 - 支持角色筛选、搜索和分页
    
    Query参数:
        role: 按角色筛选 (admin/doctor/patient)
        search: 按用户名、姓名或ID搜索
        page: 页码 (默认1)
        per_page: 每页数量 (默认20, 最大100)
    """
    # 获取查询参数
    role = request.args.get('role', '').strip()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # 限制最大每页数量
    
    # 构建查询
    query = User.query
    
    # 角色筛选
    if role and role in ['admin', 'doctor', 'patient']:
        query = query.filter_by(role=role)
    
    # 搜索功能
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                User.username.ilike(search_pattern),
                User.full_name.ilike(search_pattern),
                User.id.cast(db.String).ilike(search_pattern)
            )
        )
    
    # 排序并分页
    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # 构建返回数据，为患者角色添加patient_profile信息
    data = []
    for user in pagination.items:
        user_dict = user.to_dict()
        if user.role == 'patient' and user.patient_profile:
            user_dict['patient_profile'] = {
                'gender': user.patient_profile.gender,
                'birth_date': user.patient_profile.birth_date.isoformat() if user.patient_profile.birth_date else None,
                'patient_number': user.patient_profile.patient_number
            }
        data.append(user_dict)
    
    return jsonify({
        "data": data,
        "total": pagination.total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages
    })

@bp.route("/api/users", methods=["POST"])
@require_role('admin')
def create_user():
    """创建新用户（管理员）- 支持创建所有角色
    
    请求体:
        username: 用户名 (必填)
        password: 密码 (必填)
        role: 角色 (admin/doctor/patient, 默认patient)
        full_name: 全名 (可选)
        email: 邮箱 (可选)
        phone: 电话 (可选)
    """
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "patient").strip()
    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    
    # 验证用户名
    valid, error_msg = validate_username(username)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    # 验证密码
    valid, error_msg = validate_password(password)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    # 验证角色值
    if not validate_role(role):
        return jsonify({"error": "角色必须是 'admin', 'doctor' 或 'patient'"}), 400
    
    # 验证邮箱格式
    valid, error_msg = validate_email(email)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    # 验证电话格式
    valid, error_msg = validate_phone(phone)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    # 检查用户是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 409
    
    # 检查邮箱是否已被使用
    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "邮箱已被使用"}), 409
    
    # 创建新用户
    new_user = User(
        username=username,
        password=generate_password_hash(password),
        role=role,
        full_name=full_name,
        email=email,
        phone=phone
    )
    db.session.add(new_user)
    db.session.commit()
    
    # 记录操作日志
    log_operation(
        description=f'管理员创建用户: {username}, 角色: {role}',
        success=True
    )
    
    return jsonify({
        "success": True,
        "message": "用户创建成功",
        "user": new_user.to_dict()
    }), 201

@bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@require_role('admin')
def delete_user(user_id):
    """删除用户"""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    # 防止删除自己
    current_user = get_current_user()
    if user.id == current_user.id:
        return jsonify({"error": "不能删除自己的账户"}), 400
    
    username = user.username
    role = user.role
    
    # 删除用户相关的检测历史
    DetectionHistory.query.filter_by(username=user.username).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    # 记录操作日志
    log_operation(f"管理员删除用户:{username},角色:{role}")
    
    return jsonify({"success": True, "message": "用户已删除"})

@bp.route("/api/users/<int:user_id>", methods=["PUT"])
@require_role('admin')
def update_user(user_id):
    """更新用户信息 - 支持更新角色和个人信息
    
    请求体:
        role: 角色 (admin/doctor/patient, 可选)
        password: 密码 (可选)
        full_name: 全名 (可选)
        email: 邮箱 (可选)
        phone: 电话 (可选)
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    import re
    data = request.json
    role = data.get("role")
    password = data.get("password", "").strip()
    full_name = data.get("full_name")
    email = data.get("email")
    phone = data.get("phone")
    
    # 更新角色
    if role is not None:
        if role not in ['admin', 'doctor', 'patient']:
            return jsonify({"error": "角色必须是 'admin', 'doctor' 或 'patient'"}), 400
        # 防止admin修改自己的角色
        current_user = get_current_user()
        if user.id == current_user.id:
            return jsonify({"error": "不能修改自己的角色"}), 400
        user.role = role
    
    # 更新密码
    if password:
        if len(password) < 6:
            return jsonify({"error": "密码长度至少6个字符"}), 400
        user.password = generate_password_hash(password)
    
    # 更新全名
    if full_name is not None:
        user.full_name = full_name.strip()
    
    # 更新邮箱
    if email is not None:
        email = email.strip()
        if email:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                return jsonify({"error": "邮箱格式不正确"}), 400
            # 检查邮箱是否被其他用户使用
            existing_user = User.query.filter_by(email=email).first()
            if existing_user and existing_user.id != user_id:
                return jsonify({"error": "邮箱已被其他用户使用"}), 409
        user.email = email
    
    # 更新电话
    if phone is not None:
        phone = phone.strip()
        if phone:
            phone_pattern = r'^1[3-9]\d{9}$'
            if not re.match(phone_pattern, phone):
                return jsonify({"error": "电话格式不正确"}), 400
        user.phone = phone
    
    user.updated_at = datetime.utcnow()
    db.session.commit()
    
    # 记录操作日志
    log_operation(
        description=f'管理员更新用户: {user.username}'
    )
    
    return jsonify({
        "success": True,
        "message": "用户信息已更新",
        "user": user.to_dict()
    })

@bp.route("/api/logs", methods=["GET"])
@bp.route("/api/admin/logs", methods=["GET"])
@require_role('admin')
def get_logs():
    """获取操作日志列表
    
    权限: admin
    
    Query参数:
        page: 页码 (默认1)
        per_page: 每页数量 (默认20)
        username: 按用户名筛选 (模糊匹配)
        method: 按HTTP方法筛选 (GET/POST/PUT/DELETE/SYSTEM)
        operation_type: 按操作类型筛选 (模糊匹配description字段)
        date_from: 开始时间 (ISO格式: YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
        date_to: 结束时间 (ISO格式: YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
        success: 按成功状态筛选 (true/false)
    
    返回:
        data: 日志列表
        total: 总数
        page: 当前页
        per_page: 每页数量
    
    需求: 2.6, 14.3
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    username = request.args.get('username', '').strip()
    method = request.args.get('method', '').strip()
    operation_type = request.args.get('operation_type', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    success_param = request.args.get('success', '').strip()
    
    query = OperationLog.query
    
    # 按用户名筛选 (模糊匹配)
    if username:
        query = query.filter(OperationLog.username.contains(username))
    
    # 按HTTP方法筛选
    if method:
        query = query.filter_by(method=method)
    
    # 按操作类型筛选 (模糊匹配description字段)
    if operation_type:
        query = query.filter(OperationLog.description.contains(operation_type))
    
    # 按时间范围筛选
    if date_from:
        try:
            # 尝试解析日期时间
            from datetime import datetime
            # 支持两种格式: YYYY-MM-DD 和 YYYY-MM-DD HH:MM:SS
            if len(date_from) == 10:  # YYYY-MM-DD
                date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            else:
                date_from_dt = datetime.strptime(date_from, '%Y-%m-%d %H:%M:%S')
            # 转换为UTC时间 (数据库存储的是UTC时间)
            from datetime import timedelta
            date_from_utc = date_from_dt - timedelta(hours=8)
            query = query.filter(OperationLog.timestamp >= date_from_utc)
        except ValueError:
            pass  # 忽略无效的日期格式
    
    if date_to:
        try:
            from datetime import datetime
            if len(date_to) == 10:  # YYYY-MM-DD
                # 如果只提供日期,则包含当天的所有时间
                date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
                from datetime import timedelta
                date_to_dt = date_to_dt + timedelta(days=1) - timedelta(seconds=1)
            else:
                date_to_dt = datetime.strptime(date_to, '%Y-%m-%d %H:%M:%S')
            # 转换为UTC时间
            from datetime import timedelta
            date_to_utc = date_to_dt - timedelta(hours=8)
            query = query.filter(OperationLog.timestamp <= date_to_utc)
        except ValueError:
            pass  # 忽略无效的日期格式
    
    # 按成功状态筛选
    if success_param:
        if success_param.lower() == 'true':
            query = query.filter_by(success=True)
        elif success_param.lower() == 'false':
            query = query.filter_by(success=False)
    
    # 分页查询
    pagination = query.order_by(OperationLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'data': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page
    })

@bp.route("/api/logs/<int:log_id>", methods=["DELETE"])
@require_role('admin')
def delete_log(log_id):
    """删除单条日志"""
    log = db.session.get(OperationLog, log_id)
    if not log:
        return jsonify({"error": "日志不存在"}), 404
    
    db.session.delete(log)
    db.session.commit()
    log_operation(f"删除日志 ID:{log_id}")
    return jsonify({"success": True, "message": "日志已删除"})

@bp.route("/api/logs/clear", methods=["DELETE"])
@require_role('admin')
def clear_logs():
    """清空所有日志"""
    try:
        count = OperationLog.query.count()
        OperationLog.query.delete()
        db.session.commit()
        return jsonify({"success": True, "message": f"已清空 {count} 条日志"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# -------------------- 管理员 API --------------------

@bp.route("/api/admin/dashboard", methods=["GET"])
@require_role('admin')
def get_admin_dashboard():
    """获取管理员仪表盘数据"""
    try:
        admin = get_current_user()
        
        # 待审核的医生申请
        pending = DoctorRegistration.query.filter_by(status='pending').all()
        
        # 已审核的申请
        processed = DoctorRegistration.query.filter(DoctorRegistration.status.in_(['approved', 'rejected'])).order_by(DoctorRegistration.reviewed_at.desc()).limit(50).all()
        
        # 所有医生
        doctors = User.query.filter_by(role='doctor').all()
        doctor_list = []
        for d in doctors:
            profile = DoctorProfile.query.filter_by(user_id=d.id).first()
            doctor_list.append({
                "id": d.id,
                "username": d.username,
                "full_name": d.full_name,
                "hospital": profile.hospital if profile else '',
                "department": profile.department if profile else '',
                "title": profile.title if profile else '',
                "phone": d.phone,
                "status": profile.status if profile else 'pending'
            })
        
        # 所有患者
        patients = User.query.filter_by(role='patient').all()
        patient_list = []
        for p in patients:
            profile = PatientProfile.query.filter_by(user_id=p.id).first()
            patient_list.append({
                "id": p.id,
                "username": p.username,
                "full_name": p.full_name,
                "patient_number": profile.patient_number if profile else '',
                "gender": profile.gender if profile else '',
                "phone": p.phone,
                "created_at": profile.created_at.isoformat() if profile else ''
            })
        
        return jsonify({
            "success": True,
            "admin": {"id": admin.id, "username": admin.username},
            "pending_approvals": [p.to_dict() for p in pending],
            "processed_approvals": [p.to_dict() for p in processed],
            "doctors": doctor_list,
            "patients": patient_list
        })
    except Exception as e:
        import traceback
        logger.error(f"Dashboard API Error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route("/api/admin/approve-doctor/<int:registration_id>", methods=["POST"])
@require_role('admin')
def approve_doctor_registration(registration_id):
    """审核医生注册申请"""
    admin = get_current_user()
    data = request.json
    status = data.get('status')  # 'approved' or 'rejected'
    note = data.get('note', '')
    
    registration = db.session.get(DoctorRegistration, registration_id)
    if not registration:
        return jsonify({"error": "申请不存在"}), 404
    
    if registration.status != 'pending':
        return jsonify({"error": "该申请已处理"}), 400
    
    try:
        if status == 'approved':
            # 创建用户
            new_user = User(
                username=registration.username,
                password=registration.password,
                role='doctor',
                full_name=registration.full_name,
                email=registration.email,
                phone=registration.phone
            )
            db.session.add(new_user)
            db.session.flush()
            
            # 创建医生档案
            profile = DoctorProfile(
                user_id=new_user.id,
                department=registration.department,
                title=registration.title,
                license_number=registration.license_number,
                specialty=registration.specialty,
                hospital=registration.hospital,
                status='active',
                approved_by=admin.id,
                approved_at=datetime.utcnow()
            )
            db.session.add(profile)
        
        # 更新申请状态
        registration.status = status
        registration.reviewed_by = admin.id
        registration.reviewed_at = datetime.utcnow()
        registration.review_note = note
        
        db.session.commit()
        
        log_operation(f"管理员审核医生申请:{registration.username},结果:{status}")
        
        return jsonify({
            "success": True,
            "message": "审核成功"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"审核失败: {e}")
        return jsonify({"error": "审核失败"}), 500

@bp.route("/api/admin/statistics", methods=["GET"])
@require_role('admin')
def get_admin_statistics():
    """获取管理员统计数据"""
    try:
        from datetime import datetime, timedelta
        
        # 获取日期范围参数
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # 基础统计
        total_patients = User.query.filter_by(role='patient').count()
        total_doctors = User.query.filter_by(role='doctor').count()
        total_records = MedicalRecord.query.count()
        
        # 今日检测数
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        today_detections = DetectionHistory.query.filter(
            DetectionHistory.timestamp >= today_start,
            DetectionHistory.timestamp <= today_end
        ).count()
        
        # 总检测数
        total_detections = DetectionHistory.query.count()
        
        # 日期范围内的检测数
        date_range_detections = 0
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                date_range_detections = DetectionHistory.query.filter(
                    DetectionHistory.timestamp >= start,
                    DetectionHistory.timestamp < end
                ).count()
            except:
                pass
        
        return jsonify({
            "total_patients": total_patients,
            "total_doctors": total_doctors,
            "total_records": total_records,
            "today_detections": today_detections,
            "total_detections": total_detections,
            "date_range_detections": date_range_detections
        })
    except Exception as e:
        import traceback
        logger.error(f"Statistics API Error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route("/api/admin/statistics/detailed", methods=["GET"])
@require_role('admin')
def get_admin_statistics_detailed():
    """获取管理员详细统计数据"""
    from datetime import datetime, timedelta
    
    # 获取日期范围参数
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        # 基础统计
        total_patients = User.query.filter_by(role='patient').count()
        total_doctors = User.query.filter_by(role='doctor').count()
        
        # 患者性别分布 - 从 PatientProfile 获取
        patient_profiles = PatientProfile.query.all()
        male_count = sum(1 for p in patient_profiles if p.gender == '男')
        female_count = sum(1 for p in patient_profiles if p.gender == '女')
        
        # 患者年龄段分布 - 从 PatientProfile 获取
        age_distribution = {
            '0-18': 0, '19-35': 0, '36-50': 0, '51-65': 0, '65+': 0
        }
        for profile in patient_profiles:
            if profile.birth_date:
                age = datetime.now().year - profile.birth_date.year
                if age <= 18:
                    age_distribution['0-18'] += 1
                elif age <= 35:
                    age_distribution['19-35'] += 1
                elif age <= 50:
                    age_distribution['36-50'] += 1
                elif age <= 65:
                    age_distribution['51-65'] += 1
                else:
                    age_distribution['65+'] += 1
        
        # 医生科室分布 - 从 DoctorProfile 获取
        doctor_profiles = DoctorProfile.query.all()
        department_distribution = {}
        for profile in doctor_profiles:
            dept = profile.department or '未分配'
            department_distribution[dept] = department_distribution.get(dept, 0) + 1
        
        # 检测统计
        query = DetectionHistory.query
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(DetectionHistory.timestamp >= start, DetectionHistory.timestamp < end)
            except Exception as e:
                logger.error(f"日期解析错误: {e}")
        
        detections = query.all()
        total_detections = len(detections)
        
        # 检测类别统计
        classes_detected = {}
        models_used = {}
        daily_detections = {}
        
        for detection in detections:
            # 模型使用统计
            model = detection.model or 'unknown'
            models_used[model] = models_used.get(model, 0) + 1
            
            # 日期统计
            date_key = detection.timestamp.strftime('%Y-%m-%d')
            daily_detections[date_key] = daily_detections.get(date_key, 0) + 1
            
            # 检测类别统计
            try:
                detection_data = json.loads(detection.detections) if detection.detections else []
                for det in detection_data:
                    cls = det.get('class', 'unknown')
                    classes_detected[cls] = classes_detected.get(cls, 0) + 1
            except Exception as e:
                logger.error(f"解析检测数据错误: {e}")
        
        # 计算日均检测数
        avg_daily = 0
        if daily_detections:
            avg_daily = round(total_detections / len(daily_detections), 1)
        
        return jsonify({
            'total_patients': total_patients,
            'total_doctors': total_doctors,
            'gender_distribution': {
                'male': male_count,
                'female': female_count,
                'total': male_count + female_count
            },
            'age_distribution': age_distribution,
            'department_distribution': department_distribution,
            'total_detections': total_detections,
            'avg_daily': avg_daily,
            'classes_detected': classes_detected,
            'models_used': models_used,
            'daily_detections': daily_detections
        })
    except Exception as e:
        logger.error(f"获取详细统计数据错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'total_patients': 0,
            'total_doctors': 0,
            'gender_distribution': {'male': 0, 'female': 0, 'total': 0},
            'age_distribution': {'0-18': 0, '19-35': 0, '36-50': 0, '51-65': 0, '65+': 0},
            'department_distribution': {},
            'total_detections': 0,
            'avg_daily': 0,
            'classes_detected': {},
            'models_used': {},
            'daily_detections': {}
        })

@bp.route("/api/admin/generate-test-data", methods=["POST"])
@require_role('admin')
def generate_test_data():
    """生成测试数据"""
    from datetime import datetime, timedelta
    import random
    
    data = request.get_json(silent=True) or {}
    patient_count = data.get('patient_count', 20)
    exam_count = data.get('exam_count', 50)
    
    try:
        generated = {
            'patients': 0,
            'examinations': 0
        }
        
        # 常见姓氏和名字
        surnames = ['张', '王', '李', '刘', '陈', '杨', '黄', '赵', '吴', '周', '徐', '孙', '马', '朱', '胡', '郭', '何', '高', '林', '罗']
        names = ['伟', '芳', '娜', '秀英', '敏', '静', '丽', '强', '磊', '军', '洋', '勇', '艳', '杰', '娟', '涛', '明', '超', '秀兰', '霞', '平', '刚', '桂英']
        
        # 骨折类型
        fracture_types = ['撕脱骨折', '粉碎性骨折', '压缩性骨折', '应力性骨折', '开放性骨折', '闭合性骨折']
        
        # 生成患者
        patients = []
        for i in range(patient_count):
            name = random.choice(surnames) + random.choice(names)
            age = random.randint(18, 85)
            gender = random.choice(['男', '女'])
            
            patient = Patient(
                name=name,
                age=age,
                gender=gender,
                medical_history=random.choice(['无特殊病史', '高血压', '糖尿病', '心脏病', '']) if random.random() > 0.5 else '',
                contact_info=f"138{random.randint(10000000, 99999999)}"
            )
            db.session.add(patient)
            patients.append(patient)
        
        db.session.commit()
        generated['patients'] = len(patients)
        
        # 生成检查记录
        for i in range(exam_count):
            patient = random.choice(patients)
            
            # 随机日期（最近一年内）
            days_ago = random.randint(0, 365)
            exam_date = datetime.utcnow() - timedelta(days=days_ago)
            
            # 是否有骨折（60%概率）
            has_fracture = random.random() < 0.6
            
            if has_fracture:
                # 选择1-2种骨折类型
                num_types = random.randint(1, 2)
                selected_types = random.sample(fracture_types, num_types)
                detection_result = {
                    'has_fracture': True,
                    'fracture_types': selected_types,
                    'confidence': round(random.uniform(0.75, 0.98), 2),
                    'detections': [
                        {
                            'class': ft,
                            'confidence': round(random.uniform(0.75, 0.98), 2),
                            'bbox': [random.randint(50, 200), random.randint(50, 200), random.randint(250, 400), random.randint(250, 400)]
                        } for ft in selected_types
                    ]
                }
            else:
                detection_result = {
                    'has_fracture': False,
                    'fracture_types': [],
                    'confidence': round(random.uniform(0.85, 0.99), 2),
                    'detections': []
                }
            
            examination = Examination(
                patient_id=patient.id,
                exam_date=exam_date,
                image_path=f"/uploads/test_{i+1}.jpg",
                detection_result=json.dumps(detection_result),
                report=f"检查报告：{'发现骨折' if has_fracture else '未见明显骨折'}。" + random.choice(['建议复查', '建议手术治疗', '建议保守治疗', '定期随访']),
                created_by=random.choice(['张医生', '李医生', '王医生', '刘医生'])
            )
            db.session.add(examination)
        
        db.session.commit()
        generated['examinations'] = exam_count
        
        return jsonify({
            'success': True,
            'message': f'成功生成 {generated["patients"]} 名患者和 {generated["examinations"]} 条检查记录',
            'data': generated
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"生成测试数据错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route("/api/admin/user/<int:user_id>", methods=["PUT"])
@require_role('admin')
def admin_update_user(user_id):
    """管理员更新用户信息（医生或患者）"""
    admin = get_current_user()
    data = request.json
    
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    # 不能修改管理员自己
    if user.id == admin.id:
        return jsonify({"error": "不能通过此接口修改管理员信息"}), 400
    
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
                existing = User.query.filter(User.email == email, User.id != user.id).first()
                if existing:
                    return jsonify({"error": "邮箱已被其他用户使用"}), 409
            user.email = email
        
        # 根据角色更新特定信息
        if user.role == 'doctor':
            profile = DoctorProfile.query.filter_by(user_id=user.id).first()
            if profile:
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
                if 'status' in data:
                    profile.status = data['status']
                    
        elif user.role == 'patient':
            profile = PatientProfile.query.filter_by(user_id=user.id).first()
            if profile:
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
        log_operation(f"管理员更新用户信息:{user.username}")
        
        return jsonify({
            "success": True,
            "message": "用户信息更新成功"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新用户信息失败: {e}")
        return jsonify({"error": "更新失败"}), 500

@bp.route("/api/admin/reset-password/<int:user_id>", methods=["POST"])
@require_role('admin')
def admin_reset_password(user_id):
    """管理员重置用户密码"""
    admin = get_current_user()
    data = request.json
    
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    # 不能重置管理员自己的密码
    if user.id == admin.id:
        return jsonify({"error": "不能通过此接口重置管理员密码"}), 400
    
    new_password = data.get("new_password", "").strip()
    
    # 验证密码
    if not new_password:
        return jsonify({"error": "请输入新密码"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "密码长度至少为6位"}), 400
    
    try:
        # 更新密码
        user.password = generate_password_hash(new_password)
        db.session.commit()
        
        log_operation(f"管理员重置用户密码:{user.username}")
        
        return jsonify({
            "success": True,
            "message": "密码重置成功"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"重置密码失败: {e}")
        return jsonify({"error": "密码重置失败"}), 500

# ==================== 公告管理 API ====================

@bp.route("/api/admin/announcements", methods=["GET"])
@require_auth
def get_admin_announcements():
    """管理员获取公告列表"""
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({"error": "无权访问"}), 403

    try:
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return jsonify({
            "success": True,
            "announcements": [a.to_dict() for a in announcements]
        })
    except Exception as e:
        logger.error(f"获取公告列表失败: {e}")
        return jsonify({"error": "获取失败"}), 500

@bp.route("/api/admin/announcements", methods=["POST"])
@require_auth
def create_announcement():
    """管理员创建公告"""
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({"error": "无权访问"}), 403

    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    target_role = data.get('target_role', 'all')
    priority = data.get('priority', 'normal')

    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400

    try:
        announcement = Announcement(
            title=title,
            content=content,
            author_id=user.id,
            target_role=target_role,
            priority=priority,
            is_active=True
        )
        db.session.add(announcement)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "公告发布成功",
            "announcement": announcement.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建公告失败: {e}")
        return jsonify({"error": "发布失败"}), 500

@bp.route("/api/admin/announcements/<int:announcement_id>", methods=["PUT"])
@require_auth
def update_announcement(announcement_id):
    """管理员更新公告"""
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({"error": "无权访问"}), 403

    announcement = db.session.get(Announcement, announcement_id)
    if not announcement:
        return jsonify({"error": "公告不存在"}), 404

    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400

    try:
        announcement.title = title
        announcement.content = content
        announcement.target_role = data.get('target_role', announcement.target_role)
        announcement.priority = data.get('priority', announcement.priority)
        announcement.is_active = data.get('is_active', announcement.is_active)

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "公告更新成功",
            "announcement": announcement.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新公告失败: {e}")
        return jsonify({"error": "更新失败"}), 500

@bp.route("/api/admin/announcements/<int:announcement_id>", methods=["DELETE"])
@require_auth
def delete_announcement(announcement_id):
    """管理员删除公告"""
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({"error": "无权访问"}), 403

    announcement = db.session.get(Announcement, announcement_id)
    if not announcement:
        return jsonify({"error": "公告不存在"}), 404

    try:
        # 删除相关的已读记录
        AnnouncementRead.query.filter_by(announcement_id=announcement_id).delete()
        db.session.delete(announcement)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "公告删除成功"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除公告失败: {e}")
        return jsonify({"error": "删除失败"}), 500
