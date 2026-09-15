"""认证接口：登录 / 注册 / 登出 / 验证码 / 找回密码

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import io
import random
import time
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from flask_jwt_extended import create_access_token
from PIL import Image, ImageDraw, ImageFont
from werkzeug.security import check_password_hash, generate_password_hash

from core.auth import get_current_user, require_auth
from core.captcha import check_captcha
from core.helpers import log_operation
from core.ratelimit import limit
from core.state import CAPTCHA_TIMEOUT, captcha_store
from core.validators import (
    validate_email, validate_password, validate_phone,
    validate_role, validate_username,
)
from database import PatientProfile, User, db
from utils.logger import logger

bp = Blueprint('auth', __name__)

# ==================== 用户认证接口 ====================

@bp.route("/api/login", methods=["POST"])
@limit('login', key='ip')     # 按 IP 防爆破：攻击者用随机用户名，按账号拦不住
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    expected_role = data.get("role", "").strip()  # 前端期望登录的角色

    # 校验验证码放在最前面：既阻断暴力破解，也避免通过
    # "用户不存在 / 密码错误" 的不同响应枚举出有效用户名
    ok, error = check_captcha(
        data.get("captcha", "").strip(),
        data.get("captcha_id", "").strip(),
    )
    if not ok:
        log_operation(f"登录失败:验证码校验未通过-{username or '(空用户名)'}",
                      success=False, error_msg=error)
        return jsonify({"error": error, "error_code": "CAPTCHA_001"}), 400

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        log_operation(f"登录失败:用户不存在-{username}", success=False, error_msg="用户不存在")
        return jsonify({"error": "用户不存在"}), 401
    
    # 验证角色匹配 - 如果指定了期望角色，必须匹配
    if expected_role:
        # 患者登录入口只能登录患者账号
        if expected_role == 'patient' and user.role != 'patient':
            log_operation(f"登录失败:角色不匹配-{username}(尝试以患者身份登录{user.role}账号)", 
                         success=False, error_msg="请使用正确的登录入口")
            return jsonify({"error": "该账号不是患者账号，请使用对应的登录入口"}), 403
        
        # 医生登录入口只能登录医生账号
        if expected_role == 'doctor' and user.role != 'doctor':
            log_operation(f"登录失败:角色不匹配-{username}(尝试以医生身份登录{user.role}账号)", 
                         success=False, error_msg="请使用正确的登录入口")
            return jsonify({"error": "该账号不是医生账号，请使用对应的登录入口"}), 403
    
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
            logger.info(f"登录失败: 用户 {username} 密码验证失败（已哈希密码）")
            log_operation(f"登录失败:密码错误-{username}", success=False, error_msg="密码错误")
            return jsonify({"error": "密码错误"}), 401
    else:
        # 未哈希的密码（兼容旧数据）
        if user.password != password:
            logger.info(f"登录失败: 用户 {username} 密码验证失败（未哈希密码）")
            log_operation(f"登录失败:密码错误-{username}", success=False, error_msg="密码错误")
            return jsonify({"error": "密码错误"}), 401
    
    # 根据角色确定重定向URL
    redirect_urls = {
        'admin': '/admin',
        'doctor': '/doctor',
        'patient': '/patient'
    }
    redirect_url = redirect_urls.get(user.role, '/patient')  # 默认重定向到patient页面
    
    logger.info(f"登录成功: 用户 {username}, 角色 {user.role}")
    log_operation(f"用户登录:{username}")

    # 签发 JWT。expires_delta 留空则使用 config.py 的 JWT_ACCESS_TOKEN_EXPIRES
    access_token = create_access_token(
        identity=user.username,
        additional_claims={'role': user.role, 'uid': user.id},
    )

    return jsonify({
        "success": True,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name,
        "redirect_url": redirect_url,
        "access_token": access_token,   # 前端存入 localStorage，后续请求带 Authorization
    })

@bp.route("/api/register", methods=["POST"])
@limit('register', key='ip')  # 防脚本批量注册
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    password_confirm = data.get("password_confirm", "").strip()
    captcha = data.get("captcha", "").strip().upper()
    captcha_id = data.get("captcha_id", "").strip()
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
    
    if password != password_confirm:
        return jsonify({"error": "两次输入的密码不一致"}), 400
    
    # 验证角色值必须是admin/doctor/patient之一
    if not validate_role(role):
        return jsonify({"error": "角色必须是admin、doctor或patient之一"}), 400
    
    # 限制自注册只能选择doctor或patient角色
    if role == 'admin':
        return jsonify({"error": "不能通过自注册创建管理员账户"}), 403
    
    # 验证邮箱格式
    valid, error_msg = validate_email(email)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    # 验证电话格式
    valid, error_msg = validate_phone(phone)
    if not valid:
        return jsonify({"error": error_msg}), 400
    
    # 验证验证码（公共逻辑见 check_captcha）
    ok, error = check_captcha(captcha, captcha_id)
    if not ok:
        return jsonify({"error": error}), 400

    # 检查用户是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 409
    
    # 创建新用户
    new_user = User(
        username=username,
        password=generate_password_hash(password),
        role=role,
        full_name=full_name if full_name else None,
        email=email if email else None,
        phone=phone if phone else None
    )
    db.session.add(new_user)
    db.session.flush()  # 获取用户ID
    
    # 如果注册的是患者，创建患者档案
    if role == 'patient':
        patient_number = f"P{datetime.now().strftime('%Y%m%d')}{new_user.id:04d}"
        patient_profile = PatientProfile(
            user_id=new_user.id,
            patient_number=patient_number,
            gender='男'  # 默认性别
        )
        db.session.add(patient_profile)
    
    db.session.commit()
    
    # 清除session中的验证码
    session.pop('captcha', None)
    
    log_operation(f"用户注册:{username},角色:{role}")
    
    return jsonify({
        "success": True,
        "message": "注册成功",
        "username": username,
        "role": role
    }), 201

@bp.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    """用户登出
    
    记录用户登出操作到日志
    
    需求: 14.1
    """
    user = get_current_user()
    username = user.username if user else 'unknown'
    
    # 记录登出日志
    log_operation(f"用户登出:{username}")
    
    return jsonify({
        "success": True,
        "message": "登出成功"
    })

# ==================== 验证码接口 ====================

@bp.route("/api/captcha", methods=["GET"])
@limit('captcha', key='ip')   # 防批量拉取验证码
def generate_captcha():
    """生成验证码"""
    # 生成4位随机验证码
    captcha_text = "".join([random.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4)])
    
    # 生成唯一验证码ID
    captcha_id = "".join([random.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(16)])
    
    # 保存到内存存储
    captcha_store[captcha_id] = {
        'code': captcha_text,
        'expire_time': time.time() + CAPTCHA_TIMEOUT
    }
    
    # 清理过期验证码
    current_time = time.time()
    expired_keys = [k for k, v in captcha_store.items() if v['expire_time'] < current_time]
    for k in expired_keys:
        del captcha_store[k]
    
    logger.debug(f"[DEBUG] 生成验证码: {captcha_text}, captcha_id: {captcha_id}")
    
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
    
    # 返回图像，同时在header中返回captcha_id
    from flask import send_file, make_response
    response = make_response(send_file(buffer, mimetype='image/png'))
    response.headers['X-Captcha-ID'] = captcha_id
    return response

@bp.route("/api/captcha/verify", methods=["POST"])
def verify_captcha():
    """验证验证码

    修复：原实现从 session 读取验证码，而 generate_captcha 实际写入
    captcha_store，两者不匹配导致该接口恒返回"验证码已过期"。
    """
    data = request.json or {}
    ok, error = check_captcha(
        data.get("captcha", "").strip(),
        data.get("captcha_id", "").strip(),
    )
    if not ok:
        return jsonify({"error": error}), 400
    return jsonify({"success": True, "message": "验证码验证成功"})

# -------------------- 忘记密码 API --------------------

@bp.route("/api/forgot-password/verify", methods=["POST"])
def forgot_password_verify():
    """验证用户身份（忘记密码第一步）"""
    data = request.json
    username = data.get("username", "").strip()
    phone = data.get("phone", "").strip()
    captcha = data.get("captcha", "").strip().upper()
    captcha_id = data.get("captcha_id", "").strip()
    
    # 验证验证码
    if not captcha_id or not captcha:
        return jsonify({"error": "请输入验证码"}), 400
    
    captcha_data = captcha_store.get(captcha_id)
    if not captcha_data or captcha_data['expire_time'] < time.time():
        return jsonify({"error": "验证码已过期"}), 400
    
    if captcha != captcha_data['code'].upper():
        return jsonify({"error": "验证码错误"}), 400
    
    # 删除已使用的验证码
    del captcha_store[captcha_id]
    
    # 查找用户
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    # 验证手机号是否匹配
    if user.phone != phone:
        return jsonify({"error": "用户名和手机号不匹配"}), 400
    
    return jsonify({
        "success": True,
        "message": "身份验证通过"
    })

@bp.route("/api/forgot-password/reset", methods=["POST"])
def forgot_password_reset():
    """重置密码（忘记密码第二步）"""
    data = request.json
    username = data.get("username", "").strip()
    new_password = data.get("new_password", "").strip()
    
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "密码至少6位"}), 400
    
    # 查找用户
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    try:
        # 更新密码
        user.password = generate_password_hash(new_password)
        db.session.commit()
        
        log_operation(f"用户重置密码:{username}")
        
        return jsonify({
            "success": True,
            "message": "密码重置成功"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"重置密码失败: {e}")
        return jsonify({"error": "重置失败"}), 500
