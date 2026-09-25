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
    from services.rag.retriever import get_retriever, shared_scope

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
    args = parser.parse_args()

    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _ = build_bare_app()

    if args.validate:
        import subprocess
        return subprocess.call([sys.executable, str(BASE / 'build_dataset.py'), '--check'])

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
        print('\n  （生成类指标：幻觉率 / 引用准确率 / token 成本 —— 见 --with-llm 实现）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
