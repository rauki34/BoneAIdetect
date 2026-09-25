"""用户额度回归验证（阶段 9）

覆盖 `core/quota.py`：单会话额度、每日额度、两层互不白扣、本地日期边界、
用户隔离、Redis 不可用时的降级、429 响应形状与额度响应头。

与 `verify_auth_flow.py` 的分工：那个验的是**分钟级限流**（core/ratelimit.py），
本脚本验的是另外两个时间尺度。两者都挂在对话接口上，但失败的语义完全不同：
限流是「太快」（等一会就好），额度是「用完了」（新建会话 / 明日重置）。

用法：
    cd backend
    python scripts/verify_quota.py [日志文件路径]

**HTTP 部分需要后端以低阈值启动**，否则默认 100 次/日的额度不可能在测试里
耗尽（要真发 100 次 LLM 调用）。跑法：

    QUOTA_SESSION_MAX=2 QUOTA_DAILY_PER_USER=2 bash scripts/flask.sh restart debug
    python scripts/verify_quota.py logs/app.log
    bash scripts/flask.sh restart debug        # 改回默认阈值

阈值必须让**两条额度都能在 2 次请求内撞到**：同会话第 3 次撞会话额度（此时
不消费每日额度），换个会话第 4 次才撞每日额度。所以 daily 不能大于 session，
否则第 4 次会被放行、QUOTA_002 永远测不到。

阈值未调低时该部分会 SKIP 并打印上述命令，而不是假装通过。

退出码 = 失败用例数。
"""
import datetime
import importlib
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:5000'
LOG = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
    pathlib.Path(__file__).resolve().parent.parent / 'logs' / 'app.log'
PASSWORD = '123456'

# 假的用户 id：不会碰到任何真实账号的额度（键名含 user_id）
TEST_USER_A = 990001
TEST_USER_B = 990002
SESSION_A = 'quota-test-a'
SESSION_B = 'quota-test-b'

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def skip(name, why):
    SKIP.append(name)
    print(f'  [SKIP] {name}  {why}')


def section(title):
    print(f'\n{title}')


def login(user, attempts=12):
    for _ in range(attempts):
        r = requests.get(f'{BASE}/api/captcha', timeout=10)
        cid = r.headers.get('X-Captcha-ID')
        if not cid:
            time.sleep(1)
            continue
        time.sleep(1.2)
        text = LOG.read_text(encoding='utf-8', errors='ignore')
        code = next((c for c, i in reversed(re.findall(
            r'生成验证码:\s*([0-9A-Z]{4}),\s*captcha_id:\s*(\S+)', text)) if i == cid), None)
        if not code:
            time.sleep(1)
            continue
        r = requests.post(f'{BASE}/api/login', json={
            'username': user, 'password': PASSWORD,
            'captcha': code, 'captcha_id': cid}, timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get('access_token') or j.get('token')
        time.sleep(1)
    raise SystemExit('登录失败：确认后端以 LOG_LEVEL=DEBUG 启动'
                     '（bash scripts/flask.sh start debug）')


def chat(token, session_id, message='你好', timeout=180):
    return requests.post(f'{BASE}/api/ai-assistant/chat',
                         json={'session_id': session_id, 'message': message},
                         headers={'Authorization': 'Bearer ' + token},
                         timeout=timeout)


def _redis():
    from core.cache import get_redis
    return get_redis()


def cleanup_redis_keys():
    """删除本脚本造出来的额度键（不能让验证脚本吃掉真实账号的额度）"""
    client = _redis()
    if client is None:
        return 0
    keys = []
    for pattern in (f'quota:session:{TEST_USER_A}:*', f'quota:session:{TEST_USER_B}:*',
                    f'quota:daily:{TEST_USER_A}:*', f'quota:daily:{TEST_USER_B}:*'):
        keys.extend(client.keys(pattern))
    if keys:
        client.delete(*keys)
    return len(keys)


def part_logic(app):
    """Part 1：额度逻辑（直连 core.quota，不经过 HTTP，确定性）"""
    from core import quota
    from core.state import QUOTA_CONFIG

    original = dict(QUOTA_CONFIG)
    try:
        # ---------- 单会话额度 ----------
        section('[1] 单会话额度')
        cleanup_redis_keys()
        QUOTA_CONFIG['session_max'] = 3
        QUOTA_CONFIG['daily_max'] = 100
        results = [quota.check_and_consume(TEST_USER_A, SESSION_A) for _ in range(4)]
        check('前 3 次放行', all(r.allowed for r in results[:3]),
              f'剩余 {results[2].session_remaining}')
        check('第 4 次拒绝且 scope=session', not results[3].allowed
              and results[3].scope == 'session')
        check('返回 QUOTA_001（与每日额度区分）',
              results[3].error_code == 'QUOTA_001', f'code={results[3].error_code}')
        check('会话额度不返回 retry_after（只能靠新建会话解除，不是等一会）',
              not results[3].retry_after)
        check('提示文案写明新建会话可继续', '新建会话' in results[3].message,
              results[3].message)

        # ---------- 每日额度 ----------
        section('[2] 每日额度（跨会话累加）')
        cleanup_redis_keys()
        QUOTA_CONFIG['session_max'] = 100
        QUOTA_CONFIG['daily_max'] = 3
        got = [quota.check_and_consume(TEST_USER_A, f'{SESSION_A}-{i}').allowed
               for i in range(3)]
        r4 = quota.check_and_consume(TEST_USER_A, f'{SESSION_A}-3')
        check('换会话也累计到每日额度（3 次后拒绝）', all(got) and not r4.allowed)
        check('返回 QUOTA_002 且 scope=daily', r4.error_code == 'QUOTA_002'
              and r4.scope == 'daily', f'code={r4.error_code}')
        check('retry_after 落在 (0, 90000] 秒内（距本地 00:00）',
              0 < r4.retry_after <= 90000, f'retry_after={r4.retry_after}s')

        # ---------- 两层不互相白扣 ----------
        section('[3] 会话额度用尽时不扣每日额度')
        cleanup_redis_keys()
        QUOTA_CONFIG['session_max'] = 2
        QUOTA_CONFIG['daily_max'] = 10
        for _ in range(3):                    # 2 次成功 + 1 次被会话额度拒绝
            quota.check_and_consume(TEST_USER_A, SESSION_A)
        client = _redis()
        dkey = quota.daily_key(TEST_USER_A)
        used = int(client.get(dkey) or 0) if client else None
        check('每日计数只 += 2（被拒的那次没有白扣）', used == 2,
              f'每日已用={used}（期望 2）')

        # ---------- 本地日期边界 ----------
        section('[4] 每日键名用本地日期')
        now_local = datetime.datetime.now()
        utc_date = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        local_date = now_local.strftime('%Y-%m-%d')
        key = quota.daily_key(TEST_USER_A)
        check('键名含本地日期', key.endswith(local_date), key)
        if utc_date == local_date:
            skip('键名日期 != UTC 日期', '当前本地与 UTC 同日（北京 08:00 之后），'
                                        '该断言此刻无区分力；08:00 前跑可验')
        else:
            check('键名日期 != UTC 日期（防 8 小时时差）',
                  not key.endswith(utc_date), f'local={local_date} utc={utc_date}')

        # ---------- 用户隔离 ----------
        section('[5] 用户之间互不影响')
        cleanup_redis_keys()
        QUOTA_CONFIG['session_max'] = 2
        quota.check_and_consume(TEST_USER_A, SESSION_B)
        quota.check_and_consume(TEST_USER_A, SESSION_B)
        ra = quota.check_and_consume(TEST_USER_A, SESSION_B)
        rb = quota.check_and_consume(TEST_USER_B, SESSION_B)   # 同名会话、不同用户
        check('A 已用尽', not ra.allowed)
        check('B 用同一个 session_id 仍放行（键含 user_id，不串号）', rb.allowed)

        # ---------- Redis 不可用 ----------
        section('[6] Redis 不可用时降级并放行')
        from core import cache as cache_mod
        original_get_redis = cache_mod.get_redis
        quota.reset_memory()
        QUOTA_CONFIG['session_max'] = 2
        QUOTA_CONFIG['daily_max'] = 10
        try:
            cache_mod.get_redis = lambda: None      # 模拟 Redis 挂掉
            quota.get_redis = lambda: None
            rs = [quota.check_and_consume(TEST_USER_A, SESSION_A) for _ in range(3)]
            check('降级后仍放行 2 次、第 3 次拒绝（进程内计数生效）',
                  rs[0].allowed and rs[1].allowed and not rs[2].allowed,
                  f'{[r.allowed for r in rs]}')
        finally:
            cache_mod.get_redis = original_get_redis
            importlib.reload(quota)                 # 恢复模块内引用
            quota.reset_memory()

        # ---------- 总开关 ----------
        section('[7] 总开关 QUOTA_ENABLED=false')
        from core.state import QUOTA_CONFIG as QC
        QC['enabled'] = False
        try:
            r = quota.check_and_consume(TEST_USER_A, SESSION_A)
            check('关掉后一律放行且不计数', r.allowed and r.daily_used == 0)
        finally:
            QC['enabled'] = original['enabled']

        # ---------- 429 响应形状 ----------
        section('[8] 429 响应形状')
        with app.app_context():
            dres = quota.QuotaResult(False, 'daily', daily_used=100, session_used=1,
                                     retry_after=3600)
            resp = quota.denial_response(dres)
            check('daily 用尽 → 429', resp.status_code == 429)
            check('带 Retry-After 头', resp.headers.get('Retry-After') == '3600')
            body = resp.get_json()
            check('error_code=QUOTA_002 且带 retry_after',
                  body.get('error_code') == 'QUOTA_002' and body.get('retry_after') == 3600,
                  str(body)[:80])
            sres = quota.QuotaResult(False, 'session', daily_used=1, session_used=30)
            sbody = quota.denial_response(sres).get_json()
            check('会话用尽不带 retry_after（不是等一会的事）',
                  'retry_after' not in sbody, str(sbody)[:80])

        # ---------- 响应头 ----------
        section('[9] 额度响应头')
        with app.app_context():
            from flask import jsonify
            QC['session_max'] = 30
            QC['daily_max'] = 100
            resp = quota.attach_headers(jsonify({'ok': True}),
                                        quota.QuotaResult(True, None, 7, 2))
            check('带每日剩余与上限',
                  resp.headers.get('X-Quota-Daily-Remaining') == '93'
                  and resp.headers.get('X-Quota-Daily-Limit') == '100',
                  f"remaining={resp.headers.get('X-Quota-Daily-Remaining')}")
            check('带会话剩余与上限',
                  resp.headers.get('X-Quota-Session-Remaining') == '28',
                  f"remaining={resp.headers.get('X-Quota-Session-Remaining')}")
    finally:
        QUOTA_CONFIG.clear()
        QUOTA_CONFIG.update(original)


def part_http(app):
    """Part 2：额度经 HTTP 生效（需要后端以低阈值启动）"""
    section('[10] HTTP 端到端（需要低阈值启动）')
    token = login('admin')      # admin 角色豁免额度，用于验「不波及其他接口」
    from core import quota as quota_mod
    from database import User
    with app.app_context():
        patient = User.query.filter_by(role='patient').first()
        if patient is None:
            skip('HTTP 额度用例', '库里没有患者账号')
            return
        pname = patient.username
        pid = patient.id
    dkey = quota_mod.daily_key(pid)

    ptoken = login(pname)
    session = f'quota-verify-{int(time.time())}'
    client = _redis()
    snap = client.get(dkey) if client is not None else None

    try:
        r1 = chat(ptoken, session)
        if r1.status_code != 200:
            check('对话请求成功', False, f'HTTP {r1.status_code} {r1.text[:120]}')
            return
        limit = r1.headers.get('X-Quota-Daily-Limit')
        remaining = r1.headers.get('X-Quota-Daily-Remaining')
        check('成功响应带额度头', limit is not None and remaining is not None,
              f'limit={limit} remaining={remaining}')
        if limit is None or int(limit) > 5:
            skip('额度耗尽后的 429（QUOTA_001/002）',
                 f'当前每日上限={limit}，默认值下需要发上百次真实 LLM 请求才能耗尽。'
                 '改用低阈值启动后端再跑：'
                 'QUOTA_SESSION_MAX=2 QUOTA_DAILY_PER_USER=2 '
                 'bash scripts/flask.sh restart debug')
            return

        r2 = chat(ptoken, session)
        check('第二次剩余递减 1',
              r2.headers.get('X-Quota-Daily-Remaining') is not None
              and int(r2.headers['X-Quota-Daily-Remaining']) == int(remaining) - 1,
              f"{remaining} → {r2.headers.get('X-Quota-Daily-Remaining')}")

        r3 = chat(ptoken, session)
        check('会话额度用尽 → 429', r3.status_code == 429, f'HTTP {r3.status_code}')
        body = r3.json() if r3.status_code == 429 else {}
        check('error_code=QUOTA_001（不是 RATE_LIMIT_EXCEEDED）',
              body.get('error_code') == 'QUOTA_001', str(body)[:100])

        # 换会话 → 撞每日额度
        r4 = chat(ptoken, session + '-new')
        b4 = r4.json() if r4.status_code == 429 else {}
        check('换会话后撞每日额度 → QUOTA_002',
              r4.status_code == 429 and b4.get('error_code') == 'QUOTA_002',
              f'HTTP {r4.status_code} {str(b4)[:100]}')
        check('QUOTA_002 带 retry_after 与 Retry-After 头',
              b4.get('retry_after') and r4.headers.get('Retry-After'),
              f"retry_after={b4.get('retry_after')}")

        # 额度用尽不应波及其他接口
        r5 = requests.post(f'{BASE}/api/knowledge/search',
                           json={'query': '骨折', 'top_k': 1},
                           headers={'Authorization': 'Bearer ' + token}, timeout=60)
        check('额度用尽不影响其他账号的其他接口（不是全局故障）',
              r5.status_code in (200, 403), f'HTTP {r5.status_code}')
    finally:
        if client is not None:
            if snap is not None:
                # 还原测试消耗掉的每日额度。这些是计数键、不是业务数据，
                # 不还原的话患者账号会在测试后一直拿到 QUOTA_002
                client.set(dkey, snap)
            else:
                client.delete(dkey)
            keys = client.keys(f'quota:session:{pid}:{session}*')
            if keys:
                client.delete(*keys)
        cleanup_redis_keys()


def main():
    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _engine = build_bare_app()

    try:
        requests.get(f'{BASE}/api/captcha', timeout=10)
    except Exception as e:
        print(f'后端未就绪（{e}）。请先：bash scripts/flask.sh start debug')
        return 1

    try:
        part_logic(app)
    except Exception as e:
        check('额度逻辑用例执行', False, f'{type(e).__name__}: {e}')
    try:
        part_http(app)
    except Exception as e:
        check('HTTP 额度用例执行', False, f'{type(e).__name__}: {e}')

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)} / 跳过 {len(SKIP)}')
    for n in FAIL:
        print(f'    - {n}')
    for n in SKIP:
        print(f'    ~ {n}')
    return len(FAIL)


if __name__ == '__main__':
    sys.exit(main())
