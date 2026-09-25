"""Agent 编排（阶段 9）

    planner ──(有 tool_calls)──> tools ──> reflect ──> planner
            └──(无 tool_calls)──> responder ──> done

四个节点都是 `f(state, client=None) -> 下一节点名` 的纯函数，驱动器只按返回值
调度。**刻意不引入 LangGraph**（完整理由写在 requirements.txt 的注释里）：
它真正的价值是 checkpointer 与 interrupt，而我们是单次 HTTP 请求内的短编排，
两者都用不上；护栏照样得自己写。换成图编排的成本被压到最低 —— 只需新增
graph.py 把节点接上，本文件的节点函数一行不改。

**对 client 的约束是契约，不是习惯**：编排只允许使用 client 的
`supports_tools` / `provider_name` / `chat_reply(...)` 三个成员。
验证脚本用一个脚本化的假客户端（ScriptedClient）驱动整条编排来断言护栏与
多步串联；一旦这里访问了 client 的其它属性，真客户端能跑而假客户端跑不了，
那些确定性用例就失效了。

**为什么 reflect 节点里不调 LLM**：模型在下一轮 planner 看到 role='tool' 的
结果后，自然会决定继续调工具还是收尾。再单独发一次"结果够不够"的判断，会让
每步成本翻倍，而且那个判断无法约束模型下一轮的行为（它照样可以不按规划走）。
reflect 只承担确定性的三件事：预算护栏、重复调用拦截、决定是否强制收尾。
"""
import time
from dataclasses import dataclass, field

from config import config as app_config
from database import AIConversation
from services.agent.prompts import AGENT_SYSTEM_PROMPT, FORCE_ANSWER_HINT
from services.agent.principal import Principal
from services.agent.tools import execute_tool, tool_schemas
from services.llm_client import LLMError
from utils.logger import logger

HISTORY_LIMIT = 10


def _cfg(key, default=None):
    return getattr(app_config, key, default)


@dataclass
class AgentState:
    # ---- 输入 ----
    question: str
    session_id: str
    principal: Principal
    patient_id: int | None = None

    # ---- 可变执行状态 ----
    messages: list = field(default_factory=list)
    iterations: int = 0
    tool_calls_made: int = 0
    pending_calls: list = field(default_factory=list)
    seen_calls: set = field(default_factory=set)
    trace: list = field(default_factory=list)
    references: list = field(default_factory=list)
    answer: str = ''
    memory: dict = field(default_factory=dict)   # 本轮的记忆压缩结果（可观测）
    stopped_reason: str = ''      # answered|max_iters|tool_budget|time_budget|llm_error|degraded
    degraded: bool = False
    degraded_reason: str = ''
    started_at: float = field(default_factory=time.monotonic)
    _step: int = 0

    # ---- 派生 ----

    @property
    def elapsed_ms(self):
        return int((time.monotonic() - self.started_at) * 1000)

    def budget_left(self):
        return _cfg('AGENT_TIMEOUT_SECONDS', 150) - (time.monotonic() - self.started_at)

    def add_trace(self, type_, *, name=None, args=None, status='ok',
                  summary='', detail=None, elapsed_ms=0):
        self._step += 1
        self.trace.append({
            'step': self._step, 'type': type_, 'name': name, 'args': args,
            'status': status, 'summary': summary, 'elapsed_ms': elapsed_ms,
            'detail': detail or {},
        })


# ==================== 历史 ====================

def load_history(user_id, session_id, *, exclude_id=None, limit=None):
    """读最近若干条对话（不含 system）

    `exclude_id` 用于排除**本次刚落库的那条提问** —— 视图层为了"流式中断也不
    丢提问"会先把用户消息落库，若不排除，问题会在 messages 里出现两次，
    既浪费 token 又会让模型以为用户问了两遍。

    条数上限取 AGENT_HISTORY_LIMIT（默认 40，比普通对话的 10 大）：记忆压缩
    需要足够长的窗口才有意义 —— 只读 10 条的话，减去"必须保留的最近 6 条"，
    可压缩的余地只有 4 条，预算根本用不上。
    """
    limit = limit or _cfg('AGENT_HISTORY_LIMIT', 40)
    query = AIConversation.query.filter_by(patient_id=user_id, session_id=session_id)
    if exclude_id is not None:
        query = query.filter(AIConversation.id != exclude_id)
    rows = query.order_by(AIConversation.created_at.desc(),
                          AIConversation.id.desc()).limit(limit).all()
    messages = []
    for h in reversed(rows):          # 查出来是倒序，反转回时间正序
        if not h.message_content:
            continue
        role = 'user' if h.message_type == 'user' else 'assistant'
        # _id 只给记忆压缩算水位线用，拼 messages 前会被 _public() 剥掉
        messages.append({'role': role, 'content': h.message_content, '_id': h.id})
    return messages


def _public(message):
    """剥掉私有键（provider 只该看到 role/content[/tool_calls]）"""
    return {k: v for k, v in message.items() if not k.startswith('_')}


# ==================== 消息拼装 ====================

def _assistant_message(reply):
    msg = {'role': 'assistant',
           # content 为 None 而不是 ''：部分端点对空字符串的 assistant 消息会 400
           'content': reply.content or None}
    if reply.has_tool_calls:
        msg['tool_calls'] = [{
            'id': c.id, 'type': 'function',
            'function': {
                'name': c.name,
                # 原样回灌 provider 给的原始 JSON 字符串，不要重新序列化
                'arguments': c.raw_arguments or '{}',
            }} for c in reply.tool_calls]
    return msg


def _tool_message(call, result):
    import json
    return {'role': 'tool',
            'tool_call_id': call.id,
            'name': call.name,
            'content': json.dumps(result, ensure_ascii=False)}


# ==================== 节点 ====================

def planner_node(state, client):
    """规划 + 行动合一：模型在同一轮里既决定要不要用工具，也用 tool_calls 表达"""
    remaining = state.budget_left()
    if state.iterations >= _cfg('AGENT_MAX_ITERATIONS', 5):
        state.stopped_reason = 'max_iters'
        state.add_trace('guard', status='max_iters',
                        summary=f'达到最大轮次 {_cfg("AGENT_MAX_ITERATIONS", 5)}，强制收尾')
        return 'respond'
    if state.tool_calls_made >= _cfg('AGENT_MAX_TOOL_CALLS', 8):
        state.stopped_reason = 'tool_budget'
        state.add_trace('guard', status='tool_budget',
                        summary=f'达到工具调用上限 {_cfg("AGENT_MAX_TOOL_CALLS", 8)}，强制收尾')
        return 'respond'
    if remaining <= 5:
        state.stopped_reason = 'time_budget'
        state.add_trace('guard', status='time_budget',
                        summary='时间预算不足，强制收尾',
                        detail={'remaining_s': round(remaining, 1)})
        return 'respond'

    t0 = time.monotonic()
    try:
        reply = client.chat_reply(
            state.messages,
            tools=tool_schemas(),
            tool_choice='auto',
            max_tokens=_cfg('AGENT_MAX_TOKENS', 800),
            # 用剩余预算而不是固定值：否则"5 轮 × 单轮上限"可以远超整条预算
            timeout=max(min(_cfg('AGENT_LLM_TIMEOUT', 60), int(remaining)), 5),
        )
    except LLMError as e:
        logger.warning('Agent 规划轮失败: %s', e)
        state.stopped_reason = 'llm_error'
        state.degraded = True
        state.degraded_reason = 'llm_error'
        state.add_trace('error', status='llm_error', summary=f'模型调用失败：{e}')
        return 'stop'

    elapsed = int((time.monotonic() - t0) * 1000)
    state.iterations += 1
    state.messages.append(_assistant_message(reply))

    if not reply.has_tool_calls:
        # 没有 tool_calls 就是终答。注意 finish_reason='length'（被 max_tokens
        # 截断）时这段 content 同样是有效答案，不能当成"没有答案"
        state.answer = reply.content or ''
        state.stopped_reason = state.stopped_reason or 'answered'
        state.add_trace('planner', status='answer',
                        summary='模型直接作答（未调用工具）',
                        detail={'finish_reason': reply.finish_reason,
                                'chars': len(state.answer), 'iteration': state.iterations},
                        elapsed_ms=elapsed)
        return 'respond'

    state.pending_calls = list(reply.tool_calls)
    state.add_trace('planner', status='tool_calls',
                    summary=f'决定调用 {len(state.pending_calls)} 个工具',
                    detail={'iteration': state.iterations,
                            'tool_calls': [c.name for c in state.pending_calls],
                            'finish_reason': reply.finish_reason,
                            'usage': reply.usage},
                    elapsed_ms=elapsed)
    return 'tools'


def tools_node(state):
    """确定性节点：逐个执行本轮的全部工具调用，把结果回灌成 role='tool'

    **必须支持一轮多个 tool_calls**：实测模型第一轮就并行发出了 3 个
    （检索指南 + 查病历 + 查检测），按"一轮一个"写会丢掉后两个的结果。
    """
    for call in state.pending_calls:
        t0 = time.monotonic()
        result = execute_tool(call, state)      # 永不抛异常
        state.tool_calls_made += 1
        state.messages.append(_tool_message(call, result))
        state.add_trace(
            'tool_result', name=call.name, args=call.arguments,
            status=result.get('error') or 'ok',
            summary=_summarize(call.name, result),
            detail={k: v for k, v in result.items() if k != 'context'},
            elapsed_ms=int((time.monotonic() - t0) * 1000))
    state.pending_calls = []
    return 'reflect'


def reflect_node(state):
    """确定性的收尾判断（不发 LLM 调用，理由见模块文档）"""
    if state.stopped_reason in ('time_budget', 'max_iters', 'tool_budget'):
        return 'respond'
    return 'planner'


def responder_node(state, client):
    """强制产出文本（此时不再给工具，逼模型用已有结果作答）"""
    if state.answer:
        # 模型上一轮已经直接作答了（常见路径）。这里仍补一条 answer 轨迹，
        # 让「每次编排都以一条 answer 或 guard/error 收尾」成为稳定契约 ——
        # 否则前端的轨迹渲染要写"有时有最后一步有时没有"两种分支
        state.add_trace('answer', status='ok', summary='生成最终回答',
                        detail={'chars': len(state.answer), 'source': 'planner'})
        return 'done'
    remaining = state.budget_left()
    if remaining <= 3:
        state.stopped_reason = state.stopped_reason or 'time_budget'
        state.add_trace('guard', status='time_budget',
                        summary='预算耗尽，未生成最终回答')
        return 'done'
    t0 = time.monotonic()
    try:
        reply = client.chat_reply(
            state.messages + [{'role': 'user', 'content': FORCE_ANSWER_HINT}],
            tools=None,
            max_tokens=_cfg('AGENT_MAX_TOKENS', 800),
            timeout=max(min(_cfg('AGENT_LLM_TIMEOUT', 60), int(remaining)), 5),
        )
        state.answer = reply.content or ''
        state.stopped_reason = state.stopped_reason or 'answered'
    except LLMError as e:
        logger.warning('Agent 收尾轮失败: %s', e)
        state.stopped_reason = 'llm_error'
        state.degraded = True
        state.degraded_reason = 'llm_error'
    state.add_trace('answer', status='ok' if state.answer else 'empty',
                    summary='生成最终回答' if state.answer else '未能生成最终回答',
                    detail={'chars': len(state.answer)},
                    elapsed_ms=int((time.monotonic() - t0) * 1000))
    return 'done'


_SUMMARY_KEYS = {
    'count': lambda r: f'查到 {r["count"]} 条',
    'overdue': lambda r: f'复诊：已过期 {len(r.get("overdue") or [])} 条，'
                         f'即将到来 {len(r.get("upcoming") or [])} 条',
}


def _summarize(name, result):
    """一句话摘要（前端"正在…→已完成"直接显示它）"""
    if result.get('error'):
        return result.get('message') or result['error']
    for key, fn in _SUMMARY_KEYS.items():
        if key in result:
            try:
                return fn(result)
            except (TypeError, KeyError):
                break
    return '完成'


# ==================== 驱动器 ====================

def run(question, *, session_id, principal, patient_id=None, client=None,
        history=None, exclude_message_id=None):
    """跑一次 Agent 编排，返回 AgentState

    **必须在 Flask 请求上下文内同步执行**：工具要查库，而请求上下文里的
    db.session 正是我们想要的那个。这也让"生成器里重新落库"那套复杂性
    （api/ai.py 的流式端点为此写了一大段注释）完全不需要。

    client 可注入（验证脚本用 ScriptedClient 驱动），这是唯一的注入点，
    生产代码不需要为测试改任何东西。
    """
    state = AgentState(question=question, session_id=session_id,
                       principal=principal, patient_id=patient_id)

    if not _cfg('AGENT_ENABLED', True):
        state.degraded, state.degraded_reason = True, 'disabled'
        state.stopped_reason = 'degraded'
        return state

    if client is None:
        from services.ai_service import get_llm_client
        client = get_llm_client()

    if not getattr(client, 'supports_tools', False):
        # 编排层必须在**发请求之前**决定降级：LocalProvider 之类结构上无法
        # 承载工具协议，它不会报错，只会静默丢掉 tools 并返回一段普通文本 ——
        # 那样就永远不会有人知道 Agent 其实没生效
        state.degraded, state.degraded_reason = True, 'provider_unsupported'
        state.stopped_reason = 'degraded'
        return state

    if history is None:
        try:
            history = load_history(principal.id, session_id,
                                   exclude_id=exclude_message_id)
        except Exception as e:
            logger.warning('读取对话历史失败，按无历史处理: %s', e)
            history = []

    # 超长提问会让每轮都多花 token，且很容易是注入尝试
    limit = _cfg('AGENT_MAX_QUESTION_CHARS', 2000)
    if len(question) > limit:
        question = question[:limit]

    # 三层记忆压缩：超预算时把较早的对话压成摘要/要点（Redis 跨进程）。
    # 压缩失败只记录、不抛 —— 记忆是增强能力，坏掉不该让对话不可用。
    from services.agent import memory
    system_message = {'role': 'system', 'content': AGENT_SYSTEM_PROMPT}
    from services.rag.tokens import count_tokens
    reserved = count_tokens(AGENT_SYSTEM_PROMPT) + 8
    history, mem_info = memory.compact(
        history, user_id=principal.id, session_id=session_id,
        reserved_tokens=reserved,
        # 把整条编排的墙钟预算传下去：摘要要花一次 LLM 调用，不能把
        # 规划/收尾的时间吃光（实测无上限时它能吃掉 140 秒）
        deadline=state.started_at + _cfg('AGENT_TIMEOUT_SECONDS', 150))
    state.memory = mem_info

    state.messages = ([system_message]
                      + [_public(m) for m in history]
                      + [{'role': 'user', 'content': question}])

    handler = {'planner': planner_node, 'tools': tools_node,
               'reflect': reflect_node, 'respond': responder_node}
    node = 'planner'
    while node != 'done':
        if node in ('planner', 'respond'):
            nxt = handler[node](state, client)
        else:
            nxt = handler[node](state)
        if nxt == 'stop':
            node = 'done'                 # 模型已经不可用，不要再发一次
        elif nxt in ('done', 'stop'):
            node = 'done'
        else:
            node = nxt

    logger.info('Agent 编排结束: reason=%s iterations=%d tools=%d elapsed=%dms',
                state.stopped_reason, state.iterations, state.tool_calls_made,
                state.elapsed_ms)
    return state
