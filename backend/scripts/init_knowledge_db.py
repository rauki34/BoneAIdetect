"""知识库数据库引导（阶段 7）

把"建 knowledge 表 + pgvector 扩展 + HNSW/GIN 索引 + 新增列"做成可重复执行的
脚本。阶段 5 引入 pgvector 时 `CREATE EXTENSION vector` 是手工敲的，
仓库里没有任何记录——换台机器直接报 `type "vector" does not exist`。
本脚本补上这个洞。

应用启动时 `init_db()` 会跑同样的引导，因此正常启动不需要这个脚本；
它的用途是：检查环境是否具备 RAG 条件、在无应用环境下手动补建、
以及 CI/新机器上的一键初始化。

用法：
    cd backend
    python scripts/init_knowledge_db.py           # 试运行：只打印现状与将执行的 DDL
    python scripts/init_knowledge_db.py --apply   # 实际执行
    python scripts/init_knowledge_db.py --check   # 断言：扩展与索引是否齐备
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402

APPLY = '--apply' in sys.argv
CHECK = '--check' in sys.argv

# --check 的断言目标：索引名 -> 索引定义中必须出现的子串
EXPECTED_INDEXES = {
    'ix_kb_chunks_embedding_hnsw': 'hnsw',
    'ix_kb_chunks_content_trgm': 'gin',
    'ix_kb_docs_title_trgm': 'gin',
}
EXPECTED_TABLES = ('knowledge_docs', 'knowledge_chunks')
EXPECTED_COLUMNS = (('ai_conversations', 'references'),)


def build_app():
    """构造裸 Flask 应用并初始化数据库（见 core/bootstrap.py 的说明）"""
    from core.bootstrap import build_bare_app

    return build_bare_app()


def current_state(engine):
    """读取现状：扩展 / 索引 / 列 / 表行数"""
    state = {'extensions': {}, 'indexes': {}, 'columns': {}, 'counts': {}}
    with engine.connect() as conn:
        for name in ('vector', 'pg_trgm'):
            row = conn.execute(text(
                'SELECT extversion FROM pg_extension WHERE extname = :n'
            ), {'n': name}).first()
            state['extensions'][name] = row[0] if row else None

        rows = conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename IN ('knowledge_docs', 'knowledge_chunks')"
        )).fetchall()
        state['indexes'] = {r[0]: r[1] for r in rows}

        for table, column in EXPECTED_COLUMNS:
            row = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ), {'t': table, 'c': column}).first()
            state['columns'][f'{table}.{column}'] = bool(row)

        for table in EXPECTED_TABLES:
            try:
                state['counts'][table] = conn.execute(
                    text(f'SELECT COUNT(*) FROM {table}')).scalar()
            except Exception:
                state['counts'][table] = None       # 表还不存在
    return state


def print_state(state):
    print('扩展:')
    for name, ver in state['extensions'].items():
        print(f'  {name:12} {ver or "缺失"}')
    print('知识库索引:')
    if not state['indexes']:
        print('  （无）')
    for name, ddl in sorted(state['indexes'].items()):
        kind = 'hnsw' if 'hnsw' in ddl else ('gin' if 'using gin' in ddl else 'btree')
        print(f'  {name:34} {kind}')
    print('新增列:')
    for name, ok in state['columns'].items():
        print(f'  {name:34} {"存在" if ok else "缺失"}')
    print('行数:')
    for name, n in state['counts'].items():
        print(f'  {name:34} {"表不存在" if n is None else n}')


def run_check(engine):
    """断言扩展、索引、列齐备；返回失败项数"""
    state = current_state(engine)
    failures = []

    for name in ('vector',):
        if not state['extensions'].get(name):
            failures.append(f'扩展缺失: {name}')
    for idx, needle in EXPECTED_INDEXES.items():
        ddl = state['indexes'].get(idx)
        if not ddl:
            failures.append(f'索引缺失: {idx}')
        elif needle not in ddl.lower():
            failures.append(f'索引类型不符: {idx}（期望含 {needle}）{ddl}')
    for table in EXPECTED_TABLES:
        if state['counts'].get(table) is None:
            failures.append(f'表缺失: {table}')
    for name, ok in state['columns'].items():
        if not ok:
            failures.append(f'列缺失: {name}')

    print()
    if failures:
        for f in failures:
            print(f'  [FAIL] {f}')
        print(f'\n未通过 {len(failures)} 项')
    else:
        print('  [PASS] pgvector 扩展、HNSW/GIN 索引、表与新增列齐备')
        print('\n知识库数据库引导完整')
    return len(failures)


def main():
    try:
        _app, engine = build_app()
    except Exception as e:
        print(f'数据库连接失败: {e}')
        print('PostgreSQL 是否已启动？可执行 bash scripts/pg.sh start')
        return 1

    dialect = engine.dialect.name
    print(f'数据库方言: {dialect}')
    if dialect != 'postgresql':
        print('当前不是 PostgreSQL，向量能力不可用；引导跳过。')
        print('提示：在 backend/.env 中设置 DATABASE_URL 指向 PostgreSQL。')
        return 0
    print(f'连接: {engine.url.render_as_string(hide_password=True)}\n')

    if CHECK:
        return run_check(engine)

    before = current_state(engine)
    print('=== 执行前 ===')
    print_state(before)

    if not APPLY:
        print('\n试运行，未执行任何 DDL。加 --apply 生效。')
        return 0

    print('\n=== 执行引导 ===')
    from services.rag.store import (
        ensure_columns, ensure_extensions, ensure_indexes,
    )
    ext = ensure_extensions()
    idx = ensure_indexes()
    col = ensure_columns()
    print(f'扩展: {ext}')
    print(f'索引: {idx}')
    print(f'新增列: {col}')

    print('\n=== 执行后 ===')
    after = current_state(engine)
    print_state(after)

    failures = run_check(engine)
    return failures


if __name__ == '__main__':
    sys.exit(main())
