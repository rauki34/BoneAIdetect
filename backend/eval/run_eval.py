"""评测驱动（阶段 10）

    cd backend
    python eval/run_eval.py --all                    # 三组配置的检索指标对比（零 LLM 成本）
    python eval/run_eval.py --config C --json out.json
    python eval/run_eval.py --validate               # 只校验评测集

**两组指标，成本不同，所以分开跑**：

  检索类（本文默认，不花钱）：hit@1 / hit@5 / MRR / P95 延迟 / 越界问题误召回率
  生成类（`--with-llm`，真花钱）：幻觉率（LLM-as-judge）/ 引用准确率 / token 成本

对比实验的三组配置（对齐方案文档 10.3）：

    A  纯 LLM        不做检索 —— 检索类指标天然不适用，它的价值在生成类对比
    B  纯向量 RAG    关掉 BM25 与重排（retrieve(use_bm25=False, use_rerank=False)）
    C  混合 + Rerank 改造后的最终方案（默认行为）

"越界问题误召回率"是本脚本里最能说明问题的指标之一：对库外问题，正确行为是
**什么都检索不到**（或分数低于阈值）。它一高，说明模型迟早会拿弱相关片段当依据
—— 这正是阶段 9 加 `AGENT_RAG_MIN_SCORE` 要解决的事，这里给它一个数字。
"""
import argparse
import json
import pathlib
import re
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = pathlib.Path(__file__).resolve().parent
DATASET = BASE / 'dataset' / 'ortho_qa.jsonl'
TOP_K = 5

CONFIGS = {
    'A': {'label': '纯 LLM（无检索）', 'retrieval': False},
    'B': {'label': '纯向量 RAG', 'retrieval': True,
          'kwargs': {'use_bm25': False, 'use_rerank': False}},
    # D 是方案文档 A/B/C 之外的补充：把"混合检索"与"重排"的贡献拆开。
    # 只有 A/B/C 时，B→C 的提升无法区分是 BM25 带来的还是重排带来的
    'D': {'label': '混合（无重排）', 'retrieval': True,
          'kwargs': {'use_rerank': False}},
    'C': {'label': '混合 + Rerank', 'retrieval': True, 'kwargs': {}},
}
ORDER = ['A', 'B', 'D', 'C']


def load_dataset():
    rows = []
    for line in DATASET.read_text(encoding='utf-8').splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_retrieval(config, rows):
    """跑检索类指标（不调 LLM）"""
    from services.rag.retriever import clear_caches, get_retriever, shared_scope

    # 评测必须绕开检索缓存：命中缓存时延迟会变成 0ms（实测配置 C 第二次跑就
    # 出现了 0ms 的 P50），配置之间的延迟对比直接失真；而且缓存键不含通道开关，
    # 跨配置复用还可能拿到另一种配置算出来的结果
    clear_caches()
    retriever = get_retriever()
    scope = shared_scope()
    kwargs = CONFIGS[config].get('kwargs', {})
    per_question, latencies = [], []

    for row in rows:
        q = row['question']
        t0 = time.perf_counter()
        chunks = retriever.retrieve(q, scope=scope, top_k=TOP_K, **kwargs)
        latencies.append((time.perf_counter() - t0) * 1000)

        ids = [c.chunk_id for c in chunks]
        top_score = max((c.score or 0.0) for c in chunks) if chunks else 0.0
        item = {'id': row['id'], 'category': row['category'], 'question': q,
                'retrieved': ids,
                'retrieved_docs': [c.doc_title for c in chunks],
                'top_score': round(top_score, 4), 'latency_ms': round(latencies[-1], 1)}

        if row['category'] == 'knowledge':
            truth = set(row.get('relevant_chunk_ids') or [])
            hit_rank = next((i + 1 for i, cid in enumerate(ids) if cid in truth), None)
            item['hit_rank'] = hit_rank
            item['hit@1'] = hit_rank == 1
            item['hit@5'] = hit_rank is not None
            item['rr'] = (1.0 / hit_rank) if hit_rank else 0.0
        else:
            # 库外问题：检索到高分片段就是"误召回"
            item['false_recall'] = top_score >= float(_min_score())
        per_question.append(item)
    return per_question, latencies


def _min_score():
    import config
    return getattr(config.config, 'AGENT_RAG_MIN_SCORE', 0.25)


def summarize(config, per_question, latencies):
    know = [i for i in per_question if i['category'] == 'knowledge']
    oos = [i for i in per_question if i['category'] == 'out_of_scope']
    lat = sorted(latencies)

    def pct(vals, p):
        if not vals:
            return 0.0
        k = min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1))))
        return vals[k]

    return {
        'config': config,
        'label': CONFIGS[config]['label'],
        'n_knowledge': len(know),
        'n_out_of_scope': len(oos),
        'hit@1': sum(i['hit@1'] for i in know) / len(know) if know else 0.0,
        'hit@5': sum(i['hit@5'] for i in know) / len(know) if know else 0.0,
        'mrr': statistics.fmean([i['rr'] for i in know]) if know else 0.0,
        'false_recall': (sum(i.get('false_recall', False) for i in oos) / len(oos)
                         if oos else 0.0),
        'latency_p50_ms': pct(lat, 50),
        'latency_p95_ms': pct(lat, 95),
    }


def build_messages(row, chunks, retrieved_ids):
    """按生产路径拼消息：system（+RAG 提示词与参考资料）+ 用户问题

    与 api/ai.py 的做法一致（RAG 提示词追加进同一条 system），这样测的就是
    线上那条路径，而不是另写一套评测专用提示词。
    """
    from services.ai_service import AI_SYSTEM_PROMPT

    system = AI_SYSTEM_PROMPT
    if chunks:
        from services.rag.prompts import RAG_PROMPT, format_context
        rag_part = RAG_PROMPT.format(context=format_context(chunks),
                                     question=row['question'])
        system = AI_SYSTEM_PROMPT + '\n\n' + rag_part
    return [{'role': 'system', 'content': system},
            {'role': 'user', 'content': row['question']}]


def reference_text(chunks):
    """判官的参照：**模型这次实际看到的参考资料**

    这里改过两次，每次都是因为"尺子不对"而不是"模型不对"，记下来免得再犯：

    1. 第一版用数据集里的 `ground_truth`（我摘的一两句）→ 模型引用**其他**切片
       的合法内容被判成编造。
    2. 第二版用「标注切片的完整正文」→ 仍然太窄：模型的回答里出现的
       "髁上骨折大致对应 33-A" 出自**被检索到但没被标注**的那条切片，依旧误判。

    现在直接用模型这次收到的上下文（即检索结果的全部正文）。语义也随之明确成
    **groundedness**：答案是否被"本次提供的资料"支撑。对配置 A（不做检索）
    没有任何资料，于是它的幻觉率就是"无参照下的凭空断言率" —— 这正好是
    "纯 LLM 基线"要对比的东西。
    """
    if not chunks:
        return '（本次未提供任何参考资料）'
    return '\n\n'.join(c.content or '' for c in chunks)[:6000]


def judge(answer, reference, question):
    """LLM-as-judge：答案里有没有与资料冲突、或凭空给出的具体断言

    返回 (是否有无依据内容, 无依据片段列表)。**判官失败与"没有幻觉"必须分开**：
    解析不出 JSON 时返回 judge_error，计入统计时单列，不能算作"通过"。
    """
    from services.ai_service import get_llm_client

    prompt = (
        '你是严格的医学事实核查员。下面给你【参考资料】（该问题对应的权威资料'
        '全文）和【待核查回答】。请判断回答中是否存在**与参考资料矛盾**、或'
        '**凭空给出具体断言**的内容，具体包括：分型标准、编码、数值、时间窗、'
        '用药与剂量、手术指征。\n'
        '以下情况**不算**幻觉：\n'
        '- "建议咨询医生""以医嘱为准"这类免责或就医提示\n'
        '- 与参考资料措辞不同但意思一致\n'
        '- 参考资料之外的一般性常识（如"骨折需要固定"），只要不与资料冲突\n'
        '只输出 JSON，不要解释：{"unsupported": true/false, "claims": ["..."]}\n\n'
        f'【参考资料】{reference}\n\n'
        f'【问题】{question}\n\n'
        f'【待核查回答】{answer}')
    try:
        client = get_llm_client()
        # 裁判也要放宽：本 provider 的延迟波动很大（实测单次可达 140s），
        # 60s + 不重试会把裁判失败率推到 1/3，而判官失败**不能算通过** ——
        # 那会让幻觉率建立在一两条样本上
        reply = client.chat_reply([{'role': 'user', 'content': prompt}],
                                  max_tokens=400, timeout=180, max_retries=2)
        text = (reply.content or '').strip()
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end < 0:
            return 'judge_error', []
        data = json.loads(text[start:end + 1])
        return (bool(data.get('unsupported')),
                [str(c)[:80] for c in (data.get('claims') or [])][:3])
    except Exception as e:
        return 'judge_error', [str(e)[:80]]


def judge_refusal(answer, question, reference):
    """库外问题专用裁判：模型是否"如实说资料不足以回答"而不是硬答

    与幻觉率分开判定：幻觉率问的是"有没有编造"，这里问的是"有没有承认答不了"。
    一个回答可能既不编造也没有明确拒答（含糊带过），那不算通过。
    """
    from services.ai_service import get_llm_client

    prompt = (
        '下面给你一个【问题】、系统实际提供的【参考资料】、以及【回答】。'
        '请判断：【回答】是否明确说明了"现有资料不足以回答该问题"'
        '（等价表述如"资料未涉及""无法回答""建议咨询专科医生"均可）？\n'
        '注意：回答列出参考资料覆盖了什么、并带上引用编号来说明，属于合格拒答。\n'
        '只输出 JSON：{"refused": true/false, "reason": "..."}\n\n'
        f'【问题】{question}\n\n【参考资料】{reference[:2000]}\n\n【回答】{answer}')
    try:
        client = get_llm_client()
        reply = client.chat_reply([{'role': 'user', 'content': prompt}],
                                  max_tokens=200, timeout=180, max_retries=2)
        text = (reply.content or '').strip()
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end < 0:
            return 'judge_error', []
        data = json.loads(text[start:end + 1])
        return bool(data.get('refused')), [str(data.get('reason'))[:120]]
    except Exception as e:
        return 'judge_error', [str(e)[:100]]


def run_generation(config, rows, limit=None, out_path=None):
    """跑生成类指标（真实 LLM 计费）"""
    from services.ai_service import get_llm_client

    client = get_llm_client()
    subset = [r for r in rows if r['category'] in ('knowledge', 'out_of_scope')]
    if limit:
        # **按类别各取 N 条**，而不是按总数切前 N 条：数据集里 knowledge 排在前面，
        # 按总数切会让小样本跑不到库外问题，而拒答率会显示成 0.0%（看起来像
        # "一条都没误答"，实际是一条都没测）
        picked = []
        for cat in ('knowledge', 'out_of_scope'):
            picked.extend([r for r in subset if r['category'] == cat][:limit])
        subset = picked
    results = []
    for i, row in enumerate(subset, 1):
        chunks, retrieved_ids = [], []
        if CONFIGS[config]['retrieval']:
            from services.rag.retriever import get_retriever, shared_scope
            chunks = get_retriever().retrieve(
                row['question'], scope=shared_scope(), top_k=TOP_K,
                **CONFIGS[config].get('kwargs', {}))
            retrieved_ids = [c.chunk_id for c in chunks]

        t0 = time.perf_counter()
        try:
            reply = client.chat_reply(build_messages(row, chunks, retrieved_ids),
                                      max_tokens=800, timeout=120, max_retries=1)
            answer, usage = reply.content or '', reply.usage or {}
            error = None
        except Exception as e:
            answer, usage, error = '', {}, f'{type(e).__name__}: {e}'[:120]
        latency = (time.perf_counter() - t0) * 1000

        item = {'id': row['id'], 'category': row['category'],
                'question': row['question'], 'answer': answer,
                'retrieved': retrieved_ids, 'usage': usage,
                'latency_ms': round(latency, 1), 'error': error}

        # 引用准确率：把答案里的 [n] 映射回本次检索结果的 chunk_id，看是否命中标注。
        # 用确定性判据而不是让裁判判断"引用是否支撑结论"—— 后者主观且更贵
        cited = sorted({int(m) for m in re.findall(r'\[(\d+)\]', answer)})
        item['cited'] = cited
        if row['category'] == 'knowledge' and cited:
            truth = set(row.get('relevant_chunk_ids') or [])
            ok = [n for n in cited if 1 <= n <= len(retrieved_ids)
                  and retrieved_ids[n - 1] in truth]
            item['citation_accuracy'] = len(ok) / len(cited)
        else:
            item['citation_accuracy'] = None

        if row['category'] == 'knowledge' and answer:
            verdict, claims = judge(answer, reference_text(chunks), row['question'])
            item['hallucination'], item['unsupported_claims'] = verdict, claims
        elif row['category'] == 'out_of_scope' and answer:
            # 库外问题的正确行为是**如实说资料不足以回答**
            #
            # 这里也改过一次：最初用关键词 + "不能出现引用编号"，结果把三条正确
            # 拒答全判成了失败 —— 模型的实际行为是"列出资料覆盖了什么（带引用），
            # 然后说明这些都不涉及你的问题"，那是好行为，带引用是它说明依据的
            # 方式。现在以裁判判定为准，关键词作为另一个独立信号同时记录。
            item['refused_keyword'] = any(
                w in answer for w in ('无法回答', '没有相关资料', '资料不足',
                                      '暂时无法查证', '查不到', '无法提供',
                                      '没有找到', '无法给出', '未包含'))
            verdict, claims = judge_refusal(answer, row['question'], reference_text(chunks))
            item['refused'] = verdict if verdict in (True, False) else None
            item['refusal_note'] = claims
        results.append(item)
        print(f'    [{i}/{len(subset)}] {row["category"]:<12} '
              f'{row["question"][:26]}  {latency / 1000:.1f}s'
              f'{"" if not error else "  ERR"}')
        if out_path:
            pathlib.Path(out_path).write_text(
                json.dumps({'config': config, 'items': results},
                           ensure_ascii=False, indent=1), encoding='utf-8')
    return results


def citation_is_valid(item):
    """引用的编号是否都落在**本次提供的资料**范围内

    这是一个**确定性**判据，专门抓"伪造引用编号"（答案里写 [7] 但只给了 5 条
    资料）—— 那是模型编造依据的直接证据，不需要裁判。
    """
    cited, retrieved = item.get('cited') or [], item.get('retrieved') or []
    if not cited:
        return None
    return all(1 <= n <= len(retrieved) for n in cited)


def summarize_generation(config, results):
    know = [i for i in results if i['category'] == 'knowledge' and i['answer']]
    oos = [i for i in results if i['category'] == 'out_of_scope' and i['answer']]
    judged = [i for i in know if i.get('hallucination') in (True, False)]
    halluc = [i for i in judged if i['hallucination'] is True]
    cited = [i for i in know if i.get('citation_accuracy') is not None]
    validity = [citation_is_valid(i) for i in know]
    validity = [v for v in validity if v is not None]
    tokens = [(i['usage'].get('prompt_tokens', 0) + i['usage'].get('completion_tokens', 0))
              for i in results if i['usage']]
    lat = sorted(i['latency_ms'] for i in results if i['answer'])

    def pct(vals, p):
        return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))] if vals else 0

    # 拒答率只统计裁判成功判定的那些（判官失败不计入分母，但会单列出来）
    nb = [i for i in oos if i.get('refused') in (True, False)]

    return {
        'config': config, 'label': CONFIGS[config]['label'],
        'n_knowledge': len(know), 'n_out_of_scope': len(oos),
        'n_judge_error': len([i for i in know if i.get('hallucination') == 'judge_error']),
        'hallucination_rate': (len(halluc) / len(judged)) if judged else 0.0,
        # 两个引用指标，含义不同，别混着看：
        #   citation_valid  引用编号是否都在提供范围内（抓伪造引用，确定性判据）
        #   citation_labeled 引用是否命中**出题时依据的那条切片** —— 这是**下界**，
        #                    因为标注只有一条，而模型可以合法引用其他相关切片
        'citation_valid': (sum(validity) / len(validity)) if validity else None,
        'citation_labeled': (statistics.fmean([i['citation_accuracy'] for i in cited])
                             if cited else None),
        # 没跑到库外问题时给 None（显示 —），而不是 0.0%：0.0% 读起来像
        # "一条都没误答"，但那可能只是"一条都没测"
        'refusal_rate': (sum(1 for i in nb if i['refused']) / len(nb)) if nb else None,
        'avg_tokens': int(statistics.fmean(tokens)) if tokens else 0,
        'latency_p95_ms': pct(lat, 95),
    }


def print_generation_table(summaries):
    print('\n' + '=' * 100)
    print('  生成质量对比（真实 LLM；幻觉率与拒答率由 LLM-as-judge 判定，引用类指标是确定性判据）')
    print('=' * 100)
    print(f"{'配置':<18}{'幻觉率':>9}{'引用合法':>10}{'引用命中':>10}"
          f"{'库外拒答率':>12}{'平均token':>11}{'P95延迟':>10}")
    print('-' * 100)
    for s in summaries:
        cv = f"{s['citation_valid']:.1%}" if s['citation_valid'] is not None else '—'
        cl = f"{s['citation_labeled']:.1%}" if s['citation_labeled'] is not None else '—'
        rr = f"{s['refusal_rate']:.1%}" if s['refusal_rate'] is not None else '—'
        print(f"{s['label']:<18}{s['hallucination_rate']:>9.1%}{cv:>10}{cl:>10}"
              f"{rr:>12}{s['avg_tokens']:>11}{s['latency_p95_ms'] / 1000:>9.1f}s")
    print('=' * 100)
    print(f"  样本量：{summaries[0]['n_knowledge']} 条知识问答 / "
          f"{summaries[0]['n_out_of_scope']} 条库外问题")
    print('  幻觉率：答案里有没有与本次提供资料冲突、或凭空给出的具体断言（细节性判据）')
    print('  引用合法：引用编号是否都在提供范围内（抓伪造引用，如只给 5 条却写 [7]）')
    print('  引用命中：引用是否命中出题时依据的那条切片 —— **这是下界**，'
          '因为标注只有一条而模型可以合法引用其他相关切片')
    print('  库外拒答率：对知识库外问题是否如实说"资料不足以回答"')
    for s in summaries:
        if s['n_judge_error']:
            print(f"  ⚠️ {s['label']}: {s['n_judge_error']} 条裁判失败，未计入幻觉率"
                  f"（不能当作通过；样本量不足时结论不成立）")


def print_table(summaries):
    print('\n' + '=' * 78)
    print('  检索质量对比（评测集 %d 条知识问答 + %d 条库外问题）'
          % (summaries[0]['n_knowledge'], summaries[0]['n_out_of_scope']))
    print('=' * 78)
    head = f"{'配置':<18}{'hit@1':>8}{'hit@5':>8}{'MRR':>8}{'误召回率':>10}{'P50':>9}{'P95':>9}"
    print(head)
    print('-' * 78)
    for s in summaries:
        print(f"{s['label']:<18}{s['hit@1']:>8.1%}{s['hit@5']:>8.1%}{s['mrr']:>8.3f}"
              f"{s['false_recall']:>10.1%}{s['latency_p50_ms']:>8.0f}ms"
              f"{s['latency_p95_ms']:>8.0f}ms")
    print('=' * 78)
    print('  hit@k：标注的相关切片是否出现在前 k 条内；MRR：首个命中的倒数排名均值')
    print('  误召回率：库外问题里"仍返回高分片段"的比例（越低越好，0 表示结构上不会误用）')
    print('  配置 A 不做检索，检索类指标对它天然不适用，它的价值在生成类指标（--with-llm）')


def main():
    parser = argparse.ArgumentParser(description='RAG / Agent 评测')
    parser.add_argument('--config', choices=ORDER, help='单组配置')
    parser.add_argument('--all', action='store_true', help='跑全部配置并打对比表')
    parser.add_argument('--json', help='把逐题结果写到该文件（供后续 LLM 评测复用）')
    parser.add_argument('--validate', action='store_true', help='只校验评测集')
    parser.add_argument('--with-llm', action='store_true',
                        help='追加生成类指标（幻觉率/引用准确率，真实 LLM 计费）')
    parser.add_argument('--limit', type=int, default=None,
                        help='生成类指标**每个类别**只跑 N 条（先小样本验证，再全量）')
    parser.add_argument('--from-json', metavar='文件',
                        help='不重新调用 LLM，直接用已保存的结果重算指标表')
    parser.add_argument('--config-of-json', default='C',
                        help='配合 --from-json：这份结果属于哪个配置（决定表头）')
    args = parser.parse_args()

    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _ = build_bare_app()

    if args.validate:
        import subprocess
        return subprocess.call([sys.executable, str(BASE / 'build_dataset.py'), '--check'])

    if args.from_json:
        # 指标口径会随对评测的理解而调整，而每次重跑都要花真实 LLM 调用与时间。
        # 这个入口让"改完判据再算一遍"变成瞬间的事。
        cfg = args.config_of_json
        data = json.loads(pathlib.Path(args.from_json).read_text(encoding='utf-8'))
        print_generation_table([summarize_generation(cfg, data['items'])])
        return 0

    if not DATASET.exists():
        print(f'❌ 评测集不存在，先跑：python eval/build_dataset.py')
        return 1

    rows = load_dataset()
    configs = ORDER if args.all else ([args.config] if args.config else ['C'])

    all_results, summaries = {}, []
    with app.app_context():
        for cfg in configs:
            if not CONFIGS[cfg]['retrieval']:
                summaries.append({'config': cfg, 'label': CONFIGS[cfg]['label'],
                                  'n_knowledge': sum(1 for r in rows if r['category'] == 'knowledge'),
                                  'n_out_of_scope': sum(1 for r in rows if r['category'] == 'out_of_scope'),
                                  'hit@1': 0.0, 'hit@5': 0.0, 'mrr': 0.0,
                                  'false_recall': 0.0, 'latency_p50_ms': 0, 'latency_p95_ms': 0})
                continue
            print(f'  跑配置 {cfg}（{CONFIGS[cfg]["label"]}）…')
            per_q, lat = run_retrieval(cfg, rows)
            all_results[cfg] = per_q
            summaries.append(summarize(cfg, per_q, lat))

    print_table(summaries)

    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps(all_results, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'\n  逐题结果已写入 {args.json}')

    if args.with_llm:
        gen_summaries = []
        with app.app_context():
            for cfg in configs:
                print(f'\n  生成类指标 · 配置 {cfg}（{CONFIGS[cfg]["label"]}）…')
                res = run_generation(
                    cfg, rows, limit=args.limit,
                    out_path=(str(pathlib.Path(args.json).with_suffix(
                        f'.gen.{cfg}.json')) if args.json else None))
                gen_summaries.append(summarize_generation(cfg, res))
        print_generation_table(gen_summaries)
    return 0


if __name__ == '__main__':
    sys.exit(main())
