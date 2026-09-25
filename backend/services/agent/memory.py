"""Agent 记忆：三层上下文压缩（阶段 9）

    L1  最近 N 条对话**原文**          —— 一直在，且不参与压缩
    L2  中段摘要（Redis）             —— 把较早的对话压成一段摘要
    L3  早期要点（Redis）             —— L2 本身过长时，再压成要点列表
    近期检测结果                        —— 不在这里：由模型调 list_detection_reports
                                          按需取（是工具调用，不是预注入）

**触发逻辑是"还剩多少就压多少"**：估算 `system + 历史` 的 token 量，超过
`AGENT_CONTEXT_TOKEN_BUDGET` 时按**溢出量**决定吸收多少条 —— 每次至少腾出
溢出量的 1.5 倍（给下一轮留增长余量），但最多吸收到只剩 `AGENT_KEEP_RECENT_MESSAGES`
条原文。先扩 L2，L2 自己超过 `AGENT_L2_MAX_CHARS` 时提升为 L3（对摘要再做一次
要点化），L2 从空重新开始。

**为什么压缩状态存 Redis 而不是进程内**：多 worker、重启都会让进程内状态清零，
而记忆一旦丢失，用户会看到助手"忘了前面说过什么"。这与 store.py 的
cached_corpus_version() 面对的是同一个跨进程问题（阶段 8 已经为它付过学费）。
键名带 user_id：**不给这个就可能串号** —— 两个用户用同一个 session_id 时
会读到彼此的对话摘要。

**Redis 不可用时直接跳过压缩**（只记 WARNING），不降级到进程内：摘要错乱的
后果是会话之间串话，比"没有摘要"严重得多。同理，压缩失败绝不能让对话失败。

**不引入持久化摘要表 / 向量化语义记忆**：rag/pipeline.py 的注释已经把
「AI 生成内容入库 → 被检索为参考资料 → 下一代解读再引用它」的自引用回路写透了，
对话摘要入库的风险完全相同。患者提到相关内容已由私有化 RAG 覆盖。
"""
import json
import time

from config import config as app_config
from utils.logger import logger

L2_MARK = '【此前对话摘要】'
L3_MARK = '【更早对话要点】'
SUMMARY_KEY = 'agent:mem:{user_id}:{session_id}'


def _cfg(key, default=None):
    return getattr(app_config, key, default)


def _redis():
    from core.cache import get_redis
    return get_redis()


def _tokens(messages):
    """估算 token 数

    用 services/rag/tokens.count_tokens（真实 tokenizer）。**函数内导入**：
    该模块首次调用会加载 bge-m3 的词表并连带把 torch 拉进 sys.modules，
    放在模块顶层会让"导入 services.agent.* 不拖 torch"这条约定失效。
    """
    from services.rag.tokens import count_tokens
    total = 0
    for m in messages:
        content = m.get('content') or ''
        total += count_tokens(content) + 4        # 4 = 每条消息的角色/分隔开销
    return total


def _load_state(user_id, session_id):
    """读压缩状态；Redis 不可用返回 None（调用方据此跳过压缩）"""
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(SUMMARY_KEY.format(user_id=user_id, session_id=session_id))
        return json.loads(raw) if raw else {}
    except Exception as e:
        from core.cache import report_failure
        report_failure(e)
        logger.warning('读取会话摘要失败（本次跳过压缩）: %s', e)
        return None


def _save_state(user_id, session_id, state):
    client = _redis()
    if client is None:
        return
    key = SUMMARY_KEY.format(user_id=user_id, session_id=session_id)
    try:
        client.set(key, json.dumps(state, ensure_ascii=False),
                   ex=_cfg('AGENT_SUMMARY_TTL', 604800))
    except Exception as e:
        from core.cache import report_failure
        report_failure(e)
        logger.warning('写入会话摘要失败: %s', e)


def note_message(mark, text):
    """把摘要包成一条 system 消息

    用 role='system' 而不是 user/assistant：它既不是用户说的话也不是助手的回答，
    标成对话内容会让模型把它当成"用户之前说过这句摘要"。
    """
    return {'role': 'system', 'content': f'{mark}\n{text}'}


def _default_summarizer(texts, level):
    """默认摘要器：一次普通 LLM 调用（无工具）

    **必须硬上限**：摘要是尽力而为的旁路调用，实测不加限制时它会用 provider
    的默认超时（modelscope 120s）并重试 3 次，一次吃掉 140 秒 —— 整条编排的
    墙钟预算只有 150 秒，剩下的时间连一轮规划都不够，直接降级。
    """
    from services.ai_service import get_llm_client

    joined = '\n'.join(texts)
    if level == 'L3':
        instruction = (
            '把下面的对话摘要进一步压缩成不超过 5 条要点，每条一行短句。'
            '**医学事实（诊断、分型、过敏史、用药、日期）必须原样保留**，'
            '不得推断、不得改写数值，宁可不写也不要猜。')
    else:
        instruction = (
            '把下面的医患对话压缩成一段摘要（不超过 300 字），保留：'
            '患者提到的主诉与时间、已知诊断与分型、过敏史、医生给过的建议、'
            '待确认的问题。**医学事实与数字必须原样保留**，不得推断或改写。'
            '不要加入原文没有的内容。')
    client = get_llm_client()
    return (client.chat([{'role': 'system', 'content': instruction},
                         {'role': 'user', 'content': joined}],
                        max_tokens=_cfg('AGENT_SUMMARY_MAX_TOKENS', 400),
                        timeout=_cfg('AGENT_SUMMARY_TIMEOUT', 30),
                        max_retries=1) or '').strip()


def _label(msg):
    return '患者' if msg.get('role') == 'user' else '助手'


def compact(history, *, user_id, session_id, reserved_tokens=0, budget=None,
            keep_recent=None, summarizer=None, deadline=None):
    """按预算压缩历史，返回 (新的历史, info)

    history 元素可带私有键 `_id`（load_history 会带上）；返回的元素**保留**
    `_id`，由调用方在拼 messages 前剥掉私有键。

    `summarizer(texts, level) -> str` 可注入（验证脚本用它做确定性测试，
    不必花真实 LLM 调用）。
    """
    info = {'compressed': False, 'absorbed': 0, 'tier': None,
            'tokens_before': 0, 'tokens_after': 0, 'reused_summary': False,
            'reason': ''}
    history = list(history or [])
    if not history:
        info['reason'] = 'empty'
        return history, info

    budget = budget if budget is not None else _cfg('AGENT_CONTEXT_TOKEN_BUDGET', 3000)
    keep_recent = (keep_recent if keep_recent is not None
                   else _cfg('AGENT_KEEP_RECENT_MESSAGES', 6))
    info['tokens_before'] = reserved_tokens + _tokens(history)
    if not _cfg('AGENT_SUMMARY_ENABLED', True):
        info['reason'] = 'disabled'
        info['tokens_after'] = info['tokens_before']
        return history, info
    if info['tokens_before'] <= budget:
        info['reason'] = 'within_budget'
        info['tokens_after'] = info['tokens_before']
        return history, info

    # 超预算才去读状态（省一次 Redis 往返）
    state = _load_state(user_id, session_id)
    if state is None:
        info['reason'] = 'redis_unavailable'
        info['tokens_after'] = info['tokens_before']
        return history, info

    # **水位线的用法**：已经被摘要覆盖过的消息不再参与本轮 —— 它们的内容
    # 已经在摘要里了，再吸收一遍等于让摘要自我重复、越滚越长（实测第二次
    # 压缩会把 34 段重新摘一遍）。窗口是滚动的，旧的原文还留在窗口里很正常。
    covered_upto = state.get('l2_upto') or 0
    pending = [m for m in history if (m.get('_id') or 0) > covered_upto]
    notes = []
    if state.get('l3'):
        notes.append(note_message(L3_MARK, state['l3']))
    if state.get('l2'):
        notes.append(note_message(L2_MARK, state['l2']))
    effective = reserved_tokens + _tokens(notes + pending)
    if effective <= budget:
        # 摘要已经覆盖了大部分窗口，实际并不超预算：只带走摘要 + 未覆盖的部分
        info.update(reason='covered_by_summary', reused_summary=True,
                    tokens_after=effective)
        return notes + pending, info

    if len(pending) <= keep_recent:
        info['reason'] = 'all_recent'
        info['tokens_after'] = info['tokens_before']
        logger.warning('Agent 上下文超预算（有效 %d > %d）但可压的仅 %d 条',
                       effective, budget, len(pending))
        return history, info
    if len(pending) < _cfg('AGENT_SUMMARY_MIN_MESSAGES', 20):
        info['reason'] = 'too_few_messages'
        info['tokens_after'] = info['tokens_before']
        return history, info

    # 时间护栏：摘要要花掉一次 LLM 调用（上限 AGENT_SUMMARY_TIMEOUT），
    # 剩余预算不够就干脆不压 —— 压缩是优化，不能把编排本身的时间吃掉
    if deadline is not None:
        left = deadline - time.monotonic()
        if left < _cfg('AGENT_SUMMARY_TIMEOUT', 30) + 5:
            info.update(reason='no_time_for_summary',
                        tokens_after=info['tokens_before'])
            logger.warning('剩余预算 %.0fs 不足以做会话摘要，本轮不压缩', left)
            return history, info

    summarize = summarizer or _default_summarizer
    try:
        overflow = effective - budget
        need_free = int(overflow * 1.5)          # 给下一轮留增长余量
        absorbable = pending[:len(pending) - keep_recent]
        absorbed, freed = [], 0
        for msg in absorbable:
            absorbed.append(msg)
            freed += _tokens([msg])
            if freed >= need_free:
                break
        if not absorbed:
            info['reason'] = 'nothing_absorbable'
            info['tokens_after'] = info['tokens_before']
            return history, info

        old_l2 = state.get('l2') or ''
        # L2 自己已经太长 → 提升为 L3，L2 从空开始（这就是第三层存在的意义：
        # 一级摘要反复叠加会线性增长，最终同样撑爆预算）
        if old_l2 and len(old_l2) > _cfg('AGENT_L2_MAX_CHARS', 800):
            merged = (f'{state.get("l3")}\n{old_l2}' if state.get('l3') else old_l2)
            state['l3'] = summarize([merged], 'L3')
            state['l3_upto'] = state.get('l2_upto')
            old_l2 = ''
            info['tier'] = 'L3'

        texts = ([f'（既有摘要，请并入新内容）{old_l2}'] if old_l2 else []) + \
            [f'{_label(m)}：{m.get("content") or ""}' for m in absorbed]
        state['l2'] = summarize(texts, 'L2')
        state['l2_upto'] = absorbed[-1].get('_id')
        state['updated'] = int(time.time())
        _save_state(user_id, session_id, state)

        rest = pending[len(absorbed):]
        new_history = []
        if state.get('l3'):
            new_history.append(note_message(L3_MARK, state['l3']))
        if state.get('l2'):
            new_history.append(note_message(L2_MARK, state['l2']))
        new_history.extend(rest)

        info.update(compressed=True, absorbed=len(absorbed),
                    tier=info['tier'] or 'L2', reason='compressed')
        info['tokens_after'] = reserved_tokens + _tokens(new_history)
        logger.info('Agent 上下文压缩: 吸收 %d 条（%d→%d token, tier=%s）',
                    len(absorbed), info['tokens_before'], info['tokens_after'],
                    info['tier'])
        return new_history, info
    except Exception as e:
        # 摘要失败绝不能让对话失败：原样返回，只是这轮上下文偏大
        logger.warning('上下文压缩失败，本轮不压缩: %s', e, exc_info=True)
        info.update(reason='summarize_failed', tokens_after=info['tokens_before'])
        return history, info


def clear(user_id, session_id):
    """清掉某会话的压缩状态（验证脚本与"新建会话"用）"""
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.delete(
            SUMMARY_KEY.format(user_id=user_id, session_id=session_id)))
    except Exception as e:
        logger.warning('清除会话摘要失败: %s', e)
        return False
