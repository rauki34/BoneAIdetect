"""向量化（BAAI/bge-m3，1024 维）

三个刻意的设计决定：

1. **懒加载单例**。bge-m3 首次加载要 10-30 秒，不能待在请求路径上；也不能在
   导入时加载，那会拖慢每一次 flask CLI 调用和每一个脚本。
2. **加载失败不抛异常**，只把错误留在 `error` 里、`available` 置 False。
   知识库是增强能力，模型下载失败不该让整个系统起不来。
3. **不加 query/passage 前缀**。bge-large-zh 系列需要 "为这个句子生成表示"
   之类的前缀，bge-m3 **不需要**；画蛇添足地加上会静默降低召回。
"""
import os
import threading

from database import EMBEDDING_DIM
from utils.logger import logger

DEFAULT_MODEL = 'BAAI/bge-m3'

# 覆盖切片器 MAX_CHUNK_TOKENS(900) + 头部，确保没有切片在嵌入时被静默截断。
# bge-m3 原生支持 8192，但显存随长度增长，取 1024 是"够用且不浪费"的值。
MAX_SEQ_LENGTH = 1024


def _cfg(key, default):
    """读配置：优先应用上下文，其次环境变量，最后默认值

    脚本与请求线程都要能用，因此不能硬依赖 current_app。
    """
    try:
        from flask import current_app
        value = current_app.config.get(key)
        if value is not None:
            return value
    except Exception:
        pass
    return os.environ.get(key, default)


def resolve_device():
    device = _cfg('RAG_DEVICE', 'auto')
    if device and device != 'auto':
        return device
    try:
        import torch
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    except Exception:
        return 'cpu'


class Embedder:
    """bge-m3 懒加载单例"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._load_error = None
        self._tried = False
        self._device = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------- 加载 ----------

    def _ensure(self):
        """加载模型；成功返回 True。任何失败都记在 _load_error 里而不抛出"""
        if self._model is not None:
            return True
        with self._lock:
            if self._model is not None:
                return True
            if self._tried and self._load_error:
                return False
            self._tried = True
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                model_name = _cfg('RAG_EMBED_MODEL', DEFAULT_MODEL)
                device = resolve_device()
                kwargs = {}
                if device == 'cuda' and str(_cfg('RAG_FP16', 'true')).lower() == 'true':
                    # fp16 是 6GB 显存下与 YOLO 共存的前提
                    kwargs['model_kwargs'] = {'torch_dtype': torch.float16}

                logger.info('加载嵌入模型 %s（device=%s）...', model_name, device)
                model = SentenceTransformer(model_name, device=device, **kwargs)
                model.max_seq_length = MAX_SEQ_LENGTH

                # 维度必须与 knowledge_chunks.embedding 的列宽一致，
                # 不一致时在入库/检索前就报错，而不是等数据库报类型错误
                dim = model.get_sentence_embedding_dimension()
                if dim != EMBEDDING_DIM:
                    raise ValueError(
                        f'模型维度 {dim} 与数据库列宽 vector({EMBEDDING_DIM}) 不一致；'
                        f'换模型需同时迁移 knowledge_chunks.embedding 列'
                    )

                self._model = model
                self._device = device
                self._load_error = None
                if device == 'cuda':
                    logger.info('显存占用 %.2f GB', torch.cuda.memory_allocated() / 1024 ** 3)
                logger.info('✅ 嵌入模型就绪（%d 维，%s）', dim, device)
                return True
            except Exception as e:
                self._load_error = str(e)
                logger.error(
                    '嵌入模型加载失败，知识库检索将不可用: %s。'
                    '若为网络问题，可设置 HF_ENDPOINT=https://hf-mirror.com 后重试，'
                    '或手动执行 huggingface-cli download %s',
                    e, _cfg('RAG_EMBED_MODEL', DEFAULT_MODEL), exc_info=True,
                )
                return False

    @property
    def available(self):
        return self._ensure()

    @property
    def error(self):
        return self._load_error

    @property
    def device(self):
        return self._device

    # ---------- 编码 ----------

    def encode_documents(self, texts, batch_size=None, progress=None):
        """批量编码文档；失败返回 None（调用方据此中止入库）"""
        if not texts:
            return []
        if not self._ensure():
            raise RuntimeError(f'嵌入模型不可用: {self._load_error}')
        batch_size = batch_size or int(_cfg('RAG_EMBED_BATCH', 8))
        vectors = self._model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,      # 归一化后余弦距离与内积一致，HNSW 距离有界
            show_progress_bar=bool(progress),
        )
        return [v.tolist() for v in vectors]

    def encode_query(self, text):
        """编码查询；模型不可用时返回 None 而不是抛出"""
        if not text or not text.strip():
            return None
        if not self._ensure():
            return None
        vector = self._model.encode(
            [text], normalize_embeddings=True, show_progress_bar=False,
        )[0]
        return vector.tolist()

    def unload(self):
        """释放显存（YOLO 视频流推理前腾地方用）"""
        with self._lock:
            if self._model is None:
                return
            self._model = None
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info('已卸载嵌入模型')
