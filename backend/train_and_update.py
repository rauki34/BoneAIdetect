import os
import shutil
from ultralytics import YOLO

# -----------------------------
# 1️⃣ 数据集路径
# -----------------------------
DATASET_PATH = r"D:/grauateDesign/dataset/break-bone"
DATA_YAML = os.path.join(DATASET_PATH, "data.yaml")  # 需要提前创建 data.yaml

# -----------------------------
# 2️⃣ 模型参数
# -----------------------------
PRETRAINED_MODEL = "yolo11n.pt"  # 预训练权重
EPOCHS = 100
IMGSZ = 640
BATCH = 8
MODEL_NAME = "break_bone_yolo11"

# -----------------------------
# 3️⃣ 输出目录
# -----------------------------
TRAIN_RUNS_DIR = "runs/train"
FLASK_MODEL_DIR = "models"
FLASK_MODEL_PATH = os.path.join(FLASK_MODEL_DIR, "yolo11n.pt")
os.makedirs(FLASK_MODEL_DIR, exist_ok=True)

# -----------------------------
# 4️⃣ 主函数 (Windows 多进程安全)
# -----------------------------
if __name__ == "__main__":
    # 检查 GPU
    import torch
    device_id = 0 if torch.cuda.is_available() else -1
    print(f"设备信息: {device_id} | CUDA 可用: {torch.cuda.is_available()} | GPU 数量: {torch.cuda.device_count()}")

    # 创建模型
    print("🚀 开始训练 YOLO11 骨折检测模型...")
    model = YOLO(PRETRAINED_MODEL)

    # 开始训练
    model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        name=MODEL_NAME,
        workers=4,
        device=device_id,   # 使用 GPU
        verbose=True,
        augment=True
    )

    # -----------------------------
    # 5️⃣ 获取训练好的权重
    # -----------------------------
    def find_best_weight(model_name):
        # 常规位置
        cand = os.path.join(TRAIN_RUNS_DIR, model_name, "weights", "best.pt")
        if os.path.exists(cand):
            return cand
        # 支持 runs/detect 或其它 runs 子目录
        for root_dir in ("runs/train", "runs/detect", "runs"):
            path = os.path.join(root_dir, model_name, "weights", "best.pt")
            if os.path.exists(path):
                return path
        # 回退：在 runs 目录下查找任意 best.pt
        for root, dirs, files in os.walk("runs"):
            if "best.pt" in files:
                return os.path.join(root, "best.pt")
        return None

    best_weight_path = find_best_weight(MODEL_NAME)
    if best_weight_path and os.path.exists(best_weight_path):
        shutil.copy(best_weight_path, FLASK_MODEL_PATH)
        print(f"✅ 训练完成，模型已复制到 Flask 后端: {FLASK_MODEL_PATH}")
    else:
        print("❌ 未找到训练好的模型，请检查训练是否成功。")

    # -----------------------------
    # 6️⃣ 验证模型
    # -----------------------------
    print("🔍 开始验证模型...")
    val_results = model.val(data=DATA_YAML)

    # 尽量兼容不同版本 ultralytics 的返回类型（对象、dict 或属性为 dict）
    results = {}
    if isinstance(val_results, dict):
        results = val_results
    else:
        res_attr = getattr(val_results, "results_dict", None)
        try:
            if callable(res_attr):
                results = res_attr()
            elif isinstance(res_attr, dict):
                results = res_attr
            elif isinstance(val_results, (list, tuple)) and len(val_results) > 0:
                # 有时返回列表，尝试第一个元素
                first = val_results[0]
                r2 = getattr(first, "results_dict", None)
                if callable(r2):
                    results = r2()
                elif isinstance(r2, dict):
                    results = r2
        except Exception:
            results = {}

    print("\n🎯 验证结果:")
    if results:
        for cls_name, metrics in results.items():
            if not isinstance(metrics, dict):
                continue
            P = metrics.get('P') if metrics.get('P') is not None else metrics.get('precision', 0.0)
            R = metrics.get('R') if metrics.get('R') is not None else metrics.get('recall', 0.0)
            mAP50 = metrics.get('mAP50') if metrics.get('mAP50') is not None else metrics.get('map50', 0.0)
            mAP5095 = metrics.get('mAP50-95') if metrics.get('mAP50-95') is not None else metrics.get('map50_95', 0.0)
            try:
                print(f"{cls_name:25} | P: {P:.3f} | R: {R:.3f} | mAP50: {mAP50:.3f} | mAP50-95: {mAP5095:.3f}")
            except Exception:
                print(f"{cls_name:25} | metrics: {metrics}")
    else:
        print("未能解析验证结果的指标（返回结构可能与当前脚本不匹配）。")

    # 可选：打印 summary 表格（仅在对象有该方法时）
    if hasattr(val_results, 'summary') and callable(getattr(val_results, 'summary')):
        try:
            val_results.summary()
        except Exception:
            pass
