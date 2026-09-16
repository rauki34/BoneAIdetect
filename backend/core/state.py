"""进程内共享状态

从 app.py 抽出。各蓝图与辅助模块直接 import 这些对象，
由于它们都是**原地修改**的 dict/list（不做重新绑定），
因此共享的是同一个对象引用，拆分后行为不变。

注意：这些状态都在单个进程内，多进程部署（如 gunicorn 多 worker）
时不共享。后续阶段迁至 Redis。
"""
import os
from collections import defaultdict
from threading import Lock

from ultralytics import YOLO

from core.paths import MODEL_CANDIDATES
from utils.logger import logger

# ---------- 验证码 ----------
# {captcha_id: {'code': 'ABC1', 'expire_time': timestamp}}
captcha_store = {}
CAPTCHA_TIMEOUT = 300   # 5 分钟过期

# ---------- YOLO 模型 ----------
models = {}


def load_models():
    """加载预置模型（仅加载存在的权重文件，避免启动失败）"""
    loaded = {}
    for name, path in MODEL_CANDIDATES.items():
        if os.path.exists(path):
            try:
                loaded[name] = YOLO(path)
                logger.info(f"Loaded model {name} from {path}")
            except Exception as e:
                logger.error(f"Failed to load model {name} from {path}: {e}")
        else:
            logger.info(f"Model file for {name} not found at {path}, skipping")
    return loaded


def init_models():
    """启动时调用，把预置模型装入 models"""
    models.update(load_models())
    return models


# ---------- 限流 ----------
# {key: [timestamp, ...]}
rate_limit_storage = defaultdict(list)
rate_limit_lock = Lock()

def _env_int(key, default):
    """从环境变量读取整数阈值（.env 已由 app.py 在最顶部加载）"""
    raw = os.environ.get(key)
    try:
        return int(raw) if raw not in (None, '') else default
    except ValueError:
        return default


# 限流配置：按防护目标分层，key 的选择见 core/ratelimit.limit()
#   login / register —— 认证层，按 IP（攻击者用随机用户名，按账号拦不住）
#   ai_chat          —— 成本层，按用户（token 计费，成本归属需清晰）
#   api_general      —— 通用层，按用户或 IP
#
# 阈值可用环境变量覆盖，便于测试环境放宽（RATE_LIMIT_LOGIN=100 等）
RATE_LIMIT_CONFIG = {
    'login': {                    # 登录：防爆破、撞库
        'max_requests': _env_int('RATE_LIMIT_LOGIN', 5),
        'time_window': 60,
    },
    'register': {                 # 注册：防脚本批量注册
        'max_requests': _env_int('RATE_LIMIT_REGISTER', 3),
        'time_window': 300,
    },
    'captcha': {                  # 验证码：防批量拉取
        'max_requests': _env_int('RATE_LIMIT_CAPTCHA', 20),
        'time_window': 60,
    },
    'ai_chat': {                  # AI 调用：控成本
        'max_requests': _env_int('RATE_LIMIT_AI', 10),
        'time_window': 60,
    },
    'api_general': {
        'max_requests': _env_int('RATE_LIMIT_GENERAL', 100),
        'time_window': 60,
    },
    'kb_upload': {                # 知识库上传：入库会跑 GPU 且同步执行，须从严
        'max_requests': _env_int('RATE_LIMIT_KB_UPLOAD', 10),
        'time_window': 300,
    },
    'kb_search': {                # 知识库检索预览：比通用接口宽松，供调参用
        'max_requests': _env_int('RATE_LIMIT_KB_SEARCH', 60),
        'time_window': 60,
    },
}

# ---------- 视频流 ----------
video_tasks = {}          # {task_id: {...}}
# 注：flask_sock 的 Sock 扩展需绑定 app 实例，其路由保留在 app.py

# ---------- 模型训练 ----------
training_tasks = {}       # {task_id: {...}}
training_stop_flags = {}  # {task_id: bool}
