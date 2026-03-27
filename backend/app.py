from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from ultralytics import YOLO
import os, time, cv2, json, glob, random, io
import requests
from datetime import datetime
from pathlib import Path
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageDraw, ImageFont
from database import db, User, DetectionHistory, SystemSettings, OperationLog, FileRecord, CustomModel, TrainingTask, init_db, migrate_from_json

# 导入自定义YOLO模块（CBAM注意力机制）
try:
    from yolo_modules.cbam import CBAM, C2f_CBAM, C3_CBAM
    from yolo_modules.cbam_utils import create_yolo_with_cbam

    CBAM_AVAILABLE = True
    print("✓ CBAM注意力机制模块已加载")
except ImportError as e:
    CBAM_AVAILABLE = False
    print(f"⚠ CBAM模块加载失败: {e}")

app = Flask(__name__)

# 配置session
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'  # 生产环境要修改
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1小时

# 全局CORS配置 - 允许所有来源
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Username"],
        "supports_credentials": True  # 需要启用，因为使用session
    }
})

from flask_migrate import Migrate
migrate = Migrate(app, db)      # 注册 migrate 扩展

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bone_detection.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
init_db(app)

# 在应用启动时迁移 JSON 数据（如果存在）
with app.app_context():
    migrate_from_json(app)

# 全局模型候选（键 -> 权重文件路径）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE_DIR, "uploads")
RESULTS = os.path.join(BASE_DIR, "results")
MODELS_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
# 模型文件映射: 模型键 -> 模型文件路径
# 注意：CBAM模型(yolov8-cbam/yolo11-cbam)不需要预训练文件，训练时会动态创建
MODEL_CANDIDATES = {
    "yolov8": os.path.join(BASE_DIR, "models", "yolov8.pt"),
    "yolo12": os.path.join(BASE_DIR, "models", "yolo12n.pt"),
    "yolo11": os.path.join(BASE_DIR, "models", "yolo11n.pt"),
}

# 基础模型到实际模型文件名的映射（用于训练时加载）
# CBAM模型映射到对应的基础模型文件
BASE_MODEL_MAP = {
    "yolov8": "yolov8",
    "yolo11": "yolo11n",
    "yolo12": "yolo12n",
    "yolov8-cbam": "yolov8",  # CBAM版本使用yolov8基础模型
    "yolo11-cbam": "yolo11n",  # CBAM版本使用yolo11n基础模型
}


# 加载模型（仅加载存在的权重文件，避免启动失败）
def load_models():
    loaded = {}
    for name, path in MODEL_CANDIDATES.items():
        if os.path.exists(path):
            try:
                loaded[name] = YOLO(path)
                print(f"Loaded model {name} from {path}")
            except Exception as e:
                print(f"Failed to load model {name} from {path}: {e}")
        else:
            print(f"Model file for {name} not found at {path}, skipping")
    return loaded


models = load_models()


# ==================== 权限验证装饰器 ====================

def get_current_user():
    """从请求头获取当前用户"""
    username = request.headers.get('X-Username')
    if not username:
        return None
    return User.query.filter_by(username=username).first()

def require_auth(f):
    """要求登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "未登录或登录已过期"}), 401
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """要求管理员权限的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "未登录或登录已过期"}), 401
        if user.role != 'admin':
            return jsonify({"error": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated_function


# ==================== 用户认证接口 ====================

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user:
        log_operation(f"登录失败:用户不存在-{username}", success=False, error_msg="用户不存在")
        return jsonify({"error": "用户不存在"}), 401
    
    # 检查密码（兼容已哈希和未哈希的密码）
    # werkzeug的密码哈希通常以 pbkdf2:sha256: 或 $2b$ 开头
    is_hashed = (
        user.password.startswith('$2b$') or 
        user.password.startswith('$2a$') or 
        user.password.startswith('pbkdf2:') or
        user.password.startswith('scrypt:') or
        user.password.startswith('argon2:')
    )
    
    if is_hashed:
        # 已哈希的密码
        if not check_password_hash(user.password, password):
            print(f"登录失败: 用户 {username} 密码验证失败（已哈希密码）")
            log_operation(f"登录失败:密码错误-{username}", success=False, error_msg="密码错误")
            return jsonify({"error": "密码错误"}), 401
    else:
        # 未哈希的密码（兼容旧数据）
        if user.password != password:
            print(f"登录失败: 用户 {username} 密码验证失败（未哈希密码）")
            log_operation(f"登录失败:密码错误-{username}", success=False, error_msg="密码错误")
            return jsonify({"error": "密码错误"}), 401
    
    print(f"登录成功: 用户 {username}, 角色 {user.role}")
    log_operation(f"用户登录:{username}")
    return jsonify({
        "success": True,
        "username": user.username,
        "role": user.role
    })


@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    password_confirm = data.get("password_confirm", "").strip()
    captcha = data.get("captcha", "").strip().upper()
    
    # 验证输入
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    
    if len(username) < 3:
        return jsonify({"error": "用户名长度至少3个字符"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "密码长度至少6个字符"}), 400
    
    if password != password_confirm:
        return jsonify({"error": "两次输入的密码不一致"}), 400
    
    # 验证验证码
    if not captcha:
        return jsonify({"error": "验证码不能为空"}), 400
    
    # 从session获取验证码
    session_captcha = session.get('captcha', '').upper()
    
    if not session_captcha:
        return jsonify({"error": "验证码已过期"}), 400
    
    if captcha != session_captcha:
        return jsonify({"error": "验证码错误"}), 400
    
    # 检查用户是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 409
    
    # 创建新用户
    new_user = User(
        username=username,
        password=generate_password_hash(password),
        role="user"
    )
    db.session.add(new_user)
    db.session.commit()
    
    # 清除session中的验证码
    session.pop('captcha', None)
    
    log_operation(f"用户注册:{username}")
    
    return jsonify({
        "success": True,
        "message": "注册成功",
        "username": username
    }), 201


# ==================== 检测接口 ====================

@app.route("/api/predict", methods=["POST"])
@require_auth
def predict():
    user = get_current_user()
    file = request.files["file"]
    model_name = request.form.get("model", "yolov8")
    username = user.username  # 使用当前登录用户

    filename = f"{int(time.time())}_{file.filename}"
    img_path = os.path.join(UPLOADS, filename)
    file.save(img_path)

    # 如果模型尚未加载，尝试按需加载（避免必须重启服务）
    if model_name not in models:
        # 首先检查是否是系统模型
        candidate_path = MODEL_CANDIDATES.get(model_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                models[model_name] = YOLO(candidate_path)
                print(f"Dynamically loaded system model {model_name} from {candidate_path}")
            except Exception as e:
                print(f"Failed to dynamically load system model {model_name}: {e}")
                return jsonify({"error": f"加载系统模型失败: {str(e)}"}), 500
        else:
            # 检查是否是自定义模型（从数据库加载）
            custom_model = CustomModel.query.filter_by(model_key=model_name, status='published').first()
            if custom_model and os.path.exists(custom_model.model_path):
                try:
                    models[model_name] = YOLO(custom_model.model_path)
                    print(f"Dynamically loaded custom model {model_name} from {custom_model.model_path}")
                except Exception as e:
                    print(f"Failed to dynamically load custom model {model_name}: {e}")
                    return jsonify({"error": f"加载自定义模型失败: {str(e)}"}), 500
            else:
                print(f"Requested model '{model_name}' not available. Available: {list(models.keys())}")
                return jsonify({"error": "模型不存在", "available_models": list(models.keys())}), 400
    model = models[model_name]
    print(f"Using model: {model_name}")
    results = model(img_path)
    result = results[0]

    img = result.plot()
    result_path = os.path.join(RESULTS, filename)
    cv2.imwrite(result_path, img)

    # 提取检测信息
    detections = []
    if result.boxes:
        for box, cls, conf in zip(
            result.boxes.xyxy.cpu().numpy(),
            result.boxes.cls.cpu().numpy(),
            result.boxes.conf.cpu().numpy()
        ):
            detections.append({
                "class": result.names[int(cls)],
                "confidence": round(float(conf), 3),
                "bbox": [round(float(x), 1) for x in box]
            })

    avg_conf = sum(d['confidence'] for d in detections) / len(detections) if detections else 0

    # 保存到数据库历史记录
    history_item = DetectionHistory(
        username=username,
        filename=filename,
        model=model_name,
        result_image=f"http://127.0.0.1:5000/results/{filename}",
        original_image=f"http://127.0.0.1:5000/uploads/{filename}",
        detections=json.dumps(detections),
        count=len(detections),
        confidence=avg_conf
    )
    db.session.add(history_item)
    db.session.commit()
    
    # 记录操作日志
    log_operation(f"执行骨折检测:{filename},检测到{len(detections)}个目标")

    return jsonify({
        "result_image": f"http://127.0.0.1:5000/results/{filename}",
        "detections": detections,
        "predictions": detections,
        "model_used": model_name,
        "history_id": history_item.id
    })


# ==================== 检测历史接口 ====================

@app.route("/api/history", methods=["GET"])
@require_auth
def get_history():
    user = get_current_user()
    # 普通用户只能看到自己的记录，admin可以看到所有记录
    if user.role == 'admin':
        history_list = DetectionHistory.query.order_by(DetectionHistory.timestamp.desc()).limit(50).all()
    else:
        history_list = DetectionHistory.query.filter_by(username=user.username).order_by(DetectionHistory.timestamp.desc()).limit(50).all()
    data = [item.to_dict() for item in history_list]
    return jsonify({"data": data})


@app.route("/api/history/<int:history_id>", methods=["DELETE"])
@require_auth
def delete_history(history_id):
    user = get_current_user()
    history = DetectionHistory.query.get(history_id)
    if not history:
        return jsonify({"error": "记录不存在"}), 404
    
    # 普通用户只能删除自己的记录，admin可以删除所有记录
    if user.role != 'admin' and history.username != user.username:
        return jsonify({"error": "无权删除此记录"}), 403
    
    db.session.delete(history)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/history/clear/all", methods=["DELETE"])
@require_admin
def clear_history():
    db.session.query(DetectionHistory).delete()
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/history/<int:history_id>/advice", methods=["POST"])
@require_auth
def save_medical_advice(history_id):
    """保存医疗建议到历史记录"""
    user = get_current_user()
    history = DetectionHistory.query.get(history_id)
    
    if not history:
        return jsonify({"error": "记录不存在"}), 404
    
    # 普通用户只能修改自己的记录
    if user.role != 'admin' and history.username != user.username:
        return jsonify({"error": "无权修改此记录"}), 403
    
    data = request.json
    advice_data = {
        'interpretation': data.get('interpretation', ''),
        'patient_info': data.get('patient_info', {}),
        'prompt': data.get('prompt', ''),
        'created_at': datetime.utcnow().isoformat()
    }
    
    history.medical_advice = json.dumps(advice_data, ensure_ascii=False)
    db.session.commit()
    
    log_operation(f"保存医疗建议:历史记录ID={history_id}")
    return jsonify({"success": True, "message": "医疗建议已保存"})


@app.route("/api/history/<int:history_id>", methods=["GET"])
@require_auth
def get_history_detail(history_id):
    """获取单条历史记录详情"""
    user = get_current_user()
    history = DetectionHistory.query.get(history_id)
    
    if not history:
        return jsonify({"error": "记录不存在"}), 404
    
    # 普通用户只能查看自己的记录
    if user.role != 'admin' and history.username != user.username:
        return jsonify({"error": "无权查看此记录"}), 403
    
    return jsonify(history.to_dict())


# ==================== 统计分析接口 ====================

@app.route("/api/analysis", methods=["GET"])
@require_admin
def get_analysis():
    history_list = DetectionHistory.query.all()
    total_images = len(history_list)
    models_used = {}
    classes_detected = {}

    total_boxes = 0
    total_confidence = 0.0

    for item in history_list:
        model = item.model or "unknown"
        models_used[model] = models_used.get(model, 0) + 1

        try:
            detections = json.loads(item.detections) if item.detections else []
        except:
            detections = []

        for detection in detections:
            cls = detection.get("class", "unknown")
            classes_detected[cls] = classes_detected.get(cls, 0) + 1
            conf = float(detection.get("confidence", 0))
            total_confidence += conf
            total_boxes += 1

    avg_confidence = (total_confidence / total_boxes) if total_boxes > 0 else 0

    return jsonify({
        "total_detections": total_images,
        "models_used": models_used,
        "classes_detected": classes_detected,
        "avg_confidence": avg_confidence
    })


# ==================== 系统设置接口 ====================

@app.route("/api/settings", methods=["GET"])
@require_auth
def get_settings():
    default_model_setting = SystemSettings.query.filter_by(key='default_model').first()
    default_model = default_model_setting.value if default_model_setting else 'yolov8'
    
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
    
    # 获取所有已发布的模型（系统模型 + 自定义模型）
    available_models = []
    
    # 系统模型
    for name in ['yolov8', 'yolo11', 'yolo12']:
        if name in models:
            available_models.append({
                'key': name,
                'name': name.upper(),
                'type': 'system'
            })
    
    # 已发布的自定义模型
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
@require_admin
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
    return jsonify({"success": True, "message": "设置已保存"})


# ==================== 静态文件接口 ====================

@app.route("/results/<path:filename>")
def get_result(filename):
    return send_from_directory(RESULTS, filename)


@app.route("/uploads/<path:filename>")
def get_upload(filename):
    return send_from_directory(UPLOADS, filename)


# ==================== 用户管理接口（仅管理员） ====================

@app.route("/api/users", methods=["GET"])
@require_admin
def get_users():
    """获取所有用户列表"""
    users = User.query.order_by(User.created_at.desc()).all()
    data = [user.to_dict() for user in users]
    return jsonify({"data": data})


@app.route("/api/users", methods=["POST"])
@require_admin
def create_user():
    """创建新用户（管理员）"""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user").strip()
    
    # 验证输入
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    
    if len(username) < 3:
        return jsonify({"error": "用户名长度至少3个字符"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "密码长度至少6个字符"}), 400
    
    if role not in ['user', 'admin']:
        return jsonify({"error": "角色必须是 'user' 或 'admin'"}), 400
    
    # 检查用户是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 409
    
    # 创建新用户
    new_user = User(
        username=username,
        password=generate_password_hash(password),
        role=role
    )
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "用户创建成功",
        "user": new_user.to_dict()
    }), 201


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@require_admin
def delete_user(user_id):
    """删除用户"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    # 防止删除自己
    current_user = get_current_user()
    if user.id == current_user.id:
        return jsonify({"error": "不能删除自己的账户"}), 400
    
    # 删除用户相关的检测历史
    DetectionHistory.query.filter_by(username=user.username).delete()
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({"success": True, "message": "用户已删除"})


@app.route("/api/users/<int:user_id>", methods=["PUT"])
@require_admin
def update_user(user_id):
    """更新用户信息（主要是角色）"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    data = request.json
    role = data.get("role")
    password = data.get("password", "").strip()
    
    # 更新角色
    if role and role in ['user', 'admin']:
        # 防止修改自己的角色为普通用户
        current_user = get_current_user()
        if user.id == current_user.id and role == 'user':
            return jsonify({"error": "不能将自己的角色修改为普通用户"}), 400
        user.role = role
    
    # 更新密码（可选）
    if password:
        if len(password) < 6:
            return jsonify({"error": "密码长度至少6个字符"}), 400
        user.password = generate_password_hash(password)
    
    db.session.commit()
    return jsonify({
        "success": True,
        "message": "用户信息已更新",
        "user": user.to_dict()
    })

# ==================== AI 解读接口 ====================

AI_SERVICE_URL = "http://127.0.0.1:8000"

def get_ai_settings():
    """获取AI服务配置"""
    ai_provider_setting = SystemSettings.query.filter_by(key='ai_provider').first()
    ai_provider = ai_provider_setting.value if ai_provider_setting else 'local'
    
    ai_api_key_setting = SystemSettings.query.filter_by(key='ai_api_key').first()
    ai_api_key = ai_api_key_setting.value if ai_api_key_setting else ''
    
    ai_api_url_setting = SystemSettings.query.filter_by(key='ai_api_url').first()
    ai_api_url = ai_api_url_setting.value if ai_api_url_setting else ''
    
    ai_model_setting = SystemSettings.query.filter_by(key='ai_model').first()
    ai_model = ai_model_setting.value if ai_model_setting else 'gpt-4'
    
    return {
        'provider': ai_provider,
        'api_key': ai_api_key,
        'api_url': ai_api_url,
        'model': ai_model
    }

def call_local_ai(prompt, image_base64=None):
    """调用本地部署的AI服务"""
    ai_request = {"prompt": prompt}
    if image_base64:
        ai_request["image"] = image_base64
    
    response = requests.post(
        f"{AI_SERVICE_URL}/chat",
        json=ai_request,
        timeout=180
    )
    
    if response.status_code == 200:
        ai_result = response.json()
        return ai_result.get("reply", "AI 未能生成有效建议")
    else:
        raise Exception(f"AI服务响应失败: {response.text}")

def call_openai_api(prompt, api_key, model='gpt-4'):
    """调用OpenAI API"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=60
    )
    
    if response.status_code == 200:
        result = response.json()
        return result['choices'][0]['message']['content']
    else:
        raise Exception(f"OpenAI API调用失败: {response.text}")

def call_custom_api(prompt, api_url, api_key, model='gpt-4'):
    """调用自定义API"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    response = requests.post(
        api_url,
        headers=headers,
        json=data,
        timeout=60
    )
    
    if response.status_code == 200:
        result = response.json()
        # 适配不同API的响应格式
        if 'choices' in result:
            return result['choices'][0]['message']['content']
        elif 'result' in result:
            return result['result']
        elif 'reply' in result:
            return result['reply']
        else:
            return str(result)
    else:
        raise Exception(f"自定义API调用失败: {response.text}")

def call_modelscope_api(prompt, api_key, model, image_base64=None):
    """调用ModelScope API - 支持多模态"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 构建消息内容
    content = []
    
    # 添加文本
    content.append({
        "type": "text",
        "text": prompt
    })
    
    # 如果有图片，添加图片
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}"
            }
        })
    
    data = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": content
        }],
        "temperature": 0.7,
        "max_tokens": 2000,
        "stream": False  # 使用非流式响应
    }
    
    response = requests.post(
        "https://api-inference.modelscope.cn/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=120
    )
    
    if response.status_code == 200:
        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"ModelScope API返回格式异常: {result}")
    else:
        raise Exception(f"ModelScope API调用失败: {response.status_code} - {response.text}")

@app.route("/api/interpret", methods=["POST"])
@require_auth
def interpret_detection():
    """
    调用AI服务生成医疗建议
    支持本地部署和第三方API
    """
    data = request.json
    detections = data.get("detections", [])
    custom_prompt = data.get("prompt", "")
    image_base64 = data.get("image_base64", None)

    if not detections:
        return jsonify({"error": "没有检测结果可供解读"}), 400

    if not custom_prompt:
        detection_summary = []
        for i, det in enumerate(detections, 1):
            cls = det.get("class", "未知")
            conf = det.get("confidence", 0)
            bbox = det.get("bbox", [])
            detection_summary.append(f"检测{i}: 类别={cls}, 置信度={conf:.2f}, 位置={bbox}")

        detection_text = "\n".join(detection_summary)

        prompt = f"""你是一位专业的骨科医生助手。我将提供骨折检测的X光片图像和检测结果，请结合图像和检测信息进行专业分析。

检测结果：
{detection_text}

请结合X光片图像和检测结果，提供以下信息：
1. 图像分析：观察X光片中的骨折位置、类型和严重程度
2. 风险评估：根据检测到的骨折类型和图像表现，评估病情的严重程度
3. 进一步检查建议：建议进行哪些进一步检查（如CT、MRI等）
4. 处置建议：初步的处置建议（如固定、手术、转诊等）
5. 注意事项：患者应该注意的事项
6. 免责声明：提示此为AI辅助诊断，最终诊断需由专业医生确定

请用中文回复，结构化输出。"""
    else:
        prompt = custom_prompt

    try:
        # 获取AI配置
        ai_config = get_ai_settings()
        provider = ai_config['provider']
        
        # 根据提供商调用不同的AI服务
        if provider == 'local':
            reply = call_local_ai(prompt, image_base64)
        elif provider == 'openai':
            reply = call_openai_api(prompt, ai_config['api_key'], ai_config['model'])
        elif provider == 'custom':
            reply = call_custom_api(prompt, ai_config['api_url'], ai_config['api_key'], ai_config['model'])
        elif provider == 'modelscope':
            reply = call_modelscope_api(prompt, ai_config['api_key'], ai_config['model'], image_base64)
        else:
            return jsonify({"error": "未知的AI服务提供商"}), 400
        
        return jsonify({
            "success": True,
            "interpretation": reply,
            "detections_count": len(detections),
            "ai_provider": provider
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": "无法连接到 AI 服务",
            "hint": "请检查AI服务配置和网络连接"
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "AI 服务响应超时"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== 置信度趋势折线接口 ====================

@app.route("/api/analysis/confidence_series", methods=["GET"])
@require_admin          # 只有管理员可看趋势
def confidence_series():
    """
    返回最近 200 条检测的置信度序列，按时间升序
    """
    from datetime import timedelta
    
    rows = (DetectionHistory.query
            .order_by(DetectionHistory.timestamp.desc())
            .limit(200)
            .all())[::-1]          # 升序，图表从左到右

    data = [
        {
            # 将UTC时间转换为本地时间（中国时区 UTC+8）
            "timestamp": (r.timestamp + timedelta(hours=8)).strftime("%m-%d %H:%M:%S"),
            "confidence": round(float(r.confidence or 0), 3)
        }
        for r in rows
    ]
    return jsonify(data)


@app.route("/api/analysis/user_confidence_series", methods=["GET"])
@require_auth
def user_confidence_series():
    """
    返回当前用户最近 100 条检测的置信度序列，按时间升序
    """
    from datetime import timedelta
    user = get_current_user()
    
    rows = (DetectionHistory.query
            .filter_by(username=user.username)
            .order_by(DetectionHistory.timestamp.desc())
            .limit(100)
            .all())[::-1]          # 升序，图表从左到右

    data = [
        {
            # 将UTC时间转换为本地时间（中国时区 UTC+8）
            "timestamp": (r.timestamp + timedelta(hours=8)).strftime("%m-%d %H:%M:%S"),
            "confidence": round(float(r.confidence or 0), 3)
        }
        for r in rows
    ]
    return jsonify(data)


@app.route("/api/analysis/user_stats", methods=["GET"])
@require_auth
def user_stats():
    """
    返回当前用户的检测统计数据
    """
    user = get_current_user()
    
    # 总检测次数
    total_detections = DetectionHistory.query.filter_by(username=user.username).count()
    
    # 模型使用统计
    models_used = {}
    histories = DetectionHistory.query.filter_by(username=user.username).all()
    for history in histories:
        model = history.model
        models_used[model] = models_used.get(model, 0) + 1
    
    # 检测类别统计
    classes_detected = {}
    for history in histories:
        if history.fracture_types:
            for fracture_type in history.fracture_types:
                classes_detected[fracture_type] = classes_detected.get(fracture_type, 0) + 1
    
    # 平均置信度
    total_confidence = 0
    confidence_count = 0
    for history in histories:
        if history.confidence:
            total_confidence += float(history.confidence)
            confidence_count += 1
    avg_confidence = total_confidence / confidence_count if confidence_count > 0 else 0
    
    # 最近检测
    recent_detections = []
    recent_histories = DetectionHistory.query.filter_by(username=user.username).order_by(DetectionHistory.timestamp.desc()).limit(5).all()
    for history in recent_histories:
        recent_detections.append({
            "id": history.id,
            "timestamp": history.timestamp,
            "model": history.model,
            "count": history.count,
            "confidence": history.confidence,
            "fracture_types": history.fracture_types
        })
    
    return jsonify({
        "total_detections": total_detections,
        "models_used": models_used,
        "classes_detected": classes_detected,
        "avg_confidence": avg_confidence,
        "recent_detections": recent_detections
    })


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
        print(f"记录日志失败: {e}")
        try:
            db.session.rollback()
        except:
            pass


@app.route("/api/logs", methods=["GET"])
@require_admin
def get_logs():
    """获取操作日志列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    username = request.args.get('username', '')
    method = request.args.get('method', '')
    
    query = OperationLog.query
    
    if username:
        query = query.filter(OperationLog.username.contains(username))
    if method:
        query = query.filter_by(method=method)
    
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
@require_admin
def delete_log(log_id):
    """删除单条日志"""
    log = OperationLog.query.get(log_id)
    if not log:
        return jsonify({"error": "日志不存在"}), 404
    
    db.session.delete(log)
    db.session.commit()
    log_operation(f"删除日志 ID:{log_id}")
    return jsonify({"success": True, "message": "日志已删除"})


@app.route("/api/logs/clear", methods=["DELETE"])
@require_admin
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


# ==================== 文件管理接口（借鉴pear-admin-flask）====================

# 文件上传配置
FILES_DIR = os.path.join(BASE_DIR, "files")
os.makedirs(FILES_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'doc', 'docx', 'txt'}

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/api/files", methods=["GET"])
@require_auth
def get_files():
    """获取文件列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = FileRecord.query
    
    # 普通用户只能看到自己的文件
    user = get_current_user()
    if user.role != 'admin':
        query = query.filter_by(uploader=user.username)
    
    pagination = query.order_by(FileRecord.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'data': [f.to_dict() for f in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page
    })


@app.route("/api/files/upload", methods=["POST"])
@require_auth
def upload_file():
    """上传文件"""
    if 'file' not in request.files:
        return jsonify({"error": "没有文件"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "不支持的文件类型"}), 400
    
    try:
        # 生成唯一文件名
        original_name = file.filename
        extension = original_name.rsplit('.', 1)[1].lower()
        filename = f"{int(time.time())}_{original_name}"
        file_path = os.path.join(FILES_DIR, filename)
        
        # 保存文件
        file.save(file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        # 记录到数据库
        user = get_current_user()
        record = FileRecord(
            filename=filename,
            original_name=original_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type or 'application/octet-stream',
            extension=extension,
            uploader=user.username,
            description=request.form.get('description', '')
        )
        db.session.add(record)
        db.session.commit()
        
        log_operation(f"上传文件:{original_name}")
        return jsonify({
            "success": True,
            "data": record.to_dict(),
            "url": f"/api/files/download/{record.id}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/download/<int:file_id>", methods=["GET"])
@require_auth
def download_file(file_id):
    """下载文件"""
    record = FileRecord.query.get(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    
    # 检查权限
    user = get_current_user()
    if user.role != 'admin' and record.uploader != user.username:
        return jsonify({"error": "无权访问此文件"}), 403
    
    if not os.path.exists(record.file_path):
        return jsonify({"error": "文件已丢失"}), 404
    
    from flask import send_file
    return send_file(record.file_path, as_attachment=True, download_name=record.original_name)


@app.route("/api/files/<int:file_id>", methods=["DELETE"])
@require_auth
def delete_file(file_id):
    """删除文件"""
    record = FileRecord.query.get(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    
    # 检查权限
    user = get_current_user()
    if user.role != 'admin' and record.uploader != user.username:
        return jsonify({"error": "无权删除此文件"}), 403
    
    # 删除物理文件
    try:
        if os.path.exists(record.file_path):
            os.remove(record.file_path)
    except Exception as e:
        print(f"删除物理文件失败: {e}")
    
    # 删除数据库记录
    filename = record.original_name
    db.session.delete(record)
    db.session.commit()
    
    log_operation(f"删除文件:{filename}")
    return jsonify({"success": True, "message": "文件已删除"})


# ==================== 系统监控接口（借鉴pear-admin-flask）====================

@app.route("/api/monitor/system", methods=["GET"])
@require_admin
def get_system_info():
    """获取系统监控信息"""
    import psutil
    import platform
    
    # CPU信息
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()
    
    # 内存信息
    memory = psutil.virtual_memory()
    
    # 磁盘信息
    disk = psutil.disk_usage('/')
    
    # 系统信息
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    
    return jsonify({
        "cpu": {
            "percent": cpu_percent,
            "count": cpu_count,
            "freq": f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A"
        },
        "memory": {
            "total": f"{memory.total / (1024**3):.2f} GB",
            "available": f"{memory.available / (1024**3):.2f} GB",
            "percent": memory.percent,
            "used": f"{memory.used / (1024**3):.2f} GB"
        },
        "disk": {
            "total": f"{disk.total / (1024**3):.2f} GB",
            "used": f"{disk.used / (1024**3):.2f} GB",
            "free": f"{disk.free / (1024**3):.2f} GB",
            "percent": disk.percent
        },
        "system": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S")
        }
    })


@app.route("/api/monitor/stats", methods=["GET"])
@require_admin
def get_system_stats():
    """获取系统统计数据"""
    # 用户统计
    user_count = User.query.count()
    admin_count = User.query.filter_by(role='admin').count()
    
    # 检测统计
    detection_count = DetectionHistory.query.count()
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_detection_count = DetectionHistory.query.filter(DetectionHistory.timestamp >= today).count()
    
    # 文件统计
    file_count = FileRecord.query.count()
    total_file_size = db.session.query(db.func.sum(FileRecord.file_size)).scalar() or 0
    
    # 日志统计
    log_count = OperationLog.query.count()
    today_log_count = OperationLog.query.filter(OperationLog.timestamp >= today).count()
    
    return jsonify({
        "users": {
            "total": user_count,
            "admins": admin_count,
            "regular": user_count - admin_count
        },
        "detections": {
            "total": detection_count,
            "today": today_detection_count
        },
        "files": {
            "count": file_count,
            "total_size": FileRecord.format_file_size(total_file_size)
        },
        "logs": {
            "total": log_count,
            "today": today_log_count
        }
    })


# ==================== 视频流检测接口 ====================

import base64
import numpy as np
from flask_sock import Sock
import threading
import queue

sock = Sock(app)

# 视频检测任务管理
video_tasks = {}

@app.route("/api/video/detect", methods=["POST"])
@require_auth
def video_detect():
    """视频流检测 - 开始任务"""
    if 'video' not in request.files:
        return jsonify({"error": "没有上传视频文件"}), 400
    
    file = request.files['video']
    model_name = request.form.get('model', 'yolov8')
    username = request.headers.get('X-Username') or 'anonymous'
    
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400
    
    # 检查并加载模型
    if model_name not in models:
        # 首先检查是否是系统模型
        candidate_path = MODEL_CANDIDATES.get(model_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                models[model_name] = YOLO(candidate_path)
                print(f"Video detect: Dynamically loaded system model {model_name}")
            except Exception as e:
                return jsonify({"error": f"加载系统模型失败: {str(e)}"}), 500
        else:
            # 检查是否是自定义模型
            custom_model = CustomModel.query.filter_by(model_key=model_name, status='published').first()
            if custom_model and os.path.exists(custom_model.model_path):
                try:
                    models[model_name] = YOLO(custom_model.model_path)
                    print(f"Video detect: Dynamically loaded custom model {model_name}")
                except Exception as e:
                    return jsonify({"error": f"加载自定义模型失败: {str(e)}"}), 500
            else:
                return jsonify({"error": f"模型 {model_name} 未加载或不存在"}), 400
    
    # 保存视频文件
    timestamp = int(time.time())
    filename = f"{timestamp}_{file.filename}"
    video_path = os.path.join(UPLOADS, filename)
    file.save(video_path)
    
    # 创建任务ID
    task_id = f"video_{timestamp}"
    
    # 初始化任务状态
    video_tasks[task_id] = {
        'status': 'processing',
        'progress': 0,
        'current_frame': 0,
        'total_frames': 0,
        'detections': [],
        'clients': set()
    }
    
    # 启动异步处理线程
    thread = threading.Thread(
        target=process_video_stream,
        args=(task_id, video_path, model_name, username)
    )
    thread.daemon = True
    thread.start()
    
    log_operation(f"开始视频流检测:{filename},模型:{model_name}")
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "视频检测任务已启动"
    })


def process_video_stream(task_id, video_path, model_name, username):
    """处理视频流检测"""
    try:
        model = models[model_name]
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            video_tasks[task_id]['status'] = 'error'
            video_tasks[task_id]['message'] = '无法打开视频文件'
            return
        
        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_tasks[task_id]['total_frames'] = total_frames
        
        frame_count = 0
        detected_frames = 0
        total_detections = 0
        all_confidences = []
        
        # 处理间隔（每5帧处理一帧）
        process_interval = 5
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 只处理指定间隔的帧
            if frame_count % process_interval != 0:
                continue
            
            # 进行检测
            results = model(frame)
            detections = []
            
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    cls_name = model.names[cls_id]
                    conf = float(box.conf[0])
                    
                    detections.append({
                        'class': cls_name,
                        'confidence': conf,
                        'bbox': box.xyxy[0].tolist()
                    })
                    
                    # 绘制检测框
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"{cls_name} {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # 计算统计
            if detections:
                detected_frames += 1
                total_detections += len(detections)
                avg_conf = sum(d['confidence'] for d in detections) / len(detections)
                all_confidences.append(avg_conf)
            
            # 编码图像为 base64
            _, buffer = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # 更新任务状态
            video_tasks[task_id]['current_frame'] = frame_count
            video_tasks[task_id]['progress'] = (frame_count / total_frames) * 100 if total_frames > 0 else 0
            
            # 广播给所有连接的客户端
            message = {
                'type': 'frame',
                'frame': frame_count,
                'timestamp': frame_count / fps if fps > 0 else 0,
                'image': img_base64,
                'detections': detections,
                'avg_confidence': sum(d['confidence'] for d in detections) / len(detections) if detections else 0
            }
            
            # 发送到所有 WebSocket 客户端
            for client in list(video_tasks[task_id].get('clients', [])):
                try:
                    client.send(json.dumps(message))
                except:
                    pass
            
            # 发送统计信息（每30帧）
            if frame_count % (process_interval * 6) == 0:
                stats_message = {
                    'type': 'stats',
                    'stats': {
                        'total_frames': frame_count,
                        'detected_frames': detected_frames,
                        'total_detections': total_detections,
                        'avg_confidence': round(sum(all_confidences) / len(all_confidences) * 100, 1) if all_confidences else 0
                    }
                }
                for client in list(video_tasks[task_id].get('clients', [])):
                    try:
                        client.send(json.dumps(stats_message))
                    except:
                        pass
        
        cap.release()
        
        # 发送完成消息
        video_tasks[task_id]['status'] = 'completed'
        complete_message = {
            'type': 'complete',
            'stats': {
                'total_frames': frame_count,
                'detected_frames': detected_frames,
                'total_detections': total_detections,
                'avg_confidence': round(sum(all_confidences) / len(all_confidences) * 100, 1) if all_confidences else 0
            }
        }
        for client in list(video_tasks[task_id].get('clients', [])):
            try:
                client.send(json.dumps(complete_message))
            except:
                pass
        
        log_operation(f"视频流检测完成:{task_id},共{frame_count}帧")
        
    except Exception as e:
        print(f"视频处理错误: {e}")
        video_tasks[task_id]['status'] = 'error'
        error_message = {'type': 'error', 'message': str(e)}
        for client in list(video_tasks[task_id].get('clients', [])):
            try:
                client.send(json.dumps(error_message))
            except:
                pass


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


# ==================== 摄像头实时检测接口 ====================

@app.route("/api/camera/detect", methods=["POST"])
@require_auth
def camera_detect():
    """摄像头实时检测单帧"""
    data = request.json
    image_data = data.get('image', '')
    model_name = data.get('model', 'yolov8')
    
    if not image_data:
        return jsonify({"error": "没有图像数据"}), 400
    
    # 检查并加载模型
    if model_name not in models:
        # 首先检查是否是系统模型
        candidate_path = MODEL_CANDIDATES.get(model_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                models[model_name] = YOLO(candidate_path)
                print(f"Camera detect: Dynamically loaded system model {model_name}")
            except Exception as e:
                return jsonify({"error": f"加载系统模型失败: {str(e)}"}), 500
        else:
            # 检查是否是自定义模型
            custom_model = CustomModel.query.filter_by(model_key=model_name, status='published').first()
            if custom_model and os.path.exists(custom_model.model_path):
                try:
                    models[model_name] = YOLO(custom_model.model_path)
                    print(f"Camera detect: Dynamically loaded custom model {model_name}")
                except Exception as e:
                    return jsonify({"error": f"加载自定义模型失败: {str(e)}"}), 500
            else:
                return jsonify({"error": f"模型 {model_name} 未加载或不存在"}), 400
    
    try:
        # 解码 base64 图像
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "无法解码图像"}), 400
        
        # 进行检测
        model = models[model_name]
        results = model(frame)
        
        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                conf = float(box.conf[0])
                
                detections.append({
                    'class': cls_name,
                    'confidence': conf,
                    'bbox': box.xyxy[0].tolist()
                })
                
                # 绘制检测框
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{cls_name} {conf:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 编码结果图像
        _, buffer = cv2.imencode('.jpg', frame)
        result_image = 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode('utf-8')
        
        return jsonify({
            "success": True,
            "detections": detections,
            "result_image": result_image,
            "count": len(detections)
        })
        
    except Exception as e:
        print(f"摄像头检测错误: {e}")
        return jsonify({"error": str(e)}), 500


# ==================== 验证码接口 ====================

@app.route("/api/captcha", methods=["GET"])
def generate_captcha():
    """生成验证码"""
    # 生成4位随机验证码
    captcha_text = "".join([random.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4)])
    
    # 保存到session
    session['captcha'] = captcha_text
    
    # 创建验证码图像
    width, height = 120, 40
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 添加噪点
    for _ in range(50):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
    
    # 添加干扰线
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)), width=1)
    
    # 绘制验证码文本
    try:
        # 尝试使用系统字体
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        # 如果没有arial字体，使用默认字体
        font = ImageFont.load_default()
    
    # 计算文本位置
    # 使用textbbox替代textsize（Pillow 9.0+）
    bbox = draw.textbbox((0, 0), captcha_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    # 绘制文本
    draw.text((x, y), captcha_text, font=font, fill=(0, 0, 0))
    
    # 转换为字节流
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    
    # 返回图像
    from flask import send_file
    return send_file(buffer, mimetype='image/png')


@app.route("/api/captcha/verify", methods=["POST"])
def verify_captcha():
    """验证验证码"""
    data = request.json
    captcha = data.get("captcha", "").strip().upper()
    
    if not captcha:
        return jsonify({"error": "验证码不能为空"}), 400
    
    # 从session获取验证码
    session_captcha = session.get('captcha', '').upper()
    
    if not session_captcha:
        return jsonify({"error": "验证码已过期"}), 400
    
    if captcha != session_captcha:
        return jsonify({"error": "验证码错误"}), 400
    
    # 验证成功后清除session中的验证码
    session.pop('captcha', None)
    
    return jsonify({"success": True, "message": "验证码验证成功"})


# ==================== 模型训练管理接口 ====================

# 训练任务管理
training_tasks = {}

# 训练任务停止标志
# 格式: {task_id: stop_flag}
# stop_flag: True表示需要停止训练
training_stop_flags = {}

@app.route("/api/models", methods=["GET"])
@require_auth
def get_models():
    """获取所有模型列表（包括系统模型和自定义模型）- 优化版本"""
    from datetime import datetime
    
    # 系统模型 - 直接从内存获取，无需数据库查询
    system_models = []
    for name in ['yolov8', 'yolo11', 'yolo12']:
        if name in models:
            system_models.append({
                'id': name,
                'name': name.upper(),
                'model_key': name,
                'type': 'system',
                'status': 'published',
                'description': f'系统预置 {name.upper()} 模型'
            })
    
    # 自定义模型 - 使用分页和字段选择优化查询
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
    """获取已发布的模型列表（用于检测选择）"""
    result = []
    
    # 1. 添加已加载的系统模型（yolov8, yolo11, yolo12）
    system_model_names = {
        'yolov8': 'YOLOv8',
        'yolo11': 'YOLO11', 
        'yolo12': 'YOLO12',
    }
    
    for key, name in system_model_names.items():
        if key in models:
            result.append({
                'key': key,
                'name': name,
                'type': 'system'
            })
    
    # 2. 添加CBAM优化模型选项（用于训练时选择，检测时不可用）
    # CBAM模型在训练时动态创建，不需要预训练文件
    if CBAM_AVAILABLE:
        result.append({
            'key': 'yolov8-cbam',
            'name': 'YOLOv8-CBAM (注意力优化-仅训练)',
            'type': 'system'
        })
        result.append({
            'key': 'yolo11-cbam',
            'name': 'YOLO11-CBAM (注意力优化-仅训练)',
            'type': 'system'
        })
    
    # 已发布的自定义模型
    custom_models = CustomModel.query.filter_by(status='published').all()
    for model in custom_models:
        # 检查是否是CBAM模型
        model_name = model.name
        if 'cbam' in model.base_model.lower() or '[CBAM优化]' in (model.description or ''):
            model_name = f"{model_name} (CBAM)"
        result.append({
            'key': model.model_key,
            'name': model_name,
            'type': 'custom'
        })
    
    return jsonify({'models': result})


@app.route("/api/models/train", methods=["POST"])
@require_auth
def train_model():
    """上传数据集并开始训练模型"""
    if 'dataset' not in request.files:
        return jsonify({"error": "没有上传数据集文件"}), 400
    
    dataset_file = request.files['dataset']
    model_name = request.form.get('name', '').strip()
    description = request.form.get('description', '')
    base_model = request.form.get('base_model', 'yolov8')
    epochs = int(request.form.get('epochs', 100))
    batch_size = int(request.form.get('batch_size', 16))
    img_size = int(request.form.get('img_size', 640))
    username = request.headers.get('X-Username') or 'anonymous'
    
    if not model_name:
        return jsonify({"error": "模型名称不能为空"}), 400
    
    if dataset_file.filename == '':
        return jsonify({"error": "数据集文件名为空"}), 400
    
    # 检查基础模型是否可用（支持预训练模型、CBAM模型和自定义模型续训）
    # 支持的基础模型列表（包括CBAM优化版本）
    supported_base_models = ['yolov8', 'yolo11', 'yolo12', 'yolov8-cbam', 'yolo11-cbam']
    is_continued_training = base_model not in supported_base_models
    base_model_info = None
    use_cbam = 'cbam' in base_model.lower()  # 检查是否使用CBAM模型
    
    if is_continued_training:
        # 检查是否是已存在的自定义模型
        base_model_info = CustomModel.query.filter_by(model_key=base_model).first()
        if not base_model_info:
            return jsonify({"error": f"基础模型 {base_model} 不存在"}), 400
        if base_model_info.status not in ['trained', 'published']:
            return jsonify({"error": "基础模型尚未训练完成，无法用于续训"}), 400
        actual_base_model = base_model_info.base_model  # 获取原始基础模型类型
        use_cbam = 'cbam' in actual_base_model.lower()  # 继承CBAM设置
    else:
        # 对于常规模型，检查是否在已加载的models中
        # 对于CBAM模型，不需要预加载，训练时会动态创建
        if not use_cbam and base_model not in models:
            return jsonify({"error": f"基础模型 {base_model} 未加载"}), 400
        actual_base_model = base_model
    
    # 生成模型标识
    timestamp = int(time.time())
    model_key = f"custom_{actual_base_model}_{timestamp}"
    
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
    
    # 创建模型记录
    model_path = os.path.join(MODELS_DIR, f'{model_key}.pt')
    custom_model = CustomModel(
        name=model_name,
        model_key=model_key,
        description=description,
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
    task = TrainingTask(
        task_name=f"训练 {model_name}",
        model_id=custom_model.id,
        status='running',
        total_epochs=epochs,
        created_by=username,
        started_at=datetime.utcnow()
    )
    db.session.add(task)
    db.session.commit()
    
    # 启动异步训练线程
    # 如果是续训，传递自定义模型的路径
    if is_continued_training:
        base_model_path = base_model_info.model_path
    else:
        # 使用 BASE_MODEL_MAP 获取正确的模型文件名
        base_model_path = BASE_MODEL_MAP.get(base_model, base_model)
    
    thread = threading.Thread(
        target=train_model_task,
        args=(task.id, custom_model.id, base_model_path, dataset_dir, epochs, batch_size, img_size, is_continued_training, use_cbam)
    )
    thread.daemon = True
    thread.start()
    
    cbam_info = "(CBAM优化)" if use_cbam else ""
    log_operation(f"开始训练模型:{model_name},基础模型:{base_model}{cbam_info},创建者:{username}")
    
    return jsonify({
        "success": True,
        "model_id": custom_model.id,
        "task_id": task.id,
        "message": "模型训练任务已启动"
    })


def train_model_task(task_id, model_id, base_model_path, dataset_dir, epochs, batch_size, img_size, is_continued_training=False, use_cbam=False):
    """异步训练模型任务（支持CBAM优化）"""
    # 在整个函数中使用应用上下文
    with app.app_context():
        try:
            from ultralytics import YOLO
            import time
            
            task = db.session.get(TrainingTask, task_id)
            custom_model = db.session.get(CustomModel, model_id)
            
            if not task or not custom_model:
                return
            
            # 加载基础模型
            if is_continued_training:
                # 续训模式：从已有模型继续训练
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
                # 新训练模式：从预训练权重开始
                if use_cbam and CBAM_AVAILABLE:
                    # 使用CBAM优化的模型
                    print(f"使用CBAM优化模型进行训练: {base_model_path}")

                    # 尝试多种可能的本地模型文件名
                    possible_models = []
                    if 'yolov8' in base_model_path:
                        # 优先查找 yolov8.pt，然后是 yolov8n.pt
                        possible_models = ['yolov8.pt', 'yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt']
                    elif 'yolo11' in base_model_path:
                        # 优先查找 yolo11n.pt
                        possible_models = ['yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt']
                    elif 'yolo12' in base_model_path:
                        # 优先查找 yolo12n.pt
                        possible_models = ['yolo12n.pt', 'yolo12s.pt', 'yolo12m.pt']
                    else:
                        possible_models = ['yolov8.pt', 'yolov8n.pt']

                    # 查找存在的本地模型文件
                    base_model_file = None
                    base_yolo = None
                    for model_name in possible_models:
                        model_path = os.path.join(MODELS_DIR, model_name)
                        if os.path.exists(model_path):
                            base_model_file = model_path
                            base_yolo = model_name.replace('.pt', '')
                            print(f"✓ 找到本地模型: {base_model_file}")
                            break

                    # 如果没有找到本地模型，使用默认名称
                    if base_model_file is None:
                        if 'yolov8' in base_model_path:
                            base_yolo = 'yolov8'
                        elif 'yolo11' in base_model_path:
                            base_yolo = 'yolo11n'
                        elif 'yolo12' in base_model_path:
                            base_yolo = 'yolo12n'
                        else:
                            base_yolo = 'yolov8'
                        base_model_file = os.path.join(MODELS_DIR, f'{base_yolo}.pt')
                        print(f"⚠ 未找到本地模型，将使用: {base_yolo}")
                    
                else:
                    # 标准模型训练
                    # base_model_path 已经是正确的模型文件名（如 yolo12n）
                    base_model_file = os.path.join(MODELS_DIR, f'{base_model_path}.pt')
                    print(f"标准模型训练，加载: {base_model_file}")
                    if os.path.exists(base_model_file):
                        model = YOLO(base_model_file)
                        print(f"✓ 成功加载本地模型: {base_model_file}")
                    else:
                        # 如果本地没有，使用预训练权重
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

            # 读取数据集中的类别数
            try:
                import yaml
                with open(data_yaml, 'r', encoding='utf-8') as f:
                    data_config = yaml.safe_load(f)
                nc = data_config.get('nc', 80)  # 默认80类
                print(f"✓ 数据集类别数: {nc}")
            except Exception as e:
                print(f"⚠ 读取数据集配置失败: {e}，使用默认类别数 80")
                nc = 80

            # 如果使用CBAM，现在创建模型（在获取nc之后）
            if use_cbam and CBAM_AVAILABLE:
                try:
                    print(f"✓ 创建CBAM优化模型")
                    # 创建带CBAM的YOLO模型，使用'deep_neck'策略（推荐）
                    # 只在Backbone深层和Neck部分插入CBAM，避免浅层计算开销
                    model = create_yolo_with_cbam(base_model_file, nc=nc, verbose=True, insert_strategy='deep_neck')
                    print(f"✓ CBAM模型创建成功")

                    # 保存CBAM模型到临时文件（确保训练时使用CBAM模型）
                    cbam_model_path = os.path.join(MODELS_DIR, f'cbam_temp_{task.id}.pt')
                    model.save(cbam_model_path)
                    print(f"✓ CBAM模型已保存到: {cbam_model_path}")

                    # 重新加载保存的CBAM模型
                    model = YOLO(cbam_model_path)
                    print(f"✓ CBAM模型已重新加载")

                    # 标记模型使用CBAM
                    custom_model.description = f"{custom_model.description or ''} [CBAM优化]".strip()
                except Exception as e:
                    print(f"✗ 加载CBAM模型失败: {e}")
                    import traceback
                    traceback.print_exc()
                    task.status = 'failed'
                    task.error_message = f'加载CBAM模型失败: {str(e)}'
                    custom_model.status = 'failed'
                    db.session.commit()
                    return

            # 开始训练
            task.status = 'running'
            db.session.commit()
            
            # 创建训练回调类来更新进度和检查停止标志
            class TrainingCallback:
                def __init__(self, task_id, total_epochs, app_instance):
                    self.task_id = task_id
                    self.total_epochs = total_epochs
                    self.last_update = 0
                    self.app = app_instance

                def on_train_epoch_end(self, trainer):
                    """每个 epoch 结束时调用"""
                    try:
                        # 检查是否需要停止训练
                        if training_stop_flags.get(self.task_id, False):
                            print(f"检测到停止标志，正在终止训练任务 {self.task_id}...")
                            trainer.stop = True  # 设置停止标志，YOLO会在当前epoch结束后停止
                            return

                        current_epoch = trainer.epoch + 1
                        progress = (current_epoch / self.total_epochs) * 100

                        # 每 5 秒更新一次数据库，避免频繁写入
                        current_time = time.time()
                        if current_time - self.last_update >= 5:
                            self.last_update = current_time

                            # 获取损失值
                            loss = trainer.loss if hasattr(trainer, 'loss') else None
                            val_loss = trainer.val_loss if hasattr(trainer, 'val_loss') else None

                            # 更新数据库
                            with self.app.app_context():
                                task = db.session.get(TrainingTask, self.task_id)
                                if task and task.status == 'running':
                                    task.current_epoch = current_epoch
                                    task.progress = progress
                                    if loss is not None:
                                        task.loss = float(loss) if isinstance(loss, (int, float)) else None
                                    if val_loss is not None:
                                        task.val_loss = float(val_loss) if isinstance(val_loss, (int, float)) else None
                                    db.session.commit()
                                    print(f"训练进度更新: Epoch {current_epoch}/{self.total_epochs}, Progress {progress:.1f}%")
                    except Exception as e:
                        print(f"更新训练进度失败: {e}")
            
            # 注册回调
            callback = TrainingCallback(task_id, epochs, app)
            model.add_callback('on_train_epoch_end', callback.on_train_epoch_end)
            
            # 开始训练
            # 注意：对于CBAM模型，pretrained=False因为我们已经加载了修改后的模型
            # 添加 amp=False 来避免 PyTorch 2.6 的 weights_only 兼容性问题
            # 添加 workers=0 和 pin_memory=False 来避免 CUDA 内存映射错误
            results = model.train(
                data=data_yaml,
                epochs=epochs,
                batch=batch_size,
                imgsz=img_size,
                project=os.path.join(UPLOADS, 'training_runs'),
                name=custom_model.model_key,
                exist_ok=True,
                verbose=True,
                pretrained=False if use_cbam else True,  # CBAM模型不使用预训练权重加载
                amp=False,  # 禁用 AMP 以避免 PyTorch 2.6 兼容性问题
                workers=0,  # 禁用多进程数据加载，避免 CUDA 内存映射错误
                pin_memory=False  # 禁用 pin_memory，避免 CUDA 资源冲突
            )
            
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
                
                # 从训练结果中提取性能指标
                # results 是 DetMetrics 对象，results_dict 包含:
                # - metrics/precision(B)
                # - metrics/recall(B)
                # - metrics/mAP50(B)
                # - metrics/mAP50-95(B)
                # - fitness
                if hasattr(results, 'results_dict') and results.results_dict:
                    results_dict = results.results_dict
                    custom_model.map50 = results_dict.get('metrics/mAP50(B)', 0)
                    custom_model.map50_95 = results_dict.get('metrics/mAP50-95(B)', 0)
                    # accuracy 在检测任务中通常用 fitness 或 mAP50-95 表示
                    custom_model.accuracy = results_dict.get('fitness', custom_model.map50_95)
                    print(f"训练指标 - mAP50: {custom_model.map50}, mAP50-95: {custom_model.map50_95}, fitness: {custom_model.accuracy}")
                else:
                    # 如果 results_dict 不可用，尝试从其他属性获取
                    print(f"警告: 无法获取训练指标，results 类型: {type(results)}")
                    custom_model.map50 = 0
                    custom_model.map50_95 = 0
                    custom_model.accuracy = 0
                
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
            
            log_operation(f"模型训练完成:{custom_model.name},mAP50:{custom_model.map50}")
            
        except Exception as e:
            print(f"模型训练错误: {e}")
            import traceback
            traceback.print_exc()
            
            task = db.session.get(TrainingTask, task_id)
            custom_model = db.session.get(CustomModel, model_id)
            
            if task:
                task.status = 'failed'
                task.error_message = str(e)
            
            if custom_model:
                custom_model.status = 'failed'
            
            db.session.commit()


@app.route("/api/training/tasks/<int:task_id>/progress", methods=["GET"])
@require_auth
def get_training_progress(task_id):
    """获取训练任务实时进度"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify({
        "task_id": task.id,
        "status": task.status,
        "progress": task.progress,
        "current_epoch": task.current_epoch,
        "total_epochs": task.total_epochs,
        "loss": task.loss,
        "val_loss": task.val_loss
    })


@app.route("/api/models/<int:model_id>/publish", methods=["POST"])
@require_admin
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
@require_admin
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
        print(f"模型 {model.model_key} 已从内存中移除")
    
    log_operation(f"禁用模型:{model.name}")
    
    return jsonify({
        "success": True,
        "message": "模型已禁用"
    })


@app.route("/api/models/<int:model_id>/enable", methods=["POST"])
@require_admin
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
            print(f"模型 {model.model_key} 已加载到内存")
    except Exception as e:
        print(f"加载模型到内存失败: {e}")
        # 不影响启用操作，下次预测时会尝试加载
    
    log_operation(f"启用模型:{model.name}")
    
    return jsonify({
        "success": True,
        "message": "模型已启用"
    })


@app.route("/api/models/<int:model_id>", methods=["DELETE"])
@require_admin
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
    if model.model_path and os.path.exists(model.model_path):
        try:
            os.remove(model.model_path)
            deleted_items.append(f"模型文件: {os.path.basename(model.model_path)}")
        except Exception as e:
            errors.append(f"删除模型文件失败: {e}")
    
    # 3. 删除数据集目录
    if model.dataset_path and os.path.exists(model.dataset_path):
        try:
            import shutil
            shutil.rmtree(model.dataset_path)
            deleted_items.append(f"数据集目录: {os.path.basename(model.dataset_path)}")
        except Exception as e:
            errors.append(f"删除数据集失败: {e}")
    
    # 4. 删除训练运行目录 (runs/train/model_key)
    train_run_dir = os.path.join(UPLOADS, 'training_runs', model.model_key)
    if os.path.exists(train_run_dir):
        try:
            shutil.rmtree(train_run_dir)
            deleted_items.append(f"训练记录: {model.model_key}")
        except Exception as e:
            errors.append(f"删除训练记录失败: {e}")
    
    # 5. 删除相关的临时CBAM模型文件
    cbam_temp_pattern = f"cbam_temp_*_{model.model_key}.pt"
    cbam_temp_files = glob.glob(os.path.join(MODELS_DIR, cbam_temp_pattern))
    for temp_file in cbam_temp_files:
        try:
            os.remove(temp_file)
            deleted_items.append(f"临时文件: {os.path.basename(temp_file)}")
        except Exception as e:
            errors.append(f"删除临时文件失败: {e}")
    
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
    task = TrainingTask.query.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify(task.to_dict())


@app.route("/api/training/tasks/<int:task_id>/logs", methods=["GET"])
@require_auth
def get_training_logs(task_id):
    """获取训练日志"""
    task = TrainingTask.query.get(task_id)
    if not task or not task.log_file:
        return jsonify({"logs": ""})

    try:
        if os.path.exists(task.log_file):
            with open(task.log_file, 'r', encoding='utf-8') as f:
                logs = f.read()
            return jsonify({"logs": logs})
        else:
            return jsonify({"logs": ""})
    except Exception as e:
        return jsonify({"logs": f"读取日志失败: {str(e)}"})


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


if __name__ == "__main__":
    app.run(debug=True)
