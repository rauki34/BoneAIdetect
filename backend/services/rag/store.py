"""知识库 DDL 与数据访问

`db.create_all()` 只会建普通索引，它做不到三件事，全部在这里补：

1. **建扩展**：`CREATE EXTENSION vector` 必须在 `create_all()` **之前**执行，
   否则首次建 `knowledge_chunks` 会因为 `vector(1024)` 未知而失败。
   （阶段 5 是手工执行这条命令的，仓库里没有任何记录，换台机器必然踩。）
2. **建 HNSW / GIN 索引**：`create_all()` 只有 `Index()` 里声明的普通 B-tree。
3. **给已存在的表加列**：`create_all()` 对已存在的表完全不做改动，
   `ai_conversations.references` 就是靠 `ensure_columns()` 加上去的。

三条函数都幂等，且遵守同一套失败策略：**单条 DDL 失败只记 WARNING 并记入
返回值，不中断其余语句，更不阻断应用启动**。知识库是增强能力，
它坏了不该让医护用不了系统。
"""
from sqlalchemy import text

from utils.logger import logger

# 上一次 ensure_extensions() 里未能建立的扩展名，供索引/列阶段跳过依赖项
_missing_extensions = set()

# ---------- 扩展 ----------

_DDL_EXTENSIONS = (
    # 必需：向量列与 HNSW 索引都依赖它
    ("vector", "CREATE EXTENSION IF NOT EXISTS vector"),
    # 可选：仅用于管理界面的标题模糊搜索，缺失不影响检索
    ("pg_trgm", "CREATE EXTENSION IF NOT EXISTS pg_trgm"),
)

# ---------- 索引（必须在 create_all 之后） ----------

_DDL_INDEXES = (
    (
        'ix_kb_chunks_embedding_hnsw',
        """CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_hnsw
             ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
             WITH (m = 16, ef_construction = 64)""",
        'vector',
    ),
    (
        'ix_kb_chunks_content_trgm',
        """CREATE INDEX IF NOT EXISTS ix_kb_chunks_content_trgm
             ON knowledge_chunks USING gin (content gin_trgm_ops)""",
        'pg_trgm',
    ),
    (
        'ix_kb_docs_title_trgm',
        """CREATE INDEX IF NOT EXISTS ix_kb_docs_title_trgm
             ON knowledge_docs USING gin (title gin_trgm_ops)""",
        'pg_trgm',
    ),
)

# ---------- 新增列（create_all 不会给已有表加列） ----------

_DDL_COLUMNS = (
    (
        'ai_conversations.references',
        # references 是 SQL 保留字，必须加引号，否则 ADD COLUMN 直接语法错误
        'ALTER TABLE ai_conversations '
        'ADD COLUMN IF NOT EXISTS "references" TEXT',
    ),
    (
        # 阶段 8：训练任务搬到 Celery 后，停止排队中的任务要 revoke 它的 task id。
        # 列定义在 database.TrainingTask，但 create_all() 对**已存在**的表完全
        # 不做改动，所以必须在这里补一条。
        'training_tasks.celery_task_id',
        'ALTER TABLE training_tasks '
        'ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(64)',
    ),
)


def is_postgres() -> bool:
    """当前引擎是否 PostgreSQL（SQLite 降级启动时全部 DDL 跳过）"""
    from database import db
    return db.engine.dialect.name == 'postgresql'


def _run(statements, kind):
    """逐条执行 DDL

    每条独立事务：一条失败不影响后面的。返回 {名称: 是否成功}，
    调用方据此决定记 INFO 还是 WARNING。

    语句可以是 (名称, DDL) 或 (名称, DDL, 依赖扩展名)。依赖的扩展不存在时
    直接跳过并记 False——例如没装 pg_trgm 时装它的 GIN 索引只会白白报错。
    """
    from database import db

    # 依赖扩展不可用时跳过而不是硬报错：没装 pg_trgm 时去建它的 GIN 索引
    # 只会得到一堆无意义的权限/未知操作符报错
    missing = _missing_extensions if kind != '扩展' else set()

    results = {}
    for stmt in statements:
        name, ddl = stmt[0], stmt[1]
        requires = stmt[2] if len(stmt) > 2 else None
        if requires and requires in missing:
            results[name] = False
            logger.info('跳过 %s [%s]：依赖的扩展 %s 不可用', kind, name, requires)
            continue
        try:
            with db.engine.begin() as conn:
                conn.execute(text(ddl))
            results[name] = True
        except Exception as e:
            results[name] = False
            logger.warning(
                '知识库 %s 失败 [%s]: %s。若为权限问题，需超级用户执行 %s',
                kind, name, e, ddl.strip().split('\n')[0],
            )
    return results


def ensure_extensions():
    """建扩展。**必须在 db.create_all() 之前调用**"""
    global _missing_extensions
    if not is_postgres():
        return {'enabled': False, 'reason': 'not-postgresql'}
    results = _run(_DDL_EXTENSIONS, '扩展')
    _missing_extensions = {name for name, ok in results.items() if not ok}
    return {'enabled': True, **results}


def ensure_indexes():
    """建 HNSW / GIN 索引。**必须在 db.create_all() 之后调用**"""
    if not is_postgres():
        return {'enabled': False, 'reason': 'not-postgresql'}
    return {'enabled': True, **_run(_DDL_INDEXES, '索引')}


def ensure_columns():
    """补齐新增列。**必须在 db.create_all() 之后调用**"""
    if not is_postgres():
        return {'enabled': False, 'reason': 'not-postgresql'}
    return {'enabled': True, **_run(_DDL_COLUMNS, '新增列')}


# ---------- 中断任务回收 ----------

STALE_MINUTES = 30


def recover_stale_docs():
    """把卡在 processing 的文档置为 failed

    入库中途崩溃（或断电）会留下永久 processing 的行，管理界面上看不出区别。
    本函数在启动时回收它们。返回回收条数。
    """
    from database import KnowledgeDoc, db
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=STALE_MINUTES)
    stale = KnowledgeDoc.query.filter(
        KnowledgeDoc.status == 'processing',
        KnowledgeDoc.updated_at < cutoff,
    ).all()
    if not stale:
        return 0
    for doc in stale:
        doc.status = 'failed'
        doc.error_msg = '入库中断（进程退出或崩溃），请重新入库'
    db.session.commit()
    return len(stale)


# ---------- 语料版本戳（缓存失效依据） ----------

CORPUS_VER_KEY = 'rag:corpus_version'
CORPUS_VER_TTL = 60

# Redis 不可用时的进程内节流（降级，与 core/cache.py 的口径一致）
_local_ver = None
_local_ver_at = 0.0


def corpus_version():
    """切片集合的版本戳：任何入库都会改变它

    用于 RAG 缓存键。基于 count/max(id) 的 sha1，代价是一次聚合查询，
    因此调用方需自行节流 —— 见 cached_corpus_version()。
    """
    import hashlib

    from database import KnowledgeChunk, db
    from sqlalchemy import func

    row = db.session.query(
        func.count(KnowledgeChunk.id),
        func.max(KnowledgeChunk.id),
    ).first()
    count, max_id = (row[0] or 0), (row[1] or 0)
    return hashlib.sha1(f'{count}|{max_id}'.encode()).hexdigest()[:16]


def cached_corpus_version():
    """带节流的语料版本戳 —— 检索侧应该用这个

    **节流状态放在 Redis 而不是进程内**，这是阶段 8 把入库搬去 Celery 后的
    必需项。worker 与 API 是两个进程：worker 入库完成后，API 进程若只在本地
    缓存版本戳，最多 60 秒仍会用旧版本算缓存键。症状是「刚上传的文档搜不到」，
    60 秒后自愈 —— 无法复现，极难排查。

    放进 Redis 后，worker 侧的 invalidate_cache() 删掉这个键，
    所有进程的下一次调用都会重新计算，立刻看到新语料。
    """
    global _local_ver, _local_ver_at

    from core.cache import get_redis

    client = get_redis()
    if client is not None:
        try:
            cached = client.get(CORPUS_VER_KEY)
            if cached:
                return cached if isinstance(cached, str) else cached.decode()
            ver = corpus_version()
            client.setex(CORPUS_VER_KEY, CORPUS_VER_TTL, ver)
            return ver
        except Exception as e:
            logger.warning('语料版本戳读写 Redis 失败，退回进程内节流: %s', e)

    # 降级：Redis 不可用时退回进程内节流（多进程下会各自算各自的，
    # 但此时 broker 也不可用，不存在"worker 改了而 API 不知道"的场景）
    import time
    now = time.time()
    if _local_ver and now - _local_ver_at < CORPUS_VER_TTL:
        return _local_ver
    _local_ver = corpus_version()
    _local_ver_at = now
    return _local_ver


def invalidate_cache():
    """入库成功后主动清掉检索缓存（见 services/rag/retriever.py）

    这个函数现在**由 worker 进程调用**（阶段 8 起入库在 Celery 里跑），
    而它要影响的是 API 进程的检索结果。所以清的是 Redis 里的共享状态，
    不是本进程的内存 —— 后者清了也没用。
    """
    # 先删版本戳：它是 Redis 缓存键的组成部分（见 retriever._cache_key），
    # 删掉后所有进程的下一跳都会重算，拿到新语料。
    # 注：下面 clear_caches() 的 `rag:*` 扫描其实也会删到它，
    # 但这里显式删一次，免得哪天有人把那个扫描范围收窄了而无声退化。
    try:
        from core.cache import get_redis
        client = get_redis()
        if client is not None:
            client.delete(CORPUS_VER_KEY)
    except Exception as e:
        logger.warning('清理语料版本戳失败: %s', e)

    try:
        from services.rag.retriever import clear_caches
    except ImportError:
        return          # 检索层尚未就绪（阶段 7-1），无缓存可清
    try:
        clear_caches()
    except Exception as e:
        logger.warning('清理检索缓存失败: %s', e)
