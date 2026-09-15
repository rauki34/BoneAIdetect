# 加载 .env —— 必须位于任何项目模块导入之前。
# utils.logger 在**导入时**就会读取 LOG_LEVEL，若此时 .env 尚未加载，
# 其中的配置会被静默忽略。
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass   # 未安装 python-dotenv 时回退到系统环境变量

from flask import Flask, request, jsonify, send_from_directory, session, Response
from flask_cors import CORS
from ultralytics import YOLO
import time, cv2, json, glob, random, io, sys
import requests
from datetime import datetime
from pathlib import Path
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt, verify_jwt_in_request,
)
from PIL import Image, ImageDraw, ImageFont
from database import db, User, DetectionHistory, SystemSettings, OperationLog, CustomModel, TrainingTask, UserAIModel, Patient, Examination, AIConversation, PatientProfile, DoctorProfile, DoctorRegistration, MedicalRecord, Announcement, AnnouncementRead, DoctorPatientRelation, Message, init_db, migrate_from_json
import torch
import re
from collections import defaultdict
from threading import Lock
from sqlalchemy import func

from utils.logger import logger
from services.llm_client import (
    LLMClient, LLMError, LLMConfigError,
    LLMTimeoutError, LLMConnectionError, LLMResponseError,
)
app = Flask(__name__)

# 从 config.py 统一加载配置
# 优先级：环境变量 > config.py 默认值
# 通过 FLASK_ENV 切换配置类：development（默认） / production
from config import config_map
app.config.from_object(
    config_map.get(os.environ.get('FLASK_ENV', 'development'), config_map['development'])
)

# 全局CORS配置
CORS(app, resources={
    r"/*": {
        "origins": app.config['CORS_ORIGINS'],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Username"],
        "expose_headers": ["X-Captcha-ID"],  # 暴露自定义header
        "supports_credentials": True  # 需要启用，因为使用session
    }
})

from flask_migrate import Migrate
migrate = Migrate(app, db)      # 注册 migrate 扩展

# JWT 认证（密钥与有效期来自 config.py）
jwt = JWTManager(app)

# 路径常量与共享状态已抽至 core/ 包（供蓝图模块共用）
from core.paths import (      # noqa: E402
    BASE_DIR, UPLOADS, RESULTS, MODELS_DIR,
    MODEL_CANDIDATES, BASE_MODEL_MAP,
)
from core.state import (      # noqa: E402
    captcha_store, CAPTCHA_TIMEOUT,
    models, init_models, load_models,
    rate_limit_storage, rate_limit_lock, RATE_LIMIT_CONFIG,
    video_tasks, training_tasks, training_stop_flags,
)
from core.validators import (  # noqa: E402
    validate_role, validate_username, validate_password,
    validate_email, validate_phone, calculate_age,
)
from core.helpers import log_operation  # noqa: E402
from core.captcha import check_captcha  # noqa: E402

# 初始化数据库
init_db(app)
from core.security import filter_sensitive_content, detect_prompt_injection, sanitize_ai_input  # noqa: E402
from core.ratelimit import check_rate_limit, limit, rate_limit  # noqa: E402
from core.auth import get_current_user, require_auth, require_admin, require_role  # noqa: E402

# 在应用启动时迁移 JSON 数据（如果存在）
with app.app_context():
    migrate_from_json(app)
from services.ai_service import get_ai_settings, get_llm_client, generate_ai_advice_async, _build_assistant_messages, call_ai_assistant_api, get_mock_reply  # noqa: E402

# 加载预置 YOLO 模型
init_models()
from core.helpers import get_filtered_reports  # noqa: E402
from api.auth import bp as auth_bp  # noqa: E402
from api.detection import bp as detection_bp  # noqa: E402
from api.ai import bp as ai_bp  # noqa: E402
from api.message import bp as message_bp  # noqa: E402

# ==================== 蓝图注册 ====================
# 各业务域路由已拆至 api/ 包；路由保留完整路径，URL 与拆分前一致
from api.analysis import bp as analysis_bp  # noqa: E402
from api.auth import bp as auth_bp  # noqa: E402
from api.patient import bp as patient_bp  # noqa: E402

app.register_blueprint(analysis_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(message_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(detection_bp)
app.register_blueprint(patient_bp)


# ==================== 统一错误处理 ====================

class APIError(Exception):
    """自定义API异常类"""
    def __init__(self, message, status_code=400, error_code=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


@app.errorhandler(APIError)
def handle_api_error(error):
    """处理自定义API异常"""
    response = {
        "error": error.message,
        "timestamp": datetime.utcnow().isoformat()
    }
    if error.error_code:
        response["error_code"] = error.error_code
    
    # 记录错误到日志
    log_operation(
        description=f"API错误: {error.message}",
        success=False,
        error_msg=error.message
    )
    
    return jsonify(response), error.status_code


@app.errorhandler(400)
def handle_bad_request(error):
    """处理400错误"""
    response = {
        "error": "请求参数错误",
        "error_code": "VALIDATION_001",
        "message": str(error),
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 400


@app.errorhandler(401)
def handle_unauthorized(error):
    """处理401错误"""
    response = {
        "error": "未登录或会话过期",
        "error_code": "AUTH_001",
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 401


@app.errorhandler(403)
def handle_forbidden(error):
    """处理403错误"""
    response = {
        "error": "权限不足",
        "error_code": "AUTH_002",
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 403


@app.errorhandler(404)
def handle_not_found(error):
    """处理404错误"""
    response = {
        "error": "资源不存在",
        "error_code": "NOT_FOUND",
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 404


@app.errorhandler(409)
def handle_conflict(error):
    """处理409错误"""
    response = {
        "error": "资源冲突",
        "error_code": "CONFLICT",
        "message": str(error),
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 409


@app.errorhandler(500)
def handle_internal_error(error):
    """处理500错误"""
    response = {
        "error": "服务器内部错误",
        "error_code": "INTERNAL_ERROR",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # 记录错误到日志
    log_operation(
        description=f"服务器内部错误: {str(error)}",
        success=False,
        error_msg=str(error)
    )
    
    # 回滚数据库事务
    try:
        db.session.rollback()
    except:
        pass
    
    return jsonify(response), 500


@app.errorhandler(503)
def handle_service_unavailable(error):
    """处理503错误"""
    response = {
        "error": "服务不可用",
        "error_code": "AI_001",
        "message": "AI服务暂时不可用,请稍后重试",
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 503


@app.errorhandler(504)
def handle_gateway_timeout(error):
    """处理504错误"""
    response = {
        "error": "服务超时",
        "error_code": "AI_002",
        "message": "AI服务响应超时,请稍后重试",
        "timestamp": datetime.utcnow().isoformat()
    }
    return jsonify(response), 504


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """处理未预期的异常"""
    response = {
        "error": "未知错误",
        "error_code": "UNKNOWN_ERROR",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # 记录错误到日志
    log_operation(
        description=f"未预期的异常: {str(error)}",
        success=False,
        error_msg=str(error)
    )
    
    # 回滚数据库事务
    try:
        db.session.rollback()
    except:
        pass
    
    return jsonify(response), 500












# ==================== AI内容过滤 ====================
# SENSITIVE_WORDS / PROMPT_INJECTION_PATTERNS 及三个过滤函数已抽至 core.security








# ==================== 限流保护 ====================
# RATE_LIMIT_CONFIG / rate_limit_storage / rate_limit_lock 已抽至 core.state

































# ==================== 系统设置接口 ====================

@app.route("/api/settings", methods=["GET"])
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


@app.route("/api/settings", methods=["POST"])
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




# ==================== 静态文件接口 ====================

@app.route("/results/<path:filename>")
def get_result(filename):
    return send_from_directory(RESULTS, filename)


@app.route("/uploads/<path:filename>")
def get_upload(filename):
    return send_from_directory(UPLOADS, filename)


# ==================== 用户管理接口（仅管理员） ====================

@app.route("/api/users", methods=["GET"])
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


@app.route("/api/users", methods=["POST"])
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


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
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


@app.route("/api/users/<int:user_id>", methods=["PUT"])
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














@app.route("/api/logs", methods=["GET"])
@app.route("/api/admin/logs", methods=["GET"])
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


@app.route("/api/logs/<int:log_id>", methods=["DELETE"])
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


@app.route("/api/logs/clear", methods=["DELETE"])
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


# ==================== 数据集管理接口 ====================

@app.route("/api/datasets", methods=["GET"])
@require_auth
def get_datasets():
    """获取数据集列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    from database import Dataset
    query = Dataset.query.filter_by(status='active')
    
    # 普通用户只能看到自己的数据集
    user = get_current_user()
    if user.role != 'admin':
        query = query.filter_by(uploader=user.username)
    
    pagination = query.order_by(Dataset.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'data': [d.to_dict() for d in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page
    })


@app.route("/api/datasets", methods=["POST"])
@require_role('admin', 'doctor')
def upload_dataset():
    """上传数据集"""
    if 'file' not in request.files:
        return jsonify({"error": "没有上传文件"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400
    
    # 检查文件类型（只接受zip）
    if not file.filename.endswith('.zip'):
        return jsonify({"error": "只支持zip格式的数据集"}), 400
    
    try:
        # 获取表单数据
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '')
        
        if not name:
            name = file.filename.rsplit('.', 1)[0]
        
        # 生成唯一目录名
        timestamp = int(time.time())
        dataset_dir = os.path.join(UPLOADS, 'datasets', f'dataset_{timestamp}')
        os.makedirs(dataset_dir, exist_ok=True)
        
        # 保存zip文件
        zip_path = os.path.join(dataset_dir, file.filename)
        file.save(zip_path)
        
        # 解压数据集
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dataset_dir)
        os.remove(zip_path)  # 删除zip文件
        
        # 查找data.yaml
        data_yaml = None
        for root, dirs, files in os.walk(dataset_dir):
            for f in files:
                if f in ['data.yaml', 'dataset.yaml']:
                    data_yaml = os.path.join(root, f)
                    break
            if data_yaml:
                break
        
        # 解析数据集信息
        num_images = 0
        num_classes = 0
        class_names = []
        
        if data_yaml:
            try:
                import yaml
                with open(data_yaml, 'r', encoding='utf-8') as f:
                    data_config = yaml.safe_load(f)
                num_classes = data_config.get('nc', 0)
                class_names = data_config.get('names', [])
                
                # 统计图片数量
                train_path = data_config.get('train', '')
                if train_path:
                    train_dir = os.path.join(os.path.dirname(data_yaml), train_path)
                    if os.path.exists(train_dir):
                        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
                            num_images += len(glob.glob(os.path.join(train_dir, '**', ext), recursive=True))
            except Exception as e:
                logger.error(f"解析数据集配置失败: {e}")
        
        # 计算数据集大小
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(dataset_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        
        # 保存到数据库
        from database import Dataset
        user = get_current_user()
        dataset = Dataset(
            name=name,
            description=description,
            dataset_path=dataset_dir,
            file_size=total_size,
            num_images=num_images,
            num_classes=num_classes,
            class_names=json.dumps(class_names, ensure_ascii=False),
            status='active',
            uploader=user.username
        )
        db.session.add(dataset)
        db.session.commit()
        
        log_operation(f"上传数据集:{name}")
        return jsonify({
            "success": True,
            "data": dataset.to_dict(),
            "message": "数据集上传成功"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/datasets/<int:dataset_id>", methods=["PUT"])
@require_role('admin', 'doctor')
def update_dataset(dataset_id):
    """更新数据集信息"""
    from database import Dataset
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify({"error": "数据集不存在"}), 404
    
    # 检查权限
    user = get_current_user()
    if user.role != 'admin' and dataset.uploader != user.username:
        return jsonify({"error": "无权修改此数据集"}), 403
    
    data = request.get_json()
    if 'name' in data:
        dataset.name = data['name'].strip()
    if 'description' in data:
        dataset.description = data['description']
    
    db.session.commit()
    log_operation(f"更新数据集:{dataset.name}")
    return jsonify({"success": True, "data": dataset.to_dict()})


@app.route("/api/datasets/<int:dataset_id>", methods=["DELETE"])
@require_role('admin', 'doctor')
def delete_dataset(dataset_id):
    """删除数据集"""
    from database import Dataset
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify({"error": "数据集不存在"}), 404
    
    # 检查权限
    user = get_current_user()
    if user.role != 'admin' and dataset.uploader != user.username:
        return jsonify({"error": "无权删除此数据集"}), 403
    
    # 删除物理目录
    try:
        if os.path.exists(dataset.dataset_path):
            import shutil
            shutil.rmtree(dataset.dataset_path)
    except Exception as e:
        logger.error(f"删除数据集目录失败: {e}")
    
    # 删除数据库记录
    name = dataset.name
    db.session.delete(dataset)
    db.session.commit()
    
    log_operation(f"删除数据集:{name}")
    return jsonify({"success": True, "message": "数据集已删除"})


@app.route("/api/datasets/all", methods=["GET"])
@require_auth
def get_all_datasets():
    """获取所有数据集（用于训练选择）"""
    from database import Dataset
    user = get_current_user()
    
    query = Dataset.query.filter_by(status='active')
    if user.role != 'admin':
        query = query.filter_by(uploader=user.username)
    
    datasets = query.order_by(Dataset.created_at.desc()).all()
    
    return jsonify({
        'datasets': [d.to_dict() for d in datasets]
    })


# ==================== 视频流检测接口 ====================

import base64
import numpy as np
from flask_sock import Sock
import threading
import queue

sock = Sock(app)





@sock.route('/ws/video/<task_id>')
def video_ws(ws, task_id):
    """视频检测 WebSocket 连接"""
    if task_id not in video_tasks:
        ws.send(json.dumps({'type': 'error', 'message': '任务不存在'}))
        return
    
    # 添加客户端到任务
    if 'clients' not in video_tasks[task_id]:
        video_tasks[task_id]['clients'] = set()
    video_tasks[task_id]['clients'].add(ws)
    
    try:
        # 保持连接
        while True:
            message = ws.receive()
            if message is None:
                break
    except:
        pass
    finally:
        # 移除客户端
        if task_id in video_tasks and 'clients' in video_tasks[task_id]:
            video_tasks[task_id]['clients'].discard(ws)










# ==================== 模型训练管理接口 ====================
# training_tasks / training_stop_flags 已抽至 core.state

@app.route("/api/models", methods=["GET"])
@require_auth
def get_models():
    """获取所有模型列表（包括系统模型和自定义模型）"""
    from datetime import datetime

    # 系统模型 - 直接从内存获取，无需数据库查询
    system_models = []
    for name in ['yolov8n', 'yolov8s', 'yolov8m', 'yolo11n', 'yolo11s', 'yolo11m', 'yolo26']:
        if name in models:
            system_models.append({
                'id': name,
                'name': name.upper(),
                'model_key': name,
                'type': 'system',
                'status': 'published',
                'description': f'系统预置 {name.upper()} 模型'
            })

    # 自定义模型 - 使用分页和字段选择查询
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status_filter = request.args.get('status', None)
    
    # 限制每页最大数量
    per_page = min(per_page, 100)
    
    # 构建查询
    query = CustomModel.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    # 分页查询
    pagination = query.order_by(CustomModel.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    custom_list = []
    for model in pagination.items:
        data = model.to_dict()
        data['type'] = 'custom'
        # 添加是否在内存中的标记
        data['loaded_in_memory'] = model.model_key in models
        custom_list.append(data)
    
    return jsonify({
        'system_models': system_models,
        'custom_models': custom_list,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


@app.route("/api/models/published", methods=["GET"])
@require_auth
def get_published_models():
    """获取已发布的模型列表（用于检测选择）- 只返回管理员发布的自定义模型"""
    result = []

    # 只返回已发布的自定义模型（管理员发布的）
    # 基础模型（yolov8, yolo11, yolo26）仅供训练使用，不显示给医生
    custom_models = CustomModel.query.filter_by(status='published').all()
    for model in custom_models:
        result.append({
            'key': model.model_key,
            'name': model.name,
            'type': 'custom'
        })

    return jsonify({'models': result})


@app.route("/api/models/train", methods=["POST"])
@require_role('admin', 'doctor')
def train_model():
    """上传数据集并开始训练模型"""
    try:
        model_name = request.form.get('name', '').strip()
        description = request.form.get('description', '')
        base_model = request.form.get('base_model', 'yolov8s')
        epochs = int(request.form.get('epochs', 100))
        batch_size = int(request.form.get('batch_size', 16))
        img_size = int(request.form.get('img_size', 640))
        dataset_source = request.form.get('dataset_source', 'upload')
        use_best_hyperparams = request.form.get('use_best_hyperparams', 'false').lower() == 'true'
        
        logger.debug(f"[DEBUG] 训练请求参数: name={model_name}, base_model={base_model}, dataset_source={dataset_source}")
        logger.debug(f"[DEBUG] Form data: {dict(request.form)}")
        logger.debug(f"[DEBUG] Files: {list(request.files.keys())}")
    except Exception as e:
        return jsonify({"error": f"参数解析错误: {str(e)}"}), 400

    username = request.headers.get('X-Username') or 'anonymous'

    if not model_name:
        return jsonify({"error": "模型名称不能为空"}), 400

    # 根据数据源获取数据集
    dataset_dir = None
    if dataset_source == 'existing':
        # 使用已有数据集
        dataset_id = request.form.get('dataset_id')
        if not dataset_id:
            return jsonify({"error": "未选择数据集"}), 400

        from database import Dataset
        dataset = db.session.get(Dataset, int(dataset_id))
        if not dataset:
            return jsonify({"error": "数据集不存在"}), 404

        # 检查权限
        user = get_current_user()
        if user.role != 'admin' and dataset.uploader != user.username:
            return jsonify({"error": "无权使用此数据集"}), 403

        dataset_dir = dataset.dataset_path
        if not os.path.exists(dataset_dir):
            return jsonify({"error": "数据集目录不存在"}), 404
    else:
        # 上传新数据集
        if 'dataset' not in request.files:
            return jsonify({"error": "没有上传数据集文件"}), 400

        dataset_file = request.files['dataset']
        if dataset_file.filename == '':
            return jsonify({"error": "数据集文件名为空"}), 400

        # 生成模型标识
        timestamp = int(time.time())
        model_key = f"custom_{base_model}_{timestamp}"

        # 保存数据集
        dataset_dir = os.path.join(UPLOADS, 'datasets', model_key)
        os.makedirs(dataset_dir, exist_ok=True)

        dataset_path = os.path.join(dataset_dir, dataset_file.filename)
        dataset_file.save(dataset_path)

        # 解压数据集
        try:
            import zipfile
            with zipfile.ZipFile(dataset_path, 'r') as zip_ref:
                zip_ref.extractall(dataset_dir)
            os.remove(dataset_path)  # 删除zip文件
        except Exception as e:
            return jsonify({"error": f"解压数据集失败: {str(e)}"}), 400

    # 检查基础模型是否可用
    supported_base_models = ['yolov8n', 'yolov8s', 'yolov8m', 'yolo11n', 'yolo11s', 'yolo11m', 'yolo26n']
    is_continued_training = base_model not in supported_base_models
    base_model_info = None

    if is_continued_training:
        # 检查是否是已存在的自定义模型
        base_model_info = CustomModel.query.filter_by(model_key=base_model).first()
        if not base_model_info:
            return jsonify({"error": f"基础模型 {base_model} 不存在"}), 400
        if base_model_info.status not in ['trained', 'published']:
            return jsonify({"error": "基础模型尚未训练完成，无法用于续训"}), 400
        actual_base_model = base_model_info.base_model
    else:
        # 检查是否在已加载的models中，如果没有则尝试自动下载加载
        if base_model not in models:
            try:
                logger.info(f"基础模型 {base_model} 未加载，尝试自动下载...")
                from ultralytics import YOLO
                import shutil
                
                # 先尝试从 models 目录加载
                model_path = os.path.join(MODELS_DIR, f"{base_model}.pt")
                
                if os.path.exists(model_path):
                    # 如果 models 目录已存在，直接加载
                    models[base_model] = YOLO(model_path)
                    logger.info(f"✓ 从 models 目录加载模型 {base_model}")
                else:
                    # 下载到当前目录，然后移动到 models 目录
                    model_file = f"{base_model}.pt"
                    temp_model = YOLO(model_file)
                    
                    # 获取下载后的文件路径（通常在当前目录或 ~/.ultralytics/models/）
                    downloaded_path = os.path.join(os.getcwd(), model_file)
                    if not os.path.exists(downloaded_path):
                        # 尝试从 ultralytics 默认缓存目录查找
                        ultralytics_cache = os.path.expanduser(f"~/.ultralytics/models/{model_file}")
                        if os.path.exists(ultralytics_cache):
                            downloaded_path = ultralytics_cache
                    
                    # 移动到 models 目录
                    if os.path.exists(downloaded_path):
                        shutil.move(downloaded_path, model_path)
                        logger.info(f"✓ 模型已移动到 {model_path}")
                    
                    # 重新从 models 目录加载
                    models[base_model] = YOLO(model_path)
                    logger.info(f"✓ 成功下载并加载模型 {base_model}")
            except Exception as e:
                return jsonify({"error": f"基础模型 {base_model} 加载失败: {str(e)}"}), 400
        actual_base_model = base_model

    # 生成模型标识
    timestamp = int(time.time())
    model_key = f"custom_{actual_base_model}_{timestamp}"

    # 构建模型描述，包含基础模型和数据集信息
    enhanced_description = description
    
    # 添加基础模型信息
    model_display_names = {
        'yolov8n': 'YOLOv8n',
        'yolov8s': 'YOLOv8s',
        'yolov8m': 'YOLOv8m',
        'yolo11n': 'YOLO11n',
        'yolo11s': 'YOLO11s',
        'yolo11m': 'YOLO11m',
        'yolo26n': 'YOLO26n'
    }
    
    # 构建基础模型描述
    if is_continued_training and base_model_info:
        # 续训情况：基于已有自定义模型
        base_model_display = f"{base_model_info.name} (基于{model_display_names.get(base_model_info.base_model, base_model_info.base_model)})"
    else:
        # 标准训练：基于预训练模型
        base_model_display = model_display_names.get(actual_base_model, actual_base_model)
    
    # 添加数据集信息
    dataset_name = "上传的数据集"
    if dataset_source == 'existing' and 'dataset' in locals():
        dataset_name = dataset.name
    
    # 构建增强描述
    model_info = f"\n\n基于 {base_model_display} 模型使用 {dataset_name} 训练集训练"
    if enhanced_description:
        enhanced_description += model_info
    else:
        enhanced_description = f"基于 {base_model_display} 模型使用 {dataset_name} 训练集训练"

    # 创建模型记录
    model_path = os.path.join(MODELS_DIR, f'{model_key}.pt')

    custom_model = CustomModel(
        name=model_name,
        model_key=model_key,
        description=enhanced_description,
        base_model=actual_base_model,
        model_path=model_path,
        dataset_path=dataset_dir,
        status='training',
        epochs=epochs,
        batch_size=batch_size,
        img_size=img_size,
        created_by=username
    )
    db.session.add(custom_model)
    db.session.commit()

    # 创建训练任务
    # 设置日志文件路径
    log_file_path = os.path.join(UPLOADS, 'training_logs', f'task_{custom_model.model_key}.log')
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    
    task = TrainingTask(
        task_name=f"训练 {model_name}",
        model_id=custom_model.id,
        status='running',
        total_epochs=epochs,
        created_by=username,
        started_at=datetime.utcnow(),
        log_file=log_file_path
    )
    db.session.add(task)
    db.session.commit()

    # 启动异步训练线程
    if is_continued_training:
        base_model_path = base_model_info.model_path
    else:
        base_model_path = BASE_MODEL_MAP.get(base_model, base_model)

    thread = threading.Thread(
        target=train_model_task,
        args=(task.id, custom_model.id, base_model_path, dataset_dir, epochs, batch_size, img_size,
              is_continued_training, use_best_hyperparams)
    )
    thread.daemon = True
    thread.start()

    log_operation(f"开始训练模型:{model_name},基础模型:{base_model},创建者:{username}")

    return jsonify({
        "success": True,
        "model_id": custom_model.id,
        "task_id": task.id,
        "message": "模型训练任务已启动"
    })


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


def train_model_task(task_id, model_id, base_model_path, dataset_dir, epochs, batch_size, img_size,
                     is_continued_training=False, use_best_hyperparams=False):
    """异步训练模型任务"""
    with app.app_context():
        task = db.session.get(TrainingTask, task_id)
        custom_model = db.session.get(CustomModel, model_id)
        
        if not task or not custom_model:
            return
        
        # 设置日志记录
        logger = None
        if task.log_file:
            os.makedirs(os.path.dirname(task.log_file), exist_ok=True)
            logger = Logger(task.log_file)
            sys.stdout = logger
        
        try:
            from ultralytics import YOLO
            import time
            
            # 加载基础模型
            if is_continued_training:
                if os.path.exists(base_model_path):
                    model = YOLO(base_model_path)
                    print(f"从已有模型继续训练: {base_model_path}")
                else:
                    task.status = 'failed'
                    task.error_message = f'基础模型文件不存在: {base_model_path}'
                    custom_model.status = 'failed'
                    db.session.commit()
                    return
            else:
                # 标准模型训练
                base_model_file = os.path.join(MODELS_DIR, f'{base_model_path}.pt')
                print(f"标准模型训练，加载: {base_model_file}")
                if os.path.exists(base_model_file):
                    model = YOLO(base_model_file)
                    print(f"✓ 成功加载本地模型: {base_model_file}")
                else:
                    print(f"⚠ 本地模型不存在，尝试从Ultralytics下载: {base_model_path}")
                    model = YOLO(base_model_path)

            # 查找数据集配置文件
            data_yaml = None
            for root, dirs, files in os.walk(dataset_dir):
                for file in files:
                    if file == 'data.yaml' or file == 'dataset.yaml':
                        data_yaml = os.path.join(root, file)
                        break
                if data_yaml:
                    break

            if not data_yaml:
                task.status = 'failed'
                task.error_message = '未找到数据集配置文件 (data.yaml)'
                custom_model.status = 'failed'
                db.session.commit()
                return

            # 开始训练
            task.status = 'running'
            task.progress = 0
            task.current_epoch = 0
            db.session.commit()
            
            print(f"\n{'='*80}")
            print(f"开始训练模型: {custom_model.name}")
            print(f"任务ID: {task.id}")
            print(f"基础模型: {base_model_path}")
            print(f"数据集: {data_yaml}")
            print(f"训练配置: epochs={epochs}, batch={batch_size}, img_size={img_size}")
            print(f"使用最佳超参数: {use_best_hyperparams}")
            print(f"{'='*80}\n")

            # 1. 动态准备核心参数
            train_args = {
                'data': data_yaml,
                'epochs': epochs,
                'batch': batch_size,
                'imgsz': img_size,
                'project': os.path.join(UPLOADS, 'training_runs'),
                'name': custom_model.model_key,
                'exist_ok': True,
                'pretrained': True,
                'amp': True,
                'device': 0 if torch.cuda.is_available() else 'cpu',
                'verbose': False,
                'plots': True,
                'save': True,
                'workers': 4, 
                'optimizer':'SGD'      
            }

            # 2. 优化超参数加载逻辑 (使用 update 批量覆盖)
            if use_best_hyperparams:
                best_hp_path = os.path.join(BASE_DIR, 'runs', 'best_hyperparams.json')
                if os.path.exists(best_hp_path):
                    try:
                        with open(best_hp_path, 'r') as f:
                            best_hp = json.load(f)
                        train_args.update(best_hp)  # 批量覆盖比 if 判断更简洁
                        print(f"✓ 成功合并最佳超参数")
                    except Exception as e:
                        print(f"⚠️ 超参数解析失败: {e}")
            
            # 创建训练回调类来更新进度和检查停止标志 - 优化版本
            class TrainingCallback:
                def __init__(self, task_id, total_epochs, app_instance):
                    self.task_id = task_id
                    self.total_epochs = total_epochs
                    self.last_update = 0
                    self.app = app_instance
                    self.update_interval = 5  # 每5秒更新一次数据库
                    self.epochs_since_update = 0
                    self.epoch_update_interval = max(1, total_epochs // 20)  # 每5%更新一次

                def on_train_epoch_end(self, trainer):
                    try:
                        if training_stop_flags.get(self.task_id, False):
                            print(f"检测到停止标志，正在终止训练任务 {self.task_id}...")
                            trainer.stop = True
                            return

                        current_epoch = trainer.epoch + 1
                        progress = (current_epoch / self.total_epochs) * 100
                        self.epochs_since_update += 1

                        current_time = time.time()
                        should_update_db = (
                            current_time - self.last_update >= self.update_interval or
                            self.epochs_since_update >= self.epoch_update_interval or
                            current_epoch == self.total_epochs or
                            current_epoch == 1
                        )

                        if should_update_db:
                            self.last_update = current_time
                            self.epochs_since_update = 0

                            loss = trainer.loss if hasattr(trainer, 'loss') else None

                            # 使用新会话避免会话过期问题
                            with app.app_context():
                                task = db.session.get(TrainingTask, self.task_id)
                                if task and task.status == 'running':
                                    task.current_epoch = current_epoch
                                    task.progress = progress
                                    if loss is not None:
                                        if isinstance(loss, (int, float)):
                                            task.loss = float(loss)
                                        elif hasattr(loss, 'item'):
                                            task.loss = float(loss.item())
                                    db.session.commit()

                        # 每轮都打印日志（不操作数据库）
                        if current_epoch % max(1, self.total_epochs // 10) == 0 or current_epoch <= 3:
                            loss_val = trainer.loss.item() if hasattr(trainer.loss, 'item') else trainer.loss if trainer.loss is not None else 'N/A'
                            print(f"[Epoch {current_epoch}/{self.total_epochs}] 进度: {progress:.1f}%, 损失: {loss_val if isinstance(loss_val, str) else f'{loss_val:.4f}'}")

                    except Exception as e:
                        print(f"更新训练进度失败: {e}")
            
            callback = TrainingCallback(task_id, epochs, app)
            model.add_callback('on_train_epoch_end', callback.on_train_epoch_end)
            
            print(f"✓ 训练参数: {train_args}")
            results = model.train(**train_args)
            
            # 重新获取对象（避免会话过期）
            task = db.session.get(TrainingTask, task_id)
            custom_model = db.session.get(CustomModel, model_id)
            
            # 获取最佳模型路径
            best_model_path = os.path.join(
                UPLOADS, 'training_runs', custom_model.model_key, 'weights', 'best.pt'
            )
            
            if os.path.exists(best_model_path):
                # 复制到模型目录
                import shutil
                shutil.copy(best_model_path, custom_model.model_path)
                
                # 更新模型状态
                custom_model.status = 'trained'
                
                # 3. 增强指标提取逻辑 (增加对不同版本返回值的兼容)
                def extract_metrics(results, model_obj):
                    # 优先尝试 results.results_dict (v8/v11 常用)
                    rd = getattr(results, 'results_dict', {})
                    # 定义映射关系：模型字段 -> 可能的键名列表
                    mapping = {
                        'map50': ['metrics/mAP50(B)', 'mAP50'],
                        'map50_95': ['metrics/mAP50-95(B)', 'metrics/mAP50:0.95', 'mAP50-95'],
                        'precision': ['metrics/precision(B)', 'precision'],
                        'recall': ['metrics/recall(B)', 'recall']
                    }
                    for field, keys in mapping.items():
                        val = 0
                        for k in keys:
                            if k in rd:
                                val = rd[k]
                                break
                        # 如果 dict 没找到，尝试从属性对象获取 (results.box)
                        if val == 0 and hasattr(results, 'box'):
                            box = results.box
                            attr_map = {'map50': 'map50', 'map50_95': 'map', 'precision': 'mp', 'recall': 'mr'}
                            val = getattr(box, attr_map[field], 0)
                        setattr(model_obj, field, float(val))
                    # 计算 F1 和 Accuracy
                    if model_obj.precision + model_obj.recall > 0:
                        model_obj.f1_score = 2 * (model_obj.precision * model_obj.recall) / (model_obj.precision + model_obj.recall)
                    else:
                        model_obj.f1_score = 0
                    # 骨折检测通常更看重 mAP50 和 Recall (防止漏检)
                    model_obj.accuracy = (model_obj.map50 * 0.4 + model_obj.map50_95 * 0.3 + model_obj.f1_score * 0.3)

                extract_metrics(results, custom_model)
                print(f"✓ 训练指标 - mAP50: {custom_model.map50:.4f}, mAP50-95: {custom_model.map50_95:.4f}")
                print(f"✓ 检测指标 - Precision: {custom_model.precision:.4f}, Recall: {custom_model.recall:.4f}, F1: {custom_model.f1_score:.4f}")
                print(f"✓ 综合评分: {custom_model.accuracy:.4f}")

                # 加载新模型到内存
                models[custom_model.model_key] = YOLO(custom_model.model_path)
            else:
                custom_model.status = 'failed'
                task.error_message = '训练完成但未找到模型文件'
            
            # 更新任务状态
            task.status = 'completed'
            task.progress = 100.0
            task.current_epoch = epochs
            task.completed_at = datetime.utcnow()
            db.session.commit()
            
            print(f"\n{'='*80}")
            print(f"✅ 模型训练完成!")
            print(f"模型名称: {custom_model.name}")
            print(f"训练轮数: {epochs}")
            print(f"性能指标:")
            print(f"  mAP@0.5: {custom_model.map50:.4f}")
            print(f"  mAP@0.5:0.95: {custom_model.map50_95:.4f}")
            print(f"  精确率: {custom_model.precision:.4f}")
            print(f"  召回率: {custom_model.recall:.4f}")
            print(f"  F1-Score: {custom_model.f1_score:.4f}")
            print(f"  综合评分: {custom_model.accuracy:.4f}")
            print(f"模型保存路径: {custom_model.model_path}")
            print(f"{'='*80}\n")
            
            log_operation(f"模型训练完成:{custom_model.name},mAP50:{custom_model.map50}")
            
        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ 模型训练失败!")
            print(f"错误信息: {e}")
            print(f"详细错误:")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")
            
            task = db.session.get(TrainingTask, task_id)
            custom_model = db.session.get(CustomModel, model_id)
            
            if task:
                task.status = 'failed'
                task.error_message = str(e)
            
            if custom_model:
                custom_model.status = 'failed'
            
            db.session.commit()
        
        finally:
            # 恢复标准输出并关闭日志文件
            if logger:
                sys.stdout = logger.terminal
                logger.close()


@app.route("/api/training/tasks/<int:task_id>/progress", methods=["GET"])
@require_auth
def get_training_progress(task_id):
    """获取训练任务实时进度"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    # 确保返回的数据格式正确
    return jsonify({
        "task_id": task.id,
        "status": task.status,
        "progress": task.progress or 0,
        "current_epoch": task.current_epoch or 0,
        "total_epochs": task.total_epochs or 0,
        "loss": task.loss,
        "val_loss": task.val_loss
    })


@app.route("/api/models/<int:model_id>/publish", methods=["POST"])
@require_role('admin')
def publish_model(model_id):
    """发布模型（管理员）"""
    model = db.session.get(CustomModel, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404
    
    if model.status != 'trained':
        return jsonify({"error": "模型尚未训练完成"}), 400
    
    model.status = 'published'
    model.published_at = datetime.utcnow()
    db.session.commit()
    
    log_operation(f"发布模型:{model.name}")
    
    return jsonify({
        "success": True,
        "message": "模型已发布"
    })


@app.route("/api/models/<int:model_id>/disable", methods=["POST"])
@require_role('admin')
def disable_model(model_id):
    """禁用模型（管理员）"""
    model = db.session.get(CustomModel, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404
    
    if model.status != 'published':
        return jsonify({"error": "只能禁用已发布的模型"}), 400
    
    model.status = 'disabled'
    model.published_at = None  # 清除发布时间
    db.session.commit()
    
    # 从内存中移除模型
    if model.model_key in models:
        del models[model.model_key]
        logger.info(f"模型 {model.model_key} 已从内存中移除")
    
    log_operation(f"禁用模型:{model.name}")
    
    return jsonify({
        "success": True,
        "message": "模型已禁用"
    })


@app.route("/api/models/<int:model_id>/enable", methods=["POST"])
@require_role('admin')
def enable_model(model_id):
    """启用/发布模型（管理员）"""
    model = db.session.get(CustomModel, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404
    
    if model.status not in ['trained', 'disabled']:
        return jsonify({"error": "只能启用训练完成或已禁用的模型"}), 400
    
    # 检查模型文件是否存在
    if not os.path.exists(model.model_path):
        return jsonify({"error": "模型文件不存在，无法启用"}), 400
    
    model.status = 'published'
    model.published_at = datetime.utcnow()
    db.session.commit()
    
    # 加载模型到内存
    try:
        if model.model_key not in models:
            models[model.model_key] = YOLO(model.model_path)
            logger.info(f"模型 {model.model_key} 已加载到内存")
    except Exception as e:
        logger.error(f"加载模型到内存失败: {e}")
        # 不影响启用操作，下次预测时会尝试加载
    
    log_operation(f"启用模型:{model.name}")
    
    return jsonify({
        "success": True,
        "message": "模型已启用"
    })


@app.route("/api/models/<int:model_id>", methods=["DELETE"])
@require_role('admin')
def delete_model(model_id):
    """删除模型（管理员）- 彻底清理所有相关文件"""
    model = db.session.get(CustomModel, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404
    
    model_name = model.name
    deleted_items = []
    errors = []
    
    # 1. 从内存中移除
    if model.model_key in models:
        del models[model.model_key]
        deleted_items.append("内存中的模型")
    
    # 2. 删除模型文件 (.pt)
    if model.model_path:
        if os.path.exists(model.model_path):
            try:
                os.remove(model.model_path)
                deleted_items.append(f"模型文件: {os.path.basename(model.model_path)}")
            except Exception as e:
                errors.append(f"删除模型文件失败: {e}")
        else:
            deleted_items.append(f"模型文件不存在，跳过: {os.path.basename(model.model_path)}")
    else:
        errors.append("模型路径为空，无法删除模型文件")
    
    # 3. 删除数据集目录（仅删除训练时上传的数据集，不删除数据集管理中的数据集）
    # 训练时上传的数据集路径包含 'custom_' 前缀，如：uploads/datasets/custom_yolov8_123456/
    # 数据集管理上传的数据集路径为：uploads/datasets/dataset_123456/
    if model.dataset_path and os.path.exists(model.dataset_path):
        dataset_dir_name = os.path.basename(model.dataset_path)
        if dataset_dir_name.startswith('custom_'):
            # 这是训练时上传的数据集，可以安全删除
            try:
                import shutil
                shutil.rmtree(model.dataset_path)
                deleted_items.append(f"训练数据集: {dataset_dir_name}")
            except Exception as e:
                errors.append(f"删除训练数据集失败: {e}")
        else:
            # 这是数据集管理中的数据集，不删除
            deleted_items.append(f"保留数据集: {dataset_dir_name}（来自数据集管理）")
    
    # 4. 删除训练运行目录 (uploads/training_runs/model_key)
    train_run_dir = os.path.join(UPLOADS, 'training_runs', model.model_key)
    if os.path.exists(train_run_dir):
        try:
            shutil.rmtree(train_run_dir)
            deleted_items.append(f"训练记录: {model.model_key}")
        except Exception as e:
            errors.append(f"删除训练记录失败: {e}")
    
    # 5. 删除训练日志文件 (uploads/training_logs/task_{model_key}.log)
    log_file_path = os.path.join(UPLOADS, 'training_logs', f'task_{model.model_key}.log')
    if os.path.exists(log_file_path):
        try:
            os.remove(log_file_path)
            deleted_items.append(f"训练日志: task_{model.model_key}.log")
        except Exception as e:
            errors.append(f"删除训练日志失败: {e}")
    
    # 6. 删除关联的训练任务记录
    try:
        training_tasks = TrainingTask.query.filter_by(model_id=model_id).all()
        for task in training_tasks:
            db.session.delete(task)
        if training_tasks:
            deleted_items.append(f"训练任务记录: {len(training_tasks)}条")
    except Exception as e:
        errors.append(f"删除训练任务记录失败: {e}")
    
    # 6. 删除数据库记录
    db.session.delete(model)
    db.session.commit()
    deleted_items.append("数据库记录")
    
    # 记录操作
    log_operation(f"删除模型:{model_name}, 清理项目: {len(deleted_items)}")
    
    result = {
        "success": True,
        "message": "模型已删除",
        "deleted_items": deleted_items
    }
    if errors:
        result["warnings"] = errors
    
    return jsonify(result)


@app.route("/api/models/cleanup-orphaned", methods=["POST"])
@require_role('admin')
def cleanup_orphaned_training_runs():
    """清理孤立的训练记录目录（模型已删除但训练记录仍存在）"""
    training_runs_dir = os.path.join(UPLOADS, 'training_runs')
    if not os.path.exists(training_runs_dir):
        return jsonify({"success": True, "message": "训练记录目录不存在", "cleaned": []})
    
    # 获取所有有效的 model_key
    valid_model_keys = {m.model_key for m in CustomModel.query.all()}
    
    cleaned = []
    errors = []
    
    try:
        for item in os.listdir(training_runs_dir):
            item_path = os.path.join(training_runs_dir, item)
            # 检查是否是目录且符合训练记录命名格式
            if os.path.isdir(item_path) and item.startswith('custom_'):
                if item not in valid_model_keys:
                    # 这是一个孤立的训练记录目录
                    try:
                        shutil.rmtree(item_path)
                        cleaned.append(item)
                    except Exception as e:
                        errors.append(f"删除 {item} 失败: {e}")
    except Exception as e:
        return jsonify({"success": False, "error": f"清理失败: {e}"}), 500
    
    result = {
        "success": True,
        "message": f"清理完成，删除了 {len(cleaned)} 个孤立训练记录目录",
        "cleaned": cleaned
    }
    if errors:
        result["errors"] = errors
    
    # 记录操作
    log_operation(f"清理孤立训练记录: {len(cleaned)}个")
    
    return jsonify(result)


@app.route("/api/training/tasks", methods=["GET"])
@require_auth
def get_training_tasks():
    """获取训练任务列表"""
    tasks = TrainingTask.query.order_by(TrainingTask.created_at.desc()).all()
    return jsonify({
        'tasks': [task.to_dict() for task in tasks]
    })


@app.route("/api/training/tasks/<int:task_id>", methods=["GET"])
@require_auth
def get_training_task(task_id):
    """获取训练任务详情"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify(task.to_dict())


@app.route("/api/training/tasks/<int:task_id>/logs", methods=["GET"])
@require_auth
def get_training_logs(task_id):
    """获取训练日志"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"logs": ""})
    
    # 首先尝试从log_file读取
    if task.log_file and os.path.exists(task.log_file):
        try:
            with open(task.log_file, 'r', encoding='utf-8') as f:
                logs = f.read()
            return jsonify({"logs": logs})
        except Exception as e:
            return jsonify({"logs": f"读取日志失败: {str(e)}"})
    
    # 如果没有log_file或文件不存在，尝试从训练运行目录读取
    if task.model:
        train_run_dir = os.path.join(UPLOADS, 'training_runs', task.model.model_key)
        if os.path.exists(train_run_dir):
            # 尝试读取训练目录中的日志文件
            possible_logs = [
                os.path.join(train_run_dir, 'training.log'),
                os.path.join(train_run_dir, 'train.log'),
                os.path.join(train_run_dir, 'results.csv'),
            ]
            for log_path in possible_logs:
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r', encoding='utf-8') as f:
                            logs = f.read()
                        return jsonify({"logs": logs})
                    except:
                        continue
    
    return jsonify({"logs": "暂无日志"})


@app.route("/api/training/tasks/<int:task_id>/stop", methods=["POST"])
@require_auth
def stop_training_task(task_id):
    """终止训练任务"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    # 检查任务状态
    if task.status != 'running':
        return jsonify({"error": f"任务当前状态为 {task.status}，无法终止"}), 400

    # 设置停止标志
    training_stop_flags[task_id] = True

    # 更新任务状态
    task.status = 'stopped'
    task.error_message = '用户手动终止训练'
    db.session.commit()

    # 更新模型状态
    custom_model = db.session.get(CustomModel, task.model_id)
    if custom_model and custom_model.status == 'training':
        custom_model.status = 'failed'
        db.session.commit()

    log_operation(f"用户手动终止训练任务:{task_id},模型:{custom_model.name if custom_model else 'unknown'}")

    return jsonify({
        "success": True,
        "message": "训练任务已终止"
    })


# ==================== 患者管理相关 ====================

@app.route('/api/patients', methods=['GET', 'POST'])
@require_auth
def patients():
    """患者管理"""
    if request.method == 'GET':
        # 获取患者列表
        patients = Patient.query.all()
        return jsonify({"success": True, "data": [p.to_dict() for p in patients]})
    
    elif request.method == 'POST':
        # 添加新患者
        data = request.get_json() or {}
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


@app.route('/api/patients/<int:patient_id>', methods=['GET', 'PUT', 'DELETE'])
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
        data = request.get_json() or {}
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

@app.route('/api/examinations', methods=['GET', 'POST'])
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
        data = request.get_json() or {}
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


@app.route('/api/examinations/<int:exam_id>', methods=['GET', 'PUT', 'DELETE'])
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
        data = request.get_json() or {}
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

@app.route("/api/doctor/patients", methods=["GET"])
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


@app.route("/api/doctor/reports", methods=["POST"])
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


@app.route("/api/doctor/reports", methods=["GET"])
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


@app.route("/api/doctor/reports/<int:report_id>", methods=["PUT"])
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

@app.route("/api/doctor/dashboard", methods=["GET"])
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




@app.route("/api/doctor/patients", methods=["POST"])
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


@app.route("/api/doctor/patients/<int:patient_id>/archive", methods=["PUT"])
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


@app.route("/api/doctor/all-patients", methods=["GET"])
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


@app.route("/api/doctor/medical-records", methods=["POST"])
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


@app.route("/api/doctor/medical-records/<int:record_id>", methods=["PUT"])
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


# -------------------- 管理员 API --------------------

@app.route("/api/admin/dashboard", methods=["GET"])
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


@app.route("/api/admin/approve-doctor/<int:registration_id>", methods=["POST"])
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


# -------------------- 编辑个人信息 API --------------------

@app.route("/api/profile/update", methods=["PUT"])
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


@app.route("/api/admin/statistics", methods=["GET"])
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


@app.route("/api/admin/statistics/detailed", methods=["GET"])
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


@app.route("/api/admin/generate-test-data", methods=["POST"])
@require_role('admin')
def generate_test_data():
    """生成测试数据"""
    from datetime import datetime, timedelta
    import random
    
    data = request.get_json() or {}
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


@app.route("/api/admin/user/<int:user_id>", methods=["PUT"])
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


@app.route("/api/admin/reset-password/<int:user_id>", methods=["POST"])
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

@app.route("/api/admin/announcements", methods=["GET"])
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


@app.route("/api/admin/announcements", methods=["POST"])
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


@app.route("/api/admin/announcements/<int:announcement_id>", methods=["PUT"])
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


@app.route("/api/admin/announcements/<int:announcement_id>", methods=["DELETE"])
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
























if __name__ == "__main__":
    # debug 由 FLASK_ENV 决定：development=True（默认，同改造前行为） / production=False
    app.run(debug=app.config.get('DEBUG', True))
