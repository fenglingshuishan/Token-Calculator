#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
URL="http://127.0.0.1:8000"
LOG="$ROOT/server.log"

notify() {
  if command -v notify-send >/dev/null 2>&1; then notify-send "Prompt 成本工作台" "$1"; fi
}

open_workbench() {
  if [ "${PROMPT_WORKBENCH_NO_OPEN:-0}" != "1" ]; then xdg-open "$URL" >/dev/null 2>&1 & fi
}

if curl -fsS "$URL/health" >/dev/null 2>&1; then
  open_workbench
  exit 0
fi

if [ ! -x "$PYTHON" ]; then
  notify "首次启动：正在创建运行环境，请稍候。"
  python3 -m venv "$ROOT/.venv" || { notify "无法创建 Python 虚拟环境"; exit 1; }
  "$ROOT/.venv/bin/python" -m pip install -e "$ROOT" >>"$LOG" 2>&1 || {
    notify "依赖安装失败，请查看 $LOG"
    exit 1
  }
fi

nohup "$PYTHON" "$ROOT/run.py" --no-browser >>"$LOG" 2>&1 &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" >"$ROOT/.server.pid"
for _ in $(seq 1 40); do
  if curl -fsS "$URL/health" >/dev/null 2>&1; then
    open_workbench
    exit 0
  fi
  sleep 0.25
done

rm -f "$ROOT/.server.pid"
notify "启动失败，请查看 $LOG"
exit 1
