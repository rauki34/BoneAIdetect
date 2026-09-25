"""pytest 共享 fixture（阶段 11）

**测试分两层，边界要清楚**：

  unit/         不碰数据库、不加载模型、不发网络请求 —— CI 上跑的就是这一层
  integration/  需要完整 app（数据库/Redis）；本机跑得通，CI 默认跳过

不把 `scripts/verify_*.py` 那套端到端验收搬进 pytest：那套要起服务、要真实
LLM、跑一次几分钟。这里的定位是**几十秒内能跑完、且不依赖任何外部资源**的
契约层回归，让 CI 能拦住"改坏了但没人发现"这类问题。
"""
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# **必须在任何项目模块导入之前**加载 .env，所以放在模块顶层而不是 fixture 里。
#
# 这是本仓记过最多次的一个坑（core/bootstrap.py 的模块文档、BASELINE 二·补三
# 第 2 条）：`config.py` 在**导入时**就把环境变量求值固化，`.env` 晚一步加载
# 就再也补不回来 —— DATABASE_URL 取不到，配置静默回退到 SQLite。
#
# pytest 的收集阶段会先导入测试模块（`from core.state import QUOTA_CONFIG` 之类
# 就会连带导入 config），那时 fixture 还没跑。实测后果：整个测试进程连到一个
# 临时 SQLite 库（还在 backend/instance/ 下建了个 600KB 的文件），用例照样
# "全绿"，但验的根本不是开发库 —— 典型的静默失真。
from core.bootstrap import load_env  # noqa: E402

load_env()

import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        'markers', 'integration: 需要完整应用与数据库（CI 默认跳过）')


@pytest.fixture(scope='session')
def bare_app():
    """只建库、不加载 YOLO 的最小应用（与 scripts/ 下的脚本同一入口）"""
    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _engine = build_bare_app()
    return app


@pytest.fixture(scope='session')
def full_app():
    """真实应用：含全部蓝图与 9 个错误处理器

    会走 app.py 的 init_models()（加载 YOLO 权重，数秒）。权重文件缺失时
    app.py 自己会跳过并记日志，所以本机与 CI 都不会因此失败。
    """
    from app import app
    return app


@pytest.fixture()
def client(full_app):
    return full_app.test_client()


@pytest.fixture()
def db_session(bare_app):
    """应用上下文里的 session（integration 用例用）"""
    from database import db
    with bare_app.app_context():
        yield db.session
