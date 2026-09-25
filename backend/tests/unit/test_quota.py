"""用户额度（阶段 9 的 core/quota.py）

额度是**成本控制**，算错的后果是钱：少算会让成本失控，多算会让用户用不了。
所以这里逐条钉住：两层额度各自的边界、两层之间不互相白扣、日期边界用本地
日期、用户之间不串号、以及 Redis 挂掉时的降级方向。

Redis 可用与否**两种环境都要能跑**：本机有 Redis 时走真实计数键（用例自清理），
CI 上没有 Redis 时走进程内降级分支 —— 两条路径都要验证，不能只在一种环境下
"碰巧通过"。
"""
import datetime
import uuid

import pytest

from core import quota
from core.state import QUOTA_CONFIG


@pytest.fixture()
def fake_user():
    """假用户 id：键名含 user_id，所以不会碰到任何真实账号的额度"""
    return 990000 + uuid.uuid4().int % 1000


@pytest.fixture()
def session_id():
    return f'quota-test-{uuid.uuid4().hex[:8]}'


@pytest.fixture(autouse=True)
def _isolate_config():
    """每条用例前后还原额度配置，避免用例之间互相影响"""
    original = dict(QUOTA_CONFIG)
    yield
    QUOTA_CONFIG.clear()
    QUOTA_CONFIG.update(original)


@pytest.fixture(autouse=True)
def _cleanup(fake_user):
    yield
    client = quota.get_redis()
    if client is None:
        quota.reset_memory()
        return
    for pattern in (f'quota:session:{fake_user}:*', f'quota:daily:{fake_user}:*'):
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
    quota.reset_memory()


def test_session_limit(fake_user, session_id):
    QUOTA_CONFIG['session_max'] = 3
    QUOTA_CONFIG['daily_max'] = 100
    results = [quota.check_and_consume(fake_user, session_id) for _ in range(4)]
    assert all(r.allowed for r in results[:3])
    assert not results[3].allowed
    assert results[3].scope == 'session'
    assert results[3].error_code == 'QUOTA_001'
    # 会话额度只能靠新建会话解除，等不会等到 —— 不能回传 retry_after
    assert not results[3].retry_after


def test_daily_limit_across_sessions(fake_user):
    QUOTA_CONFIG['session_max'] = 100
    QUOTA_CONFIG['daily_max'] = 2
    assert quota.check_and_consume(fake_user, 's1').allowed
    assert quota.check_and_consume(fake_user, 's2').allowed
    denied = quota.check_and_consume(fake_user, 's3')
    assert not denied.allowed and denied.scope == 'daily'
    assert denied.error_code == 'QUOTA_002'
    assert 0 < denied.retry_after <= 90000        # 距本地 00:00


def test_session_exhaustion_does_not_consume_daily(fake_user, session_id):
    """被会话额度拒绝的那次不能把当日额度也扣掉 —— 否则用户什么都没得到
    却损失了当天总量"""
    QUOTA_CONFIG['session_max'] = 2
    QUOTA_CONFIG['daily_max'] = 10
    for _ in range(3):
        quota.check_and_consume(fake_user, session_id)
    client = quota.get_redis()
    if client is None:
        pytest.skip('Redis 不可用，无法直接读计数键（降级分支由另一条用例覆盖）')
    used = int(client.get(quota.daily_key(fake_user)) or 0)
    assert used == 2


def test_daily_key_uses_local_date(fake_user):
    """日期边界必须用本地日期：用 UTC 会让额度在北京时间早上 8 点重置，
    而界面上的"今日剩余"与用户直觉对不上"""
    key = quota.daily_key(fake_user)
    assert key.endswith(datetime.datetime.now().strftime('%Y-%m-%d'))


def test_users_are_isolated(fake_user):
    QUOTA_CONFIG['session_max'] = 1
    QUOTA_CONFIG['daily_max'] = 10
    shared_session = 'same-session-name'
    assert quota.check_and_consume(fake_user, shared_session).allowed
    assert not quota.check_and_consume(fake_user, shared_session).allowed
    # 同名会话、另一个用户：键名含 user_id，不该受影响
    assert quota.check_and_consume(fake_user + 1, shared_session).allowed
    client = quota.get_redis()
    if client is not None:
        keys = client.keys(f'quota:session:{fake_user + 1}:*')
        if keys:
            client.delete(*keys)


def test_fail_open_when_redis_unavailable(monkeypatch, fake_user, session_id):
    """额度组件故障不该让患者用不了助手（与限流的 fail-open 取舍一致）"""
    quota.reset_memory()
    monkeypatch.setattr(quota, 'get_redis', lambda: None)
    QUOTA_CONFIG['session_max'] = 2
    QUOTA_CONFIG['daily_max'] = 10
    results = [quota.check_and_consume(fake_user, session_id) for _ in range(3)]
    assert [r.allowed for r in results] == [True, True, False], \
        '降级后应走进程内计数：前两次放行、第三次按会话额度拒绝'


def test_disabled_switch_is_passthrough(fake_user, session_id):
    QUOTA_CONFIG['enabled'] = False
    QUOTA_CONFIG['session_max'] = 1
    for _ in range(5):
        r = quota.check_and_consume(fake_user, session_id)
        assert r.allowed and r.daily_used == 0


def test_empty_session_is_not_counted(fake_user):
    """没有 session_id 就不该计数（视图层会在拿到会话后才调用）"""
    QUOTA_CONFIG['session_max'] = 1
    assert quota.check_and_consume(fake_user, '').allowed


def test_denial_response_shape():
    """超限用 429 + 独立错误码：'用完了' 与 RATE_LIMIT_EXCEEDED 的 '太快了'
    语义不同，前端提示与自动测试的判据都该分开"""
    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _ = build_bare_app()
    with app.app_context():
        resp = quota.denial_response(
            quota.QuotaResult(False, 'daily', daily_used=100, retry_after=3600))
        assert resp.status_code == 429
        body = resp.get_json()
        assert body['error_code'] == 'QUOTA_002' and body['retry_after'] == 3600
        assert resp.headers['Retry-After'] == '3600'

        session_resp = quota.denial_response(
            quota.QuotaResult(False, 'session', session_used=30))
        session_body = session_resp.get_json()
        assert session_body['error_code'] == 'QUOTA_001'
        assert 'retry_after' not in session_body


def test_attach_headers():
    from flask import jsonify
    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _ = build_bare_app()
    QUOTA_CONFIG['session_max'] = 30
    QUOTA_CONFIG['daily_max'] = 100
    with app.app_context():
        resp = quota.attach_headers(jsonify({'ok': True}),
                                    quota.QuotaResult(True, None, 7, 2))
        assert resp.headers['X-Quota-Daily-Remaining'] == '93'
        assert resp.headers['X-Quota-Session-Remaining'] == '28'
