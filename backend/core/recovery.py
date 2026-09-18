"""中断任务的回收（阶段 8）

worker 崩溃、被 kill、或机器断电后，DB 里的任务行会永久停在执行中的状态：
训练任务停在 running（前端进度条永远卡住），入库文档停在 processing/pending
（管理界面显示"处理中"但永远不会变）。

启动时扫一遍，把它们标成失败，让人看到真实结果并决定是否重试。

**为什么分两处**：文档回收（`services/rag/store.recover_stale_docs`）属于
知识库模块，历史更长；这里只放阶段 8 新增的训练任务回收。两者由
`database.init_db()` 并列调用，失败策略一致：只记日志，绝不阻断启动。
"""
from datetime import datetime, timedelta

from utils.logger import logger

# 判定"卡死"的阈值。
#
# 取 2 小时而不是文档那边的 30 分钟，因为训练的心跳粒度是**每个 epoch 结束**
# （见 tasks/training.py 的 epoch 回调）：单个 epoch 超过 30 分钟的大数据集
# 属于正常情况，阈值定小了会把正在跑的任务误判为失败。代价是 worker 崩溃后
# 最长 2 小时才回收 —— 这个取舍是有意的，误杀正在跑的几小时训练更糟。
STALE_TRAINING_MINUTES = 120


def recover_stale_training_tasks():
    """把卡死的训练任务置为失败，返回回收条数

    同时扫 `running` 与 `pending`：`pending` 是"已建行但还没被 worker 取走"，
    Redis 重启丢掉队列消息时任务就永远停在 pending，只扫 running 会漏掉它。
    """
    from database import CustomModel, TrainingTask, db

    cutoff = datetime.utcnow() - timedelta(minutes=STALE_TRAINING_MINUTES)
    stale = TrainingTask.query.filter(
        TrainingTask.status.in_(('running', 'pending')),
        # updated_at 为 NULL 说明这行是加列之前建的，按 created_at 兜底判断
        db.or_(TrainingTask.updated_at < cutoff,
               db.and_(TrainingTask.updated_at.is_(None),
                       TrainingTask.created_at < cutoff)),
    ).all()

    if not stale:
        return 0

    for task in stale:
        logger.warning(
            '回收中断的训练任务: id=%s 状态=%s 最后更新=%s（worker 可能已崩溃）',
            task.id, task.status, task.updated_at or task.created_at)
        task.status = 'failed'
        task.error_message = ('任务中断（worker 进程退出或崩溃），'
                              f'最后活动于 {task.updated_at or task.created_at}')
        # 模型此时停在 training 状态：这个状态既不会被医生看到（只列 published），
        # 也不能再训练，属于死角，一并置为 failed
        model = db.session.get(CustomModel, task.model_id) if task.model_id else None
        if model is not None and model.status == 'training':
            model.status = 'failed'

    db.session.commit()
    return len(stale)
