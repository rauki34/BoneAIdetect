"""token 计数

**为什么不用估算公式**：最初为了保持切片器"纯函数、无模型依赖"，
用「中日韩字符数 + 1.3 × 英文词数」估算 token。实测下来这个估算在
生物医学英文上**低估最多近 2 倍**——像 osteoarthritis、bisphosphonate、
intramembranous 这类长术语会被 XLM-R 的 sentencepiece 切成 2-4 个子词，
而公式按"一个词 1.3 个 token"计算。

后果很隐蔽：按估算值判断切片没超窗口，实际嵌入时被 max_seq_length
静默截断——那部分内容进得了库、却永远检索不到。

因此改为调用真实 tokenizer（只加载词表，不加载权重，秒级且几乎不占显存），
仅在加载失败时回退到估算公式。
"""
import os
import threading

from utils.logger import logger

_lock = threading.Lock()
_tokenizer = None
_load_failed = False

DEFAULT_MODEL = 'BAAI/bge-m3'


def _cfg(key, default):
    try:
        from flask import current_app
        value = current_app.config.get(key)
        if value is not None:
            return value
    except Exception:
        pass
    return os.environ.get(key, default)


def get_tokenizer():
    """懒加载分词器；不可用时返回 None（调用方回退到估算）"""
    global _tokenizer, _load_failed
    if _tokenizer is not None or _load_failed:
        return _tokenizer
    with _lock:
        if _tokenizer is not None or _load_failed:
            return _tokenizer
        try:
            from transformers import AutoTokenizer
            model = _cfg('RAG_EMBED_MODEL', DEFAULT_MODEL)
            _tokenizer = AutoTokenizer.from_pretrained(model)
            logger.info('已加载分词器用于切片长度校验: %s', model)
        except Exception as e:
            _load_failed = True
            logger.warning(
                '分词器加载失败，切片长度改用估算公式（对英文医学术语可能低估，'
                '建议保证网络可用或预置模型）: %s', e,
            )
    return _tokenizer


def estimate_tokens(text):
    """回退用的估算公式（中日韩按字、英文按词 × 1.3）"""
    cjk = sum(1 for ch in text if '一' <= ch <= '鿿')
    words = len(__import__('re').findall(r'[A-Za-z0-9]+', text))
    return cjk + int(words * 1.3)


def count_tokens(text):
    """统计 token 数：优先真实分词器，失败时回退估算"""
    if not text:
        return 0
    tokenizer = get_tokenizer()
    if tokenizer is None:
        return estimate_tokens(text)
    try:
        return len(tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return estimate_tokens(text)
