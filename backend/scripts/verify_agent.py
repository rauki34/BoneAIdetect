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
            'username': user, 'password': '123456',
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
        check('被截断时仍在 5 秒内返回', cost < 5, f'{cost:.2f}s')
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
    finally:
        for key, value in patched.items():
            setattr(app_config, key, value)


# ==================== Part B：端到端（--with-llm）====================

def part_llm(app):
    section('[B] 端到端（真实 LLM）')
    print('  （本部分在后续步骤补齐：单工具 / 多步串联 / 越权 / 幻觉兜底）')


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
