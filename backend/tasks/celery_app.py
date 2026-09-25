"""Celery 应用实例

启动方式（工作目录必须是 backend/）：

    # 单 worker 串行处理两类任务（6GB 显存下的默认选择，见下）
    celery -A tasks.celery_app worker -l info -P solo -Q training,ingest

    # 或直接用它包好的脚本
    bash scripts/celery.sh start

--------------------------- 两个必须先讲的坑 ---------------------------

**1. `.env` 必须在读任何环境变量之前加载。**

`config.py` 自己不加载 `.env`，只有 `app.py` 和 `core/bootstrap.py` 加载。
worker 进程若直接 `from config import config`，`DATABASE_URL` 取不到，
配置会**静默回退到 SQLite**——任务照跑、照「成功」、日志照写，
只是数据全进了另一个库，Web 端什么也看不到且不报错。
这条排查起来非常费劲，所以这里第一件事就是 `load_env()`。

**2. Windows 只能 `-P solo`，而 solo 池不支持超时与强制终止。**

Celery 在 Windows 上不支持 prefork。solo 池不实现 `terminate_job`，因此：

- `task_time_limit` / `task_soft_time_limit` 设为非 None 时，
  **超时那一刻会抛 NotImplementedError**，任务反而卡死。必须都是 None。
- `revoke(terminate=True)` 同样无效。要停下已在执行的任务，
  只能靠任务自己周期性读取协作式停止标志（见 core/state.py 的 train:stop:*）。

`revoke()`（不带 terminate）是有效的，用于拦下**还在队列里没被消费**的任务。

--------------------------- 为什么队列这么分 ---------------------------

训练（YOLO）与入库（bge-m3 向量化）都要吃 GPU，而本机只有 6GB 显存。
solo 池的并发度恒为 1，两个队列在一个 worker 里天然串行，从而避免显存打架。
这个「串行」是刻意选择，不是妥协。

换更大显存后想并行，可以拆成两个 worker —— 但入库那个要走 CPU：

    RAG_DEVICE=cpu celery -A tasks.celery_app worker -l info -P solo -Q ingest -n ingest@%h
    celery -A tasks.celery_app worker -l info -P solo -Q training -n training@%h

`RAG_DEVICE` 在 `config.py` 里是模块导入时求值的，所以在启动命令前 export 即可生效，不用改代码。
"""
from core.bootstrap import load_env

# 必须先于下面 `import config` —— 理由见模块文档第 1 条
load_env()

from celery import Celery  # noqa: E402

from config import config  # noqa: E402

celery_app = Celery(
    'ortho',
    # 从 config 读而不是直接读 os.environ：环境变量名与默认值只在 config.py
    # 维护一份，避免两处各写各的然后慢慢对不上
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND,
    # 显式列出任务模块。不用 autodiscover：包名固定，写清楚更好读，
    # 也避免 autodiscover 去翻 tasks/ 下所有模块时把辅助模块也当任务模块导入。
    #
    # 注意 include 只影响 worker 的注册；Web 进程靠直接 import 任务模块来注册
    # （见 api/training.py、api/knowledge.py 的 .delay() 调用点）。
    # 漏写一个模块的症状是 worker 报 "Received unregistered task"，很好认。
    include=[
        'tasks.diagnostics',
        'tasks.knowledge',
        'tasks.training',
    ],
)

celery_app.conf.update(
    # ---------- 序列化 ----------
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Asia/Shanghai',
    enable_utc=True,

    # ---------- 状态可见性 ----------
    # 前端进度靠 DB 里的 TrainingTask/KnowledgeDoc 行，不靠这里。
    # 打开 STARTED 只是为了运维时能区分「在队列里」和「已在跑」
    task_track_started=True,
    result_expires=7 * 24 * 3600,

    # ---------- 池与并发 ----------
    worker_pool='solo',              # 冗余但必要：防止有人手敲命令时漏掉 -P solo
    worker_prefetch_multiplier=1,     # 长任务，一次只取一条，避免独占队列
    worker_redirect_stdouts=True,     # 任务内遗留的 print 仍会被转进日志
    worker_redirect_stdouts_level='INFO',

    # ---------- 超时：solo 池不支持，必须 None ----------
    # 设了非 None 会在超时时抛 NotImplementedError，反而把任务卡死。理由见模块文档第 2 条
    task_time_limit=None,
    task_soft_time_limit=None,

    # ---------- 投递语义：刻意选「至多一次」 ----------
    # acks_late=True 会让 worker 崩溃后任务被重新投递，对训练意味着
    # 重跑一遍几小时的训练。宁可丢失，由 core/recovery.py 把它标成 failed 让人决定是否重试
    task_acks_late=False,
    task_reject_on_worker_lost=False,

    # ---------- 队列路由 ----------
    task_default_queue='training',
    task_routes={
        'training.run': {'queue': 'training'},
        'knowledge.ingest': {'queue': 'ingest'},
        # 患者记录重切片与文档入库同类（都要跑嵌入模型），走同一个队列 ——
        # solo 池下两者天然串行，不会互相抢显存
        'knowledge.ingest_patient': {'queue': 'ingest'},
        'diagnostics.*': {'queue': 'training'},
    },

    # ---------- Redis 传输 ----------
    # visibility_timeout 只在 acks_late=True 时才会导致任务被重复投递。
    # 这里设大是防御性的：万一有人把 acks_late 改成 True，
    # 4 小时的训练也不会因为默认 1 小时的可见性超时被另一个 worker 领走跑第二遍
    broker_transport_options={'visibility_timeout': 12 * 3600},
    broker_connection_retry_on_startup=True,
)
