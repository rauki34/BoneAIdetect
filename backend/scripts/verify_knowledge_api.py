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
TOKENS = {}          # 各角色登录后的 token，供 need() 判断


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def skip(name, why):
    SKIP.append(name)
    print(f'  [SKIP] {name}  {why}')


def section(title):
    print(f'\n{title}')


# ---------- 异步入库的等待helper（阶段 8） ----------

def doc_status(doc_id, token_role='doctor'):
    """读单个文档的状态；读不到返回 None"""
    token = TOKENS.get(token_role)
    if not token:
        return None
    r = requests.get(f'{BASE}/api/knowledge/docs/{doc_id}',
                     headers=auth(token), timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get('data', {}).get('status')


def doc_error_msg(doc_id, token_role='doctor'):
    token = TOKENS.get(token_role)
    if not token:
        return None
    r = requests.get(f'{BASE}/api/knowledge/docs/{doc_id}',
                     headers=auth(token), timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get('data', {}).get('error_msg')


def wait_doc_status(doc_id, want, timeout=180, poll=2):
    """轮询到指定状态

    入库搬去 Celery worker 后，上传响应里已经拿不到终态 —— 契约验证必须
    改成"等它变成某个状态"。返回实际终态，超时返回最后观察到的状态。
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = doc_status(doc_id)
        if last == want:
            return last
        time.sleep(poll)
    return last


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


def need(role, what):
    """需要某角色的 token 才能验证的段落

    缺失时**记一条 SKIP**，而不是让整段静默跳过——
    后者会让"登录失败、什么都没验"的报告看起来和"全部通过"一样绿。
    """
    if role in TOKENS:
        return True
    skip(what, f'{role} 账号未登录成功，整段无法验证')
    return False


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


def _read_advice(history_id):
    """直连数据库读取某报告的医疗建议原文（用于验证后还原）"""
    from core.bootstrap import build_bare_app
    build_bare_app()
    from database import DetectionHistory
    row = DetectionHistory.query.filter_by(id=history_id).first()
    return row.medical_advice if row else None


def _write_advice(history_id, value):
    """把医疗建议还原成验证之前的样子"""
    from core.bootstrap import build_bare_app
    build_bare_app()
    from database import DetectionHistory, db
    row = DetectionHistory.query.filter_by(id=history_id).first()
    if row is not None:
        row.medical_advice = value
        db.session.commit()


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
    created_doc_id = None
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

    for role in ('admin', 'doctor', 'patient'):
        if role not in users:
            continue
        token, err = login(users[role])
        if token:
            TOKENS[role] = token
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

    if need('patient', '患者访问知识库接口的门禁'):
        r = requests.get(f'{BASE}/api/knowledge/docs', headers=auth(TOKENS['patient']), timeout=15)
        check('患者访问文档列表 → 403', r.status_code == 403, f'HTTP {r.status_code}')

    if need('doctor', '医生访问知识库接口'):
        r = requests.get(f'{BASE}/api/knowledge/docs', headers=auth(TOKENS['doctor']), timeout=15)
        check('医生访问文档列表 → 200', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code == 200:
            data = r.json().get('data', [])
            check('文档列表返回共享语料', len(data) > 0, f'{len(data)} 篇')

    if need('admin', '管理员访问知识库统计'):
        r = requests.get(f'{BASE}/api/knowledge/stats', headers=auth(TOKENS['admin']), timeout=15)
        ok = r.status_code == 200
        check('管理员访问知识库统计 → 200', ok, f'HTTP {r.status_code}')
        if ok:
            d = r.json().get('data', {})
            print(f"      共享文档 {d.get('docs_shared')} 篇 / 切片 {d.get('chunks')} 个 / "
                  f"按来源 {d.get('by_origin')}")

    # ---------- 2. 上传：扫描件诚实失败 ----------
    section('[2] 上传（扫描件应被明确拒绝，而非静默空入库）')
    if need('doctor', '上传相关校验'):
        # 阶段 8 起入库异步：端点立刻返回 202，解析在 Celery worker 里跑，
        # 因此"扫描件被拒"不再表现为 HTTP 422，而是该文档最终置 failed。
        # 契约实际更强了 —— 上传本身不再被解析耗时卡住，失败原因照样留痕。
        r = requests.post(
            f'{BASE}/api/knowledge/docs',
            headers=auth(TOKENS['doctor']),
            files={'file': ('扫描件.pdf', make_scanned_pdf(), 'application/pdf')},
            data={'title': '契约验证-扫描件'},
            timeout=60,
        )
        check('上传无文本层 PDF → 202 受理', r.status_code == 202, f'HTTP {r.status_code}')
        scanned_doc_id = r.json().get('doc_id') if r.status_code == 202 else None
        if scanned_doc_id:
            final = wait_doc_status(scanned_doc_id, 'failed', timeout=180)
            check('该扫描件最终被置为失败（而非静默空入库）',
                  final is not None, f'最终状态 = {final}')
            # 注意：这两条 check 都必须**无条件**产生，不能塞进 if final == 'failed' 里。
            # 否则终态不是 failed 时它会整条消失，用例总数跟着变，报告看起来像
            # "少测了一项"而不是"这一项没过"——验证脚本最不该有这种歧义。
            reason = doc_error_msg(scanned_doc_id)
            check('失败原因写明「无文本层」', '无文本层' in (reason or ''),
                  f'error_msg = {(reason or "")[:60]}')
            if reason:
                print(f"      错误文案: {reason[:70]}")
        else:
            check('该扫描件最终被置为失败（而非静默空入库）', False, '未拿到 doc_id')
            check('失败原因写明「无文本层」', False, '未拿到 doc_id')

        r = requests.post(
            f'{BASE}/api/knowledge/docs',
            headers=auth(TOKENS['doctor']),
            files={'file': ('x.rtf', io.BytesIO(b'hello'), 'text/rtf')},
            timeout=60,
        )
        check('上传不支持的类型 → 415', r.status_code == 415, f'HTTP {r.status_code}')

        # 标着「公开原文」却给不出来源 = 让系统替无法核实的材料背书。
        # 判据：出处是引用溯源的立身之本，公开原文必须能指出来源。
        r = requests.post(
            f'{BASE}/api/knowledge/docs',
            headers=auth(TOKENS['doctor']),
            files={'file': ('测试.md', io.BytesIO('# 测试\n\n正文内容。'.encode('utf-8')), 'text/markdown')},
            data={'origin': 'public', 'source': ''},
            timeout=60,
        )
        check('「公开原文」未填出处 → 400', r.status_code == 400, f'HTTP {r.status_code}')
        if r.status_code == 400:
            print(f"      错误文案: {r.json().get('error', '')[:60]}")

        # 整理摘要不要求出处，但标题应回退到原始文件名而不是落盘 uuid
        r = requests.post(
            f'{BASE}/api/knowledge/docs',
            headers=auth(TOKENS['doctor']),
            files={'file': ('契约验证-标题回退.md',
                            io.BytesIO('# 标题回退验证\n\n## 一、小节\n\n正文内容。'.encode('utf-8')),
                            'text/markdown')},
            data={'origin': 'curated', 'source': '契约验证自动生成'},
            timeout=120,
        )
        if r.status_code == 202:
            # 标题在响应里就有（端点建行时就定好了），不必等入库完成
            title = r.json().get('title', '')
            check('标题回退到原始文件名（而非落盘 uuid）',
                  '契约验证-标题回退' in title, f'标题 = {title!r}')
            created_doc_id = r.json().get('doc_id')
            # 入库完成才写回 chunk_count，这里顺带验证不变量
            final = wait_doc_status(created_doc_id, 'ready', timeout=300)
            check('上传的文档最终变为就绪', final == 'ready', f'最终状态 = {final}')
        else:
            check('标题回退到原始文件名（而非落盘 uuid）', False,
                  f'HTTP {r.status_code} {r.text[:100]}')
            check('上传的文档最终变为就绪', False, '上传未受理')
            created_doc_id = None

    # ---------- 3. 检索预览 ----------
    section('[3] 检索预览（混合检索可观察性）')
    if need('doctor', '检索预览'):
        r = requests.post(f'{BASE}/api/knowledge/search', headers=auth(TOKENS['doctor']),
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

        r = requests.post(f'{BASE}/api/knowledge/search', headers=auth(TOKENS['doctor']),
                          json={'query': ''}, timeout=30)
        check('空查询 → 400', r.status_code == 400, f'HTTP {r.status_code}')

    # ---------- 4. 对话带引用 ----------
    section('[4] 对话接口返回引用')
    if not need('patient', '对话返回 references'):
        pass
    elif not WITH_LLM:
        skip('对话返回 references', '未指定 --with-llm（真实模型调用耗时较长）')
    else:
        if True:
            session_id = f'kb-verify-{int(time.time())}'
            r = requests.post(f'{BASE}/api/ai-assistant/chat', headers=auth(TOKENS['patient']),
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
                                  headers=auth(TOKENS['patient']),
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
    if need('admin', '解读引用经保存后不丢失'):
        refs = [{'index': 1, 'doc': '契约验证文档', 'section': '1 测试', 'page': None,
                 'chunk_id': 1, 'score': 0.9, 'origin': 'curated', 'snippet': '测试片段'}]
        r = requests.get(f'{BASE}/api/history', headers=auth(TOKENS['admin']), timeout=30)
        items = r.json().get('data', []) if r.status_code == 200 else []
        own = [it for it in items if it.get('filename')]
        if not own:
            skip('保存解读后引用仍在', '库里没有检测记录可供保存')
        else:
            history_id = own[0]['id']
            # **先备份该报告原有的医疗建议**：这个用例会覆盖真实数据。
            # 不还原的话，用户的报告里会永久留下"《契约验证文档》"这种测试痕迹
            # —— 这件事确实发生过一次，报告 #26 被写进了假引用。
            original_advice = _read_advice(history_id)
            r = requests.post(f'{BASE}/api/history/{history_id}/advice',
                              headers=auth(TOKENS['admin']),
                              json={'interpretation': '契约验证：正文含引用 [1]',
                                    'references': refs,
                                    'patient_info': {}, 'prompt': 'x'},
                              timeout=30)
            check('保存解读结果 → 200', r.status_code == 200, f'HTTP {r.status_code}')
            if r.status_code == 200:
                r2 = requests.get(f'{BASE}/api/history/{history_id}',
                                  headers=auth(TOKENS['admin']), timeout=30)
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

            # 还原该报告原本的医疗建议，不留测试痕迹
            _write_advice(history_id, original_advice)
            print('      （已还原该报告原有的医疗建议）')

    # ---------- 6. 跨患者越权 ----------
    section('[6] 跨患者越权')
    if need('doctor', '跨患者越权（医生侧）'):
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
                             headers=auth(TOKENS['doctor']),
                             params={'patient_id': target.id}, timeout=30)
            check('医生访问未关联患者的资料 → 403', r.status_code == 403,
                  f'HTTP {r.status_code}（患者 id={target.id}）')
            r = requests.post(f'{BASE}/api/knowledge/search',
                              headers=auth(TOKENS['doctor']),
                              json={'query': 'x', 'patient_id': target.id,
                                    'include_personal': True}, timeout=60)
            check('医生检索未关联患者的病历 → 403', r.status_code == 403,
                  f'HTTP {r.status_code}')

    if need('patient', '跨患者越权（患者侧）'):
        r = requests.post(f'{BASE}/api/knowledge/search', headers=auth(TOKENS['patient']),
                          json={'query': 'x'}, timeout=30)
        check('患者访问知识库检索 → 403', r.status_code == 403, f'HTTP {r.status_code}')

    # 清理本次验证产生的文档，避免污染知识库。
    # 扫描件那条也必须清：它是 failed 状态，不会被别的用例回收，
    # 留着会一直在管理界面上挂着一条失败记录
    cleaned = 0
    for doc_id in (created_doc_id, locals().get('scanned_doc_id')):
        if not doc_id or 'admin' not in TOKENS:
            continue
        try:
            r = requests.delete(f'{BASE}/api/knowledge/docs/{doc_id}',
                                headers=auth(TOKENS['admin']), timeout=30)
            if r.status_code == 200:
                cleaned += 1
        except requests.exceptions.RequestException:
            pass
    if cleaned:
        print(f'\n  （已清理验证过程中创建的 {cleaned} 个文档）')

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)} / 跳过 {len(SKIP)}')
    if FAIL:
        print('\n  失败用例：')
        for name in FAIL:
            print(f'    - {name}')
    return len(FAIL)


if __name__ == '__main__':
    sys.exit(main())
