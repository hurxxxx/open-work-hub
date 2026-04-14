#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

prodlike_load_dotenv() {
  local env_file="${1:?env file is required}"
  [[ -f "$env_file" ]] || return 0

  local python_bin="${ROOT_DIR}/apps/api/.venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    python_bin="$(command -v python3)"
  fi

  eval "$(
    PRODLIKE_ENV_FILE="$env_file" "$python_bin" - <<'PY'
import os
import pathlib
import shlex

path = pathlib.Path(os.environ["PRODLIKE_ENV_FILE"])
for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
  )"
}

prodlike_lower() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

prodlike_load_dotenv "$ROOT_DIR/.env"

export DOOWON_PRODLIKE_API_COUNT="${DOOWON_PRODLIKE_API_COUNT:-8}"
export DOOWON_PRODLIKE_NGINX_PORT="${DOOWON_PRODLIKE_NGINX_PORT:-4200}"
export DOOWON_PRODLIKE_POSTGRES_PORT="${DOOWON_PRODLIKE_POSTGRES_PORT:-55432}"
export DOOWON_PRODLIKE_REDIS_PORT="${DOOWON_PRODLIKE_REDIS_PORT:-56379}"
export DOOWON_PRODLIKE_REDIS_URL="${DOOWON_PRODLIKE_REDIS_URL:-redis://127.0.0.1:${DOOWON_PRODLIKE_REDIS_PORT}/0}"
export DOOWON_PRODLIKE_REDIS_RESULT_BACKEND="${DOOWON_PRODLIKE_REDIS_RESULT_BACKEND:-redis://127.0.0.1:${DOOWON_PRODLIKE_REDIS_PORT}/1}"
export DOOWON_PRODLIKE_COLLAB_REDIS_URL="${DOOWON_PRODLIKE_COLLAB_REDIS_URL:-$DOOWON_PRODLIKE_REDIS_URL}"
export DOOWON_PRODLIKE_WORKER_BROKER_URL="${DOOWON_PRODLIKE_WORKER_BROKER_URL:-$DOOWON_PRODLIKE_REDIS_URL}"
export DOOWON_PRODLIKE_WORKER_RESULT_BACKEND="${DOOWON_PRODLIKE_WORKER_RESULT_BACKEND:-$DOOWON_PRODLIKE_REDIS_RESULT_BACKEND}"
export DOOWON_PRODLIKE_MINIO_PORT="${DOOWON_PRODLIKE_MINIO_PORT:-59000}"
export DOOWON_PRODLIKE_MINIO_CONSOLE_PORT="${DOOWON_PRODLIKE_MINIO_CONSOLE_PORT:-59001}"
export DOOWON_PRODLIKE_USE_LOCAL_POSTGRES="${DOOWON_PRODLIKE_USE_LOCAL_POSTGRES:-auto}"
export DOOWON_PRODLIKE_USE_LOCAL_MINIO="${DOOWON_PRODLIKE_USE_LOCAL_MINIO:-auto}"
export DOOWON_PRODLIKE_BASE_URL="${DOOWON_PRODLIKE_BASE_URL:-http://127.0.0.1:${DOOWON_PRODLIKE_NGINX_PORT}}"
export DOOWON_PRODLIKE_RUNTIME_DIR="${DOOWON_PRODLIKE_RUNTIME_DIR:-$ROOT_DIR/.prod-like}"
export DOOWON_PRODLIKE_PID_DIR="${DOOWON_PRODLIKE_PID_DIR:-$DOOWON_PRODLIKE_RUNTIME_DIR/pids}"
export DOOWON_PRODLIKE_LOG_DIR="${DOOWON_PRODLIKE_LOG_DIR:-$DOOWON_PRODLIKE_RUNTIME_DIR/logs}"
export DOOWON_PRODLIKE_NGINX_CONF_TEMPLATE_PATH="${DOOWON_PRODLIKE_NGINX_CONF_TEMPLATE_PATH:-$ROOT_DIR/ops/prod-like/nginx.conf.template}"
export DOOWON_PRODLIKE_NGINX_CONF_PATH="${DOOWON_PRODLIKE_NGINX_CONF_PATH:-$DOOWON_PRODLIKE_RUNTIME_DIR/nginx.conf}"

export DOOWON_POSTGRES_DSN="${DOOWON_POSTGRES_DSN:-postgresql+psycopg://aidoo_db:aidoo_db@127.0.0.1:${DOOWON_PRODLIKE_POSTGRES_PORT}/doowon_ai_portal}"
export DOOWON_REDIS_URL="$DOOWON_PRODLIKE_REDIS_URL"
export DOOWON_API_COLLAB_REDIS_URL="$DOOWON_PRODLIKE_COLLAB_REDIS_URL"
export DOOWON_WORKER_BROKER_URL="$DOOWON_PRODLIKE_WORKER_BROKER_URL"
export DOOWON_WORKER_RESULT_BACKEND="$DOOWON_PRODLIKE_WORKER_RESULT_BACKEND"
export DOOWON_MINIO_ENDPOINT="${DOOWON_MINIO_ENDPOINT:-http://127.0.0.1:${DOOWON_PRODLIKE_MINIO_PORT}}"
export DOOWON_MINIO_ACCESS_KEY="${DOOWON_MINIO_ACCESS_KEY:-minioadmin}"
export DOOWON_MINIO_SECRET_KEY="${DOOWON_MINIO_SECRET_KEY:-minioadmin}"
export DOOWON_MINIO_BUCKET="${DOOWON_MINIO_BUCKET:-aidoo-portal}"
export DOOWON_LLM_HEALTHCHECK_ON_STARTUP="${DOOWON_LLM_HEALTHCHECK_ON_STARTUP:-0}"
export DOOWON_LLM_REQUIRED="${DOOWON_LLM_REQUIRED:-0}"
export DOOWON_API_ALLOW_DEV_ADMIN_LOGIN="${DOOWON_API_ALLOW_DEV_ADMIN_LOGIN:-1}"

prodlike_api_port() {
  local index="${1:?instance index is required}"
  printf '%s\n' "$((8000 + index))"
}

prodlike_api_name() {
  local index="${1:?instance index is required}"
  printf 'prodlike-api-%s\n' "$index"
}

prodlike_ensure_runtime_dirs() {
  mkdir -p "$DOOWON_PRODLIKE_RUNTIME_DIR" "$DOOWON_PRODLIKE_PID_DIR" "$DOOWON_PRODLIKE_LOG_DIR"
}

prodlike_detect_api_upstream_host() {
  docker run --rm --add-host=prodlike-host:host-gateway nginx:1.27-alpine \
    sh -lc "grep -m1 -E '^[0-9]+(\\.[0-9]+){3}[[:space:]]+prodlike-host([[:space:]]|\$)' /etc/hosts | awk '{print \$1}'"
}

prodlike_render_nginx_conf() {
  prodlike_ensure_runtime_dirs
  local upstream_host
  upstream_host="$(prodlike_detect_api_upstream_host)"
  if [[ -z "$upstream_host" ]]; then
    echo "[prod-like] failed to detect Docker host gateway IPv4 for nginx upstream" >&2
    return 1
  fi

  PRODLIKE_NGINX_TEMPLATE="$DOOWON_PRODLIKE_NGINX_CONF_TEMPLATE_PATH" \
  PRODLIKE_NGINX_OUTPUT="$DOOWON_PRODLIKE_NGINX_CONF_PATH" \
  PRODLIKE_API_UPSTREAM_HOST="$upstream_host" \
  python3 - <<'PY'
import os
from pathlib import Path

template = Path(os.environ["PRODLIKE_NGINX_TEMPLATE"]).read_text(encoding="utf-8")
rendered = template.replace("__DOOWON_PRODLIKE_API_UPSTREAM_HOST__", os.environ["PRODLIKE_API_UPSTREAM_HOST"])
Path(os.environ["PRODLIKE_NGINX_OUTPUT"]).write_text(rendered, encoding="utf-8")
PY
}

prodlike_use_local_postgres() {
  case "$(prodlike_lower "$DOOWON_PRODLIKE_USE_LOCAL_POSTGRES")" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if [[ "$DOOWON_POSTGRES_DSN" == *"@127.0.0.1:${DOOWON_PRODLIKE_POSTGRES_PORT}/"* ]] || \
         [[ "$DOOWON_POSTGRES_DSN" == *"@localhost:${DOOWON_PRODLIKE_POSTGRES_PORT}/"* ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[prod-like] invalid DOOWON_PRODLIKE_USE_LOCAL_POSTGRES: $DOOWON_PRODLIKE_USE_LOCAL_POSTGRES" >&2
      return 1
      ;;
  esac
}

prodlike_use_local_minio() {
  case "$(prodlike_lower "$DOOWON_PRODLIKE_USE_LOCAL_MINIO")" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if [[ "$DOOWON_MINIO_ENDPOINT" == *"127.0.0.1:${DOOWON_PRODLIKE_MINIO_PORT}"* ]] || \
         [[ "$DOOWON_MINIO_ENDPOINT" == *"localhost:${DOOWON_PRODLIKE_MINIO_PORT}"* ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[prod-like] invalid DOOWON_PRODLIKE_USE_LOCAL_MINIO: $DOOWON_PRODLIKE_USE_LOCAL_MINIO" >&2
      return 1
      ;;
  esac
}
