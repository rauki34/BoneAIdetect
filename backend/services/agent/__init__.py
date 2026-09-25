"""Agent 子系统（阶段 9）

对外入口：
    from services.agent import get_orchestrator   # 编排（延迟导入）
    from services.agent.tools import TOOL_REGISTRY, execute_tool

注意：本文件保持轻量。`services/agent/tools.py` 里对 RAG 检索是**函数内导入**
（retriever 顶层会 import embedder/reranker，进而把 torch 拖进 Flask 启动路径，
那是十几秒的代价）。这里同样只做包装，不在模块顶层导入 tools/orchestrator，
免得将来有谁从 `services.agent` 导入一个常量就把 torch 带进来。

阶段 9 的编排刻意**不依赖 LangGraph**（理由写在 requirements.txt 的注释里）：
节点函数都是 `f(state) -> 下一节点名` 的纯函数，驱动器只按返回值调度，
将来若要换成图编排，只需新增 graph.py 把节点接上，节点本身一行不改。
"""
__all__ = ['run']


def run(*args, **kwargs):
    """运行一次 Agent 编排（延迟导入）"""
    from services.agent.orchestrator import run as _run
    return _run(*args, **kwargs)
