"""项目路径与模型文件映射

从 app.py 抽出，供各蓝图模块共用。
"""
import os

# 项目根目录（backend/）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UPLOADS = os.path.join(BASE_DIR, "uploads")
RESULTS = os.path.join(BASE_DIR, "results")
MODELS_DIR = os.path.join(BASE_DIR, "models")

# 启动时确保目录存在
for _d in (UPLOADS, RESULTS, MODELS_DIR):
    os.makedirs(_d, exist_ok=True)

# 预置模型：模型键 -> 权重文件路径
MODEL_CANDIDATES = {
    "yolov8n": os.path.join(MODELS_DIR, "yolov8n.pt"),
    "yolov8s": os.path.join(MODELS_DIR, "yolov8s.pt"),
    "yolov8m": os.path.join(MODELS_DIR, "yolov8m.pt"),
    "yolo11n": os.path.join(MODELS_DIR, "yolo11n.pt"),
    "yolo11s": os.path.join(MODELS_DIR, "yolo11s.pt"),
    "yolo11m": os.path.join(MODELS_DIR, "yolo11m.pt"),
    "yolo26n": os.path.join(MODELS_DIR, "yolo26n.pt"),
}

# 基础模型到实际模型文件名的映射（训练时加载用）
BASE_MODEL_MAP = {
    "yolov8n": "yolov8n",
    "yolov8s": "yolov8s",
    "yolov8m": "yolov8m",
    "yolo11n": "yolo11n",
    "yolo11s": "yolo11s",
    "yolo11m": "yolo11m",
    "yolo26n": "yolo26n",
}
