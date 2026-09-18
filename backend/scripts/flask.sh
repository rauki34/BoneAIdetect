#!/usr/bin/env bash
# Flask 后端启停脚本
#
# 用法：
#   bash scripts/flask.sh start             # 启动（后台，日志进 logs/flask-stdout.log）
#   bash scripts/flask.sh start debug       # 启动并放宽限流、开 DEBUG 日志（供验证脚本用）
#   bash scripts/flask.sh stop              # 停止（含 reloader 子进程）
#   bash scripts/flask.sh restart [debug]
#   bash scripts/flask.sh status            # 查看状态
#   bash scripts/flask.sh log               # 跟踪日志
#
# ---------- 为什么需要这个脚本 ----------
# `python app.py` 的 debug 模式会开 Werkzeug reloader，那是**父子两个进程**。
# 直接 taskkill 掉监听端口那个，父进程会立刻把它拉起来，看起来像"杀不掉"。
# 本脚本按 pidfile 记录父进程，停止时递归清理整棵进程树。
#
# ---------- 两个已踩过的坑 ----------
# 1. 必须用 venv 的 python：系统 Python 没有 flask_cors 等依赖，会直接 ModuleNotFoundError。
# 2. 绝不要用 `taskkill /PID`：Git Bash 会把 /PID 当成路径转换成 D:/Git/PID，
#    命令静默失效（还回一句成功）。这里统一走 PowerShell。

set -u

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$BACKEND_DIR/../venv/Scripts/python.exe"
PIDFILE="$BACKEND_DIR/logs/flask.pid"
LOGFILE="$BACKEND_DIR/logs/flask-stdout.log"
PORT=5000

mkdir -p "$BACKEND_DIR/logs"

pid_alive() {
  [ -n "${1:-}" ] && powershell -NoProfile -Command \
    "if (Get-Process -Id $1 -EA SilentlyContinue) { exit 0 } else { exit 1 }" 2>/dev/null
}

running_pid() {
  # 注意：末尾必须有显式 return 1。函数最后一条是 `if` 而无 else 时返回 0，
  # 会让调用方 `if pid=$(running_pid)` 在"没在跑"时也判真（输出却是空的）
  if [ -f "$PIDFILE" ] && pid_alive "$(cat "$PIDFILE" 2>/dev/null)"; then
    cat "$PIDFILE"
    return 0
  fi
  return 1
}

port_owner() {
  powershell -NoProfile -Command \
    "(Get-NetTCPConnection -LocalPort $PORT -State Listen -EA SilentlyContinue |
      Select-Object -First 1 -ExpandProperty OwningProcess)" 2>/dev/null | tr -d '\r'
}

stop_tree() {
  # 递归停掉该进程及其所有后代 —— reloader 的子进程不会随父进程一起退出
  powershell -NoProfile -Command "
    function Stop-Tree(\$id) {
      Get-CimInstance Win32_Process -Filter \"ParentProcessId=\$id\" -EA SilentlyContinue |
        ForEach-Object { Stop-Tree \$_.ProcessId }
      Stop-Process -Id \$id -Force -EA SilentlyContinue
    }
    Stop-Tree $1
  " 2>/dev/null
}

case "${1:-}" in
  start)
    if pid=$(running_pid); then
      echo "后端已在运行 (PID $pid)"
      exit 0
    fi
    owner=$(port_owner)
    if [ -n "$owner" ]; then
      echo "❌ 端口 $PORT 已被 PID $owner 占用，但不是本脚本管理的进程。"
      echo "   请先确认它是什么，再手动处理："
      echo "   bash scripts/flask.sh status"
      exit 1
    fi
    if ! powershell -NoProfile -Command "if (Test-Path '$VENV_PY') { exit 0 } else { exit 1 }"; then
      echo "❌ 找不到 venv 解释器: $VENV_PY"
      exit 1
    fi

    # 验证脚本要从日志里读验证码明文，且自身连续登录不能被限流拦下
    if [ "${2:-}" = "debug" ]; then
      export LOG_LEVEL=DEBUG
      export RATE_LIMIT_LOGIN=100
      export RATE_LIMIT_REGISTER=100
      export RATE_LIMIT_CAPTCHA=100
      echo "（debug 模式：LOG_LEVEL=DEBUG，限流已放宽）"
    fi

    cd "$BACKEND_DIR" || exit 1
    nohup "$VENV_PY" app.py > "$LOGFILE" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"

    for _ in $(seq 1 60); do
      code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://127.0.0.1:$PORT/api/captcha" 2>/dev/null)
      [ "$code" = "200" ] && break
      sleep 1
    done
    if [ "$code" = "200" ]; then
      echo "✅ 后端已启动 (PID $(cat "$PIDFILE"))  http://127.0.0.1:$PORT"
      echo "   日志: $LOGFILE"
    else
      echo "❌ 后端启动失败，日志尾部："
      tail -20 "$LOGFILE"
      rm -f "$PIDFILE"
      exit 1
    fi
    ;;
  stop)
    pid=$(running_pid)
    if [ -z "$pid" ]; then
      # pidfile 没了但端口还占着，兜底按端口清理
      owner=$(port_owner)
      if [ -n "$owner" ]; then
        echo "pidfile 丢失，按端口 $PORT 清理 PID $owner"
        stop_tree "$owner"
      else
        echo "后端未在运行"
      fi
      rm -f "$PIDFILE"
      exit 0
    fi
    stop_tree "$pid"
    sleep 2
    rm -f "$PIDFILE"
    if [ -n "$(port_owner)" ]; then
      echo "⚠️  端口 $PORT 仍被占用"
    else
      echo "已停止"
    fi
    ;;
  restart)
    "$0" stop
    sleep 2
    "$0" start "${2:-}"
    ;;
  status)
    if pid=$(running_pid); then
      echo "运行中 (PID $pid)"
      owner=$(port_owner)
      [ -n "$owner" ] && echo "监听 $PORT: PID $owner"
    else
      echo "未运行 (pidfile 无记录或进程已退出)"
      owner=$(port_owner)
      [ -n "$owner" ] && echo "⚠️  但端口 $PORT 被 PID $owner 占用"
    fi
    ;;
  log)
    tail -f "$LOGFILE"
    ;;
  *)
    sed -n '4,10p' "$0"
    exit 1
    ;;
esac
