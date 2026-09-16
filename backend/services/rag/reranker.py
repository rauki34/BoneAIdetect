"""重排（BAAI/bge-reranker-v2-m3）

召回与精排是两件事：向量与 BM25 负责"从几千条里捞出可能相关的 20 条"，
CrossEncoder 负责"把这 20 条按真实相关度重新排序"。前者快而粗，后者慢而准，
所以只在候选集上跑。

与 embedder 一样是懒加载单例 + 不抛异常：模型缺失时保留 RRF 顺序继续返回结果，
而不是让检索 500。
"""
import os
import threading

from utils.logger import logger

DEFAULT_MODEL = 'BAAI/bge-reranker-v2-m3'

# 与嵌入模型一致，覆盖切片的最大长度
MAX_LENGTH = 1024


def _cfg(key, default):
    try:
        from flask import current_app
        value = current_app.config.get(key)
        if value is not None:
            return value
    except Exception:
        pass
    return os.environ.get(key, default)


class Reranker:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._load_error = None
        self._tried = False

    @classmethod
    def instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure(self):
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
                from sentence_transformers import CrossEncoder

                model_name = _cfg('RAG_RERANK_MODEL', DEFAULT_MODEL)
                device = _cfg('RAG_DEVICE', 'auto')
                if not device or device == 'auto':
                    device = 'cuda' if torch.cuda.is_available() else 'cpu'
                kwargs = {}
                if device == 'cuda' and str(_cfg('RAG_FP16', 'true')).lower() == 'true':
                    kwargs['automodel_args'] = {'torch_dtype': torch.float16}

                logger.info('加载重排模型 %s（device=%s）...', model_name, device)
                model = CrossEncoder(model_name, max_length=MAX_LENGTH,
                                     device=device, **kwargs)
                self._model = model
                self._load_error = None
                if device == 'cuda':
                    logger.info('重排模型就绪，显存占用 %.2f GB',
                                torch.cuda.memory_allocated() / 1024 ** 3)
                return True
            except Exception as e:
                self._load_error = str(e)
                logger.error(
                    '重排模型加载失败，检索将退回 RRF 排序（结果仍可用）: %s。'
                    '可设置 HF_ENDPOINT=https://hf-mirror.com 后重试',
                    e, exc_info=True,
                )
                return False

    @property
    def available(self):
        return self._ensure()

    @property
    def error(self):
        return self._load_error

    def rerank(self, query, candidates, top_k=None):
        """对候选 (id, content) 重排，返回 [(id, score)]

        模型不可用时返回 None，调用方保留原顺序。
        """
        if not candidates:
            return []
        if not self._ensure():
            return None
        batch_size = int(_cfg('RAG_RERANK_BATCH', 8))
        pairs = [(query, content) for _, content in candidates]
        scores = self._model.predict(pairs, batch_size=batch_size,
                                     show_progress_bar=False)
        ranked = sorted(
            zip([cid for cid, _ in candidates], [float(s) for s in scores]),
            key=lambda item: -item[1],
        )
        return ranked[:top_k] if top_k else ranked

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
            logger.info('已卸载重排模型')
