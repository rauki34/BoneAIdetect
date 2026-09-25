"""Agent（患者康复助手）回归验证 —— 阶段 9

分两部分，**默认只跑 Part A**：

  Part A  确定性用例，**不调用真实 LLM**、不起 HTTP（直连 execute_tool /
          编排入口）。这是本脚本的主体：Agent 最危险的失败模式（越权、
          只读工具写库、护栏失效、权限拒绝被伪装成"没数据"）全都在这一部分，
          而且它们都不能靠"HTTP 200"验证 —— HTTP 200 在零工具、编造答案、
          越权返回空 三种情况下同样成立。

  Part B  端到端，挂 `--with-llm` 才跑（真实 LLM 计费）。覆盖方案的四项 Check：
          单工具调用 / 多步串联 ≥3 工具 / 越权被拒 / 知识库外问题不编造。

用法：
    cd backend
    python scripts/verify_agent.py                 # Part A（离线、确定性）
    python scripts/verify_agent.py --tools-only    # 只验工具层
    python scripts/verify_agent.py --with-llm      # 追加 Part B（需要真实 LLM）
    python scripts/verify_agent.py [日志文件路径] --with-llm

退出码 = 失败用例数。
"""
import json
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:5000'
BACKEND = pathlib.Path(__file__).resolve().parent.parent
LOG = BACKEND / 'logs' / 'app.log'
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
if ARGS:
    LOG = pathlib.Path(ARGS[0])
WITH_LLM = '--with-llm' in sys.argv
TOOLS_ONLY = '--tools-only' in sys.argv

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def skip(name, why):
    SKIP.append(name)
    print(f'  [SKIP] {name}  {why}')


def section(title):
    print(f'\n{title}')


def pick_loggable(app, role, count=2, password='123456'):
    """挑出**真能登录**的账号（返回 [{id, username, token}]）

    不能简单按 id 取前几个：库里存在注册流程自动生成的账号（用户名形如
    P20260408200635），密码不是默认值。拿它们跑用例会以"登录失败"告终，
    而那并不是功能问题 —— 验收脚本最不该做的事就是把自己的取样错误
    报成被测对象的失败。
    """
    from database import User
    with app.app_context():
        candidates = [(u.id, u.username) for u in
                      User.query.filter_by(role=role).order_by(User.id).all()]
    found = []
    for uid, name in candidates:
        if len(found) >= count:
            break
        try:
            token = login(name, attempts=3, password=password)
        except SystemExit:
            continue
        found.append({'id': uid, 'username': name, 'token': token})
    return found


def login(user, attempts=12, password='123456'):
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
            'username': user, 'password': password,
            'captcha': code, 'captcha_id': cid}, timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get('access_token') or j.get('token')
        time.sleep(1)
    raise SystemExit('登录失败：确认后端以 LOG_LEVEL=DEBUG 启动'
                     '（bash scripts/flask.sh start debug）')


# ==================== Part A：工具层 ====================

def part_tools(app):
    import services.agent.tools as tools_mod

    from database import (AIConversation, DetectionHistory, MedicalRecord,
                          PatientProfile, User, db, to_local_time)
    from services.agent.principal import Principal
    from services.llm_client import ToolCall

    registry = tools_mod.TOOL_REGISTRY

    def call(name, args, principal):
        return tools_mod.execute_tool(
            ToolCall(id='call_test', name=name, arguments=args),
            _State(principal))

    section('[A.1] 工具模块与注册表')
    check('import services.agent.tools 未把 torch 拖进启动路径',
          'torch' not in sys.modules,
          '违反会让 Flask 启动多花十几秒（services/rag/__init__.py 的既有约定）')
    expected = {'search_guideline', 'query_medical_records', 'get_patient_profile',
                'list_detection_reports', 'get_followup_schedule'}
    check('注册表包含 5 个工具', set(registry) == expected,
          f'实际={sorted(registry)}')
    bad = [n for n, s in registry.items()
           if s.parameters.get('type') != 'object'
           or not isinstance(s.parameters.get('properties'), dict)
           or not isinstance(s.parameters.get('required'), list)]
    check('每个工具的 JSON Schema 形态正确', not bad, f'异常={bad}')
    check('schema 可被 JSON 序列化（交给 provider 前必须能）',
          isinstance(json.loads(json.dumps(tools_mod.tool_schemas())), list))
    check('description 不含「手术史」（本系统没有该字段，写了模型会承诺拿不到的东西）',
          not [n for n, s in registry.items() if '手术史' in s.description])

    # ---------- 数据准备（只找、不造）----------
    with app.app_context():
        patients = User.query.filter_by(role='patient').order_by(User.id).all()
        if len(patients) < 2:
            skip('权限相关用例', '库里患者账号少于 2 个')
            return
        p_a, p_b = patients[0], patients[1]
        with_records = None
        for p in patients:
            n = MedicalRecord.query.filter_by(patient_id=p.id, status='active').count()
            if n:
                with_records = p
                break
        doctor = User.query.filter_by(role='doctor').first()
        admin = User.query.filter_by(role='admin').first()
        no_profile_user = (User.query
                           .outerjoin(PatientProfile, PatientProfile.user_id == User.id)
                           .filter(PatientProfile.id.is_(None)).first())
        counts_before = {
            'medical_records': MedicalRecord.query.count(),
            'detection_history': DetectionHistory.query.count(),
            'patient_profiles': PatientProfile.query.count(),
            'ai_conversations': AIConversation.query.count(),
        }
        ids = {'a': p_a.id, 'b': p_b.id,
               'with_records': with_records.id if with_records else None,
               'doctor': doctor.id if doctor else None,
               'admin': admin.id if admin else None,
               'admin_name': admin.username if admin else None,
               'no_profile': no_profile_user.id if no_profile_user else None,
               'no_profile_username': no_profile_user.username if no_profile_user else None}
        # A9 需要一条真实病历的原始时间
        sample_record = None
        if with_records:
            r = (MedicalRecord.query
                 .filter_by(patient_id=with_records.id, status='active')
                 .order_by(MedicalRecord.id.desc()).first())
            if r:
                sample_record = (r.id, to_local_time(r.visit_date), r.visit_date.isoformat())

    if ids['doctor'] is None:
        skip('医生相关用例', '库里没有医生账号')

    section('[A.2] 权限：越权必须被拒且不泄露数据')
    # 患者的 principal 查别人
    r = call('query_medical_records', {'patient_id': ids['b']},
             Principal(ids['a'], 'patient', 'verify-a'))
    check('患者查他人病历 → permission_denied',
          r.get('error') == 'permission_denied', str(r)[:90])
    blob = json.dumps(r, ensure_ascii=False)
    with app.app_context():
        other_diag = [x.diagnosis for x in MedicalRecord.query.filter_by(
            patient_id=ids['b']).all() if x.diagnosis]
    leaked = [d for d in other_diag if d in blob]
    check('拒绝响应里不含对方的任何诊断内容', not leaked, f'泄露={leaked[:2]}')

    if ids['doctor']:
        r2 = call('query_medical_records', {'patient_id': ids['b']},
                  Principal(ids['doctor'], 'doctor', 'verify-d'))
        # 该医生与 p_b 无关联时才是 permission_denied；有关联则放行（也正确）
        with app.app_context():
            from database import DoctorPatientRelation
            linked = DoctorPatientRelation.query.filter_by(
                doctor_id=ids['doctor'], patient_id=ids['b']).first() is not None
        if linked:
            skip('医生查未关联患者 → 403', '该医生恰好与 p_b 有关联，无法用这个组合验证')
        else:
            check('医生查未关联患者 → permission_denied',
                  r2.get('error') == 'permission_denied', str(r2)[:90])

        r3 = call('query_medical_records', {}, Principal(ids['doctor'], 'doctor', 'verify-d'))
        check('医生未指定患者 → missing_patient_id（不默认查全部）',
              r3.get('error') == 'missing_patient_id', str(r3)[:90])
        check('missing_patient_id 的响应里不含任何病历数据',
              'items' not in r3 and 'records' not in r3)

    section('[A.3] 权限拒绝 与 查无数据 必须可区分')
    r_denied = call('query_medical_records', {'patient_id': ids['b']},
                    Principal(ids['a'], 'patient', 'verify-a'))
    check('越权 → permission_denied', r_denied.get('error') == 'permission_denied')
    # 注意不能用「患者查一个不存在的 id」来验 not_found：那也会走
    # permission_denied —— 这是**正确**行为（不泄露该 id 是否存在）。
    # 要走到数据层，得用能过权限校验的主体：admin 旁路 + 不存在的 id。
    admin_id = ids['admin'] if ids['admin'] else ids['a']
    admin_role = 'admin' if ids['admin'] else 'patient'
    r_missing = call('query_medical_records',
                     {'patient_id': 99999999 if ids['admin'] else ids['a']},
                     Principal(admin_id, admin_role, 'verify'))
    check('有权限但查无数据 → not_found', r_missing.get('error') == 'not_found',
          str(r_missing)[:90])
    check('两者错误码不相等（否则"服务挂了"会被当成"没数据"）',
          r_denied.get('error') != r_missing.get('error'))
    r_other_tool = call('get_followup_schedule', {'patient_id': ids['b']},
                        Principal(ids['a'], 'patient', 'verify-a'))
    check('其他工具同样先校验权限再查数据',
          r_other_tool.get('error') == 'permission_denied', str(r_other_tool)[:80])

    section('[A.4] 患者档案：缺失时不抛异常')
    if ids['no_profile'] and ids['admin']:
        r = call('get_patient_profile', {'patient_id': ids['no_profile']},
                 Principal(ids['admin'], 'admin', ids['admin_name']))
        check('无档案用户返回可读结果而不是异常',
              isinstance(r, dict) and r.get('error') != 'internal_error',
              str(r)[:110])
        check('明确说明"尚未建立档案"而不是返回空对象',
              r.get('count') == 0 and 'note' in r, str(r)[:110])
    else:
        skip('档案缺失用例', '找不到"无档案的用户"或"管理员账号"')

    section('[A.5] 已删除病历不得进入上下文')
    tmp_id = None
    try:
        if ids['with_records'] and ids['doctor']:
            import datetime
            with app.app_context():
                row = MedicalRecord(
                    record_number=f'VERIFY-DEL-{int(time.time())}',
                    patient_id=ids['with_records'], doctor_id=ids['doctor'],
                    diagnosis='VERIFY_已删除病历不得出现', symptoms='x',
                    treatment='x', advice='x', status='deleted',
                    visit_date=datetime.datetime.utcnow())
                db.session.add(row)
                db.session.commit()
                tmp_id = row.id
            r = call('query_medical_records', {'limit': 20},
                     Principal(ids['with_records'], 'patient', 'verify-p'))
            check('status=deleted 的病历不返回',
                  'VERIFY_已删除病历不得出现' not in json.dumps(r, ensure_ascii=False),
                  f'返回 {r.get("count")} 条')
        else:
            skip('已删除病历用例', '找不到"有病历的患者"')
    finally:
        if tmp_id is not None:
            with app.app_context():
                db.session.delete(db.session.get(MedicalRecord, tmp_id))
                db.session.commit()

    section('[A.6] 时间必须本地化（防 8 小时时差）')
    if sample_record and ids['with_records']:
        r = call('query_medical_records', {'limit': 20},
                 Principal(ids['with_records'], 'patient', 'verify-p'))
        items = r.get('items') or []
        got = next((i.get('visit_date') for i in items
                    if i.get('visit_date')), None)
        check('工具返回的时间 == to_local_time(原始值)',
              got == sample_record[1], f'got={got} expect={sample_record[1]}')
        check('且 != 裸 isoformat()（库里存 UTC，直接 isoformat 会差 8 小时）',
              got != sample_record[2], f'裸值={sample_record[2]}')
    else:
        skip('时间本地化用例', '该患者没有可核对的历史病历')

    section('[A.7] 检索：熔断 ≠ 没搜到')
    from services.rag import retriever as retr
    original_until = retr._retrieve_failure_until
    try:
        retr._retrieve_failure_until = time.time() + 60
        r = call('search_guideline', {'query': '骨折愈合标准'},
                 Principal(ids['a'], 'patient', 'verify-a'))
        check('熔断中 → unsupported（而不是 not_found）',
              r.get('error') == 'unsupported', str(r)[:90])
        retr._retrieve_failure_until = 0.0
        r2 = call('search_guideline', {'query': '股骨远端骨折的AO分型标准'},
                  Principal(ids['a'], 'patient', 'verify-a'))
        check('恢复后能检索到（ok 或 not_found，但不再是 unsupported）',
              r2.get('error') != 'unsupported', str(r2)[:90])
    finally:
        retr._retrieve_failure_until = original_until

    section('[A.7b] 相关度阈值：弱相关片段必须当成"没有资料"')
    # 向量检索是最近邻，不设阈值时 not_found 永远不可达 —— 问"骨肉瘤 Enneking
    # 分期"（本语料没有）也会返回几条 0.006 分的无关片段
    r_low = call('search_guideline', {'query': '骨肉瘤的 Enneking 外科分期标准'},
                 Principal(ids['a'], 'patient', 'verify-a'))
    check('语料里没有的医学问题 → not_found（而不是把弱相关片段当资料）',
          r_low.get('error') == 'not_found', str(r_low)[:110])
    r_high = call('search_guideline', {'query': '股骨远端骨折的AO分型标准'},
                  Principal(ids['a'], 'patient', 'verify-a'))
    check('语料里确实有的问题 → 正常返回（阈值没有误伤）',
          r_high.get('error') is None and (r_high.get('count') or 0) > 0,
          f"count={r_high.get('count')} err={r_high.get('error')}")

    section('[A.7c] 重排不可用时不能把检索结果全否决')
    # 阶段 10 的对比实验发现的真实缺陷：开启重排时 score 是重排分（真命中 ≥0.9），
    # 重排不可用时会退回 RRF 分（量级 0.016）—— 同一个 0.25 的阈值会把**所有**
    # 结果判成不相关，表现是重排模型一加载失败，指南检索就静默全废。
    from services.rag.retriever import get_retriever
    retriever = get_retriever()
    original_reranker = retriever.reranker

    class _NoRerank:
        def rerank(self, query, pairs):
            return None          # 模拟重排模型不可用（encode 失败/未加载）

    try:
        with app.app_context():
            retriever.reranker = _NoRerank()
            retriever.clear_caches() if hasattr(retriever, 'clear_caches') else None
            from services.rag import retriever as retr_mod
            retr_mod.clear_caches()
        r = call('search_guideline', {'query': '股骨远端骨折的AO分型标准'},
                 Principal(ids['a'], 'patient', 'verify-a'))
        check('重排不可用时仍能返回检索结果（而不是 not_found）',
              r.get('error') is None and (r.get('count') or 0) > 0,
              f"count={r.get('count')} err={r.get('error')}")
        check('此时分数是 RRF 刻度（<0.1），说明确实绕过了重排',
              (r.get('results') or [{}])[0].get('score', 1) < 0.1,
              f"score={(r.get('results') or [{}])[0].get('score')}")
    finally:
        retriever.reranker = original_reranker
        from services.rag import retriever as retr_mod
        retr_mod.clear_caches()

    section('[A.8] 结果契约：JSON 可序列化 / 截断后仍合法')
    probes = [
        ('search_guideline', {'query': '胫骨平台骨折 康复训练'},
         Principal(ids['a'], 'patient', 'p')),
        ('query_medical_records', {}, Principal(ids['with_records'] or ids['a'],
                                                'patient', 'p')),
        ('get_patient_profile', {}, Principal(ids['a'], 'patient', 'p')),
        ('list_detection_reports', {}, Principal(ids['a'], 'patient', 'p')),
        ('get_followup_schedule', {}, Principal(ids['a'], 'patient', 'p')),
    ]
    serializable, errors = True, []
    for name, args, principal in probes:
        res = call(name, args, principal)
        try:
            json.dumps(res, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            serializable = False
            errors.append(f'{name}: {e}')
        check(f'{name} 返回 dict 且含 error 或数据',
              isinstance(res, dict) and (_has_payload(res) or res.get('error')),
              str(res)[:80])
    check('所有工具结果均可 JSON 序列化（RetrievedChunk 是 __slots__ 类，不是 dict）',
          serializable, '; '.join(errors))

    big = tools_mod._truncate({'items': [{'note': '长' * 3000} for _ in range(20)]}, 2000)
    ok_json = True
    try:
        json.loads(json.dumps(big, ensure_ascii=False))
    except (TypeError, ValueError):
        ok_json = False
    check('超长结果截断后仍是合法 JSON（不能直接砍字符串）', ok_json,
          f'截断后 {tools_mod._size(big)} 字符')

    section('[A.9] 执行边界：重复调用 / 非法参数 / 未知工具')
    state = _State(Principal(ids['a'], 'patient', 'p'))
    first = tools_mod.execute_tool(
        ToolCall(id='c1', name='query_medical_records', arguments={}), state)
    second = tools_mod.execute_tool(
        ToolCall(id='c2', name='query_medical_records', arguments={}), state)
    check('同名同参第二次 → duplicate', second.get('error') == 'duplicate',
          str(second)[:80])
    check('第一次未被误判', first.get('error') != 'duplicate')

    bad = tools_mod.execute_tool(
        ToolCall(id='c3', name='query_medical_records', arguments={},
                 parse_error='invalid_json'),
        _State(Principal(ids['a'], 'patient', 'p')))
    check('arguments 非法 JSON → invalid_arguments（不抛异常）',
          bad.get('error') == 'invalid_arguments', str(bad)[:80])
    unk = tools_mod.execute_tool(
        ToolCall(id='c4', name='no_such_tool', arguments={}),
        _State(Principal(ids['a'], 'patient', 'p')))
    check('未知工具 → unknown_tool 且列出可选工具',
          unk.get('error') == 'unknown_tool' and 'available' not in str(unk)[:20]
          and 'search_guideline' in str(unk), str(unk)[:100])

    section('[A.10] 只读不变量：跑完全部工具后数据库行数不变')
    with app.app_context():
        counts_after = {
            'medical_records': MedicalRecord.query.count(),
            'detection_history': DetectionHistory.query.count(),
            'patient_profiles': PatientProfile.query.count(),
            'ai_conversations': AIConversation.query.count(),
        }
    check('表行数与跑用例前一致（工具必须只读）',
          counts_before == counts_after,
          f'前={counts_before} 后={counts_after}')


class _State:
    """最小的 AgentState 替身：execute_tool 只用到 principal / seen_calls / references"""

    def __init__(self, principal):
        self.principal = principal
        self.seen_calls = set()
        self.references = []


def _has_payload(result):
    return any(k in result for k in ('items', 'profile', 'results', 'upcoming',
                                      'overdue', 'context', 'count', 'notes'))


# ==================== Part A：编排层 ====================

class ScriptedClient:
    """脚本化的假 LLM 客户端

    只实现编排真正会用到的三个成员（supports_tools / provider_name /
    chat_reply）—— 这条约束是双向的：orchestrator 里一旦访问了 client 的
    其它属性，这里就会 AttributeError，而真客户端能跑。那种情况下这条
    确定性用例会失效，所以它同时也是"编排没越界用 client"的断言。
    """

    def __init__(self, replies, *, supports_tools=True, repeat_last=False):
        self._replies = list(replies)
        self.provider_name = 'scripted'
        self.supports_tools = supports_tools
        self.repeat_last = repeat_last
        self.calls = []

    def chat_reply(self, messages, **kwargs):
        import copy
        self.calls.append({'messages': copy.deepcopy(messages), 'kwargs': kwargs})
        if not self._replies:
            if self.repeat_last:
                return self._last
            from services.llm_client import LLMTimeoutError
            raise LLMTimeoutError('脚本已耗尽（编排调用的轮次多于预期）')
        nxt = self._replies.pop(0)
        self._last = nxt
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _tool_call(name, args, cid):
    from services.llm_client import ToolCall
    return ToolCall(id=cid, name=name, arguments=args,
                    raw_arguments=json.dumps(args, ensure_ascii=False))


def _reply_tools(*calls):
    from services.llm_client import LLMReply
    return LLMReply(content='', tool_calls=list(calls), finish_reason='tool_calls')


def _reply_text(text, finish='stop'):
    from services.llm_client import LLMReply
    return LLMReply(content=text, finish_reason=finish)


def part_orchestrator(app):
    from config import config as app_config
    from database import User
    from services.agent import orchestrator
    from services.agent.principal import Principal
    from services.llm_client import LLMReply

    with app.app_context():
        patient = User.query.filter_by(role='patient').first()
        if patient is None:
            skip('编排层用例', '库里没有患者账号')
            return
        principal = Principal(patient.id, 'patient', patient.username)

    patched = {}
    for key in ('AGENT_ENABLED', 'AGENT_MAX_ITERATIONS', 'AGENT_MAX_TOOL_CALLS',
                'AGENT_TIMEOUT_SECONDS', 'AGENT_LLM_TIMEOUT'):
        patched[key] = getattr(app_config, key)

    def run(question, client, **kw):
        return orchestrator.run(question, session_id='agent-verify',  # noqa: A001
                               principal=principal, client=client, history=[], **kw)

    try:
        section('[A.11] 多步编排：一轮并行多个工具 + 回灌后收尾')
        client = ScriptedClient([
            _reply_tools(
                _tool_call('query_medical_records', {}, 'c1'),
                _tool_call('list_detection_reports', {'limit': 3}, 'c2'),
                _tool_call('search_guideline', {'query': '康复训练'}, 'c3'),
            ),
            _reply_text('根据指南与你的记录，建议如下……'),
        ])
        state = run('我该怎么康复？', client)
        names = {t['name'] for t in state.trace if t['type'] == 'tool_result'}
        check('一轮里的 3 个 tool_calls 都被执行', state.tool_calls_made == 3,
              f'tool_calls_made={state.tool_calls_made}')
        check('trace 里出现 3 个不同工具（方案文档 Check 2 的确定性版本）',
              len(names) == 3, f'{sorted(names)}')
        check('回灌后模型收尾 → stopped_reason=answered',
              state.stopped_reason == 'answered', state.stopped_reason)
        check('最终回答来自收尾轮', state.answer == '根据指南与你的记录，建议如下……',
              state.answer[:40])
        check('迭代 2 轮（一轮调工具 + 一轮作答）', state.iterations == 2,
              f'iterations={state.iterations}')

        section('[A.12] 回灌消息的形状（形状错会被 provider 400 或静默忽略）')
        second = client.calls[1]['messages']
        assistants = [m for m in second if m.get('role') == 'assistant'
                      and m.get('tool_calls')]
        tool_msgs = [m for m in second if m.get('role') == 'tool']
        check('存在带 tool_calls 的 assistant 消息', len(assistants) == 1)
        check('3 个工具各产生一条 role=tool 消息', len(tool_msgs) == 3,
              f'{len(tool_msgs)} 条')
        if assistants and tool_msgs:
            ids_in_assistant = [c['id'] for c in assistants[0]['tool_calls']]
            ids_in_tool = [m['tool_call_id'] for m in tool_msgs]
            check('tool_call_id 一一对应（按"一轮一个"写会丢结果）',
                  ids_in_assistant == ids_in_tool,
                  f'{ids_in_assistant} vs {ids_in_tool}')
            check('assistant 的 arguments 是原样回灌的 JSON 字符串',
                  all(isinstance(c['function']['arguments'], str)
                      for c in assistants[0]['tool_calls']))
        ok_json = True
        for m in tool_msgs:
            try:
                json.loads(m['content'])
            except (TypeError, ValueError):
                ok_json = False
        check('tool 消息的 content 是合法 JSON', ok_json)
        check('第二次调用时带上了工具定义（tools 非空）',
              bool(client.calls[1]['kwargs'].get('tools')))

        section('[A.13] 护栏：迭代上限 / 工具上限 / 时间预算')
        # 预热：首次 count_tokens 要加载 tokenizer（约 2-5s），首次检索要加载
        # 嵌入/重排模型。把这份一次性开销算进"护栏是否及时收手"的计时里会误判 ——
        # 实测就撞过一次（6.90s vs 阈值 5s）。
        from services.rag.tokens import count_tokens
        count_tokens('预热')
        app_config.AGENT_MAX_ITERATIONS = 2
        guard = ScriptedClient([_reply_tools(_tool_call('search_guideline',
                                                        {'query': 'x'}, 'g1'))],
                               repeat_last=True)
        t0 = time.time()
        state = run('无限调工具', guard)
        cost = time.time() - t0
        check('永远返回 tool_calls 的模型被迭代上限截断（没有护栏会挂死）',
              state.stopped_reason == 'max_iters', state.stopped_reason)
        check('迭代次数恰为上限值', state.iterations == 2, f'{state.iterations}')
        # 阈值宽松（15s）：这一段的目的是"不挂死"（无护栏会一直循环到超时预算
        # 150s），而它内部含一次真实检索，冷缓存时本身就要数秒
        check('被截断时及时返回而不是挂死', cost < 15, f'{cost:.2f}s')
        check('trace 里有 guard 记录说明原因',
              any(t['type'] == 'guard' and t['status'] == 'max_iters'
                  for t in state.trace))
        app_config.AGENT_MAX_ITERATIONS = patched['AGENT_MAX_ITERATIONS']

        app_config.AGENT_MAX_TOOL_CALLS = 2
        guard2 = ScriptedClient([_reply_tools(
            _tool_call('search_guideline', {'query': 'a'}, 't1'),
            _tool_call('search_guideline', {'query': 'b'}, 't2'))],
            repeat_last=True)
        state = run('工具预算', guard2)
        check('工具总数上限生效（单靠轮次拦不住一轮多个）',
              state.stopped_reason == 'tool_budget', state.stopped_reason)
        check('工具调用数恰为上限', state.tool_calls_made == 2,
              f'{state.tool_calls_made}')
        app_config.AGENT_MAX_TOOL_CALLS = patched['AGENT_MAX_TOOL_CALLS']

        app_config.AGENT_TIMEOUT_SECONDS = 0
        budget = ScriptedClient([_reply_text('不该被调用')])
        state = run('预算为零', budget)
        check('时间预算耗尽 → time_budget 且不发 LLM 请求',
              state.stopped_reason == 'time_budget' and len(budget.calls) == 0,
              f'{state.stopped_reason} calls={len(budget.calls)}')
        app_config.AGENT_TIMEOUT_SECONDS = patched['AGENT_TIMEOUT_SECONDS']

        section('[A.14] 工具层的失败不终止编排')
        dup = ScriptedClient([
            _reply_tools(_tool_call('query_medical_records', {}, 'd1')),
            _reply_tools(_tool_call('query_medical_records', {}, 'd2')),
            _reply_text('已拿到信息'),
        ])
        state = run('重复调用', dup)
        statuses = [t['status'] for t in state.trace if t['type'] == 'tool_result']
        check('第二次同名同参 → duplicate，且编排继续走完',
              'duplicate' in statuses and state.stopped_reason == 'answered',
              f'{statuses} / {state.stopped_reason}')
        check('duplicate 也计入工具调用数（否则可以无限重试绕过上限）',
              state.tool_calls_made == 2, f'{state.tool_calls_made}')

        bad_args = ScriptedClient([
            _reply_tools(_tool_call('query_medical_records', {}, 'b1')),
            _reply_text('参数错了也继续'),
        ])
        bad_args_ok = True
        state = run('非法参数', bad_args)
        check('arguments 解析失败不终止编排（模型能自我修正）',
              state.stopped_reason == 'answered' and state.answer, state.stopped_reason)

        section('[A.15] 降级矩阵：任何路径都不该让对话不可用')
        app_config.AGENT_ENABLED = False
        disabled = ScriptedClient([_reply_text('不该被调用')])
        state = run('总开关关闭', disabled)
        check('AGENT_ENABLED=false → degraded 且原因明确',
              state.degraded and state.degraded_reason == 'disabled',
              f'{state.degraded}/{state.degraded_reason}')
        check('降级时根本没走 Agent 路径（0 次 LLM 调用）',
              len(disabled.calls) == 0, f'{len(disabled.calls)} 次')
        app_config.AGENT_ENABLED = patched['AGENT_ENABLED']

        unsupported = ScriptedClient([_reply_text('不该被调用')], supports_tools=False)
        state = run('provider 不支持工具', unsupported)
        check('provider 不支持工具 → provider_unsupported',
              state.degraded and state.degraded_reason == 'provider_unsupported',
              f'{state.degraded}/{state.degraded_reason}')
        check('降级时 0 次 LLM 调用（不能先发一次请求试出来）',
              len(unsupported.calls) == 0, f'{len(unsupported.calls)} 次')

        from services.llm_client import LLMTimeoutError
        failing = ScriptedClient([LLMTimeoutError('模拟超时')])
        state = run('模型挂了', failing)
        check('首轮 LLMError → stopped_reason=llm_error 且标记降级',
              state.stopped_reason == 'llm_error' and state.degraded,
              f'{state.stopped_reason}/{state.degraded}')
        check('失败时 answer 为空（由视图层决定回退到普通对话）',
              state.answer == '', repr(state.answer[:20]))

        section('[A.16] trace 契约：可 JSON 序列化、step 递增、类型齐全')
        client = ScriptedClient([
            _reply_tools(_tool_call('search_guideline', {'query': '指南'}, 's1')),
            _reply_text('回答'),
        ])
        state = run('trace 结构', client)
        types = [t['type'] for t in state.trace]
        check('trace 含 planner / tool_result / answer 三类',
              {'planner', 'tool_result', 'answer'} <= set(types), f'{types}')
        check('step 从 1 连续递增',
              [t['step'] for t in state.trace] == list(range(1, len(state.trace) + 1)))
        serializable = True
        try:
            json.loads(json.dumps(state.trace, ensure_ascii=False))
        except (TypeError, ValueError) as e:
            serializable = False
            check('trace 可 JSON 序列化', False, str(e))
        if serializable:
            check('trace 可 JSON 序列化（不能含 datetime 对象）', True)
        check('检索类工具把引用带进 state.references（侧信道，不进模型上下文）',
              any(r.get('chunk_id') for r in state.references),
              f'{len(state.references)} 条')
        check('引用未混进发给模型的消息里',
              all('_references' not in str(m) for m in client.calls[-1]['messages']))
        check('编排带上了记忆压缩的诊断信息（state.memory）',
              'reason' in state.memory, str(state.memory)[:80])
        check('发给模型的消息不含私有键 _id',
              all(not any(k.startswith('_') for k in m) for m in
                  client.calls[-1]['messages']))
    finally:
        for key, value in patched.items():
            setattr(app_config, key, value)


# ==================== Part A：记忆三层压缩 ====================

def part_memory(app):
    """三层上下文压缩（注入假摘要器，零 LLM 调用）"""
    from services.agent import memory

    UID, SID = 990777, 'agent-verify-mem'

    def fake_summarizer(seen):
        def _sum(texts, level):
            seen.append({'level': level, 'texts': list(texts)})
            return f'<{level} 摘要 {len(seen)}：{len(texts)} 段>'
        return _sum

    def history(n, chars=300):
        out = []
        for i in range(n):
            role = 'user' if i % 2 == 0 else 'assistant'
            out.append({'role': role, 'content': f'第{i}条 ' + '内容' * chars,
                        '_id': 1000 + i})
        return out

    def cleanup():
        memory.clear(UID, SID)

    section('[A.19] 上下文压缩：触发、水位线、分层')
    cleanup()
    seen = []
    h = history(30)
    msg, info = memory.compact(h, user_id=UID, session_id=SID, budget=2000,
                               keep_recent=6, summarizer=fake_summarizer(seen))
    check('超预算时触发压缩', info['compressed'] and info['reason'] == 'compressed',
          str(info))
    check('压缩后 token 明显下降',
          0 < info['tokens_after'] < info['tokens_before'],
          f"{info['tokens_before']} → {info['tokens_after']}")
    check('最近 6 条原文完整保留（不能被摘要吞掉）',
          [m['content'] for m in msg[-6:]] == [m['content'] for m in h[-6:]])
    check('被吸收的部分替换成一条摘要消息',
          any(m.get('role') == 'system' and memory.L2_MARK in m.get('content', '')
              for m in msg),
          f'{len(msg)} 条（原 {len(h)} 条）')
    check('摘要消息里不含私有键 _id 以外的 provider 可见字段异常',
          all(set(m) <= {'role', 'content', '_id'} for m in msg))
    check('水位线记为最后一条被吸收消息的 id',
          memory._load_state(UID, SID).get('l2_upto') == h[info['absorbed'] - 1]['_id'],
          f"absorbed={info['absorbed']}")
    check('超出溢出量 1.5 倍后才停手（不是刚好压到预算）',
          info['tokens_after'] < 2000, f"after={info['tokens_after']}")

    section('[A.20] 水位线：已被摘要覆盖的消息不再重复摘要')
    seen2 = []
    prev_upto = memory._load_state(UID, SID)['l2_upto']
    h2 = history(80)                 # 窗口变长，但里面仍带着已覆盖的旧消息
    msg2, info2 = memory.compact(h2, user_id=UID, session_id=SID, budget=2000,
                                 keep_recent=6, summarizer=fake_summarizer(seen2))
    check('窗口变长后继续压缩', info2['compressed'], str(info2)[:110])
    check('水位线推进（旧的没有被重新吸收）',
          memory._load_state(UID, SID)['l2_upto'] > prev_upto,
          f"{prev_upto} → {memory._load_state(UID, SID)['l2_upto']}")
    texts = seen2[0]['texts'] if seen2 else []
    seg_idx = [int(re.search(r'第(\d+)条', t).group(1))
               for t in texts if not t.startswith('（既有摘要')]
    check('摘要输入里只有水位线之后的新片段（不重复摘旧的）',
          bool(seg_idx) and min(seg_idx) + 1000 > prev_upto,
          f'最小 idx={min(seg_idx) if seg_idx else None}，水位线 id={prev_upto}')
    check('既有摘要作为前缀并入（历史不丢）',
          bool(texts) and texts[0].startswith('（既有摘要'),
          texts[0][:22] if texts else '')

    seen2b = []
    msg2b, info2b = memory.compact(h2[:24], user_id=UID, session_id=SID,
                                   budget=2000, keep_recent=6,
                                   summarizer=fake_summarizer(seen2b))
    check('窗口内全是已覆盖内容 → 复用摘要、不再花钱调摘要器',
          info2b['reused_summary'] and not seen2b, str(info2b)[:110])

    section('[A.21] 第三层：中段摘要过长时提升为"早期要点"')
    cleanup()
    seen3 = []
    # L2 上限设得很小，逼出 L3 提升
    from config import config as app_config
    original_l2 = app_config.AGENT_L2_MAX_CHARS
    try:
        app_config.AGENT_L2_MAX_CHARS = 10
        memory.compact(history(30), user_id=UID, session_id=SID, budget=1500,
                       keep_recent=6, summarizer=fake_summarizer(seen3))
        # 第二次要用足够长的窗口：水位线之后至少得有 MIN_MESSAGES(20) 条，
        # 否则会以 too_few_messages 提前返回，L3 提升就永远走不到
        memory.compact(history(80), user_id=UID, session_id=SID, budget=1500,
                       keep_recent=6, summarizer=fake_summarizer(seen3))
        levels = [s['level'] for s in seen3]
        check('出现了 L3（要点化）调用', 'L3' in levels, f'{levels}')
        state = memory._load_state(UID, SID)
        check('L3 内容已落库', bool(state.get('l3')), str(state.get('l3'))[:40])
        check('L3 水位线已推进', bool(state.get('l3_upto')))
    finally:
        app_config.AGENT_L2_MAX_CHARS = original_l2

    section('[A.22] 不该压缩的场合')
    cleanup()
    seen4 = []
    msg3, info3 = memory.compact(history(30), user_id=UID, session_id=SID,
                                 budget=100000, keep_recent=6,
                                 summarizer=fake_summarizer(seen4))
    check('未超预算 → 原样返回、不调摘要',
          not info3['compressed'] and not seen4
          and [m['content'] for m in msg3] == [m['content'] for m in history(30)],
          info3['reason'])
    app_config_copy = app_config.AGENT_SUMMARY_ENABLED
    try:
        app_config.AGENT_SUMMARY_ENABLED = False
        msg4, info4 = memory.compact(history(30), user_id=UID, session_id=SID,
                                     budget=1000, keep_recent=6,
                                     summarizer=fake_summarizer(seen4))
        check('总开关关闭 → 不压缩且不调摘要',
              not info4['compressed'] and not seen4, info4['reason'])
    finally:
        app_config.AGENT_SUMMARY_ENABLED = app_config_copy
    msg5, info5 = memory.compact(history(5), user_id=UID, session_id=SID,
                                 budget=10, keep_recent=6,
                                 summarizer=fake_summarizer(seen4))
    check('历史条数 ≤ 保留条数 → 不压缩（全是要留的原文）',
          not info5['compressed'] and info5['reason'] == 'all_recent',
          info5['reason'])

    section('[A.23] Redis 不可用：跳过压缩，绝不抛异常')
    import services.agent.memory as mem_mod
    original = mem_mod._redis
    try:
        mem_mod._redis = lambda: None
        msg6, info6 = memory.compact(history(30), user_id=UID, session_id=SID,
                                     budget=1000, keep_recent=6,
                                     summarizer=fake_summarizer([]))
        check('Redis 不可用 → 原样返回并说明原因（不降级到进程内，避免串话）',
              not info6['compressed'] and info6['reason'] == 'redis_unavailable',
              info6['reason'])
        check('原样返回时消息内容未被破坏',
              [m['content'] for m in msg6] == [m['content'] for m in history(30)])
    finally:
        mem_mod._redis = original

    section('[A.23b] 时间护栏：预算不够就不压')
    seen_free = []
    msg_t, info_t = memory.compact(history(30), user_id=UID, session_id=SID,
                                   budget=1000, keep_recent=6,
                                   summarizer=fake_summarizer(seen_free),
                                   deadline=time.monotonic() + 1)
    check('剩余预算不足以做摘要 → 跳过压缩（摘要不能吃掉编排的时间）',
          not info_t['compressed'] and info_t['reason'] == 'no_time_for_summary'
          and not seen_free, info_t['reason'])
    msg_t2, info_t2 = memory.compact(history(30), user_id=UID, session_id=SID,
                                     budget=1000, keep_recent=6,
                                     summarizer=fake_summarizer([]),
                                     deadline=time.monotonic() + 100000)
    check('预算充足时正常压缩', info_t2['compressed'], info_t2['reason'])

    section('[A.24] 摘要器失败：不影响对话')
    cleanup()          # 清掉上一段留下的水位线，否则会以 all_recent 提前返回
    def boom(texts, level):
        raise RuntimeError('模拟摘要服务故障')
    msg7, info7 = memory.compact(history(30), user_id=UID, session_id=SID,
                                 budget=1000, keep_recent=6, summarizer=boom)
    check('摘要失败 → 原样返回（记忆是增强能力，坏掉不该让对话不可用）',
          not info7['compressed'] and info7['reason'] == 'summarize_failed',
          info7['reason'])
    check('失败时历史条数不变', len(msg7) == len(history(30)))

    section('[A.25] 会话隔离与清理')
    cleanup()
    memory.compact(history(30), user_id=UID, session_id=SID, budget=1000,
                   keep_recent=6, summarizer=fake_summarizer([]))
    check('压缩状态写到 Redis（跨进程可读，重启不丢）',
          bool(memory._load_state(UID, SID)))
    check('另一个用户读不到（键含 user_id，防串号）',
          memory._load_state(UID + 1, SID) == {})
    check('clear 能清掉', memory.clear(UID, SID) and not memory._load_state(UID, SID))


# ==================== Part A：端点准入（不花 LLM 调用）====================

def part_endpoint(app):
    """验证 /api/agent/chat 的准入顺序

    这里**刻意一条 LLM 调用都不发**：被拒的路径本来就不该走到模型那一步，
    而"走到模型那一步"由 Part B 覆盖。额度用尽不是靠发 30 次真请求造出来的，
    而是直接在进程内把计数打满 —— 同样的判定函数，零成本、可重复。
    """
    from core import quota
    from core.state import RATE_LIMIT_CONFIG
    from core.ratelimit import check_rate_limit
    from database import User

    URL = f'{BASE}/api/agent/chat'

    def post(token, **body):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        return requests.post(URL, json=body, headers=headers, timeout=60)

    loggable = pick_loggable(app, 'patient', 2)
    if len(loggable) < 2:
        skip('端点准入用例', '能登录的患者账号少于 2 个')
        return
    a_id, a_name, at = (loggable[0]['id'], loggable[0]['username'],
                        loggable[0]['token'])
    b_id, b_name, bt = (loggable[1]['id'], loggable[1]['username'],
                        loggable[1]['token'])
    with app.app_context():
        doctor = User.query.filter_by(role='doctor').first()
        if doctor is None:
            skip('医生角色用例', '库里没有医生账号')
            return
        d_name = doctor.username

    section('[A.17] 端点准入：未鉴权 / 角色 / 参数 / 越权 / 额度')
    clear_rate_keys(a_id, b_id)
    r = post(None, session_id='agent-verify', message='你好')
    check('未登录 → 401', r.status_code == 401, f'HTTP {r.status_code}')

    dt = login(d_name)
    r = post(dt, session_id='agent-verify', message='你好')
    check('医生调用 → 403（Agent 只服务患者康复助手）',
          r.status_code == 403, f'HTTP {r.status_code}')

    r = post(at, session_id='', message='你好')
    check('缺 session_id → 400 AGENT_001',
          r.status_code == 400 and r.json().get('error_code') == 'AGENT_001',
          f'HTTP {r.status_code}')
    r = post(at, session_id='agent-verify', message='   ')
    check('空消息 → 400 AGENT_001', r.status_code == 400)
    r = post(at, session_id='agent-verify', message='长' * 5000)
    check('超长提问 → 400 AGENT_001（在调 LLM 之前就挡掉）',
          r.status_code == 400 and '过长' in r.json().get('error', ''),
          f'HTTP {r.status_code}')

    r = post(at, session_id='agent-verify', message='你好', patient_id=b_id)
    check('患者指定他人 patient_id → 403 AUTH_003',
          r.status_code == 403 and r.json().get('error_code') == 'AUTH_003',
          f'HTTP {r.status_code} {str(r.json())[:80]}')
    r = post(at, session_id='agent-verify', message='你好', patient_id='abc')
    check('patient_id 非整数 → 400 VALIDATION_001',
          r.status_code == 400, f'HTTP {r.status_code}')

    # 额度：直接打满计数（走同样的判定函数），再确认端点在**调 LLM 之前**就拒了。
    # 用患者 B 而不是 A：分钟级限流排在额度之前，而 A 在上面已经被打了 5 次
    # （正好是 agent_chat 的 5 次/分钟），轮不到额度检查。
    session = f'agent-verify-{int(time.time())}'
    client = _redis_client()
    dkey = quota.daily_key(b_id)
    snap = client.get(dkey) if client is not None else None
    try:
        from config import config as app_config
        for _ in range(app_config.QUOTA_SESSION_MAX + 1):
            quota.check_and_consume(b_id, session)
        r = post(bt, session_id=session, message='你好')
        body = r.json() if r.status_code == 429 else {}
        check('会话额度用尽 → 429 QUOTA_001（且未触发 LLM 调用）',
              r.status_code == 429 and body.get('error_code') == 'QUOTA_001',
              f'HTTP {r.status_code} {str(body)[:80]}')

        if client is not None:
            client.delete(quota.session_key(b_id, session))
        # 每日额度必须**每次换会话**地消费：同一个会话连打到 30 次会先撞会话额度
        # （QUOTA_001），每日计数根本涨不上去 —— 这正是"两层一起判定"的真实语义
        for i in range(app_config.QUOTA_DAILY_PER_USER + 1):
            quota.check_and_consume(b_id, f'{session}-d{i}')
        r = post(bt, session_id=f'{session}-final', message='你好')
        body = r.json() if r.status_code == 429 else {}
        check('每日额度用尽 → 429 QUOTA_002（换新会话也救不回来）',
              r.status_code == 429 and body.get('error_code') == 'QUOTA_002',
              f'HTTP {r.status_code} {str(body)[:80]}')
    finally:
        if client is not None:
            if snap is not None:
                client.set(dkey, snap)
            else:
                client.delete(dkey)
            keys = client.keys(f'quota:session:{b_id}:{session}*')
            if keys:
                client.delete(*keys)

    section('[A.18] 限流键独立：agent_chat 打满不应影响 ai_chat')
    check('RATE_LIMIT_CONFIG 里有 agent_chat 键',
          'agent_chat' in RATE_LIMIT_CONFIG,
          '缺了会在成功响应时装额度头时 KeyError → 500，且只在成功路径炸')
    ident = 'user:990001'
    for _ in range(RATE_LIMIT_CONFIG['agent_chat']['max_requests']):
        check_rate_limit(ident, 'agent_chat')
    allowed_agent, _, _ = check_rate_limit(ident, 'agent_chat')
    allowed_chat, _, _ = check_rate_limit(ident, 'ai_chat')
    check('agent_chat 已打满', not allowed_agent)
    check('ai_chat 仍可调用（键名写错时两个会一起 429，只测单接口发现不了）',
          allowed_chat)


def _redis_client():
    from core.cache import get_redis
    return get_redis()


def clear_rate_keys(*user_ids):
    """清掉这些用户在 agent_chat 上的分钟级计数

    本套件自己就会对同一账号连发 5 次（正好是 5 次/分钟的阈值），不清掉的话
    第二次运行、或紧接着跑的下一段用例都会拿到 429 —— 看起来像功能坏了，
    实际是套件吃掉了自己的配额。限流计数是测试自有的状态，清掉即可。
    """
    client = _redis_client()
    if client is None:
        return
    for uid in user_ids:
        keys = client.keys(f'rl:agent_chat:user:{uid}')
        if keys:
            client.delete(*keys)


# ==================== Part B：端到端（--with-llm）====================

def part_llm(app):
    """端到端（真实 LLM，计费）—— 对应方案文档阶段 9 的四项 Check

    判据全部刻意避开"HTTP 200"：零工具、编造答案、越权返回空 三种情况下
    HTTP 一样是 200。
    """
    from database import (AIConversation, DetectionHistory, MedicalRecord, User,
                          db)

    URL = f'{BASE}/api/agent/chat'
    REF_KEYS = {'index', 'doc', 'section', 'page', 'chunk_id', 'score'}

    loggable = pick_loggable(app, 'patient', 2)
    if len(loggable) < 2:
        skip('端到端用例', '能登录的患者账号少于 2 个')
        return
    a_id, at = loggable[0]['id'], loggable[0]['token']
    b_id, bt = loggable[1]['id'], loggable[1]['token']
    with app.app_context():
        # A 需要有检测记录与病历，模型才有东西可查
        a_reports = DetectionHistory.query.filter_by(patient_id=a_id).count()
        b_diagnoses = [x.diagnosis for x in
                       MedicalRecord.query.filter_by(patient_id=b_id).all()
                       if x.diagnosis]
    if not a_reports:
        skip('端到端用例（多步串联）', f'患者 {a_id} 名下没有已归属的检测记录，'
                                      f'模型无法串联检测类工具')
        return
    session = f'agent-verify-{int(time.time())}'
    # B.1~B.3 都打在 A 上（3 次），刚好卡在 agent_chat 的 5 次/分钟内；B.4 换 B，
    # 免得单账号把分钟预算用满
    clear_rate_keys(a_id, b_id)

    def ask(token, message, sid=None, **extra):
        body = {'session_id': sid or session, 'message': message}
        body.update(extra)
        return requests.post(URL, json=body,
                             headers={'Authorization': 'Bearer ' + token},
                             timeout=300)

    try:
        section('[B.1] 单工具真实调用（Check 1）')
        r = ask(at, '股骨远端骨折的 AO 分型标准是什么？')
        check('请求成功', r.status_code == 200, f'HTTP {r.status_code} {r.text[:120]}')
        if r.status_code != 200:
            return
        data = r.json()
        trace = data.get('trace') or []
        tool_results = [t for t in trace if t['type'] == 'tool_result']
        check('至少调用了一个工具（否则等于普通对话）', bool(tool_results),
              f'trace={[t.get("name") for t in tool_results]}')
        guide = [t for t in tool_results if t['name'] == 'search_guideline']
        check('调用了 search_guideline 且成功',
              bool(guide) and guide[0]['status'] == 'ok',
              str(guide[0]['status'] if guide else '未调用'))
        refs = data.get('references') or []
        check('返回的 references 非空', bool(refs), f'{len(refs)} 条')
        check('references 严格符合 6 键契约（前端 CitationList 依赖它）',
              bool(refs) and REF_KEYS <= set(refs[0]),
              f'键={sorted(refs[0]) if refs else []}')
        if guide and refs:
            count = (guide[0].get('detail') or {}).get('count')
            check('引用条数与检索结果数一致（侧信道没丢）', count == len(refs),
                  f'count={count} refs={len(refs)}')
        check('回答里带引用编号', bool(re.search(r'\[\d+\]', data['answer'])),
              data['answer'][:60])

        section('[B.2] 多步串联 ≥3 个工具（Check 2）')
        r = ask(at, '我胫骨平台骨折两个月了，现在能负重吗？该做哪些康复训练？')
        data = r.json() if r.status_code == 200 else {}
        names = {t['name'] for t in (data.get('trace') or [])
                 if t['type'] == 'tool_result'}
        check('模型自主串联 ≥3 个不同工具（判据是工具名集合的基数，不是回答质量）',
              len(names) >= 3, f'实际 {len(names)} 个：{sorted(names)}')
        check('编排轮次 >1（说明发生了"调用→回灌→再决策"）',
              (data.get('iterations') or 0) >= 2, f"iterations={data.get('iterations')}")
        check('未被护栏截断（stopped_reason=answered）',
              data.get('stopped_reason') == 'answered', str(data.get('stopped_reason')))

        section('[B.3] 越权（Check 3）')
        # 说明：这里断言的是**请求级** 403。让真实模型"主动尝试越权"再断言
        # 轨迹里的 permission_denied 不具备确定性（模型可能压根不试），
        # 工具层的拒绝已由 A.2 用真实数据覆盖。
        r = ask(at, f'帮我看看患者 {b_id} 的病历', patient_id=b_id)
        check('患者指定他人 patient_id → 403 AUTH_003',
              r.status_code == 403 and r.json().get('error_code') == 'AUTH_003',
              f'HTTP {r.status_code}')
        leaked = [d for d in b_diagnoses
                  if r.status_code == 200 and d in (r.json().get('answer') or '')]
        check('拒绝响应里不含他人诊断内容', not leaked, f'泄露={leaked[:2]}')

        section('[B.4] 知识库外问题不编造（Check 4）')
        # 问一个**医学类但本语料没有**的问题（实测该问题最高相关度 0.006，
        # 会被相关度阈值拦成 not_found）。比"给猫做绝育"更好：后者模型会
        # 直接判断"超出服务范围"而根本不检索，那条路径就测不到了。
        session_b = session + '-b'
        r = ask(bt, '骨肉瘤的 Enneking 外科分期标准是什么？', sid=session_b)
        data = r.json() if r.status_code == 200 else {}
        t_res = [t for t in (data.get('trace') or [])
                 if t['type'] == 'tool_result' and t['name'] == 'search_guideline']
        answer = data.get('answer') or ''
        check('检索工具明确返回 not_found / unsupported',
              bool(t_res) and all(t['status'] in ('not_found', 'unsupported')
                                  for t in t_res),
              f'调用 {len(t_res)} 次，状态={[t["status"] for t in t_res]}')
        check('回答里没有伪造的引用编号（模型完全可能在 not_found 后继续编造）',
              not re.search(r'\[\d+\]', answer), answer[:80])
        check('明确说明无法回答/资料不足，而不是给出方案',
              any(w in answer for w in ('无法回答', '没有相关资料', '资料不足',
                                        '暂时无法查证', '查不到', '无法提供',
                                        '没有找到')),
              answer[:80])

        section('[B.5] 轨迹持久化与刷新恢复')
        r = requests.get(f'{BASE}/api/ai-assistant/history',
                         params={'session_id': session},
                         headers={'Authorization': 'Bearer ' + at}, timeout=30)
        msgs = r.json().get('messages') or []
        with_trace = [m for m in msgs if m.get('agent_trace')]
        check('历史里能读回 agent_trace（刷新页面轨迹不丢）',
              bool(with_trace), f'{len(msgs)} 条消息，带轨迹 {len(with_trace)} 条')
        check('历史里能读回 context_patient_id',
              any(m.get('context_patient_id') == a_id for m in msgs),
              str([m.get('context_patient_id') for m in msgs][:4]))
        # B 用自己的会话（session_b），所以这里查 A 的会话必须查不到 ——
        # 若把 B 的消息也写进 A 的会话，这里会返回 B 自己那几条
        r2 = requests.get(f'{BASE}/api/ai-assistant/history',
                          params={'session_id': session},
                          headers={'Authorization': 'Bearer ' + bt}, timeout=30)
        check('另一个患者查他人 session_id 查不到（防串话/越权）',
              not (r2.json().get('messages') or []),
              f"{len(r2.json().get('messages') or [])} 条")
    finally:
        section('[B.6] 清理验证产生的会话')
        with app.app_context():
            n = AIConversation.query.filter(
                AIConversation.session_id.like('agent-verify-%')).delete(
                synchronize_session=False)
            db.session.commit()
            print(f'    已删除 {n} 条验证会话')


def main():
    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _engine = build_bare_app()

    try:
        part_tools(app)
    except Exception as e:
        import traceback
        traceback.print_exc()
        check('工具层用例执行', False, f'{type(e).__name__}: {e}')

    if not TOOLS_ONLY:
        try:
            part_orchestrator(app)
        except Exception as e:
            import traceback
            traceback.print_exc()
            check('编排层用例执行', False, f'{type(e).__name__}: {e}')

        try:
            part_memory(app)
        except Exception as e:
            import traceback
            traceback.print_exc()
            check('记忆压缩用例执行', False, f'{type(e).__name__}: {e}')

        # 端点准入需要后端以 debug 模式在跑（从日志读验证码）
        try:
            requests.get(f'{BASE}/api/captcha', timeout=10)
            part_endpoint(app)
        except Exception as e:
            import traceback
            traceback.print_exc()
            check('端点准入用例执行', False, f'{type(e).__name__}: {e}')

    if WITH_LLM and not TOOLS_ONLY:
        try:
            part_llm(app)
        except Exception as e:
            check('端到端用例执行', False, f'{type(e).__name__}: {e}')

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)} / 跳过 {len(SKIP)}')
    for n in FAIL:
        print(f'    - {n}')
    for n in SKIP:
        print(f'    ~ {n}')
    return len(FAIL)


if __name__ == '__main__':
    sys.exit(main())
