"""Celery 任务包（阶段 8）

**这个 `__init__.py` 刻意留空。**

凡是 `from tasks.xxx import yyy` 都会先把 `tasks` 包执行一遍。若在这里
`from .celery_app import celery_app`，那么任何 import 了任务模块的 Web 侧代码
（例如 `api/knowledge.py` 为了拿到 `.delay()`）都会连带把 celery + kombu
拖进导入链。Web 进程不需要它们，而 import 失败会直接让整个应用起不来。

需要 Celery 实例时请显式写 `from tasks.celery_app import celery_app`。
"""
