"""知识库入库

用法：
    cd backend
    python scripts/ingest_knowledge.py                     # 试运行：解析+切片，报告将写入多少切片
    python scripts/ingest_knowledge.py --apply             # 实际入库（跳过未变更文档）
    python scripts/ingest_knowledge.py --apply --replace   # 强制重建（切片策略变更后用）
    python scripts/ingest_knowledge.py --file x.pdf --doc-type guideline
    python scripts/ingest_knowledge.py --file x.pdf --patient-id 3   # 患者个人资料
    python scripts/ingest_knowledge.py --apply --patient-records     # 患者病历/报告入库
    python scripts/ingest_knowledge.py --apply --prune     # 清理语料目录中已删除的文件
    python scripts/ingest_knowledge.py --apply --batch 32  # YOLO 不在显存时用大批次

首次运行会下载 bge-m3（约 2.2GB），耗时较长。
"""
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

APPLY = '--apply' in sys.argv
REPLACE = '--replace' in sys.argv
PRUNE = '--prune' in sys.argv
PATIENT_RECORDS = '--patient-records' in sys.argv


def arg_value(flag, default=None):
    if flag in sys.argv:
        index = sys.argv.index(flag)
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def print_results(results, apply):
    if not results:
        print('  没有需要处理的文档')
        return 0, 0, 0

    ok = skipped = failed = 0
    dry_chunks = 0
    for r in results:
        if r.status == 'failed':
            failed += 1
            flag = '[失败]'
        elif r.skipped:
            skipped += 1
            flag = '[跳过]'
        else:
            ok += 1
            flag = '[待入库]' if not apply else '[完成]'

        detail = f'{r.chunks:4d} 切片'
        if r.reason:
            detail += f'  {r.reason}'
        if r.error:
            detail += f'  错误: {r.error[:80]}'
        name = r.title or r.path
        print(f'  {flag} {name:36} {detail}')
        if not apply and not r.skipped:
            dry_chunks += r.chunks

    print('-' * 70)
    print(f'  合计 {len(results)} 篇：成功 {ok} / 跳过 {skipped} / 失败 {failed}')
    if not apply:
        print(f'  预计新增约 {dry_chunks} 个切片')
        print('  试运行，未写入。加 --apply 生效。')
    return ok, skipped, failed


def main():
    from core.bootstrap import build_bare_app
    from services.rag.pipeline import RAGPipeline

    try:
        _app, engine = build_bare_app()
    except Exception as e:
        print(f'数据库连接失败: {e}')
        print('PostgreSQL 是否已启动？可执行 bash scripts/pg.sh start')
        return 1

    from database import KnowledgeChunk, KnowledgeDoc

    print(f'数据库: {engine.url.render_as_string(hide_password=True)}')
    print(f'语料目录: {BACKEND / "knowledge" / "corpus"}')
    print(f'模式: {"实际写入" if APPLY else "试运行"}{"（强制重建）" if REPLACE else ""}\n')

    pipeline = RAGPipeline()
    batch = int(arg_value('--batch', 0)) or None
    started = time.time()

    if PRUNE:
        if not APPLY:
            print('--prune 只在 --apply 下生效')
            return 1
        removed = pipeline.prune_corpus()
        print(f'已清理 {removed} 条失效的语料记录')
        return 0

    if PATIENT_RECORDS:
        patient_id = arg_value('--patient-id')
        patient_id = int(patient_id) if patient_id else None
        scope = f'患者 {patient_id}' if patient_id else '全部患者'
        print(f'=== 患者病历入库（{scope}）===')
        results = pipeline.ingest_patient_records(
            patient_id, apply=APPLY, replace=REPLACE, batch_size=batch)
    else:
        only = arg_value('--file')
        if only:
            only = Path(only)
            if not only.is_absolute():
                only = BACKEND / only
            print(f'=== 单文件入库: {only} ===')
            doc_type = arg_value('--doc-type')
            patient_id = arg_value('--patient-id')
            results = [pipeline.ingest_file(
                only,
                doc_type=doc_type,
                department=arg_value('--department'),
                source=arg_value('--source'),
                origin=arg_value('--origin'),
                title=arg_value('--title'),
                patient_id=int(patient_id) if patient_id else None,
                apply=APPLY, replace=REPLACE, batch_size=batch,
            )]
        else:
            print('=== 语料目录入库 ===')
            results = pipeline.ingest_corpus(
                apply=APPLY, replace=REPLACE, batch_size=batch)

    ok, skipped, failed = print_results(results, APPLY)
    elapsed = time.time() - started

    if APPLY:
        total = KnowledgeChunk.query.count()
        docs = KnowledgeDoc.query.filter_by(status='ready').count()
        shared = KnowledgeDoc.query.filter(
            KnowledgeDoc.status == 'ready', KnowledgeDoc.patient_id.is_(None)).count()
        print(f'\n  当前知识库：{docs} 篇 ready（其中共享 {shared} 篇），'
              f'共 {total} 个切片，用时 {elapsed:.1f}s')
        if total:
            print('  [OK] 入库完成')
        else:
            print('  [警告] 切片数为 0，请检查语料目录')

    if failed:
        print(f'\n  有 {failed} 篇失败，详见上面输出与 logs/app.log')
    return failed


if __name__ == '__main__':
    sys.exit(main())
