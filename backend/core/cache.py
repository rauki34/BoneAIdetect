"""Redis 缓存层

替代进程内状态（限流计数、验证码、会话），解决两个问题：
  - 多 worker / 多机部署时不共享
  - 重启即清零

**降级策略**：Redis 不可用时各调用方回退到进程内实现，而不是直接报错。
医疗场景下，缓存组件故障不应导致医护无法工作。

注意：本机为 Redis 5.0（tporadowski 的 Windows 构建），不支持 RESP3，
因此 redis-py 需显式指定 protocol=2。
"""
import os
import time

from utils.logger import logger

# 连接失败后的重试间隔（秒），避免每次调用都去连一个挂掉的 Redis
_RETRY_INTERVAL = 30

_client = None
_last_failure = 0.0


def get_redis():
    """获取 Redis 客户端；不可用时返回 None（调用方应降级处理）"""
    global _client, _last_failure

    if _client is not None:
        return _client

    # 失败后短期内不再重试
    if _last_failure and (time.time() - _last_failure) < _RETRY_INTERVAL:
        return None

    try:
        import redis as redis_lib

        url = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
        client = redis_lib.from_url(
            url,
            decode_responses=True,
            protocol=2,                 # Redis 5 不支持 RESP3 的 HELLO 命令
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _client = client
        _last_failure = 0.0
        logger.info('Redis 已连接: %s', url)
        return _client

    except Exception as e:
        _last_failure = time.time()
        logger.warning('Redis 不可用（%s），降级为进程内存储', e)
        return None


def report_failure(exc=None):
    """**Redis 操作中途失败**时由调用方调用 —— 丢弃死客户端并进入冷却

    补的是一个 get_redis() 覆盖不到的口子：它的降级只处理**建立连接**失败。
    已经缓存下来的客户端，在 Redis 运行中挂掉之后连接池里的连接全是死的，
    后续调用会直接抛异常，而不是让 get_redis() 返回 None。症状是
    Redis 挂掉后的第一批请求失败，要等 _RETRY_INTERVAL 冷却到期才恢复降级。

    医疗场景下缓存组件故障不该让医护用不了系统，所以各调用方捕获异常后
    调本函数：下一次 get_redis() 会重新尝试连接（成功则恢复，失败则返回
    None，调用方走进程内降级）。

    用法：
        try:
            ...用 client 干活...
        except Exception as e:
            report_failure(e)
            return 进程内降级实现()
    """
    global _client, _last_failure
    _client = None
    _last_failure = time.time()
    if exc is not None:
        logger.warning('Redis 操作失败，本进程改用进程内实现: %s', exc)


def reset():
    """强制下次调用重新连接（Redis 恢复后可用）"""
    global _client, _last_failure
    _client = None
    _last_failure = 0.0
