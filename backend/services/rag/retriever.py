"""混合检索：向量 + BM25 → RRF 融合 → CrossEncoder 重排

为什么混合：纯向量对"Pilon 骨折""Schatzker 分型"这类专有名词不敏感
（罕见词在训练语料里出现少，向量表示不锐利），纯 BM25 又不懂同义表达。
医疗场景两者都需要，所以两路召回后用 RRF 融合。

**患者数据隔离是本模块的首要约束**，做法是把"作用域"变成一个必须显式传入的
对象，而不是一个容易忘记的过滤条件——细节见 RetrievalScope。
"""
import hashlib
import json
import os
import threading
import time

from sqlalchemy import or_, select

from core.paths import KNOWLEDGE_DIR
from database import KnowledgeChunk, KnowledgeDoc, db
from services.rag.embedder import Embedder
from services.rag.reranker import Reranker
from utils.logger import logger

# 语料版本戳的节流已移至 services/rag/store.py（阶段 8：状态放 Redis，
# 否则 worker 入库后本进程最多 60 秒看不到新语料）。见 cached_corpus_version()。
_retrieve_failure_until = 0.0
_FAILURE_COOLDOWN = 30

# 进程内缓存（Redis 只是加速层，Redis 挂了也必须能跑）
_bm25_lock = threading.Lock()
_bm25_cache = {}            # scope.signature -> (corpus_ver, BM25Okapi, [ids])
_local_cache = {}           # cache_key -> (expire_at, payload)
_local_cache_lock = threading.Lock()

_jieba_lock = threading.Lock()
_jieba_ready = False


def _cfg(key, default):
    try:
        from flask import current_app
        value = current_app.config.get(key)
        if value is not None:
            return value
    except Exception:
        pass
    return os.environ.get(key, default)


def _custom_dict_path():
    return os.path.join(KNOWLEDGE_DIR, 'jieba_dict.txt')


def tokenize(text):
    """jieba 分词（查询与语料必须用同一套词典，否则词法通道对不上）"""
    global _jieba_ready
    import jieba
    if not _jieba_ready:
        with _jieba_lock:
            if not _jieba_ready:
                path = _custom_dict_path()
                if os.path.exists(path):
                    try:
                        jieba.load_userdict(path)
                        logger.info('已加载医学分词词典: %s', path)
                    except Exception as e:
                        logger.warning('加载分词词典失败，使用默认词典: %s', e)
                _jieba_ready = True
    return [t for t in jieba.lcut(text.lower()) if t.strip()]


# ==================== 作用域 ====================

class RetrievalScope:
    """检索作用域 —— 患者数据隔离的唯一入口

    设计目标是把"不要泄露他人病历"从一条需要记住的约定，变成一道绕不过去的
    结构：检索方法一律只接受本对象，不接受裸 patient_id，因此过滤条件只有
    一个构造点（clause()），可被审计、可被搜索。

    四层防护（缺一层都不算数）：
    1. 单一构造点：clause() 是全模块唯一拼 patient 谓词的地方
    2. fail-closed：patient_id 为空却要求包含个人病历 → 直接抛异常，
       忘记传用户只会拿到共享库，而不是所有人的病历
    3. BM25 索引本身按作用域构建，他人的词元根本不进索引
    4. 回填候选时再套一次作用域，上游任何通道出错都带不进外来内容
    """

    __slots__ = ('patient_id', 'include_shared', 'include_personal')

    def __init__(self, patient_id=None, include_shared=True, include_personal=False):
        if include_personal and patient_id is None:
            raise PermissionError(
                '检索个人病历必须指定 patient_id：'
                '未指定时只能检索共享知识库，拒绝退化为"检索全部患者"'
            )
        if not include_shared and not include_personal:
            raise ValueError('include_shared 与 include_personal 不能同时为 False')
        self.patient_id = patient_id
        self.include_shared = include_shared
        self.include_personal = include_personal

    def __eq__(self, other):
        return (isinstance(other, RetrievalScope)
                and self.signature == other.signature)

    def __hash__(self):
        return hash(self.signature)

    def clause(self):
        """唯一的患者过滤条件构造点"""
        if not self.include_personal:
            # 只查共享库：不需要 patient_id
            return KnowledgeChunk.patient_id.is_(None)
        if self.include_shared:
            return or_(
                KnowledgeChunk.patient_id.is_(None),
                KnowledgeChunk.patient_id == self.patient_id,
            )
        return KnowledgeChunk.patient_id == self.patient_id   # 只查本人病历

    @property
    def signature(self):
        return f'{self.patient_id}|{self.include_shared}|{self.include_personal}'

    def __repr__(self):
        return (f'<RetrievalScope patient={self.patient_id} '
                f'shared={self.include_shared} personal={self.include_personal}>')


def breaker_open():
    """检索断路器是否处于打开状态（只读，不改变任何既有行为）

    存在的理由：`retrieve_safely()` 在两种完全不同的情况下都返回 `[]` ——
    「服务/模型挂了（断路器打开）」与「知识库确实没有这条」。调用方若不加
    区分，就会把前者告诉用户成"没有相关资料"，而那是在为一次故障撒谎。
    Agent 工具据此分别返回 unsupported 与 not_found（阶段 9）。
    """
    return time.time() < _retrieve_failure_until


def shared_scope():
    """只检索共享知识库（医生/管理员默认）"""
    return RetrievalScope()


def patient_scope(patient_id):
    """检索共享知识库 + 该患者本人病历"""
    return RetrievalScope(patient_id=patient_id, include_personal=True)


# ==================== 结果对象 ====================

class RetrievedChunk:
    __slots__ = ('chunk_id', 'doc_id', 'doc_title', 'doc_type', 'source',
                 'origin', 'section', 'page', 'content', 'score', 'rrf_score',
                 'vec_rank', 'bm25_rank', 'is_personal', 'rerank_used')

    def __init__(self, **kwargs):
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))

    @classmethod
    def from_dict(cls, data):
        """从缓存载荷还原

        必须与 to_dict() 严格对称：to_dict 对外用 `doc` 作为键名（响应契约
        要求），而内部字段叫 doc_title。少了这一步映射，缓存命中时
        doc_title 会是 None——**只在缓存预热后才会暴露**，冷启动测不出来。
        """
        payload = dict(data)
        payload['doc_title'] = payload.pop('doc', payload.get('doc_title'))
        payload.pop('snippet', None)      # 展示用字段，不是内部槽位
        return cls(**payload)

    def to_dict(self, with_content=True):
        data = {
            'chunk_id': self.chunk_id,
            'doc_id': self.doc_id,
            'doc': self.doc_title,
            'doc_type': self.doc_type,
            'section': self.section or '',
            'page': self.page,
            'origin': self.origin,
            'source': self.source,
            'score': round(self.score, 4) if self.score is not None else None,
            'rrf_score': round(self.rrf_score, 6) if self.rrf_score is not None else None,
            'vec_rank': self.vec_rank,
            'bm25_rank': self.bm25_rank,
            'is_personal': bool(self.is_personal),
            'rerank_used': bool(self.rerank_used),
        }
        if with_content:
            data['content'] = self.content
            data['snippet'] = (self.content or '')[:400]
        return data


# ==================== 检索器 ====================

class HybridRetriever:

    def __init__(self, embedder=None, reranker=None):
        self.embedder = embedder or Embedder.instance()
        self.reranker = reranker or Reranker.instance()

    # ---------- 语料版本 ----------

    def corpus_version(self):
        """语料版本戳（带节流）

        节流状态在 **Redis 里而不是本进程内**：阶段 8 起入库由 Celery worker
        执行，worker 写进新切片后，API 进程必须立刻看到新版本，否则会出现
        "刚上传的文档搜不到、60 秒后自愈"这种无法复现的问题。
        实现见 store.cached_corpus_version()。
        """
        from services.rag import store
        return store.cached_corpus_version()

    # ---------- 缓存的底层读写 ----------

    @staticmethod
    def _cache_get(key):
        client = None
        try:
            from core.cache import get_redis
            client = get_redis()
        except Exception:
            client = None
        if client is not None:
            try:
                raw = client.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning('RAG 缓存读取失败，按未命中处理: %s', e)
        with _local_cache_lock:
            entry = _local_cache.get(key)
            if entry and entry[0] > time.time():
                return entry[1]
            if entry:
                _local_cache.pop(key, None)
        return None

    @staticmethod
    def _cache_set(key, payload, ttl):
        try:
            from core.cache import get_redis
            client = get_redis()
            if client is not None:
                client.setex(key, ttl, json.dumps(payload, ensure_ascii=False))
                return
        except Exception as e:
            logger.warning('RAG 缓存写入失败，仅用进程内缓存: %s', e)
        with _local_cache_lock:
            # 进程内缓存加个上限，避免长期运行无限增长
            if len(_local_cache) > 512:
                _local_cache.clear()
            _local_cache[key] = (time.time() + ttl, payload)

    # ---------- 两路召回 ----------

    def _vector_search(self, query, scope, k, doc_types=None):
        if db.engine.dialect.name != 'postgresql':
            return []               # SQLite 降级：无向量能力，只走 BM25
        vector = self.embedder.encode_query(query)
        if vector is None:
            return []
        stmt = (
            select(KnowledgeChunk.id)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .where(
                KnowledgeDoc.status == 'ready',
                scope.clause(),
                KnowledgeChunk.embedding.isnot(None),
            )
            .order_by(KnowledgeChunk.embedding.cosine_distance(vector))
            .limit(k)
        )
        if doc_types:
            stmt = stmt.where(KnowledgeDoc.doc_type.in_(doc_types))
        try:
            return [row[0] for row in db.session.execute(stmt)]
        except Exception as e:
            logger.warning('向量检索失败，本轮仅用词法通道: %s', e)
            return []

    def _scoped_corpus(self, scope):
        """加载作用域内的 (id, tokens)

        词法通道的隔离保证就在这一句：语料来自带 scope.clause() 的查询，
        他人的切片根本不进索引，也就不可能被打分排上来。
        """
        rows = db.session.execute(
            select(KnowledgeChunk.id, KnowledgeChunk.content)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .where(KnowledgeDoc.status == 'ready', scope.clause())
        ).all()
        return [(row[0], tokenize(row[1] or '')) for row in rows]

    def _bm25_search(self, query, scope, k):
        from rank_bm25 import BM25Okapi

        corpus_ver = self.corpus_version()
        signature = scope.signature
        with _bm25_lock:
            cached = _bm25_cache.get(signature)
        if cached and cached[0] == corpus_ver:
            bm25, ids = cached[1], cached[2]
            corpus_tokens = None
        else:
            corpus = self._scoped_corpus(scope)
            if not corpus:
                return []
            ids = [cid for cid, _ in corpus]
            corpus_tokens = [tokens for _, tokens in corpus]
            bm25 = BM25Okapi(corpus_tokens)
            with _bm25_lock:
                _bm25_cache[signature] = (corpus_ver, bm25, ids)

        if not ids:
            return []
        scores = bm25.get_scores(tokenize(query))
        ranked = sorted(zip(ids, scores), key=lambda item: -item[1])
        return [cid for cid, score in ranked[:k] if score > 0]

    @staticmethod
    def _rrf(rank_lists, k=60):
        """Reciprocal Rank Fusion

        推广到 N 路列表（两路是 N=2 的特例）：后续想加一路"精确术语匹配"
        不需要动融合逻辑。
        """
        scores = {}
        for ids in rank_lists:
            for rank, cid in enumerate(ids):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        return scores

    def _hydrate(self, ids, scope, doc_types=None):
        """按 id 取回切片，并**再套一次作用域**

        这是第 4 层防护：即使上游某条通道出了错（比如向量检索的过滤条件写漏），
        外来内容也到不了响应里，因为物化时用的是同一套过滤。
        """
        if not ids:
            return {}
        stmt = (
            select(KnowledgeChunk, KnowledgeDoc)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .where(
                KnowledgeChunk.id.in_(list(ids)),
                KnowledgeDoc.status == 'ready',
                scope.clause(),
            )
        )
        if doc_types:
            stmt = stmt.where(KnowledgeDoc.doc_type.in_(doc_types))
        result = {}
        for chunk, doc in db.session.execute(stmt):
            result[chunk.id] = (chunk, doc)
        return result

    # ---------- 主流程 ----------

    def retrieve(self, query, *, scope, top_k=5, recall_k=20, rrf_k=60,
                 doc_types=None):
        if not query or not query.strip():
            return []
        cache_key = self._cache_key(query, scope, top_k, doc_types)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return [RetrievedChunk.from_dict(item) for item in cached]

        vec_ids = self._vector_search(query, scope, recall_k, doc_types)
        bm25_ids = self._bm25_search(query, scope, recall_k)
        fused = self._rrf([vec_ids, bm25_ids], k=rrf_k)
        if not fused:
            return []

        # RRF 分数排序后取前 recall_k 个进入重排
        ordered = sorted(fused.items(), key=lambda item: -item[1])[:recall_k]
        candidates = self._hydrate([cid for cid, _ in ordered], scope, doc_types)

        vec_rank = {cid: i + 1 for i, cid in enumerate(vec_ids)}
        bm25_rank = {cid: i + 1 for i, cid in enumerate(bm25_ids)}

        rerank_input = [(cid, candidates[cid][0].content)
                        for cid, _ in ordered if cid in candidates]
        reranked = self.reranker.rerank(query, rerank_input) if rerank_input else None
        rerank_used = reranked is not None

        if rerank_used:
            final = [(cid, score) for cid, score in reranked]
        else:
            final = [(cid, fused.get(cid, 0.0)) for cid, _ in ordered if cid in candidates]

        chunks = []
        for cid, score in final:
            if cid not in candidates:
                continue
            chunk, doc = candidates[cid]
            chunks.append(RetrievedChunk(
                chunk_id=chunk.id, doc_id=doc.id, doc_title=doc.title,
                doc_type=doc.doc_type, source=doc.source, origin=doc.origin,
                section=chunk.section, page=chunk.page, content=chunk.content,
                score=float(score), rrf_score=fused.get(cid),
                vec_rank=vec_rank.get(cid), bm25_rank=bm25_rank.get(cid),
                is_personal=chunk.patient_id is not None,
                rerank_used=rerank_used,
            ))

        chunks = self._apply_personal_slots(chunks, scope, top_k)
        payload = [c.to_dict() for c in chunks]
        self._cache_set(cache_key, payload, int(_cfg('RAG_CACHE_TTL', 600)))
        return chunks

    def _apply_personal_slots(self, chunks, scope, top_k):
        """保证患者本人病历在结果里占有一席之地

        只做一次合并检索的话，个人切片（往往只有几条）会被共享库里成百上千条
        切片挤掉——即使问的是"我上次膝盖伤是什么时候"。这里在重排之后保留
        至多 N 个个人切片，替换掉末尾的共享切片。

        要求分数不低于 RAG_MIN_SCORE，避免一条不相关的个人切片顶掉一条
        强相关的指南内容。
        """
        if not scope.include_personal or not scope.patient_id:
            return chunks[:top_k]

        slots = int(_cfg('RAG_PERSONAL_SLOTS', 2))
        min_score = float(_cfg('RAG_MIN_SCORE', 0.0))
        if slots <= 0:
            return chunks[:top_k]

        personal = [c for c in chunks
                    if c.is_personal and (c.score or 0) >= min_score][:slots]
        if not personal:
            return chunks[:top_k]

        personal_ids = {c.chunk_id for c in personal}
        head = [c for c in chunks if c.chunk_id in personal_ids]
        # 把个人切片按原相对顺序提上来，其余按顺序填充到 top_k
        tail = [c for c in chunks if c.chunk_id not in personal_ids]
        merged = head + tail
        return merged[:top_k]

    def _cache_key(self, query, scope, top_k, doc_types):
        raw = '|'.join([
            query.strip(), scope.signature, str(top_k),
            ','.join(sorted(doc_types or [])), self.corpus_version(),
        ])
        return 'rag:retr:' + hashlib.sha1(raw.encode('utf-8')).hexdigest()

    # ---------- 安全入口 ----------

    def retrieve_safely(self, query, *, scope, top_k=None, **kwargs):
        """任何异常都返回 []，绝不抛出

        调用方（对话、解读）据此降级为"无参考资料回答"。另外加一个 30 秒
        断路器：模型或数据库坏掉时，不能让每个请求都白等一遍完整超时。
        """
        global _retrieve_failure_until
        now = time.time()
        if now < _retrieve_failure_until:
            return []
        if str(_cfg('RAG_ENABLED', 'true')).lower() != 'true':
            return []
        try:
            return self.retrieve(query, scope=scope,
                                 top_k=top_k or int(_cfg('RAG_TOP_K', 5)),
                                 **kwargs)
        except Exception as e:
            _retrieve_failure_until = time.time() + _FAILURE_COOLDOWN
            logger.warning(
                'RAG 检索失败，%d 秒内降级为无参考资料回答: %s',
                _FAILURE_COOLDOWN, e, exc_info=True,
            )
            return []


def clear_caches():
    """入库后清缓存（语料变了，旧的检索结果随即失效）"""
    with _bm25_lock:
        _bm25_cache.clear()
    with _local_cache_lock:
        _local_cache.clear()
    try:
        from core.cache import get_redis
        client = get_redis()
        if client is not None:
            keys = list(client.scan_iter(match='rag:*', count=200))
            if keys:
                client.delete(*keys)
    except Exception as e:
        logger.warning('清理 Redis 检索缓存失败: %s', e)


_retriever = None


def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
