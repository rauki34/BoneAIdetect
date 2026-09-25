"""Agent 工具层与权限的**可离线验证部分**（阶段 9）

刻意只测不需要数据库的分支：注册表、schema、执行边界、错误码区分、权限判定
中不查库的那几条（患者本人 / admin 旁路 / 参数非法）。需要真实数据的那部分
（病历 status 过滤、时间本地化、删除病历不进上下文等）在
`scripts/verify_agent.py` 的 Part A 里跑，那里有真实语料与患者数据。
"""
import datetime
import json

import pytest

from services.agent.principal import Principal, err, resolve_patient
from services.agent import tools as tools_mod
from services.agent.tools import TOOL_REGISTRY, execute_tool, tool_schemas
from services.llm_client import ToolCall

EXPECTED_TOOLS = {'search_guideline', 'query_medical_records', 'get_patient_profile',
                  'list_detection_reports', 'get_followup_schedule'}


class _State:
    """execute_tool 只用到 principal / seen_calls / references"""

    def __init__(self, principal):
        self.principal = principal
        self.seen_calls = set()
        self.references = []


# ---------------------------------------------------------------- 注册表

def test_registry_is_complete():
    assert set(TOOL_REGISTRY) == EXPECTED_TOOLS


def test_schemas_are_valid_and_serializable():
    schemas = tool_schemas()
    assert len(schemas) == len(EXPECTED_TOOLS)
    for s in schemas:
        assert s['type'] == 'function'
        fn = s['function']
        assert fn['name'] and fn['description']
        params = fn['parameters']
        assert params['type'] == 'object'
        assert isinstance(params['properties'], dict)
        assert isinstance(params['required'], list)
        # 模型给的参数可能有默认值，required 里必须都是已声明的属性
        assert set(params['required']) <= set(params['properties'])
    json.dumps(schemas)          # provider 只接受能序列化的 schema


def test_tools_are_read_only_by_contract():
    """工具集里**不允许**出现写操作

    让 LLM 自主触发写操作（重跑检测、改病历）意味着把"谁在何时对哪张片子做了
    什么"交给模型决定，医疗场景要求检测由医生在检测页面发起、审计链完整。
    这里用名字做一层笨但有效的护栏：新增工具若带这些前缀就该来改这条测试，
    并在评审时说清为什么它可以写库。
    """
    write_prefixes = ('create_', 'update_', 'delete_', 'run_', 'detect_', 'save_')
    offenders = [n for n in TOOL_REGISTRY if n.startswith(write_prefixes)]
    assert not offenders, f'工具集里出现了疑似写操作：{offenders}'


def test_no_surgery_history_promise():
    """本系统没有手术史字段，description 里绝不能写

    写了模型就会承诺一个拿不到的字段，然后为了圆场而编造。
    """
    assert not [n for n, s in TOOL_REGISTRY.items() if '手术史' in s.description]


def test_duplicate_registration_raises():
    with pytest.raises(ValueError):
        @tools_mod.tool(name='search_guideline', description='x',
                        parameters={'type': 'object', 'properties': {}, 'required': []})
        def _dup(principal, args):
            return {}


# ---------------------------------------------------------------- 执行边界

def test_unknown_tool():
    r = execute_tool(ToolCall(id='c', name='nope'), _State(Principal(1, 'patient')))
    assert r['error'] == 'unknown_tool'
    assert 'search_guideline' in r['message']


def test_invalid_json_arguments():
    r = execute_tool(ToolCall(id='c', name='query_medical_records',
                              arguments={}, parse_error='invalid_json'),
                     _State(Principal(1, 'patient')))
    assert r['error'] == 'invalid_arguments'


def test_duplicate_call_is_blocked_and_counted_once():
    """重复调用检查发生在**调用 handler 之前**，所以这里刻意选一个
    参数非法、立刻返回的工具：不必碰数据库就能验重复拦截本身。"""
    state = _State(Principal(1, 'patient'))
    args = {'query': ''}          # search_guideline 对空 query 直接返回参数错误
    first = execute_tool(ToolCall(id='c1', name='search_guideline', arguments=args), state)
    second = execute_tool(ToolCall(id='c2', name='search_guideline', arguments=args), state)
    assert first['error'] == 'invalid_arguments'
    assert second['error'] == 'duplicate'
    assert len(state.seen_calls) == 1


def test_execute_tool_never_raises(monkeypatch):
    """**永不抛异常**是 execute_tool 的核心契约：异常会终止整条编排，
    而失败返回 {'error': ...} 能让模型换个思路继续。"""
    def boom(principal, args):
        raise RuntimeError('模拟工具内部炸了')

    monkeypatch.setitem(TOOL_REGISTRY, 'boom_tool',
                        tools_mod.ToolSpec('boom_tool', '', {}, boom, False))
    r = execute_tool(ToolCall(id='c', name='boom_tool'), _State(Principal(1, 'patient')))
    assert r['error'] == 'internal_error'
    # 只回类型名，不回异常消息：消息里可能带表名/列名等实现细节
    assert 'RuntimeError' in r['message'] and '模拟工具内部炸了' not in r['message']


# ---------------------------------------------------------------- 权限

def test_patient_defaults_to_self():
    pid, e = resolve_patient(Principal(7, 'patient'), {})
    assert (pid, e) == (7, None)


def test_patient_cannot_access_other_patient():
    pid, e = resolve_patient(Principal(7, 'patient'), {'patient_id': 8})
    assert pid is None and e['error'] == 'permission_denied'


def test_doctor_must_specify_patient():
    """绝不默认"查全部患者"：宁可让模型反问用户"""
    pid, e = resolve_patient(Principal(5, 'doctor'), {})
    assert pid is None and e['error'] == 'missing_patient_id'
    assert 'items' not in e and 'records' not in e


def test_optional_patient_returns_none():
    pid, e = resolve_patient(Principal(5, 'doctor'), {}, required=False)
    assert (pid, e) == (None, None)


@pytest.mark.parametrize('raw', ['abc', [], {}])
def test_invalid_patient_id_type(raw):
    pid, e = resolve_patient(Principal(7, 'patient'), {'patient_id': raw})
    assert pid is None and e['error'] == 'invalid_arguments'


def test_admin_bypasses_patient_check():
    """admin 旁路是 can_access_patient 的既有语义（无需查库）"""
    pid, e = resolve_patient(Principal(1, 'admin'), {'patient_id': 999})
    assert (pid, e) == (999, None)


def test_permission_denied_and_not_found_are_distinct():
    """「权限拒绝」与「查无数据」必须能分开

    两者都表现为"返回空"，压成同一个返回值就只能测 HTTP 200，而 HTTP 200 在
    越权、真没数据、服务挂了三种情况下同样成立。
    """
    _, denied = resolve_patient(Principal(7, 'patient'), {'patient_id': 8})
    not_found = err('not_found', '没有病历')
    assert denied['error'] != not_found['error']
    assert denied['error'] == 'permission_denied'


# ---------------------------------------------------------------- 结果处理

def test_jsonable_localizes_datetime():
    """时间必须走 to_local_time：库里存 naive UTC，裸 isoformat 会差 8 小时，
    而工具结果直接进 prompt，差 8 小时会让模型把"明天复诊"算错一天"""
    dt = datetime.datetime(2026, 4, 8, 16, 40, 44)
    out = tools_mod._jsonable(dt)
    assert out.startswith('2026-04-09T00:40')      # +8 小时
    assert out != dt.isoformat()


def test_jsonable_handles_nested_structures():
    class Fake:
        def to_dict(self):
            return {'a': datetime.datetime(2026, 1, 1, 0, 0, 0)}

    out = tools_mod._jsonable({'items': [Fake()], 'n': 1, 'none': None})
    json.dumps(out)                                 # 必须可序列化
    assert out['items'][0]['a'].startswith('2026-01-01T08:00')


def test_truncate_keeps_json_valid():
    """超长结果不能靠截断 JSON 字符串来压缩 —— 那会产出非法 JSON"""
    big = {'items': [{'note': '长' * 3000} for _ in range(20)]}
    out = tools_mod._truncate(big, 2000)
    json.loads(json.dumps(out, ensure_ascii=False))
    assert tools_mod._size(out) <= 2000 or out.get('truncated')


def test_truncate_passthrough_when_small():
    small = {'count': 1}
    assert tools_mod._truncate(small, 1000) == small
