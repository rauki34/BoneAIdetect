"""独立脚本的启动样板

供 `scripts/` 下的脚本使用，解决两件 app.py 帮忙做了、而脚本必须自己做的事：

1. **加载 .env**。配置来自环境变量，而 `python app.py` 是靠文件头部的
   `load_dotenv()` 把 `.env` 灌进环境变量的。脚本若不自己加载，`DATABASE_URL`
   就取不到，`config.py` 会静默回退到 SQLite——脚本会连上一个空库并"成功"，
   排查起来非常费劲。所以必须在 import config **之前**执行。
2. **构造不加载 YOLO 的应用**。`import app` 会触发 `init_models()`，
   把全部权重读进显存（约 1GB、数秒）。入库/校验类脚本经常要在开发服务器
   占着 GPU 时运行，因此这里只做 `init_db()`——那才是真实的建表路径。
"""
import os

_ENV_LOADED = False


def load_env():
    """加载 backend/.env（幂等）

    与 app.py 文件头部同样的处理：python-dotenv 缺失时静默回退到系统环境变量。
    utils.logger 在导入时读取 LOG_LEVEL，因此本函数要早于任何项目模块导入。
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    except ImportError:
        pass
    _ENV_LOADED = True


def enable_utf8_console():
    """让脚本输出（含日志里的 emoji）在 GBK 控制台上不乱码

    Windows 控制台默认 GBK，logger 的 StreamHandler 往 stdout 写 '✅' 会抛
    UnicodeEncodeError，logging 转而把整条记录以 "Message: ... Arguments: ..."
    的原始形式打到 stderr——脚本输出会变得既乱码又噪声大。
    reconfigure 是就地修改，日志 handler 持有的流对象同样生效。
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass    # 被重定向到不支持 reconfigure 的对象时忽略


def build_bare_app():
    """构造最小 Flask 应用并初始化数据库

    返回 (app, engine)。engine 需要应用上下文，因此本函数会 push 一个
    上下文并常驻——调用方用完正常退出即可。
    """
    enable_utf8_console()
    load_env()

    from flask import Flask
    from config import config
    from database import db, init_db

    app = Flask(__name__)
    app.config.from_object(config)
    app_context = app.app_context()
    app_context.push()
    init_db(app)
    return app, db.engine
