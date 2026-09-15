"""SQLite → PostgreSQL 数据迁移

迁移策略：
1. 用应用的 SQLAlchemy metadata 在 PG 建表（保证与模型定义一致）
2. 反射 SQLite 的实际表结构，逐表复制数据
3. 迁移期间关闭外键约束，避免表间依赖顺序问题
4. 按各表主键重置 sequence，否则后续 INSERT 会主键冲突
5. 逐表比对行数，不一致则报错退出

用法：
    cd backend
    python scripts/migrate_sqlite_to_pg.py            # 试运行（只报告）
    python scripts/migrate_sqlite_to_pg.py --apply    # 实际写入
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import MetaData, Table, create_engine, insert, select, text

SQLITE_PATH = BACKEND / 'instance' / 'bone_detection.db'
SQLITE_URL = f'sqlite:///{SQLITE_PATH}'
PG_URL = os.environ.get(
    'PG_URL', 'postgresql://postgres:postgres@127.0.0.1:5432/ortho')

APPLY = '--apply' in sys.argv


def table_columns(engine, table_name):
    """返回某张表在目标库中的列名集合"""
    meta = MetaData()
    try:
        meta.reflect(bind=engine, only=[table_name])
    except Exception:
        return set()
    tbl = meta.tables.get(table_name)
    return {c.name for c in tbl.columns} if tbl is not None else set()


def reset_sequences(pg_engine, tables):
    """重置自增序列，使其从当前最大 id 继续

    SQLite 的 AUTOINCREMENT 与 PG 的 sequence 机制不同；
    若手工插入了显式 id 而不重置，后续 INSERT 会从 1 开始并主键冲突。
    """
    with pg_engine.begin() as conn:
        for t in tables:
            cols = table_columns(pg_engine, t)
            if 'id' not in cols:
                continue
            conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('"{t}"', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{t}"), 1)
                )
            """))


def main():
    if not SQLITE_PATH.exists():
        print(f'源数据库不存在: {SQLITE_PATH}')
        return 1

    src = create_engine(SQLITE_URL)
    dst = create_engine(PG_URL)

    # 连通性
    with dst.connect() as c:
        c.execute(text('SELECT 1'))
    print(f'源: {SQLITE_URL}')
    print(f'目标: {PG_URL}\n')

    src_meta = MetaData()
    src_meta.reflect(bind=src)
    tables = sorted(src_meta.tables)

    # 1) 在 PG 建表 —— 用应用模型的 metadata，确保与代码定义一致
    import database  # noqa: E402
    database.db.metadata.create_all(dst)
    print(f'已在 PG 建表（metadata 共 {len(database.db.metadata.tables)} 张）\n')

    total_src = total_dst = 0
    mismatches = []

    # 2) 迁移期间关闭外键约束（仅当前会话）
    with dst.begin() as conn:
        conn.execute(text('SET session_replication_role = replica'))

    for name in tables:
        src_tbl = src_meta.tables[name]
        if name not in database.db.metadata.tables:
            print(f'  跳过 {name}: 模型中没有对应表')
            continue

        src_cols = {c.name for c in src_tbl.columns}
        dst_cols = table_columns(dst, name)
        common = sorted(src_cols & dst_cols)
        if not common:
            print(f'  跳过 {name}: 无公共列')
            continue

        with src.connect() as s:
            rows = [dict(r) for r in
                    s.execute(select(*[src_tbl.c[c] for c in common])).mappings()]

        print(f'  {name:32} SQLite {len(rows):5} 行'
              + (f'  (缺列: {sorted(src_cols - dst_cols)})' if src_cols - dst_cols else ''))

        if rows and APPLY:
            dst_tbl = Table(name, MetaData(), autoload_with=dst)
            # 分批插入，避免单条 SQL 过大
            with dst.begin() as conn:
                for i in range(0, len(rows), 500):
                    conn.execute(insert(dst_tbl), rows[i:i + 500])

        total_src += len(rows)

    if APPLY:
        reset_sequences(dst, tables)

    # 3) 校验行数
    print('\n' + '=' * 62)
    for name in tables:
        if name not in database.db.metadata.tables:
            continue
        with src.connect() as s:
            a = s.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
        with dst.connect() as d:
            b = d.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
        total_dst += b
        if a != b:
            mismatches.append((name, a, b))

    print(f'源总行数: {total_src}   目标总行数: {total_dst}')
    if mismatches:
        print('\n行数不一致的表:')
        for n, a, b in mismatches:
            print(f'  {n}: SQLite={a}  PG={b}')
    else:
        print('✅ 全部表行数一致')

    if not APPLY:
        print('\n试运行，未写入。加 --apply 生效。')
    return 1 if mismatches else 0


if __name__ == '__main__':
    sys.exit(main())
