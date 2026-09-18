#!/usr/bin/env bash
# Redis 启停脚本
#
# 项目用 tporadowski 的 Windows 构建（Redis 5.0.14.1，便携版免安装），
# 位于 D:/ortho-redis。它不是 Windows 服务，重启电脑后需要手动 start。
#
# 用法：
#   bash scripts/redis.sh start     # 启动（后台）
#   bash scripts/redis.sh stop      # 停止
#   bash scripts/redis.sh status    # 查看状态
#   bash scripts/redis.sh cli       # 进入交互终端
#   bash scripts/redis.sh keys      # 查看限流与验证码相关的键
#   bash scripts/redis.sh queues    # 查看 Celery 队列长度（阶段 8）
#
# 关于 RESP 协议（阶段 8 踩过）：
#   Redis 5 不支持 RESP3 的 HELLO 命令，而 redis-py 从 8.0 起默认走 RESP3。
#   本项目把 redis-py 钉在 6.4.0（kombu 要求 <6.5），它的默认值是 RESP2，
#   因此这里不需要任何额外配置。core/cache.py 里显式传的 protocol=2 是冗余但
#   无害的保险，别删。
#
# 关于持久化（阶段 8 起改变）：
#   阶段 6 引入 Redis 时它只做缓存，所以刻意 `--save "" --appendonly no`。
#   阶段 8 起它同时是 Celery 的 broker，排队中的任务若因 Redis 重启而丢失，
#   DB 里的行会永久停在 pending/running。因此改开 AOF。

set -u

REDIS_HOME=/d/ortho-redis
REDIS_PORT=6379
PIDFILE="$REDIS_HOME/redis.pid"
LOGFILE="$REDIS_HOME/redis.log"

case "${1:-}" in
  start)
    if "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "Redis 已在运行"
      exit 0
    fi
    # AOF 持久化：Redis 现在同时是缓存与消息队列 broker，排队中的任务不能丢。
    # --dir 显式指定，否则 aof 文件会落在调用者的当前目录里。
    "$REDIS_HOME/redis-server.exe" --port "$REDIS_PORT" \
        --dir "$REDIS_HOME" \
        --save "" --appendonly yes \
        --logfile "$LOGFILE" --daemonize no &
    echo $! > "$PIDFILE"
    sleep 2
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" ping
    ;;
  stop)
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" shutdown nosave 2>/dev/null \
      && echo "已停止" || echo "Redis 未在运行"
    rm -f "$PIDFILE"
    ;;
  status)
    if "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "运行中 (端口 $REDIS_PORT)"
      "$REDIS_HOME/redis-cli.exe" info server | grep redis_version
      "$REDIS_HOME/redis-cli.exe" dbsize
    else
      echo "未运行"
    fi
    ;;
  cli)
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT"
    ;;
  keys)
    # 用 keys 而非 --scan：tporadowski 这个 Windows 构建的 redis-cli **不支持
    # --scan**，它会静默返回空结果（不报错），看起来像"一个键都没有"。
    # keyspace 很小，KEYS 的开销可以接受。
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" keys 'rl:*'
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" keys 'captcha:*'
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" keys 'train:stop:*'
    ;;
  queues)
    # Celery 队列与结果后端在 db1 / db2（见 tasks/celery_app.py），缓存用 db0
    for db in 1 2; do
      echo "--- db$db ---"
      "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" -n "$db" keys '*' | head -20
    done
    ;;
  *)
    sed -n '7,15p' "$0"
    exit 1
    ;;
esac
