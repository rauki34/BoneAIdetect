"""编排循环与护栏（阶段 9）

**不碰数据库、不碰模型、不发网络请求**：用一个脚本化的假客户端驱动整条编排，
把"模型返回什么"变成确定输入。这样护栏（迭代上限 / 工具上限 / 墙钟预算 /
降级矩阵）就能进 CI —— 它们恰恰是最不该只在人工验收时才被验到的部分。

两处规避：
- 工具调用一律用**参数非法**的调用（`search_guideline` 空 query），它在碰数据库
  之前就返回 invalid_arguments，于是不必连库也能验"一轮多个 tool_call 都被执行、
  回灌消息一一对应"。
- `count_tokens` 会被替换掉：真实实现要加载 bge-m3 词表（连带 torch），
  对一个纯逻辑用例来说代价太大且与结论无关。
"""
import json

import pytest

from config import config as app_config
from services.agent import orchestrator
from services.agent.principal import Principal
from services.llm_client import (LLMReply, LLMTimeoutError, ToolCall)


def tool_call(name, args, cid):
    return ToolCall(id=cid, name=name, arguments=args,
                    raw_arguments=json.dumps(args, ensure_ascii=False))


def reply_tools(*calls):
    return LLMReply(content='', tool_calls=list(calls), finish_reason='tool_calls')


def reply_text(text, finish='stop'):
    return LLMReply(content=text, finish_reason=finish)


class ScriptedClient:
    """按脚本吐回复的假客户端

    只实现编排真正会用到的三个成员（supports_tools / provider_name /
    chat_reply）—— 这条约束双向生效：orchestrator 一旦访问 client 的其它属性，
    这里就会 AttributeError，而真客户端能跑。所以它同时也是"编排没越界用
    client"的断言。
    """

    provider_name = 'scripted'

    def __init__(self, replies, *, supports_tools=True, repeat_last=False):
        self._replies = list(replies)
        self.supports_tools = supports_tools
        self.repeat_last = repeat_last
        self.calls = []

    def chat_reply(self, messages, **kwargs):
        import copy
        self.calls.append({'messages': copy.deepcopy(messages), 'kwargs': kwargs})
        if not self._replies:
            if self.repeat_last:
                return self._last
            raise LLMTimeoutError('脚本已耗尽（编排调用的轮次多于预期）')
        nxt = self._replies.pop(0)
        self._last = nxt
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture(autouse=True)
def _fast_tokens(monkeypatch):
    """替换真实 tokenizer（它会加载 bge-m3 词表并拖入 torch）"""
    import services.rag.tokens as tokens
    monkeypatch.setattr(tokens, 'count_tokens', lambda text: max(1, len(text) // 2))


@pytest.fixture(autouse=True)
def _isolate_agent_config():
    keys = ('AGENT_ENABLED', 'AGENT_MAX_ITERATIONS', 'AGENT_MAX_TOOL_CALLS',
            'AGENT_TIMEOUT_SECONDS', 'AGENT_LLM_TIMEOUT')
    original = {k: getattr(app_config, k) for k in keys}
    yield
    for k, v in original.items():
        setattr(app_config, k, v)


@pytest.fixture()
def patient():
    return Principal(1, 'patient', 'p1')


def run(question, client, principal, **kw):
    # 默认 history=[] 让编排完全不碰数据库（load_history 只在 history=None 时才查库）
    kw.setdefault('history', [])
    return orchestrator.run(question, session_id='pytest',
                            principal=principal, client=client, **kw)


BAD_ARGS = {'query': ''}          # search_guideline 空 query：不碰库即返回参数错误


# ---------------------------------------------------------------- 多步编排

def test_batch_tool_calls_all_executed(patient):
    """一轮里的多个 tool_calls 必须**全部**执行

    实测模型第一轮就并行发出 3-4 个 tool_calls；按"一轮一个"写会丢掉后面的结果。
    """
    client = ScriptedClient([
        reply_tools(tool_call('search_guideline', BAD_ARGS, 'c1'),
                    tool_call('search_guideline', {'query': 'a'}, 'c2'),
                    tool_call('search_guideline', {'query': 'b'}, 'c3')),
        reply_text('结论'),
    ])
    state = run('我该怎么康复？', client, patient)
    assert state.tool_calls_made == 3
    names = {t['name'] for t in state.trace if t['type'] == 'tool_result'}
    assert names == {'search_guideline'}
    assert len([t for t in state.trace if t['type'] == 'tool_result']) == 3
    assert state.stopped_reason == 'answered'
    assert state.answer == '结论'
    assert state.iterations == 2


def test_tool_call_ids_are_paired(patient):
    """回灌形状：assistant 的 tool_calls 与后续 role='tool' 消息必须一一对应"""
    client = ScriptedClient([
        reply_tools(tool_call('search_guideline', BAD_ARGS, 'x1'),
                    tool_call('search_guideline', {'query': 'a'}, 'x2')),
        reply_text('好'),
    ])
    run('q', client, patient)
    second = client.calls[1]['messages']
    assistant = [m for m in second if m.get('role') == 'assistant' and m.get('tool_calls')]
    tool_msgs = [m for m in second if m.get('role') == 'tool']
    assert len(assistant) == 1 and len(tool_msgs) == 2
    assert [c['id'] for c in assistant[0]['tool_calls']] == \
           [m['tool_call_id'] for m in tool_msgs]
    for m in tool_msgs:
        json.loads(m['content'])          # content 必须是合法 JSON
    # arguments 要原样回灌（重新序列化会改键序，没有收益）
    assert all(isinstance(c['function']['arguments'], str)
               for c in assistant[0]['tool_calls'])


def test_force_answer_when_model_returns_empty(patient):
    """模型给了空回复（如 finish_reason=length 截断到空）时，要再逼一次收尾"""
    client = ScriptedClient([reply_text(''), reply_text('强制收尾的回答')])
    state = run('q', client, patient)
    assert state.answer == '强制收尾的回答'
    assert any(t['type'] == 'answer' for t in state.trace)


# ---------------------------------------------------------------- 护栏

def test_max_iterations_guard(patient):
    """永远返回 tool_calls 的模型必须被迭代上限截断 —— 没有护栏它会挂死"""
    app_config.AGENT_MAX_ITERATIONS = 2
    client = ScriptedClient([reply_tools(tool_call('search_guideline', BAD_ARGS, 'g'))],
                            repeat_last=True)
    state = run('无限调工具', client, patient)
    assert state.stopped_reason == 'max_iters'
    assert state.iterations == 2
    assert any(t['type'] == 'guard' and t['status'] == 'max_iters' for t in state.trace)


def test_tool_budget_guard(patient):
    """一轮多个 tool_calls 时，单靠轮次拦不住总量"""
    app_config.AGENT_MAX_TOOL_CALLS = 2
    client = ScriptedClient([
        reply_tools(tool_call('search_guideline', BAD_ARGS, 't1'),
                    tool_call('search_guideline', {'query': 'a'}, 't2'))],
        repeat_last=True)
    state = run('工具预算', client, patient)
    assert state.stopped_reason == 'tool_budget'
    assert state.tool_calls_made == 2


def test_time_budget_guard_does_not_call_llm(patient):
    """预算耗尽时**不发下一次请求**：否则"护栏"自己就是超时来源"""
    app_config.AGENT_TIMEOUT_SECONDS = 0
    client = ScriptedClient([reply_text('不该被调用')])
    state = run('预算为零', client, patient)
    assert state.stopped_reason == 'time_budget'
    assert client.calls == []


def test_duplicate_tool_call_does_not_stop_loop(patient):
    """工具层失败不该终止编排：模型看到错误可以换策略"""
    client = ScriptedClient([
        reply_tools(tool_call('search_guideline', BAD_ARGS, 'd1')),
        reply_tools(tool_call('search_guideline', BAD_ARGS, 'd2')),
        reply_text('拿到信息了'),
    ])
    state = run('重复调用', client, patient)
    statuses = [t['status'] for t in state.trace if t['type'] == 'tool_result']
    assert statuses == ['invalid_arguments', 'duplicate']
    assert state.stopped_reason == 'answered'
    # 重复调用也计入工具数，否则可以靠重复重试绕过上限
    assert state.tool_calls_made == 2


# ---------------------------------------------------------------- 降级矩阵

def test_disabled_switch_short_circuits(patient):
    app_config.AGENT_ENABLED = False
    client = ScriptedClient([reply_text('不该被调用')])
    state = run('q', client, patient)
    assert state.degraded and state.degraded_reason == 'disabled'
    assert client.calls == [], '降级时不能先发一次请求试出来'


def test_provider_without_tools_short_circuits(patient):
    client = ScriptedClient([reply_text('不该被调用')], supports_tools=False)
    state = run('q', client, patient)
    assert state.degraded and state.degraded_reason == 'provider_unsupported'
    assert client.calls == []


def test_llm_error_marks_degraded(patient):
    client = ScriptedClient([LLMTimeoutError('模拟超时')])
    state = run('q', client, patient)
    assert state.stopped_reason == 'llm_error'
    assert state.degraded
    assert state.answer == '', '由视图层决定回退到普通对话，这里不该编一个答案出来'


# ---------------------------------------------------------------- 轨迹契约

def test_trace_contract(patient):
    """每次编排都以一条 answer 或 guard/error 收尾 —— 前端才不用写两种分支"""
    client = ScriptedClient([reply_text('直接作答')])
    state = run('q', client, patient)
    types = [t['type'] for t in state.trace]
    assert types[-1] == 'answer'
    assert [t['step'] for t in state.trace] == list(range(1, len(state.trace) + 1))
    json.dumps(state.trace, ensure_ascii=False)     # 不含 datetime 等不可序列化对象


def test_private_keys_not_sent_to_model(patient):
    """`_id` 只给记忆压缩算水位线用，不能进模型上下文"""
    client = ScriptedClient([reply_text('好')])
    run('q', client, patient,
        history=[{'role': 'user', 'content': '之前的问题', '_id': 42}])
    sent = client.calls[0]['messages']
    assert all(not any(k.startswith('_') for k in m) for m in sent)
    assert any(m.get('content') == '之前的问题' for m in sent)


def test_no_grounding_flag_when_nothing_retrieved(patient):
    """调了工具但一次资料都没取到，却照样作答 → 必须标 no_grounding

    实测模型会无视 not_found 凭记忆作答（提示词已写明不得编造）。这个标记是
    产品层的兜底：让用户看到"本次回答未检索到资料支撑"，而不是以为它查过。
    """
    client = ScriptedClient([
        reply_tools(tool_call('search_guideline', BAD_ARGS, 'n1')),
        reply_text('凭记忆给出的具体分期标准……'),
    ])
    state = run('库外问题', client, patient)
    assert state.material_ok is False
    assert state.degraded and state.degraded_reason == 'no_grounding'
    assert any(t['type'] == 'guard' and t['status'] == 'no_grounding'
               for t in state.trace)


def test_no_flag_when_material_was_retrieved(monkeypatch, patient):
    """取到了资料就不该误标 —— 否则这个标记会变成噪声，用户会忽略它

    用注入的假工具而不是真实检索：单测不连数据库，真检索会失败并返回
    internal_error，那样测的就成了"环境不可用"，而不是这里的标记逻辑。
    """
    from services.agent import tools as tools_mod

    monkeypatch.setitem(
        tools_mod.TOOL_REGISTRY, 'fake_ok',
        tools_mod.ToolSpec('fake_ok', '', {'type': 'object', 'properties': {},
                                           'required': []},
                           lambda principal, args: {'count': 2}, False))
    client = ScriptedClient([
        reply_tools(tool_call('fake_ok', {}, 'm1')),
        reply_text('根据资料……'),
    ])
    state = run('正常问答', client, patient)
    assert state.material_ok is True
    assert state.degraded_reason != 'no_grounding'


def test_tool_schemas_sent_to_model(patient):
    client = ScriptedClient([reply_text('好')])
    run('q', client, patient)
    tools = client.calls[0]['kwargs'].get('tools')
    assert tools and {t['function']['name'] for t in tools} >= {'search_guideline'}
    assert client.calls[0]['kwargs'].get('tool_choice') == 'auto'
