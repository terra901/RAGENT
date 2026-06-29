#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/.runtime"
API_PID="$PID_DIR/api.pid"
WORKER_PID="$PID_DIR/celery.pid"

stop_pid() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name 未记录 PID，跳过。"
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid"
    fi
    echo "已停止 $name，PID=$pid"
  else
    echo "$name PID 已不存在，PID=$pid"
  fi
  rm -f "$pid_file"
}

stop_pid "Celery worker" "$WORKER_PID"
stop_pid "后端 API" "$API_PID"

if [[ "${1:-}" == "--all" || "${1:-}" == "--compose" ]]; then
  cd "$ROOT"
  docker compose down
  echo "已停止 RAGENT Docker 依赖容器，数据卷已保留。"
else
  echo "Docker 依赖容器仍在运行。需要一起停止时运行: scripts/stop_ragent_full.sh --all"
fi
