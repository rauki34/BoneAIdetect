"""图形验证码校验

从 app.py 抽出。验证码存于 core.state.captcha_store（进程内，5 分钟过期）。
"""
import time

from core.state import captcha_store

def check_captcha(captcha, captcha_id):
    """校验图形验证码

    返回 (是否通过, 错误信息)。校验通过后立即销毁验证码，防止重放攻击。

    验证码存于进程内 captcha_store（见 generate_captcha），5 分钟过期。
    注意：多进程部署时该存储不共享，需改为 Redis 等外部存储。
    """
    if not captcha:
        return False, "验证码不能为空"
    if not captcha_id:
        return False, "验证码ID不能为空"

    data = captcha_store.get(captcha_id)
    if not data:
        return False, "验证码已过期"

    if data['expire_time'] < time.time():
        captcha_store.pop(captcha_id, None)
        return False, "验证码已过期"

    if captcha.upper() != data['code'].upper():
        return False, "验证码错误"

    captcha_store.pop(captcha_id, None)   # 一次性使用
    return True, None
