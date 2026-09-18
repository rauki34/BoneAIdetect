"""worker 侧的 Flask 应用上下文

任务里要访问 `TrainingTask.query`、`log_operation()` 这些依赖 Flask 应用上下文的
东西，但 worker 进程里没有请求、也没有 `app.py` 那个应用。

**为什么不 import app.py**：`app.py` 是模块级 `app = Flask(__name__)`，import 它会连带
执行 `init_db()`、`init_models()`（把全部 YOLO 权重读进显存）、注册 10 个蓝图、绑定
flask_sock。worker 一个都不需要，而显存那个尤其致命 —— worker 自己要跑训练。

**为什么不用自己拼一个 Flask 应用**：`core/bootstrap.py:build_bare_app()` 已经做好了，
而且它覆盖了三件容易漏掉的事：

1. `load_env()` —— 加载 `.env`。少了它 `DATABASE_URL` 取不到，会静默连到 SQLite。
   这是本项目踩过的坑，`bootstrap.py` 的模块文档写的就是它。
2. `enable_utf8_console()` —— Windows GBK 控制台下日志里的 emoji 会抛
   UnicodeEncodeError，logging 转而把整条记录以原始形式打到 stderr。
3. `init_db()` —— 走真实的建表/加列路径，因此 worker 启动时就会把
   `_DDL_COLUMNS` 里新增的列补上，不必等 Web 进程重启。

**contextvars 与线程模型**：Flask 的应用上下文存在 ContextVar 里，是线程隔离的。
solo 池下任务跑在主线程，`build_bare_app()` 里 push 的常驻上下文能看见。
但不要依赖这一点 —— 每个任务都自己 `with app_context():`。除了不绑死线程模型，
退出 `with` 时还会触发 `teardown_appcontext`，自动 `db.session.remove()`，
避免 solo 池下任务之间共享一个脏 session。
"""
from contextlib import contextmanager

_app = None


def worker_app():
    """获取（首次调用时构建）worker 用的 Flask 应用

    `build_bare_app()` 内部会 push 一个常驻上下文，因此模块级代码也能直接用
    `db.session`。每个任务仍应使用下面的 `app_context()`。
    """
    global _app
    if _app is None:
        from core.bootstrap import build_bare_app

        _app, _ = build_bare_app()
    return _app


@contextmanager
def app_context():
    """任务用的应用上下文

    用法：
        with app_context():
            task = db.session.get(TrainingTask, task_id)
    """
    with worker_app().app_context():
        yield
