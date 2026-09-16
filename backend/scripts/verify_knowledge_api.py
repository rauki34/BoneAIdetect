"""知识库接口契约验证（HTTP 层）

覆盖：权限门禁 → 上传（含扫描件诚实失败）→ 检索预览 →
对话带引用 → 解读引用落库不丢 → 跨患者越权

用法：
    # 1. 以 DEBUG 级别启动后端（脚本需从日志读取验证码明文）
    cd backend && LOG_LEVEL=DEBUG python app.py

    # 2. 另开终端运行本脚本
    cd backend && python scripts/verify_knowledge_api.py [日志文件路径]
                                  [--with-llm]

不加 --with-llm 时，不触发真实模型调用（对话用例会因耗时而跳过）。

退出码 = 失败用例数。
"""
import io
import json
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:5000'
LOG = None
for arg in sys.argv[1:]:
    if not arg.startswith('--'):
        LOG = pathlib.Path(arg)
WITH_LLM = '--with-llm' in sys.argv
PASSWORD = '123456'

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def skip(name, why):
    SKIP.append(name)
    print(f'  [SKIP] {name}  {why}')


def section(title):
    print(f'\n{title}')


# ---------- 登录（复用 verify_auth_flow 的验证码方案） ----------

def fetch_captcha():
    r = requests.get(f'{BASE}/api/captcha', timeout=10)
    r.raise_for_status()
    captcha_id = r.headers.get('X-Captcha-ID')
    if not captcha_id:
        raise RuntimeError('响应缺少 X-Captcha-ID')
    code = None
    if LOG and LOG.exists():
        text = LOG.read_text(encoding='utf-8', errors='ignore')
        hits = re.findall(r'生成验证码:\s*([0-9A-Z]{4}),\s*captcha_id:\s*(\S+)', text)
        for found, cid in reversed(hits):
            if cid == captcha_id:
                code = found
                break
    return captcha_id, code


def login(username, attempts=3):
    """登录，遇到限流时等待重试

    登录限流是 5 次/分钟（按 IP），连续跑几次验证脚本就会撞上——
    此时必须等，不能当作"登录失败"直接跳过后续用例。
    """
    last = ''
    for attempt in range(attempts):
        captcha_id, code = fetch_captcha()
        if not code:
            return None, '未能从日志读到验证码明文（后端需以 LOG_LEVEL=DEBUG 启动）'
        r = requests.post(f'{BASE}/api/login', json={
            'username': username, 'password': PASSWORD,
            'captcha_id': captcha_id, 'captcha': code,
        }, timeout=30)
        if r.status_code == 200:
            return (r.json().get('access_token') or r.json().get('token')), ''
        last = f'HTTP {r.status_code} {r.text[:100]}'
        if r.status_code == 429:
            wait = 22 if attempt == 0 else 45
            print(f'    （{username} 登录被限流，等待 {wait}s 后重试）')
            time.sleep(wait)
            continue
        break
    return None, last


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def discover_users():
    """从数据库取各角色真实账号，避免硬编码"""
    from core.bootstrap import build_bare_app
    build_bare_app()
    from database import User
    users = {}
    for role in ('admin', 'doctor', 'patient'):
        u = User.query.filter_by(role=role).first()
        if u:
            users[role] = u.username
    return users


def make_scanned_pdf():
    """生成一个无文本层的 PDF（模拟扫描件）"""
    from pypdf import PdfWriter
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(buf)
    buf.seek(0)
    return buf


def main():
    served = False
    try:
        requests.get(f'{BASE}/api/captcha', timeout=5)
        served = True
    except requests.exceptions.RequestException as e:
        print(f'后端未启动或不可达: {e}')
        print('请先运行: cd backend && LOG_LEVEL=DEBUG python app.py')
        return 1

    users = discover_users()
    print(f'接口地址: {BASE}')
    print(f'账号: {users}\n')

    tokens = {}
    for role in ('admin', 'doctor', 'patient'):
        if role not in users:
            continue
        token, err = login(users[role])
        if token:
            tokens[role] = token
        else:
            print(f'  [{role}] 登录失败: {err}')

    # ---------- 0. 基础端点 ----------
    # 放在这里而不是单开脚本：这个脚本每阶段都会跑。
    # 起因是阶段 4 的收尾提交把 app.py 里的 `from core.paths import ...`
    # 收窄成只剩 MODEL_CANDIDATES，而 /results、/uploads 两个静态路由仍在用
    # 裸的 RESULTS/UPLOADS —— 图片从此全部 500，却跨过两个阶段无人发现，
    # 因为没有任何测试真正**取过一张图**（冒烟只验证接口返回了图片路径）。
    section('[0] 基础端点（静态资源）')
    import os
    backend_dir = pathlib.Path(__file__).resolve().parent.parent
    assets = [('/results', backend_dir / 'results'),
              ('/uploads', backend_dir / 'uploads')]
    for prefix, directory in assets:
        names = sorted(os.listdir(directory)) if directory.exists() else []
        if not names:
            skip(f'{prefix}/<file> 可取', '目录下没有文件可供测试')
            continue
        r = requests.get(f'{BASE}{prefix}/{names[0]}', timeout=15)
        ok = r.status_code == 200 and 'image' in r.headers.get('Content-Type', '')
        check(f'{prefix}/<file> 返回图片', ok,
              f'HTTP {r.status_code} {r.headers.get("Content-Type", "")} '
              f'{len(r.content)} 字节')

    # ---------- 1. 权限门禁 ----------
    section('[1] 知识库接口权限门禁')
    r = requests.get(f'{BASE}/api/knowledge/docs', timeout=15)
    check('未认证访问文档列表 → 401', r.status_code == 401, f'HTTP {r.status_code}')

    if 'patient' in tokens:
        r = requests.get(f'{BASE}/api/knowledge/docs', headers=auth(tokens['patient']), timeout=15)
        check('患者访问文档列表 → 403', r.status_code == 403, f'HTTP {r.status_code}')

    if 'doctor' in tokens:
        r = requests.get(f'{BASE}/api/knowledge/docs', headers=auth(tokens['doctor']), timeout=15)
        check('医生访问文档列表 → 200', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code == 200:
            data = r.json().get('data', [])
            check('文档列表返回共享语料', len(data) > 0, f'{len(data)} 篇')

    if 'admin' in tokens:
        r = requests.get(f'{BASE}/api/knowledge/stats', headers=auth(tokens['admin']), timeout=15)
        ok = r.status_code == 200
        check('管理员访问知识库统计 → 200', ok, f'HTTP {r.status_code}')
        if ok:
            d = r.json().get('data', {})
            print(f"      共享文档 {d.get('docs_shared')} 篇 / 切片 {d.get('chunks')} 个 / "
                  f"按来源 {d.get('by_origin')}")

    # ---------- 2. 上传：扫描件诚实失败 ----------
    section('[2] 上传（扫描件应被明确拒绝，而非静默空入库）')
    if 'doctor' in tokens:
        r = requests.post(
            f'{BASE}/api/knowledge/docs',
            headers=auth(tokens['doctor']),
            files={'file': ('扫描件.pdf', make_scanned_pdf(), 'application/pdf')},
            data={'title': '契约验证-扫描件'},
            timeout=120,
        )
        check('上传无文本层 PDF → 422', r.status_code == 422, f'HTTP {r.status_code}')
        if r.status_code == 422:
            print(f"      错误文案: {r.json().get('error', '')[:70]}")

        r = requests.post(
            f'{BASE}/api/knowledge/docs',
            headers=auth(tokens['doctor']),
            files={'file': ('x.rtf', io.BytesIO(b'hello'), 'text/rtf')},
            timeout=60,
        )
        check('上传不支持的类型 → 415', r.status_code == 415, f'HTTP {r.status_code}')

    # ---------- 3. 检索预览 ----------
    section('[3] 检索预览（混合检索可观察性）')
    if 'doctor' in tokens:
        r = requests.post(f'{BASE}/api/knowledge/search', headers=auth(tokens['doctor']),
                          json={'query': '股骨远端骨折的AO分型标准', 'top_k': 3}, timeout=180)
        ok = r.status_code == 200
        check('检索接口 → 200', ok, f'HTTP {r.status_code}')
        if ok:
            body = r.json()
            results = body.get('results', [])
            check('检索返回结果', len(results) > 0, f'{len(results)} 条，耗时 {body.get("took_ms")}ms')
            if results:
                first = results[0]
                print(f"      首条: {first.get('doc', '')[:30]} | {first.get('section', '')} "
                      f"| score={first.get('score')} vec#{first.get('vec_rank')} "
                      f"bm25#{first.get('bm25_rank')}")
                check('结果含混合检索诊断字段',
                      all(k in first for k in
                          ('vec_rank', 'bm25_rank', 'rrf_score', 'origin', 'snippet')))

        r = requests.post(f'{BASE}/api/knowledge/search', headers=auth(tokens['doctor']),
                          json={'query': ''}, timeout=30)
        check('空查询 → 400', r.status_code == 400, f'HTTP {r.status_code}')

    # ---------- 4. 对话带引用 ----------
    section('[4] 对话接口返回引用')
    if 'patient' not in tokens:
        # 必须显式记一条 SKIP：整块静默跳过会让报告看起来"全都通过了"
        skip('对话返回 references', '患者账号登录失败，无法验证')
    elif not WITH_LLM:
        skip('对话返回 references', '未指定 --with-llm（真实模型调用耗时较长）')
    else:
        if True:
            session_id = f'kb-verify-{int(time.time())}'
            r = requests.post(f'{BASE}/api/ai-assistant/chat', headers=auth(tokens['patient']),
                              json={'session_id': session_id,
                                    'message': '股骨远端骨折的AO分型标准是什么'},
                              timeout=300)
            ok = r.status_code == 200
            check('对话接口 → 200', ok, f'HTTP {r.status_code}')
            if ok:
                body = r.json()
                refs = body.get('references', [])
                check('对话返回 references', len(refs) > 0, f'{len(refs)} 条')
                if refs:
                    spec_keys = ('index', 'doc', 'section', 'page', 'chunk_id', 'score')
                    check('references 含契约要求的 6 个键',
                          all(k in refs[0] for k in spec_keys),
                          f'缺少 {[k for k in spec_keys if k not in refs[0]]}')
                    print(f"      引用[1]: {refs[0].get('doc', '')[:36]} | "
                          f"origin={refs[0].get('origin')} | score={refs[0].get('score')}")
                reply = body.get('reply', '')
                check('回答含引用编号 [n]', bool(re.search(r'\[\d+\]', reply)),
                      f'回答片段: {reply[:50]}')

                # 刷新后引用应仍在（对应 ai_conversations.references 列）
                r2 = requests.get(f'{BASE}/api/ai-assistant/history',
                                  headers=auth(tokens['patient']),
                                  params={'session_id': session_id}, timeout=30)
                if r2.status_code == 200:
                    msgs = r2.json().get('messages', [])
                    assistant = [m for m in msgs if m.get('role') == 'assistant']
                    persisted = bool(assistant and assistant[-1].get('references'))
                    check('引用随历史持久化（刷新不丢）', persisted,
                          f'历史中 assistant 消息 {len(assistant)} 条')

    # ---------- 5. 解读引用落库不丢 ----------
    section('[5] 解读引用经保存后不丢失（回归：白名单会静默丢弃字段）')
    # 用 admin 提交：它可修改任意记录，因此不受"医生只能改自己创建的记录"
    # 的限制，用例不会因数据缺失而跳过
    if 'admin' in tokens:
        refs = [{'index': 1, 'doc': '契约验证文档', 'section': '1 测试', 'page': None,
                 'chunk_id': 1, 'score': 0.9, 'origin': 'curated', 'snippet': '测试片段'}]
        r = requests.get(f'{BASE}/api/history', headers=auth(tokens['admin']), timeout=30)
        items = r.json().get('data', []) if r.status_code == 200 else []
        own = [it for it in items if it.get('filename')]
        if not own:
            skip('保存解读后引用仍在', '库里没有检测记录可供保存')
        else:
            history_id = own[0]['id']
            r = requests.post(f'{BASE}/api/history/{history_id}/advice',
                              headers=auth(tokens['admin']),
                              json={'interpretation': '契约验证：正文含引用 [1]',
                                    'references': refs,
                                    'patient_info': {}, 'prompt': 'x'},
                              timeout=30)
            check('保存解读结果 → 200', r.status_code == 200, f'HTTP {r.status_code}')
            if r.status_code == 200:
                r2 = requests.get(f'{BASE}/api/history/{history_id}',
                                  headers=auth(tokens['admin']), timeout=30)
                if r2.status_code == 200:
                    advice = r2.json().get('medical_advice') or {}
                    if isinstance(advice, str):
                        try:
                            advice = json.loads(advice)
                        except ValueError:
                            advice = {}
                    saved = advice.get('references')
                    check('保存后 references 仍存在', bool(saved),
                          f'读回 {len(saved) if saved else 0} 条')

    # ---------- 6. 跨患者越权 ----------
    section('[6] 跨患者越权')
    if 'doctor' in tokens:
        # 找一个该医生无权访问的患者 id：取一个不存在关联的
        from core.bootstrap import build_bare_app
        build_bare_app()
        from database import DoctorPatientRelation, User
        doctor = User.query.filter_by(username=users.get('doctor')).first()
        linked = {r.patient_id for r in
                  DoctorPatientRelation.query.filter_by(doctor_id=doctor.id).all()}
        target = User.query.filter(User.role == 'patient',
                                   ~User.id.in_(linked or {0})).first()
        if not target:
            skip('医生访问未关联患者的资料 → 403', '找不到未关联的患者')
        else:
            r = requests.get(f'{BASE}/api/knowledge/docs',
                             headers=auth(tokens['doctor']),
                             params={'patient_id': target.id}, timeout=30)
            check('医生访问未关联患者的资料 → 403', r.status_code == 403,
                  f'HTTP {r.status_code}（患者 id={target.id}）')
            r = requests.post(f'{BASE}/api/knowledge/search',
                              headers=auth(tokens['doctor']),
                              json={'query': 'x', 'patient_id': target.id,
                                    'include_personal': True}, timeout=60)
            check('医生检索未关联患者的病历 → 403', r.status_code == 403,
                  f'HTTP {r.status_code}')

    if 'patient' in tokens:
        r = requests.post(f'{BASE}/api/knowledge/search', headers=auth(tokens['patient']),
                          json={'query': 'x'}, timeout=30)
        check('患者访问知识库检索 → 403', r.status_code == 403, f'HTTP {r.status_code}')

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)} / 跳过 {len(SKIP)}')
    if FAIL:
        print('\n  失败用例：')
        for name in FAIL:
            print(f'    - {name}')
    return len(FAIL)


if __name__ == '__main__':
    sys.exit(main())
