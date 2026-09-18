"""YOLO 训练任务

从 `api/training.py` 的 `train_model_task` 迁来（阶段 8）。搬运时做了四类改动，
都不是形式调整，理由写在各自的位置上：

1. 应用上下文换成 worker 侧的（tasks/context.py）
2. 去掉 `sys.stdout` 全局劫持，改成任务专属的 FileHandler
3. 39 个 `print()` 改 logger —— 顺带达成 BASELINE 里「print < 20」的指标
4. 删掉收尾处往 Web 进程内存塞模型那一行（发布门禁，见下）
"""
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime

import torch

from tasks.celery_app import celery_app
from tasks.context import app_context
from utils.logger import logger


# ---------- 任务日志文件 ----------
#
# 原实现是 `sys.stdout = Logger(task.log_file)` —— 把整个进程的标准输出
# 重定向到训练日志文件。在 solo 池里这么做会把 Celery 自己的日志一起吞掉，
# 而且它是个全局副作用，任务结束前任何输出都会串到训练日志里。
#
# 改成给任务挂一个 FileHandler。文件路径与内容形态保持不变：
# GET /api/training/tasks/<id>/logs 读的就是这个文件的全文，前端用 <pre> 直接展示。

def _open_task_log(log_file):
    """给单个训练任务开一个写文件的 logger

    用独立的 logger 名字而不是往根 logger 上挂 handler：训练任务可能
    并发排队，共用一个 logger 会让两个任务的输出串台。
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    log = logging.getLogger(f'training.task.{os.getpid()}.{os.path.basename(log_file)}')
    log.setLevel(logging.INFO)
    log.propagate = False        # 不要冒泡到 Celery 的 root，避免重复输出

    handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    log.addHandler(handler)
    return log, handler


def _close_task_log(log, handler):
    """**必须** removeHandler

    只 close() 不摘 handler 的话，同一个 logger 对象上的 handler 会越积越多
    （旧的文件句柄也不释放，Windows 上还会锁住文件删不掉）。
    """
    try:
        log.removeHandler(handler)
        handler.close()
    except Exception:
        pass


@celery_app.task(name='training.run', bind=True)
def run_training_task(self, task_id, model_id, base_model_path, dataset_dir,
                      epochs, batch_size, img_size,
                      is_continued_training=False, use_best_hyperparams=False,
                      username=None):
    """异步训练模型任务

    返回 dict 而不是抛异常来表失败：训练失败是业务结果（可能只是数据集
    有问题），不需要 Celery 重试，状态已经落在 TrainingTask 行上。
    """
    from core.helpers import log_operation
    from core.state import (
        clear_training_stop, is_training_stop,
    )
    from core.paths import BASE_DIR, MODELS_DIR, UPLOADS
    from database import CustomModel, TrainingTask, db
    from ultralytics import YOLO

    with app_context():
        task = db.session.get(TrainingTask, task_id)
        custom_model = db.session.get(CustomModel, model_id)
        if not task or not custom_model:
            logger.warning('训练任务的目标记录不存在: task=%s model=%s', task_id, model_id)
            return {'status': 'missing'}

        model_key = custom_model.model_key
        model_name = custom_model.name
        task_log_file = task.log_file

    tlog, handler = _open_task_log(task_log_file) if task_log_file else (logger, None)

    try:
        # 续训用已有权重，标准训练用 models/ 下的基础模型
        if is_continued_training:
            if not os.path.exists(base_model_path):
                return _fail(task_id, model_id, tlog,
                             f'基础模型文件不存在: {base_model_path}')
            tlog.info('从已有模型继续训练: %s', base_model_path)
            model = YOLO(base_model_path)
        else:
            base_model_file = os.path.join(MODELS_DIR, f'{base_model_path}.pt')
            if os.path.exists(base_model_file):
                tlog.info('加载本地基础模型: %s', base_model_file)
                model = YOLO(base_model_file)
            else:
                tlog.warning('本地模型不存在，尝试从 Ultralytics 下载: %s', base_model_path)
                model = YOLO(base_model_path)

        data_yaml = _find_data_yaml(dataset_dir)
        if not data_yaml:
            return _fail(task_id, model_id, tlog, '未找到数据集配置文件 (data.yaml)')

        with app_context():
            task = db.session.get(TrainingTask, task_id)
            task.status = 'running'
            task.progress = 0
            task.current_epoch = 0
            db.session.commit()

        tlog.info('=' * 70)
        tlog.info('开始训练: %s', model_name)
        tlog.info('任务ID: %s', task_id)
        tlog.info('基础模型: %s', base_model_path)
        tlog.info('数据集: %s', data_yaml)
        tlog.info('配置: epochs=%s batch=%s img_size=%s 最佳超参=%s',
                  epochs, batch_size, img_size, use_best_hyperparams)
        tlog.info('=' * 70)

        train_args = {
            'data': data_yaml,
            'epochs': epochs,
            'batch': batch_size,
            'imgsz': img_size,
            'project': os.path.join(UPLOADS, 'training_runs'),
            'name': model_key,
            'exist_ok': True,
            'pretrained': True,
            'amp': True,
            'device': 0 if torch.cuda.is_available() else 'cpu',
            'verbose': False,
            'plots': True,
            'save': True,
            'workers': 0,
            'optimizer': 'SGD',
        }

        if use_best_hyperparams:
            best_hp_path = os.path.join(BASE_DIR, 'runs', 'best_hyperparams.json')
            if os.path.exists(best_hp_path):
                try:
                    with open(best_hp_path, 'r') as f:
                        train_args.update(json.load(f))
                    tlog.info('已合并最佳超参数')
                except Exception as e:
                    tlog.warning('超参数解析失败: %s', e)

        callback = _make_epoch_callback(task_id, epochs, tlog, is_training_stop)
        model.add_callback('on_train_epoch_end', callback)

        tlog.info('训练参数: %s', train_args)
        results = model.train(**train_args)

        # 用户点了停止：trainer.stop 只是让训练提前返回，模型是半成品。
        # 必须在写状态之前判断，否则会把 stopped 覆写成 completed 并复制半成品权重
        if is_training_stop(task_id):
            tlog.info('检测到停止标志，训练已提前结束，不产出模型')
            _finish(task_id, status='stopped', error_message='用户手动终止训练')
            with app_context():
                log_operation(f'模型训练已终止:{model_name}', username=username)
            return {'status': 'stopped'}

        best_model_path = os.path.join(
            UPLOADS, 'training_runs', model_key, 'weights', 'best.pt')

        if os.path.exists(best_model_path):
            with app_context():
                custom_model = db.session.get(CustomModel, model_id)
                shutil.copy(best_model_path, custom_model.model_path)
                custom_model.status = 'trained'
                _extract_metrics(results, custom_model)
                db.session.commit()

                tlog.info('=' * 70)
                tlog.info('训练完成: %s', model_name)
                tlog.info('  mAP@0.5:      %.4f', custom_model.map50)
                tlog.info('  mAP@0.5:0.95: %.4f', custom_model.map50_95)
                tlog.info('  精确率:        %.4f', custom_model.precision)
                tlog.info('  召回率:        %.4f', custom_model.recall)
                tlog.info('  F1-Score:     %.4f', custom_model.f1_score)
                tlog.info('  综合评分:      %.4f', custom_model.accuracy)
                tlog.info('模型保存路径: %s', custom_model.model_path)
                tlog.info('=' * 70)

                log_operation(
                    f'模型训练完成:{model_name},mAP50:{custom_model.map50}',
                    username=username)

            # 刻意**不**把模型加载进内存。
            # 原先那行 `models[model_key] = YOLO(...)` 有两个问题：
            #   1. 现在跑在 worker 里，加载到的是 worker 的内存，Web 进程用不到；
            #   2. 它绕过了发布门禁 —— 检测端只对 status='published' 的模型做
            #      按需加载（见 api/admin.py 的 available_models），而医生端本来就
            #      只列已发布模型。训练产物必须由管理员在模型库点「发布」后才可用。
            _finish(task_id, status='completed', progress=100.0, current_epoch=epochs,
                    completed=True)
            return {'status': 'completed', 'metrics': _metrics_dict(model_id)}

        tlog.error('训练结束但未找到模型文件: %s', best_model_path)
        return _fail(task_id, model_id, tlog, '训练完成但未找到模型文件')

    except Exception as e:
        tlog.exception('模型训练失败: %s', e)
        with app_context():
            log_operation(f'模型训练失败:{model_name}', False, str(e), username=username)
        _finish(task_id, status='failed', error_message=str(e))
        with app_context():
            custom_model = db.session.get(CustomModel, model_id)
            if custom_model:
                custom_model.status = 'failed'
                db.session.commit()
        return {'status': 'failed', 'error': str(e)}
    finally:
        clear_training_stop(task_id)
        if handler is not None:
            _close_task_log(tlog, handler)


# ---------- 辅助 ----------

def _make_epoch_callback(task_id, total_epochs, tlog, is_training_stop):
    """构造每轮结束时的回调：写进度、检查停止标志

    原先这个类定义在函数体内，且用 `with current_app.app_context()` 开新会话。
    这里改成显式提交 + 短事务：写进度是一次 UPDATE，不值得每轮都 commit 一次
    整个会话状态。
    """
    from database import TrainingTask, db

    state = {'last_update': 0.0, 'epochs_since_update': 0,
             'epoch_update_interval': max(1, total_epochs // 20)}

    def on_train_epoch_end(trainer):
        try:
            if is_training_stop(task_id):
                tlog.info('检测到停止标志，正在终止训练任务 %s ...', task_id)
                trainer.stop = True
                return

            current_epoch = trainer.epoch + 1
            progress = (current_epoch / total_epochs) * 100
            state['epochs_since_update'] += 1

            now = time.time()
            should_update_db = (
                now - state['last_update'] >= 5
                or state['epochs_since_update'] >= state['epoch_update_interval']
                or current_epoch == total_epochs
                or current_epoch == 1
            )

            loss = getattr(trainer, 'loss', None)
            loss_val = loss.item() if hasattr(loss, 'item') else loss

            if should_update_db:
                state['last_update'] = now
                state['epochs_since_update'] = 0
                with app_context():
                    task = db.session.get(TrainingTask, task_id)
                    # 用户可能已经点了停止（端点会把行置为 stopped），
                    # 这时不能再把进度写回去
                    if task and task.status == 'running':
                        task.current_epoch = current_epoch
                        task.progress = progress
                        if loss_val is not None and isinstance(loss_val, (int, float)):
                            task.loss = float(loss_val)
                        db.session.commit()

            if current_epoch % max(1, total_epochs // 10) == 0 or current_epoch <= 3:
                shown = f'{loss_val:.4f}' if isinstance(loss_val, (int, float)) else 'N/A'
                tlog.info('[Epoch %d/%d] 进度 %.1f%%，损失 %s',
                          current_epoch, total_epochs, progress, shown)
        except Exception as e:
            tlog.warning('更新训练进度失败: %s', e)

    return on_train_epoch_end


def _find_data_yaml(dataset_dir):
    for root, _dirs, files in os.walk(dataset_dir):
        for name in files:
            if name in ('data.yaml', 'dataset.yaml'):
                return os.path.join(root, name)
    return None


def _finish(task_id, *, status, progress=None, current_epoch=None,
            error_message=None, completed=False):
    """统一的收尾写状态

    先重读一遍：用户可能在训练跑着的时候点了停止，端点已经把行置为
    stopped。无条件覆写成 completed 会让"已停止"闪一下又变回"已完成"。
    """
    from database import TrainingTask, db

    with app_context():
        task = db.session.get(TrainingTask, task_id)
        if task is None:
            return
        if task.status == 'stopped' and status == 'completed':
            return
        task.status = status
        if progress is not None:
            task.progress = progress
        if current_epoch is not None:
            task.current_epoch = current_epoch
        if error_message is not None:
            task.error_message = error_message
        if completed:
            task.completed_at = datetime.utcnow()
        db.session.commit()


def _fail(task_id, model_id, tlog, message):
    from database import CustomModel, db

    tlog.error(message)
    _finish(task_id, status='failed', error_message=message)
    with app_context():
        custom_model = db.session.get(CustomModel, model_id)
        if custom_model:
            custom_model.status = 'failed'
            db.session.commit()
    return {'status': 'failed', 'error': message}


def _extract_metrics(results, model_obj):
    """从 ultralytics 的返回值里取指标

    保留原实现的多键名兼容（v8/v11 的键名不一致），只是去掉了 print。
    """
    rd = getattr(results, 'results_dict', {}) or {}
    mapping = {
        'map50': ['metrics/mAP50(B)', 'mAP50'],
        'map50_95': ['metrics/mAP50-95(B)', 'metrics/mAP50:0.95', 'mAP50-95'],
        'precision': ['metrics/precision(B)', 'precision'],
        'recall': ['metrics/recall(B)', 'recall'],
    }
    for field, keys in mapping.items():
        val = 0
        for k in keys:
            if k in rd:
                val = rd[k]
                break
        if val == 0 and hasattr(results, 'box'):
            box = results.box
            attr_map = {'map50': 'map50', 'map50_95': 'map',
                        'precision': 'mp', 'recall': 'mr'}
            val = getattr(box, attr_map[field], 0)
        setattr(model_obj, field, float(val))

    if model_obj.precision + model_obj.recall > 0:
        model_obj.f1_score = (2 * model_obj.precision * model_obj.recall
                              / (model_obj.precision + model_obj.recall))
    else:
        model_obj.f1_score = 0
    # 骨折检测更看重 mAP50 与 Recall（防漏检），沿用原权重
    model_obj.accuracy = (model_obj.map50 * 0.4
                          + model_obj.map50_95 * 0.3
                          + model_obj.f1_score * 0.3)


def _metrics_dict(model_id):
    from database import CustomModel, db

    with app_context():
        m = db.session.get(CustomModel, model_id)
        if m is None:
            return {}
        return {'map50': m.map50, 'map50_95': m.map50_95,
                'precision': m.precision, 'recall': m.recall,
                'f1': m.f1_score, 'accuracy': m.accuracy}
