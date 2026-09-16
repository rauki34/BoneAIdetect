"""RAG 提示词与引用契约

提示词文本独立成模块，与 ai_service 的 AI_SYSTEM_PROMPT 保持同样的处理方式：
提示词是会被反复调整的东西，不该埋在编排逻辑里。

**强制引用溯源是医疗场景的关键**：回答里的每条结论都要能指回具体资料，
而不是让模型自由发挥。同时必须给出"资料不足"的出口——没有这个出口，
模型在检索为空时只会编造。
"""

# 与「项目改造方案.md」阶段 7.4 的模板一致
RAG_PROMPT = """你是骨科诊疗辅助系统。请**严格基于以下参考资料**回答问题。

【参考资料】
{context}

【要求】
1. 只使用参考资料中的信息，不得编造
2. 每条结论后必须标注引用编号，格式如 [1]、[2]
3. 如果参考资料不足以回答，明确说明"现有资料无法回答该问题"
4. 涉及用药建议时，必须提示"具体用药请遵医嘱"

【问题】{question}

【回答】"""

# 检索为空时给模型的说明。必须显式说明"没有资料"，
# 否则模型会把"没给资料"理解成"可以自由回答"。
EMPTY_CONTEXT_NOTE = '（本次没有检索到可用的参考资料，请如实说明现有资料无法回答该问题）'

ORIGIN_LABELS = {
    'public': '公开资料',
    'curated': '整理摘要',
    'patient_record': '患者本人病历',
}


def format_context(chunks):
    """把检索结果拼成参考资料文本块

    带上来源、章节、页码与**来源性质**（公开原文 / 整理摘要 / 本人病历）。
    来源性质必须进提示词：模型据此知道自己在引用什么，回答措辞才能相应调整。
    """
    if not chunks:
        return EMPTY_CONTEXT_NOTE
    parts = []
    for i, c in enumerate(chunks, 1):
        label = ORIGIN_LABELS.get(c.origin, '')
        page = f'第{c.page}页' if c.page else '页码不详'
        section = c.section or ''
        head = f'[{i}] 来源：《{c.doc_title}》{section} {page}'
        if label:
            head += f'（{label}）'
        parts.append(f'{head}\n{c.content}')
    return '\n\n'.join(parts)


def build_references(chunks):
    """构造响应里的 references 数组

    契约要求的 6 个键（index / doc / section / page / chunk_id / score）
    保持不变，其余为增量附加字段——前端与验收脚本都按这 6 个键核对。
    """
    references = []
    for i, c in enumerate(chunks, 1):
        references.append({
            'index': i,
            'doc': c.doc_title,
            'section': c.section or '',
            'page': c.page,
            'chunk_id': c.chunk_id,
            'score': round(c.score, 4) if c.score is not None else None,
            # ---- 以下为附加字段 ----
            'doc_id': c.doc_id,
            'doc_type': c.doc_type,
            'origin': c.origin,
            'origin_label': ORIGIN_LABELS.get(c.origin, ''),
            'source': c.source,
            'snippet': (c.content or '')[:400],
            'is_personal': bool(c.is_personal),
        })
    return references
