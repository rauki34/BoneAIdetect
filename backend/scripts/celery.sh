#!/usr/bin/env bash
# Celery worker 启停脚本
#
# worker 与 Flask 后端是**两个进程**，都要起：后端负责投递任务，
# worker 负责执行。只起后端的话任务会一直躺在队列里不动。
#
# 用法：
#   bash scripts/celery.sh start      # 启动（后台，日志进 logs/celery.log）
#   bash scripts/celery.sh stop       # 停止
#   bash scripts/celery.sh restart    # 重启
#   bash scripts/celery.sh status     # 查看状态与已注册任务
#   bash scripts/celery.sh log        # 跟踪日志
#   bash scripts/celery.sh queues     # 查看队列长度
#
# ---------- 为什么是 -P solo ----------
# Celery 在 Windows 上不支持 prefork 池。solo 池并发度恒为 1，两类 GPU 任务
# （YOLO 训练、bge-m3 向量化）因此天然串行，在 6GB 显存下不会互相抢。
# 代价是 task_time_limit 不生效（solo 池没有 terminate_job），详见 tasks/celery_app.py。
#
# ---------- 三个踩过的坑 ----------
# 1. 用 `python -m celery` 而不是 venv/Scripts/celery.exe：后者 sys.path 是
#    venv/Scripts，不含 backend/，worker 里 `from config import ...` 直接 ModuleNotFoundError。
# 2. 不能用 `$!` 当 worker 的 PID。本机 venv 的解释器是个 shim，会 re-exec 基础解释器，
#    所以 `$!` 拿到的是**立刻退出的 shim**，pidfile 里存的是死 PID。
#    这里改成启动后扫描命令行匹配的进程，把真实的 PID 记下来。
# 3. 不能用 `taskkill /PID`：Git Bash 会把 /PID 当路径转换成 D:/Git/PID，命令静默失效。
#    统一走 PowerShell。

set -u

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$BACKEND_DIR/../venv/Scripts/python.exe"
PIDFILE="$BACKEND_DIR/logs/celery.pid"
LOGFILE="$BACKEND_DIR/logs/celery.log"
REDIS_CLI=/d/ortho-redis/redis-cli.exe
QUEUES="training,ingest"
NODE_NAME="ortho@$(hostname)"

mkdir -p "$BACKEND_DIR/logs"

# `python -m` 会把 cwd（下面会 cd 到 backend/）放进 sys.path，与 `python app.py` 一致
CELERY_CMD=("$VENV_PY" -m celery -A tasks.celery_app)

# 扫描本项目的 worker 进程。命令行里同时含 `-A tasks.celery_app worker` 和我们的
# 节点名，足以和其他 python 进程区分开
worker_pids() {
  powershell -NoProfile -Command \
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |
       Where-Object { \$_.CommandLine -like '*tasks.celery_app worker*' -and
                      \$_.CommandLine -like '*$NODE_NAME*' } |
       Select-Object -ExpandProperty ProcessId" 2>/dev/null | tr -d '\r'
}

alive_pids() {
  # 从 pidfile 读回 PID 列表，过滤掉已经不存在的
  [ -f "$PIDFILE" ] || return 1
  local found=''
  for pid in $(cat "$PIDFILE" 2>/dev/null); do
    if powershell -NoProfile -Command \
         "if (Get-Process -Id $pid -EA SilentlyContinue) { exit 0 } else { exit 1 }" 2>/dev/null; then
      found="$found $pid"
    fi
  done
  found=$(echo "$found" | xargs 2>/dev/null)
  [ -n "$found" ] || return 1
  echo "$found"
  return 0
}

case "${1:-}" in
  start)
    if pids=$(alive_pids); then
      echo "worker 已在运行 (PID $pids)"
      exit 0
    fi

    # 队列依赖 Redis：broker 不在的话 worker 起来也会不停重连，先拦一道
    if ! "$REDIS_CLI" -p 6379 ping >/dev/null 2>&1; then
      echo "❌ Redis 未运行，请先执行: bash scripts/redis.sh start"
      exit 1
    fi

    cd "$BACKEND_DIR" || exit 1
    # stdout/stderr 全部重定向到日志文件、stdin 接 /dev/null，
    # 否则后台进程会占住调用方的管道，脚本看起来像卡住
    "${CELERY_CMD[@]}" worker \
        -l info -P solo -Q "$QUEUES" -n "$NODE_NAME" \
        > "$LOGFILE" 2>&1 < /dev/null &
    shim_pid=$!

    # 等 worker 真正起来，并记下实际进程的 PID（不只 $!）
    pids=''
    for _ in $(seq 1 30); do
      pids=$(worker_pids)
      [ -n "$pids" ] && break
      sleep 1
    done
    if [ -z "$pids" ]; then
      echo "❌ worker 启动失败，日志尾部："
      tail -20 "$LOGFILE"
      exit 1
    fi

    # shim 也算进来，停止时一并清理，避免留下孤儿
    echo "$pids $shim_pid" | tr '\n' ' ' | xargs > "$PIDFILE"
    echo "✅ worker 已启动 (PID $(cat "$PIDFILE"))，队列: $QUEUES"
    echo "   日志: $LOGFILE"
    ;;
  stop)
    if ! pids=$(alive_pids); then
      # pidfile 没了但进程还在（例如上一次启动中途失败），按命令行兜底
      pids=$(worker_pids | tr '\n' ' ' | xargs 2>/dev/null)
      if [ -z "$pids" ]; then
        echo "worker 未在运行"
        rm -f "$PIDFILE"
        exit 0
      fi
      echo "pidfile 无记录，按进程扫描清理 PID $pids"
    fi
    # 用 PowerShell 而不是 taskkill，理由见文件头第 3 条
    ids=$(echo "$pids" | tr ' ' ',')
    powershell -NoProfile -Command \
      "Stop-Process -Id $ids -Force -EA SilentlyContinue" 2>/dev/null
    for _ in 1 2 3 4 5; do
      [ -z "$(worker_pids)" ] && break
      sleep 1
    done
    rm -f "$PIDFILE"
    if [ -n "$(worker_pids)" ]; then
      echo "⚠️  worker 仍在运行；若正跑着 solo 任务，它不会立刻响应停止"
    else
      echo "已停止"
    fi
    ;;
  restart)
    "$0" stop
    sleep 2
    "$0" start
    ;;
  status)
    if pids=$(alive_pids); then
      echo "运行中 (PID $pids)"
      cd "$BACKEND_DIR" || exit 1
      "${CELERY_CMD[@]}" inspect registered 2>/dev/null | sed -n '2,40p'
    else
      echo "未运行"
    fi
    ;;
  log)
    tail -f "$LOGFILE"
    ;;
  queues)
    # 用 keys 而非 --scan：本机 redis-cli 的构建不支持 --scan，会静默返回空
    for db in 1 2; do
      echo "--- redis db$db ---"
      "$REDIS_CLI" -p 6379 -n "$db" keys '*' 2>/dev/null | head -20
    done
    ;;
  *)
    sed -n '7,13p' "$0"
    exit 1
    ;;
esac
