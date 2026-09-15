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

# 限流配置（键名与结构须与 consume 处保持一致）
RATE_LIMIT_CONFIG = {
    'ai_chat': {
        'max_requests': 10,   # 最大请求数
        'time_window': 60,    # 时间窗口(秒)
    },
    'api_general': {
        'max_requests': 100,
        'time_window': 60,
    },
}

# ---------- 视频流 ----------
video_tasks = {}          # {task_id: {...}}
# 注：flask_sock 的 Sock 扩展需绑定 app 实例，其路由保留在 app.py

# ---------- 模型训练 ----------
training_tasks = {}       # {task_id: {...}}
training_stop_flags = {}  # {task_id: bool}
