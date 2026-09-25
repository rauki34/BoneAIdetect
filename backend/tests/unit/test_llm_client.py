"""LLM 接入层契约（阶段 9 起支持工具调用）

这一层最要紧的性质是**零回归**：`chat()` 的既有五个调用点（对话流式、多模态
解读、AI 服务两处、RAG 验证脚本）都依赖它"返回 str"的契约。所以这里的用例
不只是"新功能能用"，更要钉住"老路径没变"——用桩 provider 断言两条路径发出的
请求体完全一致。
"""
import json

import pytest

from services.llm_client import (LLMClient, LLMConfigError, LLMReply,
                                 OpenAIProvider, PROVIDER_MAP, ToolCall,
                                 _parse_tool_call)


class _Response:
    status_code = 200
    text = ''

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class StubProvider(OpenAIProvider):
    """记录**真实 payload**、返回固定响应的 provider（不发网络请求）

    刻意穿过真实的 `_build_request` 再记录它的产物：只记 `_post` 的入参是测不到
    "tools/tool_choice 有没有真的进 payload" 的 —— 而那正是零回归与端点兼容性
    的关键（孤立的 tool_choice 会被部分端点 400）。
    """

    def __init__(self, payload):
        super().__init__({'api_key': 'test-key'})
        self.payload = payload
        self.payloads = []

    def _post(self, messages, max_tokens, temperature, timeout, image_base64,
              prompt_style, stream, *, tools=None, tool_choice=None):
        _url, _headers, payload = self._build_request(
            messages, max_tokens, temperature, stream,
            tools=tools, tool_choice=tool_choice)
        self.payloads.append(payload)
        return _Response(self.payload)


TEXT_PAYLOAD = {'choices': [{'finish_reason': 'stop',
                             'message': {'content': '你好'}}]}
TOOL_PAYLOAD = {'choices': [{'finish_reason': 'tool_calls',
                             'message': {'content': None, 'tool_calls': [
                                 {'id': 'call_1', 'type': 'function',
                                  'function': {'name': 'search_guideline',
                                               'arguments': '{"query": "AO分型"}'}},
                             ]}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}


def _client(payload):
    client = LLMClient('openai', {'api_key': 'test-key'})
    client.provider = StubProvider(payload)
    return client


# ---------------------------------------------------------------- 零回归

def test_chat_returns_text():
    client = _client(TEXT_PAYLOAD)
    assert client.chat([{'role': 'user', 'content': 'hi'}]) == '你好'


def test_chat_and_chat_reply_send_identical_request():
    """tools 缺省时，两条路径发出的 payload 必须逐字段一致

    这是"加了工具能力但没改变老行为"的**结构性证据**：不是靠跑一遍测试碰巧
    通过，而是断言两者发给端点的请求体完全相同。
    """
    a, b = _client(TEXT_PAYLOAD), _client(TEXT_PAYLOAD)
    a.chat([{'role': 'user', 'content': 'hi'}])
    b.chat_reply([{'role': 'user', 'content': 'hi'}])
    assert a.provider.payloads == b.provider.payloads
    assert 'tools' not in a.provider.payloads[0]


def test_tool_choice_only_sent_with_tools():
    """孤立的 tool_choice 会被部分端点 400，所以只在带 tools 时才进 payload"""
    client = _client(TEXT_PAYLOAD)
    client.chat_reply([{'role': 'user', 'content': 'hi'}], tool_choice='auto')
    assert 'tool_choice' not in client.provider.payloads[0]
    assert 'tools' not in client.provider.payloads[0]

    client.chat_reply([{'role': 'user', 'content': 'hi'}],
                      tools=[{'type': 'function'}], tool_choice='auto')
    assert client.provider.payloads[1]['tool_choice'] == 'auto'


# ---------------------------------------------------------------- 工具调用

def test_chat_reply_parses_tool_calls():
    client = _client(TOOL_PAYLOAD)
    reply = client.chat_reply([{'role': 'user', 'content': 'hi'}],
                              tools=[{'type': 'function'}])
    assert isinstance(reply, LLMReply)
    assert reply.has_tool_calls
    assert reply.finish_reason == 'tool_calls'
    call = reply.tool_calls[0]
    assert call.name == 'search_guideline'
    assert call.arguments == {'query': 'AO分型'}      # 已解析成 dict
    assert call.raw_arguments == '{"query": "AO分型"}'  # 原样保留给回灌用
    assert reply.usage['prompt_tokens'] == 100


def test_tools_are_forwarded():
    client = _client(TOOL_PAYLOAD)
    tools = [{'type': 'function', 'function': {'name': 'f'}}]
    client.chat_reply([{'role': 'user', 'content': 'hi'}], tools=tools,
                      tool_choice='auto')
    assert client.provider.payloads[0]['tools'] == tools
    assert client.provider.payloads[0]['tool_choice'] == 'auto'


def test_content_none_becomes_empty_string():
    """带 tool_calls 的响应里 content 是 null（OpenAI）或空串（ModelScope）

    透传 None 会一路流到 AIConversation.message_content（NOT NULL）触发
    IntegrityError，所以两条路径都必须把它变成 ''。
    """
    client = _client(TOOL_PAYLOAD)
    assert client.chat([{'role': 'user', 'content': 'hi'}]) == ''
    assert client.chat_reply([{'role': 'user', 'content': 'hi'}],
                             tools=[{'type': 'function'}]).content == ''


def test_stream_with_tools_is_rejected():
    """流式会丢弃 delta.tool_calls，必须先拿全 tool_calls 才能执行"""
    client = _client(TEXT_PAYLOAD)
    with pytest.raises(LLMConfigError):
        list(client.chat([{'role': 'user', 'content': 'hi'}], stream=True,
                         tools=[{'type': 'function'}]))


def test_unsupported_provider_rejects_tools():
    client = LLMClient('local', {})
    assert client.supports_tools is False
    with pytest.raises(LLMConfigError):
        client.chat_reply([{'role': 'user', 'content': 'hi'}],
                          tools=[{'type': 'function'}])


@pytest.mark.parametrize('name,expected', [
    ('openai', True), ('modelscope', True), ('custom', False), ('local', False)])
def test_provider_capability_flags(name, expected):
    """能力用标志表达而不是"发一次请求看会不会 400"

    LocalProvider 结构上无法承载工具协议，它不会报错，只会静默丢掉 tools 并
    正常返回文本 —— 那样永远不会有人知道 Agent 没生效。
    """
    assert PROVIDER_MAP[name].supports_tools is expected


def test_custom_provider_can_opt_in():
    client = LLMClient('custom', {'api_url': 'http://x/v1/chat', 'supports_tools': 'true'})
    assert client.supports_tools is True


# ---------------------------------------------------------------- 参数解析

@pytest.mark.parametrize('call_id,name,arguments,expected', [
    ('c1', 'f', '{"a": 1}', None),
    ('c1', 'f', '{bad json', 'invalid_json'),
    ('c1', 'f', '[1, 2]', 'not_object'),
    ('c1', 'f', '', None),                       # 无参工具是合法的
    ('c1', None, '{}', 'missing_function_name'),
    ('c1', 'f', {'a': 1}, None),                 # 少数端点直接给对象
])
def test_parse_tool_call_branches(call_id, name, arguments, expected):
    call = _parse_tool_call(call_id, name, arguments)
    assert call.parse_error == expected
    assert isinstance(call.arguments, dict)


def test_parse_tool_call_generates_id_when_missing():
    assert _parse_tool_call(None, 'f', '{}').id.startswith('call_')


def test_invalid_json_does_not_raise():
    """一次格式抖动不该终止整条编排：模型看到提示后能自我修正"""
    call = _parse_tool_call('c1', 'f', '{oops')
    assert call.arguments == {} and call.raw_arguments == '{oops'


def test_reply_defaults():
    reply = LLMReply()
    assert reply.content == '' and not reply.has_tool_calls
