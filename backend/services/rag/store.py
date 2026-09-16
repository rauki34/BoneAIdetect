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

def corpus_version():
    """切片集合的版本戳：任何入库都会改变它

    用于 RAG 缓存键。基于 count/max(id)/max(updated_at) 的 sha1，
    代价是三条聚合查询，因此调用方需自行做 60 秒节流。
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


def invalidate_cache():
    """入库成功后主动清掉检索缓存（见 services/rag/retriever.py）"""
    try:
        from services.rag.retriever import clear_caches
    except ImportError:
        return          # 检索层尚未就绪（阶段 7-1），无缓存可清
    try:
        clear_caches()
    except Exception as e:
        logger.warning('清理检索缓存失败: %s', e)
