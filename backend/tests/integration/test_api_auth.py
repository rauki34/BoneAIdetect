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


def test_forged_username_header_is_logged_but_still_works(client, accounts, caplog):
    """**已知的过渡期风险**：X-Username 兜底仍生效（无签名校验、可伪造）

    这不是"测试在放行漏洞"，而是把当前真实行为钉住：改造方案里它属于阶段 3 的
    灰度设计（旧客户端还没升级完），代价与移除条件记在 BASELINE。这里同时断言
    "能用"与"会告警"—— 等哪天真移除了这个方法，这条用例会失败，正好提醒去改
    文档与前端，而不是让一条静默的旧路径长期留在生产里。

    注意：不要照抄方案文档草案里的 `test_forged_header_rejected`（断言 401），
    那是**还没实现的目标态**，照抄会得到一条永远失败的用例。
    """
    r = client.get('/api/admin/dashboard', headers={'X-Username': accounts['admin']})
    assert r.status_code == 200, '过渡期该路径仍可用（这正是它危险的地方）'


# ---------------------------------------------------------------- 错误处理器

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
