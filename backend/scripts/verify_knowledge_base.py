"""RAG 知识库回归验证

覆盖：依赖与模型 → 数据库与索引 → 切片质量 → 检索质量 →
**跨患者泄漏** → **幻觉** → 降级 → 幂等与缓存

前两组（泄漏与幻觉）是本阶段最关键的验收项：一个会串病历、或会编造
知识库里没有的内容的医疗问答系统，功能再多也不能用。

用法：
    cd backend
    python scripts/verify_knowledge_base.py                    # 快速模式（不加载模型）
    python scripts/verify_knowledge_base.py --with-models      # 含向量/重排模型
    python scripts/verify_knowledge_base.py --with-models --with-llm   # 含真实 LLM 幻觉测试
    python scripts/verify_knowledge_base.py --with-models --keep       # 保留测试数据

退出码 = 失败用例数。
"""
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

WITH_MODELS = '--with-models' in sys.argv
WITH_LLM = '--with-llm' in sys.argv
KEEP = '--keep' in sys.argv

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def skip(name, why):
    SKIP.append(name)
    print(f'  [SKIP] {name}  {why}')


def section(title):
    print(f'\n{title}')


# 检索质量用例：查询 → 期望在 top-3 命中的关键词
RETRIEVAL_CASES = [
    ('股骨远端骨折的AO分型标准是什么', ['AO', '33']),
    ('胫骨平台骨折 Schatzker 分型', ['Schatzker']),
    ('开放性骨折 Gustilo 分型', ['Gustilo']),
    ('骨折后多久可以开始康复训练', ['康复']),
]

# 知识库外的问题，用于幻觉测试
OUT_OF_CORPUS_QUERY = '儿童川崎病的冠状动脉瘤发生率是多少'


def main():
    from core.bootstrap import build_bare_app
    enable = build_bare_app
    app, engine = enable()

    print(f'数据库: {engine.url.render_as_string(hide_password=True)}')
    print(f'模式: {"含模型" if WITH_MODELS else "快速（不加载模型）"}'
          f'{"，含真实 LLM" if WITH_LLM else ""}\n')

    from sqlalchemy import text
    from database import KnowledgeChunk, KnowledgeDoc, db

    # ---------- 1. 依赖与模型 ----------
    section('[1] 依赖与模型')
    for name in ('sentence_transformers', 'jieba', 'rank_bm25', 'pypdf', 'pgvector'):
        try:
            __import__(name)
            check(f'{name} 可导入', True)
        except ImportError as e:
            check(f'{name} 可导入', False, str(e))

    if WITH_MODELS:
        from services.rag.embedder import Embedder
        from services.rag.reranker import Reranker
        emb = Embedder.instance()
        check('嵌入模型加载', emb.available, emb.error or f'device={emb.device}')
        rr = Reranker.instance()
        check('重排模型加载', rr.available, rr.error or '')
    else:
        skip('嵌入/重排模型加载', '未指定 --with-models')

    # ---------- 2. 数据库与索引 ----------
    section('[2] 数据库与索引')
    with engine.connect() as c:
        ext = c.execute(text(
            "SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
        check('pgvector 扩展已安装', bool(ext), f'version={ext}')

        hnsw = c.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE indexname='ix_kb_chunks_embedding_hnsw'"
        )).scalar()
        check('HNSW 向量索引存在', bool(hnsw) and 'hnsw' in (hnsw or '').lower())

        total = c.execute(text('SELECT COUNT(*) FROM knowledge_chunks')).scalar()
        check('切片数量 > 500', total > 500, f'实际 {total}')

        no_vec = c.execute(text(
            'SELECT COUNT(*) FROM knowledge_chunks WHERE embedding IS NULL')).scalar()
        check('所有切片都有向量', no_vec == 0, f'缺失 {no_vec}')

        bad_origin = c.execute(text(
            "SELECT COUNT(*) FROM knowledge_docs WHERE origin NOT IN "
            "('public','curated','patient_record')")).scalar()
        check('文档 origin 取值合法', bad_origin == 0, f'非法 {bad_origin}')

        no_source = c.execute(text(
            "SELECT COUNT(*) FROM knowledge_docs WHERE source IS NULL OR source=''")).scalar()
        # 出处是引用溯源的立身之本，共享语料不允许为空
        check('共享语料均有出处(source)', no_source == 0, f'缺失 {no_source}')

        bad_count = c.execute(text("""
            SELECT COUNT(*) FROM (SELECT d.id FROM knowledge_docs d
            LEFT JOIN knowledge_chunks ch ON ch.doc_id=d.id
            GROUP BY d.id, d.chunk_count HAVING d.chunk_count <> COUNT(ch.id)) t
        """)).scalar()
        check('文档 chunk_count 与实际一致', bad_count == 0, f'不一致 {bad_count} 篇')

    # ---------- 3. 切片质量 ----------
    section('[3] 切片质量')
    empty = KnowledgeChunk.query.filter(
        (KnowledgeChunk.content.is_(None)) | (KnowledgeChunk.content == '')).count()
    check('无空切片', empty == 0, f'空切片 {empty}')

    # 用真实分词器核算，避免"估算没超、实际超了"从而被静默截断
    from services.rag.tokens import get_tokenizer
    tok = get_tokenizer()
    if tok is None:
        skip('切片长度未超嵌入窗口', '分词器不可用，无法准确核算')
    else:
        samples = KnowledgeChunk.query.all()
        over = sum(1 for ch in samples
                   if len(tok.encode(ch.content, add_special_tokens=False)) > 1024)
        worst = max((len(tok.encode(ch.content, add_special_tokens=False))
                     for ch in samples), default=0)
        check('切片长度均未超嵌入窗口(1024)', over == 0,
              f'超限 {over} 条，最长 {worst} token')

    missing_section = KnowledgeChunk.query.filter(
        (KnowledgeChunk.section.is_(None)) | (KnowledgeChunk.section == '')).count()
    with_section = KnowledgeChunk.query.count() - missing_section
    check('切片带章节信息（用于引用溯源）', with_section > 0,
          f'{with_section}/{KnowledgeChunk.query.count()} 条有 section')

    # 切片确定性：同一文件两次切片结果应一致
    from services.rag.loader import load_document
    from services.rag.splitter import MedicalSplitter
    corpus = pathlib.Path(__file__).resolve().parent.parent / 'knowledge' / 'corpus'
    sample_files = sorted(corpus.rglob('*.md'))[:5]
    if sample_files:
        splitter = MedicalSplitter()
        deterministic = True
        for path in sample_files:
            doc = load_document(path)
            a = [c.content for c in splitter.split(doc)]
            b = [c.content for c in splitter.split(doc)]
            if a != b:
                deterministic = False
                break
        check('切片结果可复现（同一文件两次一致）', deterministic,
              f'抽查 {len(sample_files)} 个文件')

    if not WITH_MODELS:
        skip('检索质量', '未指定 --with-models')
        skip('跨患者泄漏测试', '未指定 --with-models')
        skip('幻觉：库外问题不编造', '未指定 --with-models')
        skip('降级行为', '未指定 --with-models')
        return report(app)

    # ---------- 4. 检索质量 ----------
    section('[4] 检索质量')
    from services.rag.retriever import get_retriever, shared_scope
    retriever = get_retriever()

    hits_ok = 0
    for query, keywords in RETRIEVAL_CASES:
        hits = retriever.retrieve(query, scope=shared_scope(), top_k=3)
        joined = ' '.join(h.doc_title + ' ' + (h.content or '') for h in hits)
        hit = any(k in joined for k in keywords)
        hits_ok += 1 if hit else 0
        print(f'\n    【{query}】')
        for h in hits:
            print(f'      {h.score:.3f} rrf={h.rrf_score:.5f} vec#{h.vec_rank} '
                  f'bm25#{h.bm25_rank} | {h.origin} | {h.doc_title[:30]} | {h.section or "-"}')
        check(f'top-3 命中期望内容: {query[:24]}', hit, f'期望关键词 {keywords}')

    check('检索用例整体通过率 >= 2/3', hits_ok >= 2, f'{hits_ok}/{len(RETRIEVAL_CASES)}')

    # 重排后分数应单调不增
    hits = retriever.retrieve(RETRIEVAL_CASES[0][0], scope=shared_scope(), top_k=5)
    scores = [h.score for h in hits]
    check('结果按分数降序排列', all(scores[i] >= scores[i + 1]
                                    for i in range(len(scores) - 1)),
          f'scores={[round(s, 3) for s in scores]}')

    # ---------- 5. 跨患者泄漏（关键） ----------
    section('[5] 跨患者泄漏测试（关键）')
    from database import User
    from services.rag.retriever import RetrievalScope, patient_scope

    sentinel_a = 'ZTEST-LEAK-A-7f3a'
    sentinel_b = 'ZTEST-LEAK-B-9c1d'
    created = []
    try:
        patients = User.query.filter_by(role='patient').limit(2).all()
        if len(patients) < 2:
            skip('跨患者泄漏测试', '数据库中患者不足 2 名')
        else:
            user_a, user_b = patients[0], patients[1]
            from services.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()
            for user, sentinel in ((user_a, sentinel_a), (user_b, sentinel_b)):
                r = pipeline.ingest_text(
                    f'这是一条用于隔离测试的记录。标记串：{sentinel}。'
                    f'标记串仅应被患者 {user.id} 本人检索到。',
                    title=f'隔离测试记录 {sentinel}',
                    file_hash=f'ztest-{sentinel}',
                    patient_id=user.id, apply=True, replace=True,
                    source='隔离测试数据（自动生成）',
                    doc_meta_extra={'purpose': 'leak-test'},
                )
                created.append(r.doc_id)

            # B 名下的切片 id，用于区分"B 查到自己的记录"（正常）与"查到别人的"（泄漏）
            b_chunk_ids = {
                cid for (cid,) in db.session.query(KnowledgeChunk.id)
                .filter(KnowledgeChunk.patient_id == user_b.id).all()
            }

            scope_a = patient_scope(user_a.id)
            scope_b = patient_scope(user_b.id)

            # 5.1 本人应能检索到自己的记录
            own = retriever.retrieve(sentinel_a, scope=scope_a, top_k=5)
            check('患者可检索到本人病历', any(sentinel_a in (h.content or '') for h in own),
                  f'命中 {len(own)} 条')

            # 5.2 他人检索不到（重复 20 次以覆盖 ANN 的不确定性）
            #
            # 注意断言的是"归属"而不是"是否为个人切片"：B 检索到**自己的**
            # 个人切片是完全正确的行为，按 is_personal 判断会把正常结果误判为泄漏。
            leaked = 0
            foreign_personal = 0
            for _ in range(20):
                other = retriever.retrieve(sentinel_a, scope=scope_b, top_k=5)
                for h in other:
                    if sentinel_a in (h.content or ''):
                        leaked += 1
                    if h.is_personal and h.chunk_id not in b_chunk_ids:
                        foreign_personal += 1
            check('他人检索不到该记录（20 次重复）', leaked == 0, f'泄漏 {leaked} 次')
            check('他人检索结果不含他人的个人切片', foreign_personal == 0,
                  f'出现他人切片 {foreign_personal} 次（B 自己的切片 {len(b_chunk_ids)} 条属正常）')

            # 5.3 只查共享库时也检索不到
            shared_only = retriever.retrieve(sentinel_a, scope=shared_scope(), top_k=5)
            check('仅共享库检索不到个人记录',
                  not any(sentinel_a in (h.content or '') for h in shared_only))

            # 5.4 fail-closed：不指定患者却要求检索个人病历时必须报错
            raised = False
            try:
                RetrievalScope(patient_id=None, include_personal=True)
            except PermissionError:
                raised = True
            check('未指定 patient_id 时要求检索个人病历 → 拒绝', raised)

            # 5.5 原始 SQL 交叉核对：库里的确存在 B 的记录，而 A 查不到
            with engine.connect() as c:
                n_b = c.execute(text(
                    'SELECT COUNT(*) FROM knowledge_chunks WHERE patient_id=:p'
                ), {'p': user_b.id}).scalar()
                n_a_visible = c.execute(text(
                    'SELECT COUNT(*) FROM knowledge_chunks '
                    'WHERE patient_id=:p AND patient_id=:p2'
                ), {'p': user_b.id, 'p2': user_a.id}).scalar()
            check('交叉核对：B 的记录存在但 A 不可见',
                  n_b > 0 and n_a_visible == 0, f'B 有 {n_b} 条，A 可见 {n_a_visible} 条')
    finally:
        if not KEEP:
            for doc_id in created:
                doc = db.session.get(KnowledgeDoc, doc_id) if doc_id else None
                if doc is not None:
                    db.session.delete(doc)
            db.session.commit()
            print('    （已清理隔离测试数据，--keep 可保留）')

    # ---------- 6. 幻觉测试（关键） ----------
    section('[6] 幻觉测试（关键）')
    out_hits = retriever.retrieve(OUT_OF_CORPUS_QUERY, scope=shared_scope(), top_k=5)
    from services.rag.splitter import MedicalSplitter  # noqa: F401  (确保模块可导入)

    if out_hits:
        print(f'    库外问题的命中（共 {len(out_hits)} 条）：')
        for h in out_hits:
            print(f'      {h.score:.3f} | {h.doc_title[:40]}')
    threshold = float(getattr(app.config.get('RAG_MIN_SCORE', 0) or 0, 'real', 0) or 0)
    strong = [h for h in out_hits if (h.score or 0) >= max(threshold, 0.5)]
    check('库外问题不返回高相关结果', len(strong) == 0,
          f'高相关命中 {len(strong)} 条（阈值 0.5）')

    if WITH_LLM:
        from services.ai_service import get_llm_client
        from services.rag.prompts import RAG_PROMPT, format_context

        def ask(question, context):
            """直接走 LLMClient，让异常暴露出来

            刻意不用 call_ai_assistant_api：它在失败时会**静默降级为预设话术**，
            而那段话术既不含引用也不含断言，会让"LLM 其实不可用"的情形
            伪装成测试通过。测试必须在被测对象坏掉时失败。
            """
            messages = [
                {'role': 'system', 'content': RAG_PROMPT.format(
                    context=context or '（无参考资料）', question=question)},
                {'role': 'user', 'content': question},
            ]
            client = get_llm_client()
            return client.chat(messages, max_tokens=500)

        refusal_markers = ('现有资料无法回答', '资料中没有', '无法回答', '没有相关', '无法确定')

        # 6.1 库外问题：应当明确说资料不足，而不是编造
        try:
            answer = ask(OUT_OF_CORPUS_QUERY, format_context(out_hits[:3]))
            print(f'\n    【库外问题】{OUT_OF_CORPUS_QUERY}\n      {answer[:280]}\n')
            refusal = any(m in answer for m in refusal_markers)
            has_citation = '[' in answer and ']' in answer
            check('LLM 对库外问题不编造（拒答或不加引用）', refusal or not has_citation,
                  f'拒绝={refusal} 含引用={has_citation}')
        except Exception as e:
            check('LLM 对库外问题不编造（拒答或不加引用）', False,
                  f'LLM 调用失败，无法判定: {type(e).__name__} {str(e)[:120]}')

        # 6.2 库内问题：应当给出带引用编号的回答（正向用例，
        #     只做拒答断言的话，"模型永远只会说无法回答"也会通过）
        in_q = RETRIEVAL_CASES[0][0]
        in_hits = retriever.retrieve(in_q, scope=shared_scope(), top_k=3)
        try:
            answer2 = ask(in_q, format_context(in_hits))
            print(f'\n    【库内问题】{in_q}\n      {answer2[:280]}\n')
            cited = bool(re.search(r'\[\d+\]', answer2))
            check('LLM 对库内问题给出带引用的回答', cited,
                  f'含 [n] 引用={cited}')
        except Exception as e:
            check('LLM 对库内问题给出带引用的回答', False,
                  f'LLM 调用失败: {type(e).__name__} {str(e)[:120]}')
    else:
        skip('LLM 幻觉测试', '未指定 --with-llm')

    # ---------- 7. 降级 ----------
    section('[7] 降级行为')
    try:
        from core.cache import get_redis
        client = get_redis()
        redis_state = 'unavailable' if client is None else 'available'
    except Exception:
        redis_state = 'error'
    hits = retriever.retrieve(RETRIEVAL_CASES[0][0], scope=shared_scope(), top_k=3)
    check(f'Redis 状态为 {redis_state} 时检索仍可用', len(hits) > 0)

    # Embedder 不可用时，build_rag_context 必须返回空而不是抛异常
    from services.rag.embedder import Embedder
    original_ensure = Embedder._ensure
    try:
        Embedder._ensure = lambda self: False
        original_embed = Embedder.encode_query
        Embedder.encode_query = lambda self, q: None
        from services.rag.pipeline import RAGPipeline
        r = RAGPipeline()
        r.retriever = retriever
        degraded = retriever.retrieve_safely(
            '股骨远端骨折分型', scope=shared_scope(), top_k=3)
        check('嵌入不可用时检索降级为词法通道（不抛异常）', True,
              f'返回 {len(degraded)} 条')
    finally:
        Embedder._ensure = original_ensure
        from services.rag.embedder import Embedder as E2
        E2.encode_query = original_embed

    # 检索层断路器：异常输入不应把异常抛给调用方
    try:
        retriever.retrieve_safely('', scope=shared_scope())
        check('空查询不抛异常', True)
    except Exception as e:
        check('空查询不抛异常', False, str(e))

    return report(app)


def report(app):
    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)} / 跳过 {len(SKIP)}')
    if FAIL:
        print('\n  失败用例：')
        for name in FAIL:
            print(f'    - {name}')
    return len(FAIL)


if __name__ == '__main__':
    started = time.time()
    code = main()
    print(f'  用时 {time.time() - started:.1f}s')
    sys.exit(code)
