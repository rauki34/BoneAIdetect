"""认证、权限与错误处理器的 HTTP 层契约（需要完整 app + 数据库）

与 `scripts/verify_auth_flow.py` 的分工：那个脚本要从日志读验证码做**真实登录**，
覆盖验证码、限流、注册等完整链路；这里直接签发 JWT，只钉住"每个请求都要重新
确认"的那几条结构性质，跑得快、放在 CI 里也能拦住改坏。

需要数据库里有账号，没有则 skip（而不是失败）——CI 上没有种子数据是正常的。
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope='session')
def accounts(full_app):
    """从库里挑三类角色的真实账号；库里没有就跳过整个文件"""
    from database import User
    with full_app.app_context():
        found = {}
        for role in ('admin', 'doctor', 'patient'):
            user = User.query.filter_by(role=role).first()
            if user:
                found[role] = user.username
    if len(found) < 3:
        pytest.skip(f'数据库里角色不全（找到 {sorted(found)}），跳过 HTTP 权限用例')
    return found


@pytest.fixture()
def token(full_app):
    def _mint(username):
        from flask_jwt_extended import create_access_token
        with full_app.app_context():
            return create_access_token(identity=username)
    return _mint


@pytest.fixture(autouse=True)
def _clear_rate_and_quota(accounts, full_app):
    """清掉这些账号的分钟级限流与本次会话的额度计数

    本文件会往 `/api/agent/chat` 连打几个请求，而它的分钟阈值是 5 次/分
    —— 连着跑两次、或者紧跟在 `scripts/verify_agent.py` 之后跑（它也会打满），
    拿到的就是 429 而不是被测的状态码，看起来像功能坏了。
    限流计数是测试自有的状态，清掉即可（`verify_agent.py` 开头做的是同一件事）。
    """
    from core.cache import get_redis
    client = get_redis()
    if client is None:
        yield
        return
    from database import User
    with full_app.app_context():
        ids = [u.id for u in User.query.filter(
            User.username.in_(list(accounts.values()))).all()]
    for uid in ids:
        client.delete(f'rl:agent_chat:user:{uid}', f'rl:ai_chat:user:{uid}',
                      f'quota:session:{uid}:pytest')
    yield


def auth(tok):
    return {'Authorization': f'Bearer {tok}'}


# ---------------------------------------------------------------- 认证

def test_protected_endpoint_requires_token(client):
    assert client.get('/api/admin/dashboard').status_code == 401
    assert client.get('/api/history').status_code == 401


def test_invalid_token_rejected(client):
    """伪造/失效的 JWT 必须被拒 —— 这是 JWT 相对 X-Username 的全部意义"""
    r = client.get('/api/admin/dashboard', headers=auth('not-a-real-token'))
    assert r.status_code == 401
    body = r.get_json()
    assert body['error_code'] == 'AUTH_001'


def test_valid_token_accepted(client, accounts, token):
    r = client.get('/api/admin/dashboard', headers=auth(token(accounts['admin'])))
    assert r.status_code == 200


# ---------------------------------------------------------------- 角色隔离

@pytest.mark.parametrize('path', ['/api/admin/dashboard', '/api/users',
                                  '/api/logs', '/api/knowledge/docs'])
def test_patient_cannot_reach_admin_endpoints(client, accounts, token, path):
    r = client.get(path, headers=auth(token(accounts['patient'])))
    assert r.status_code == 403
    assert r.get_json()['error_code'] == 'AUTH_002'


def test_doctor_cannot_reach_admin_only_endpoint(client, accounts, token):
    r = client.get('/api/users', headers=auth(token(accounts['doctor'])))
    assert r.status_code == 403


def test_forged_username_header_rejected(client, accounts):
    """伪造的 X-Username 必须被拒

    这条曾经是**反着写的**：改造期间为了灰度切换，后端保留了 X-Username 兜底
    （无签名校验，`curl -H "X-Username: admin"` 即管理员权限），当时的用例把
    "仍能用"钉住并注明"等移除后这条会失败，正好提醒改文档"。

    2026-09-25 移除了那段兜底，用例随之翻面 —— 方案文档草案里的
    `test_forged_header_rejected`（断言 401）从"还没实现的目标态"变成了现实。
    """
    r = client.get('/api/admin/dashboard', headers={'X-Username': accounts['admin']})
    assert r.status_code == 401, '过期两个阶段的认证兜底又回来了？'
    assert r.get_json()['error_code'] == 'AUTH_001'


def test_forged_header_does_not_change_data_scope(client, accounts, token):
    """伪造头不得影响**数据归属**（比伪造身份更隐蔽的一类）

    移除此前的兜底时顺带发现 5 处**直接读该请求头**的地方，其中
    `/api/user-ai-models` 是把它当数据过滤键用的 —— 任何登录用户换个请求头就能
    列出别人的 AI 模型配置。现在那些地方统一改用已认证身份，这里钉住这条不变量：
    带上伪造头与不带，返回必须一致。
    """
    headers = auth(token(accounts['patient']))
    plain = client.get('/api/user-ai-models', headers=headers)
    forged = client.get('/api/user-ai-models',
                        headers={**headers, 'X-Username': accounts['admin']})
    assert plain.status_code == forged.status_code == 200
    assert plain.get_json() == forged.get_json(), '请求头仍在影响数据范围'


# ---------------------------------------------------------------- 错误处理器

def test_health_endpoint(client):
    """健康检查的契约：数据库通才算 ok，Redis 挂了只算 degraded

    Compose 的 healthcheck 与负载均衡探活都读它（`/api/health`），所以判定口径
    要立得住：数据库不可用 = 整个系统不可用；Redis 不可用只是降级（缓存与队列
    退化），不该让容器被判成 unhealthy 而反复重启。
    """
    r = client.get('/api/health')
    assert r.status_code == 200
    body = r.get_json()
    assert body['status'] == 'ok' and body['db'] is True
    assert body['redis'] is True, '本条用例要求本机 Redis 在跑'
    assert body['timestamp']


def test_404_returns_json_error_body(client):
    """错误处理器必须返回约定好的 JSON

    阶段 8 修过一个 bug：9 个 errorhandler 全都用了从未导入的 datetime，
    任何走到错误处理器的请求都会在处理器内部抛 NameError，返回 500 的 HTML
    调试页。这条用例把"错误体是 JSON 且带 error_code"钉住。
    """
    r = client.get('/api/definitely-not-a-real-endpoint')
    assert r.status_code == 404
    body = r.get_json()
    assert body and body.get('error_code') == 'NOT_FOUND'
    assert body.get('timestamp'), '缺少 timestamp 说明错误处理器自身抛异常了'


def test_non_json_body_is_not_500(client, accounts, token, full_app):
    """请求体不是 JSON 时必须返回 4xx，而不是 500

    阶段 11 写这条用例时抓到的真 bug：`request.get_json()` 在 Content-Type
    不对时抛 UnsupportedMediaType(415)，而 Flask 按类层次匹配到了本文件末尾注册的
    `@app.errorhandler(Exception)` → 返回 500「未知错误」。客户端只是漏带
    Content-Type，却看到"服务器内部错误"，会把调试方向完全带偏。

    修法是两层：视图层统一 `get_json(silent=True)`（走各自的"请求数据为空"分支），
    app.py 另加 415 处理器兜底。
    """
    headers = auth(token(accounts['patient']))
    r = client.post('/api/ai-assistant/chat', headers=headers)
    assert r.status_code == 400, f'实际 {r.status_code} —— 又退化成 500 了？'
    assert '请求数据为空' in r.get_json()['error']

    # 带 Content-Type 但没有 body：Flask 抛 BadRequest → 400，同样不能是 500
    r2 = client.post('/api/ai-assistant/chat', headers=headers, data='',
                     content_type='application/json')
    assert r2.status_code == 400

    # 415 处理器本身：所有视图都 silent 之后，HTTP 上已经触发不到它（这本身
    # 是期望的终态），所以这里白盒断言它确实注册着 —— 它是给"将来忘了写
    # silent=True 的新视图"兜底的，缺了就会重新退化成 500
    handlers = full_app.error_handler_spec.get(None, {})
    assert 415 in handlers, '415 处理器缺失：新视图一旦忘了 silent=True 就会 500'


def test_agent_endpoint_rejects_non_patient(client, accounts, token):
    """Agent 只服务患者康复助手：医生/管理员打这个端点应当被角色门禁挡住"""
    r = client.post('/api/agent/chat', headers=auth(token(accounts['doctor'])),
                    json={'session_id': 'pytest', 'message': '你好'})
    assert r.status_code == 403


def test_agent_endpoint_validates_body(client, accounts, token):
    headers = auth(token(accounts['patient']))
    assert client.post('/api/agent/chat', headers=headers,
                       json={'message': '你好'}).status_code == 400
    r = client.post('/api/agent/chat', headers=headers,
                    json={'session_id': 's', 'message': '   '})
    assert r.status_code == 400
    assert r.get_json()['error_code'] == 'AGENT_001'
