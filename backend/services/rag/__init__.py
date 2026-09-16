"""RAG 知识库（阶段 7）

对外入口：`from services.rag import get_pipeline`。

注意：本文件的导入保持轻量。`database.py::init_db` 会在启动时导入
`services.rag.store`，若此处顺手导入 pipeline，就会把 sentence-transformers
和 torch 一并拖进启动路径——那是十几秒的代价，而且和建表毫无关系。
"""
__all__ = ['get_pipeline']


def get_pipeline(*args, **kwargs):
    """获取 RAGPipeline 单例（延迟导入，避免启动时加载模型）"""
    from services.rag.pipeline import get_pipeline as _get_pipeline
    return _get_pipeline(*args, **kwargs)
