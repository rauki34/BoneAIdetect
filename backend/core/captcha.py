"""图形验证码的存储与校验

优先使用 Redis（多 worker 共享、TTL 由 Redis 管理）；
Redis 不可用时降级为进程内 dict，保证登录流程不受影响。

安全属性：验证码**一次性使用** —— 校验后立即删除，防止重放。
"""
import time

from core.cache import get_redis, report_failure
from core.state import CAPTCHA_TIMEOUT, captcha_store

_KEY_PREFIX = 'captcha:'


def save_captcha(captcha_id, code):
    """保存验证码（TTL = CAPTCHA_TIMEOUT）"""
    client = get_redis()
    if client is not None:
        try:
            client.setex(f'{_KEY_PREFIX}{captcha_id}', CAPTCHA_TIMEOUT, code)
            return
        except Exception as e:
            # Redis 运行中挂掉时缓存的客户端是死的，必须降级 ——
            # 验证码在登录路径上，抛出去等于 Redis 一挂谁也别想登录
            report_failure(e)

    captcha_store[captcha_id] = {
        'code': code,
        'expire_time': time.time() + CAPTCHA_TIMEOUT,
    }
    # 降级模式下顺带清理过期项，避免内存无限增长
    now = time.time()
    for key in [k for k, v in captcha_store.items() if v['expire_time'] < now]:
        captcha_store.pop(key, None)


def consume_captcha(captcha_id):
    """取出并删除验证码，返回 (code, 是否不存在或已过期)

    读取与删除在同一 pipeline 中执行，避免并发请求用同一验证码通过两次校验。
    （Redis 6.2+ 有 GETDEL，本机为 Redis 5，故用 pipeline 近似原子。）
    """
    client = get_redis()
    if client is not None:
        try:
            key = f'{_KEY_PREFIX}{captcha_id}'
            pipe = client.pipeline()
            pipe.get(key)
            pipe.delete(key)
            code, _ = pipe.execute()
            return code, code is None
        except Exception as e:
            report_failure(e)
            # 落到下面的进程内分支。注意本函数在 Redis 正常时**不会**写进程内
            # dict，所以这里多半取不到 —— 但取不到就是"验证码不存在"，
            # 会要求重新拉一个，不会误放行

    data = captcha_store.pop(captcha_id, None)
    if data is None or data['expire_time'] < time.time():
        return None, True
    return data['code'], False


def check_captcha(captcha, captcha_id):
    """校验图形验证码，返回 (是否通过, 错误信息)

    无论成功与否都会销毁该验证码（一次性使用）。

    注意：Redis 不可用时会降级为进程内存储，此时多 worker 部署下
    各进程的 captcha_store 互不可见（在 A 进程生成、到 B 进程校验会失败），
    相当于只能单进程运行。
    """
    if not captcha:
        return False, "验证码不能为空"
    if not captcha_id:
        return False, "验证码ID不能为空"

    code, gone = consume_captcha(captcha_id)
    if gone or code is None:
        return False, "验证码已过期"

    if captcha.upper() != code.upper():
        return False, "验证码错误"

    return True, None
