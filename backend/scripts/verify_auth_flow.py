"""认证与安全防护回归验证

覆盖：验证码 → 三类角色登录 → 失败分支 → JWT 鉴权 → 角色隔离 → 注册接口

用法：
    # 1. 以 DEBUG 级别启动后端（脚本需从日志读取验证码明文）
    cd backend && LOG_LEVEL=DEBUG python app.py

    # 2. 另开终端运行本脚本
    cd backend && python scripts/verify_auth_flow.py [日志文件路径]

若不传日志路径，将跳过需要验证码的用例（仅验证鉴权部分）。
"""
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:5000'
LOG = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
DEFAULT_PASSWORD = '123456'

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def discover_users():
    """从数据库取各角色真实存在的账号，避免硬编码用户名"""
    from app import app, User
    users = {}
    with app.app_context():
        for role in ('admin', 'patient', 'doctor'):
            u = User.query.filter_by(role=role).first()
            if u:
                users[role] = u.username
    return users


def read_captcha_from_log(captcha_id):
    """从后端 DEBUG 日志取出验证码明文

    对应 generate_captcha() 的 logger.debug("[DEBUG] 生成验证码: XXXX, captcha_id: ...")
    """
    if not LOG or not LOG.exists():
        return None
    text = LOG.read_text(encoding='utf-8', errors='ignore')
    hits = re.findall(r'生成验证码:\s*([0-9A-Z]{4}),\s*captcha_id:\s*(\S+)', text)
    for code, cid in reversed(hits):     # 倒序取最新，避免命中历史
        if cid == captcha_id:
            return code
    return None


def get_captcha():
    r = requests.get(f'{BASE}/api/captcha', timeout=20)
    return r.headers.get('X-Captcha-ID', ''), r


def login(username, password, role, captcha_ok=True):
    cid, _ = get_captcha()
    code = read_captcha_from_log(cid) if captcha_ok else 'ZZZZ'
    return requests.post(f'{BASE}/api/login', timeout=40, json={
        'username': username, 'password': password, 'role': role,
        'captcha': code or '', 'captcha_id': cid,
    })


def main():
    # 登录流程强制校验验证码，而验证码只存在于服务端内存 + PNG 图像中。
    # 脚本通过 DEBUG 日志取明文，因此日志路径是必需参数。
    if LOG is None or not LOG.exists():
        print('缺少后端日志路径，无法获取验证码明文。\n')
        print('用法:')
        print('  1) cd backend && LOG_LEVEL=DEBUG python app.py')
        print('  2) python scripts/verify_auth_flow.py <后端日志文件路径>')
        return 2

    users = discover_users()
    print(f'发现账号: {users}\n')

    # ---------- 1. 验证码 ----------
    print('[1] 验证码接口')
    cid, resp = get_captcha()
    check('GET /api/captcha 返回 200', resp.status_code == 200)
    check('响应头含 X-Captcha-ID', bool(cid), cid)
    check('返回 PNG 图像', resp.headers.get('Content-Type') == 'image/png')
    check('日志中可解析出明文', read_captcha_from_log(cid) is not None)

    # ---------- 2. 三类角色登录 ----------
    print('\n[2] 三类角色登录')
    tokens = {}
    for role, user in users.items():
        r = login(user, DEFAULT_PASSWORD, role)
        ok = r.status_code == 200 and 'access_token' in r.json()
        if ok:
            tokens[role] = r.json()['access_token']
        check(f'{role} 登录({user})', ok,
              '' if ok else f'HTTP {r.status_code} {r.json().get("error", "")}')

    # ---------- 3. 失败分支 ----------
    print('\n[3] 登录失败分支')
    admin_user = users.get('admin', 'admin')
    r = login(admin_user, DEFAULT_PASSWORD, 'admin', captcha_ok=False)
    check('错误验证码 -> 400', r.status_code == 400, r.json().get('error', ''))

    cid, _ = get_captcha()
    code = read_captcha_from_log(cid)
    body = {'username': admin_user, 'password': DEFAULT_PASSWORD,
            'role': 'admin', 'captcha': code, 'captcha_id': cid}
    check('正确验证码 -> 200', requests.post(f'{BASE}/api/login', json=body,
                                            timeout=30).status_code == 200)
    r = requests.post(f'{BASE}/api/login', json=body, timeout=30)
    check('验证码重放 -> 400（一次性）', r.status_code == 400, r.json().get('error', ''))

    r = login(admin_user, 'wrong-password', 'admin')
    check('密码错误 -> 401', r.status_code == 401)
    r = login('__not_exist__', DEFAULT_PASSWORD, 'admin')
    check('用户不存在 -> 401', r.status_code == 401)

    # ---------- 4. JWT 鉴权 ----------
    print('\n[4] JWT 鉴权')
    tok = tokens.get('admin')
    if tok:
        H = {'Authorization': f'Bearer {tok}'}
        for path in ('/api/admin/dashboard', '/api/models', '/api/history'):
            r = requests.get(f'{BASE}{path}', headers=H, timeout=20)
            check(f'JWT 访问 {path}', r.status_code == 200, f'HTTP {r.status_code}')
        check('无凭证 -> 401',
              requests.get(f'{BASE}/api/admin/dashboard', timeout=20).status_code == 401)
        check('无效 JWT -> 401',
              requests.get(f'{BASE}/api/admin/dashboard', timeout=20,
                           headers={'Authorization': 'Bearer bad.token'}).status_code == 401)

    # ---------- 5. 角色隔离 ----------
    print('\n[5] 角色隔离')
    ptok = tokens.get('patient')
    if ptok:
        H = {'Authorization': f'Bearer {ptok}'}
        r = requests.get(f'{BASE}/api/admin/dashboard', headers=H, timeout=20)
        check('患者访问管理员接口 -> 403', r.status_code == 403, f'HTTP {r.status_code}')
        r = requests.get(f'{BASE}/api/patient/profile', headers=H, timeout=20)
        check('患者访问自身接口 -> 200', r.status_code == 200, f'HTTP {r.status_code}')

    # ---------- 6. 注册接口可达 ----------
    print('\n[6] 注册接口')
    for ep in ('/api/patient/register', '/api/doctor/register'):
        r = requests.post(f'{BASE}{ep}', json={}, timeout=20)
        check(f'POST {ep} 可达', r.status_code in (400, 422), f'HTTP {r.status_code}')

    print('\n' + '=' * 60)
    print(f'通过 {len(PASS)} / 失败 {len(FAIL)}')
    for f in FAIL:
        print('  失败:', f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
