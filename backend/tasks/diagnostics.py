"""队列自检任务

存在的意义是给 `scripts/verify_queue.py` 一个可断言的对象，尤其是第 2 个：
**worker 到底连的是哪个库**。

`.env` 没加载时 `config.py` 会静默回退到 SQLite，任务照跑、照「成功」，
只是数据进了另一个库。这种故障没有报错、没有异常、界面也无从察觉，
只能靠主动断言 engine.url 来发现。别删这个任务。
"""
from tasks.celery_app import celery_app
from tasks.context import app_context


@celery_app.task(name='diagnostics.ping')
def ping(payload=None):
    """回声任务：确认 worker 活着，并回报它实际使用的数据库"""
    with app_context():
        from database import db

        url = db.engine.url
        # 隐去口令，日志与接口返回里不该出现凭证
        safe_url = url.set(password='***') if url.password else url

        return {
            'ok': True,
            'echo': payload,
            'db_dialect': url.get_backend_name(),
            'db_url': str(safe_url),
        }


@celery_app.task(name='diagnostics.sleep')
def sleep_task(seconds=5):
    """占位长任务：用来验证「任务在跑时队列确实被占住、且 Web 进程不受影响」"""
    import time

    time.sleep(seconds)
    return {'ok': True, 'slept': seconds}
