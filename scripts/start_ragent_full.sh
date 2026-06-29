#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/src/backend"
PYTHON_BIN="${RAGENT_PYTHON:-/home/chenjy/miniconda3/envs/RAGENT/bin/python}"
CELERY_BIN="${RAGENT_CELERY:-/home/chenjy/miniconda3/envs/RAGENT/bin/celery}"
PID_DIR="$ROOT/.runtime"
LOG_DIR="$ROOT/logs"
API_PID="$PID_DIR/api.pid"
WORKER_PID="$PID_DIR/celery.pid"

mkdir -p "$PID_DIR" "$LOG_DIR"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

wait_port() {
  local port="$1"
  local name="$2"
  for _ in $(seq 1 60); do
    if "$PYTHON_BIN" -c 'import socket,sys; s=socket.create_connection(("127.0.0.1", int(sys.argv[1])), 1); s.close()' "$port" >/dev/null 2>&1; then
      echo "$name 已就绪: 127.0.0.1:$port"
      return 0
    fi
    sleep 1
  done
  echo "$name 未在预期时间内就绪: 127.0.0.1:$port" >&2
  return 1
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "找不到 RAGENT Python: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -x "$CELERY_BIN" ]]; then
  echo "找不到 Celery: $CELERY_BIN" >&2
  exit 1
fi

if [[ ! -f "$BACKEND/.env" ]]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  echo "已从 .env.example 生成 $BACKEND/.env，请按需填写 DA_LLM_API_KEY。"
fi

cd "$ROOT"
docker compose up -d
wait_port 3307 "MySQL"
wait_port 6380 "Redis"
wait_port 5673 "RabbitMQ"

if is_running "$API_PID"; then
  echo "后端 API 已在运行，PID=$(cat "$API_PID")"
else
  (
    cd "$BACKEND"
    PYTHONPATH="$BACKEND" nohup "$PYTHON_BIN" -m uvicorn data_agent.api.main:app --host 127.0.0.1 --port 8000 \
      > "$LOG_DIR/api.log" 2>&1 &
    echo $! > "$API_PID"
  )
  echo "已启动后端 API，PID=$(cat "$API_PID")，日志: $LOG_DIR/api.log"
fi

if is_running "$WORKER_PID"; then
  echo "Celery worker 已在运行，PID=$(cat "$WORKER_PID")"
else
  (
    cd "$BACKEND"
    PYTHONPATH="$BACKEND" nohup "$CELERY_BIN" -A worker.celery_app worker -l info \
      > "$LOG_DIR/celery.log" 2>&1 &
    echo $! > "$WORKER_PID"
  )
  echo "已启动 Celery worker，PID=$(cat "$WORKER_PID")，日志: $LOG_DIR/celery.log"
fi

wait_port 8000 "RAGENT API"
echo "RAGENT 全量启动完成: http://127.0.0.1:8000/"
echo "后台管理员: admin@ragent.local / 140617"
echo "RabbitMQ 管理台: http://127.0.0.1:15673/ 账号 ragent / 140617"
