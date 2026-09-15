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
#
# 注意：Redis 5 不支持 RESP3，redis-py 连接时需指定 protocol=2（见 core/cache.py）。

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
    # 关闭持久化：本项目只把它当缓存用，无需落盘
    "$REDIS_HOME/redis-server.exe" --port "$REDIS_PORT" \
        --save "" --appendonly no \
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
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" keys 'rl:*'
    "$REDIS_HOME/redis-cli.exe" -p "$REDIS_PORT" keys 'captcha:*'
    ;;
  *)
    sed -n '2,15p' "$0"
    exit 1
    ;;
esac
