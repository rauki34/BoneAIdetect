"""模型训练与数据集管理接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import glob
import json
import os
import shutil
import time
from datetime import datetime

from flask import Blueprint, jsonify, request
from ultralytics import YOLO

from core.auth import get_current_user, require_auth, require_role
from core.helpers import log_operation
from core.paths import BASE_DIR, BASE_MODEL_MAP, MODELS_DIR, UPLOADS
from core.state import models, set_training_stop
from database import CustomModel, TrainingTask, db
from utils.logger import logger

# 阶段 8：训练执行逻辑已迁至 tasks/training.py 并由 Celery worker 运行。
# 随之移除的导入：threading / sys / torch（裸线程与 stdout 劫持已不在本进程）
# 与 Logger（训练日志现在由 worker 侧的 FileHandler 写）。

bp = Blueprint('training', __name__)

# ==================== 数据集管理接口 ====================

@bp.route("/api/datasets", methods=["GET"])
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

@bp.route("/api/datasets", methods=["POST"])
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

@bp.route("/api/datasets/<int:dataset_id>", methods=["PUT"])
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
    
    data = request.get_json(silent=True)
    if 'name' in data:
        dataset.name = data['name'].strip()
    if 'description' in data:
        dataset.description = data['description']
    
    db.session.commit()
    log_operation(f"更新数据集:{dataset.name}")
    return jsonify({"success": True, "data": dataset.to_dict()})

@bp.route("/api/datasets/<int:dataset_id>", methods=["DELETE"])
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

@bp.route("/api/datasets/all", methods=["GET"])
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

# ==================== 模型训练管理接口 ====================
# training_tasks / training_stop_flags 已抽至 core.state

@bp.route("/api/models", methods=["GET"])
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

@bp.route("/api/models/published", methods=["GET"])
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

@bp.route("/api/models/train", methods=["POST"])
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

    if is_continued_training:
        base_model_path = base_model_info.model_path
    else:
        base_model_path = BASE_MODEL_MAP.get(base_model, base_model)

    # 投递到 Celery（阶段 8）。原先这里是裸 threading.Thread：Web 进程一重启
    # 任务就没了，且多进程部署时停止标志不共享。现在换成队列，任务持久化在
    # Redis 里，由独立的 worker 进程执行。
    err = _enqueue_training(task, custom_model, base_model_path, dataset_dir,
                            epochs, batch_size, img_size,
                            is_continued_training, use_best_hyperparams, username)
    if err is not None:
        # 队列不可用时把刚建的两行清掉：留着会让界面上出现一个永远不会动的
        # "训练中"模型，而且它的 status 是 training，医生端不会列出来但也删不掉
        db.session.delete(task)
        db.session.delete(custom_model)
        db.session.commit()
        return jsonify({"success": False, "error": err}), 503

    log_operation(f"开始训练模型:{model_name},基础模型:{base_model},创建者:{username}")

    return jsonify({
        "success": True,
        "model_id": custom_model.id,
        "task_id": task.id,
        "message": "模型训练任务已提交队列"
    })


def _enqueue_training(task, custom_model, base_model_path, dataset_dir, epochs,
                      batch_size, img_size, is_continued_training,
                      use_best_hyperparams, username):
    """投递训练任务；成功返回 None，失败返回给用户看的错误文案

    broker 不可用时 `.delay()` 会抛 OperationalError。不处理的话请求直接 500
    并留下一条永远 running 的记录，所以这里必须捕获并回滚。
    """
    from tasks.training import run_training_task
    try:
        async_result = run_training_task.delay(
            task.id, custom_model.id, base_model_path, dataset_dir,
            epochs, batch_size, img_size,
            is_continued_training, use_best_hyperparams, username=username,
        )
    except Exception as e:
        logger.error('投递训练任务失败(task_id=%s): %s', task.id, e, exc_info=True)
        db.session.rollback()
        return ('任务队列不可用，训练未启动。请确认 Redis 与 Celery worker 已启动'
                '（bash scripts/redis.sh start && bash scripts/celery.sh start）')

    # 记下 Celery 的 task id：停止时若任务还在队列里没被消费，
    # 只能靠 revoke(它) 拦住；协作式停止标志对还没开始的任务不起作用
    task.celery_task_id = async_result.id
    db.session.commit()
    return None

@bp.route("/api/training/tasks/<int:task_id>/progress", methods=["GET"])
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

@bp.route("/api/models/<int:model_id>/publish", methods=["POST"])
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

@bp.route("/api/models/<int:model_id>/disable", methods=["POST"])
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

@bp.route("/api/models/<int:model_id>/enable", methods=["POST"])
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

@bp.route("/api/models/<int:model_id>", methods=["DELETE"])
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

@bp.route("/api/models/cleanup-orphaned", methods=["POST"])
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

@bp.route("/api/training/tasks", methods=["GET"])
@require_auth
def get_training_tasks():
    """获取训练任务列表"""
    tasks = TrainingTask.query.order_by(TrainingTask.created_at.desc()).all()
    return jsonify({
        'tasks': [task.to_dict() for task in tasks]
    })

@bp.route("/api/training/tasks/<int:task_id>", methods=["GET"])
@require_auth
def get_training_task(task_id):
    """获取训练任务详情"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify(task.to_dict())

@bp.route("/api/training/tasks/<int:task_id>/logs", methods=["GET"])
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

@bp.route("/api/training/tasks/<int:task_id>/stop", methods=["POST"])
@require_auth
def stop_training_task(task_id):
    """终止训练任务"""
    task = db.session.get(TrainingTask, task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    # 检查任务状态
    if task.status != 'running':
        return jsonify({"error": f"任务当前状态为 {task.status}，无法终止"}), 400

    # 停止要覆盖**两种**情形，缺一不可：
    #   1. 任务还在队列里没被消费 —— 标志没用（worker 还没读它），
    #      必须 revoke 把消息从队列里撤掉；
    #   2. 任务已经在跑 —— revoke 在 solo 池下**无效**（没有 terminate_job），
    #      只能靠协作式标志，由训练回调每轮读一次。
    revoked = _revoke_training(task.celery_task_id)

    # 设置停止标志（Redis，跨进程可读）
    set_training_stop(task_id)

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
        # 两种情形的用户预期不同，文案要分开：撤销掉排队任务就是立刻结束；
        # 已在跑的任务只能等当前 epoch 跑完，别让用户以为它已经停了
        "message": ("训练任务已终止（尚未开始，已从队列撤销）" if revoked
                    else "已发出终止请求，任务将在当前轮次结束后停止"),
        "revoked": revoked,
    })


def _revoke_training(celery_task_id):
    """把还在队列里的训练任务撤下来；返回是否撤到

    只对**尚未被 worker 取走**的任务有效。已经在跑的任务在 solo 池下无法
    强制中断（solo 不实现 terminate_job），那种情况由 set_training_stop 的
    协作式标志兜底。两者是互补的，不是二选一。
    """
    if not celery_task_id:
        return False
    try:
        from tasks.celery_app import celery_app
        celery_app.control.revoke(celery_task_id, terminate=False)
        logger.info('已撤销排队中的训练任务: %s', celery_task_id)
        return True
    except Exception as e:
        # revoke 走的是 broker：Redis 不可用时这里会失败。
        # 此时训练任务本来就跑不起来，记一条日志即可，不必让停止接口报错
        logger.warning('撤销排队中的训练任务失败(%s): %s', celery_task_id, e)
        return False

