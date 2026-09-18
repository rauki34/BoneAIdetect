# 加载 .env —— 必须位于任何项目模块导入之前。
# utils.logger 在**导入时**就会读取 LOG_LEVEL，若此时 .env 尚未加载，
# 其中的配置会被静默忽略。
import os
import threading
# 全部 9 个 @app.errorhandler 都用 datetime.utcnow() 拼响应里的 timestamp，
# 而这个导入此前**从未存在**：任何走到错误处理器的请求都会在处理器内部抛
# NameError，返回 500 的 HTML 调试页，而不是约定好的 JSON 错误体。
# 阶段 8 验证 broker 故障时，限流层因 Redis 不可用抛异常 → 撞上这个 bug，
# 才把它暴露出来。（正常路径不经过错误处理器，所以一直没被发现。）
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass   # 未安装 python-dotenv 时回退到系统环境变量

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from config import config_map
from database import db, init_db, migrate_from_json

# ==================== 应用与扩展 ====================

app = Flask(__name__)

# 配置优先级：环境变量 > config.py 默认值
# 通过 FLASK_ENV 切换配置类：development（默认） / production
app.config.from_object(
    config_map.get(os.environ.get('FLASK_ENV', 'development'), config_map['development'])
)

# 全局 CORS 配置
CORS(app, resources={
    r"/*": {
        "origins": app.config['CORS_ORIGINS'],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Username"],
        "expose_headers": ["X-Captcha-ID"],  # 暴露自定义header
        "supports_credentials": True  # 需要启用，因为使用session
    }
})

migrate = Migrate(app, db)      # 注册 migrate 扩展
jwt = JWTManager(app)           # JWT 认证（密钥与有效期来自 config.py）

# ==================== 导入共享模块 ====================
# 各业务域的实现已拆至 core/（通用能力）、services/（服务层）、api/（路由蓝图）
# RESULTS / UPLOADS 供下方 /results、/uploads 两个静态路由使用。
# 阶段 4 的收尾提交把这里的导入收窄成只剩 MODEL_CANDIDATES，静态路由随即
# 因 NameError 全部 500 —— 图片从此取不出来，且连续两个阶段无人察觉
# （没有测试真正取过图，冒烟只验证了接口返回了图片路径）。
from core.paths import MODEL_CANDIDATES, RESULTS, UPLOADS  # noqa: E402,F401
from core.state import (  # noqa: E402,F401
    RATE_LIMIT_CONFIG, init_models,
    load_models, models, rate_limit_lock, rate_limit_storage,
    training_stop_flags, training_tasks, video_tasks,
)
from core.auth import (  # noqa: E402,F401
    get_current_user, require_admin, require_auth, require_role,
)
from core.captcha import check_captcha  # noqa: E402,F401
from core.helpers import log_operation  # noqa: E402
from core.ratelimit import check_rate_limit, limit, rate_limit  # noqa: E402,F401
from core.security import (  # noqa: E402,F401
    detect_prompt_injection, filter_sensitive_content, sanitize_ai_input,
)
from core.validators import (  # noqa: E402,F401
    calculate_age, validate_email, validate_password,
    validate_phone, validate_role, validate_username,
)
from services.ai_service import (  # noqa: E402,F401
    _build_assistant_messages, call_ai_assistant_api, generate_ai_advice_async,
    get_ai_settings, get_llm_client, get_mock_reply,
)
from services.llm_client import (  # noqa: E402,F401
    LLMClient, LLMConfigError, LLMConnectionError, LLMError,
    LLMResponseError, LLMTimeoutError,
)
from utils.logger import logger  # noqa: E402,F401

# ==================== 初始化 ====================

init_db(app)

# 在应用启动时迁移 JSON 数据（如果存在）
with app.app_context():
    migrate_from_json(app)

init_models()   # 加载预置 YOLO 模型

# RAG 模型预热（默认关闭）。首次检索要等模型加载 10-30 秒，
# 预热把这段等待挪到启动阶段；默认关闭是为了不让启动时间变长，
# 需要时置 RAG_WARMUP=true。
if app.config.get('RAG_WARMUP'):
    def _warmup_rag():
        try:
            from services.rag.embedder import Embedder
            from services.rag.reranker import Reranker
            Embedder.instance().available
            Reranker.instance().available
            logger.info('✅ RAG 模型预热完成')
        except Exception as e:
            logger.warning('RAG 模型预热失败（不影响其余功能）: %s', e)

    threading.Thread(target=_warmup_rag, daemon=True).start()

# ==================== 蓝图注册 ====================
# 各业务域路由已拆至 api/ 包；路由保留完整路径（不使用 url_prefix），
# 因此 URL 与拆分前逐字一致
from api.admin import bp as admin_bp  # noqa: E402
from api.ai import bp as ai_bp  # noqa: E402
from api.analysis import bp as analysis_bp  # noqa: E402
from api.auth import bp as auth_bp  # noqa: E402
from api.detection import bp as detection_bp  # noqa: E402
from api.doctor import bp as doctor_bp  # noqa: E402
from api.knowledge import bp as knowledge_bp  # noqa: E402
from api.message import bp as message_bp  # noqa: E402
from api.patient import bp as patient_bp  # noqa: E402
from api.training import bp as training_bp  # noqa: E402

for _bp in (admin_bp, ai_bp, analysis_bp, auth_bp, detection_bp,
            doctor_bp, knowledge_bp, message_bp, patient_bp, training_bp):
    app.register_blueprint(_bp)


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









































# ==================== 静态文件接口 ====================

@app.route("/results/<path:filename>")
def get_result(filename):
    return send_from_directory(RESULTS, filename)


@app.route("/uploads/<path:filename>")
def get_upload(filename):
    return send_from_directory(UPLOADS, filename)






































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






















































































































































if __name__ == "__main__":
    # debug 由 FLASK_ENV 决定：development=True（默认，同改造前行为） / production=False
    app.run(debug=app.config.get('DEBUG', True))
