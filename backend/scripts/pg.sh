#!/usr/bin/env bash
# PostgreSQL 启停脚本
#
# 本项目用 conda 安装的 PostgreSQL 16 + pgvector，数据目录在 D:/ortho-pgdata。
# 它不是 Windows 服务，重启电脑后需要手动 start。
#
# 用法：
#   bash scripts/pg.sh start     # 启动
#   bash scripts/pg.sh stop      # 停止
#   bash scripts/pg.sh status    # 查看状态
#   bash scripts/pg.sh psql      # 进入 psql 交互终端
#   bash scripts/pg.sh log       # 查看服务日志

set -u

PGBIN=/d/Anaconda/envs/ortho-pg/Library/bin
PGDATA=/d/ortho-pgdata
PGPORT=5432
PGDB=ortho

export PGPASSWORD=${PGPASSWORD:-postgres}

case "${1:-}" in
  start)
    "$PGBIN/pg_ctl.exe" -D "$PGDATA" -l "$PGDATA/server.log" -o "-p $PGPORT" start
    sleep 3
    "$PGBIN/pg_ctl.exe" -D "$PGDATA" status
    ;;
  stop)
    "$PGBIN/pg_ctl.exe" -D "$PGDATA" -m fast stop
    ;;
  status)
    "$PGBIN/pg_ctl.exe" -D "$PGDATA" status
    ;;
  psql)
    "$PGBIN/psql.exe" -h 127.0.0.1 -p "$PGPORT" -U postgres -d "$PGDB"
    ;;
  log)
    tail -40 "$PGDATA/server.log"
    ;;
  *)
    sed -n '2,14p' "$0"
    exit 1
    ;;
esac
