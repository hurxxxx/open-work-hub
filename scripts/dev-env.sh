#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

dev_python_bin() {
  local python_bin="${ROOT_DIR}/apps/api/.venv/bin/python"
  if [[ -x "$python_bin" ]]; then
    printf '%s\n' "$python_bin"
  else
    command -v python3
  fi
}

dev_load_dotenv() {
  local env_file="${1:?env file is required}"
  [[ -f "$env_file" ]] || return 0

  local python_bin
  python_bin="$(dev_python_bin)"

  eval "$(
    DEV_ENV_FILE="$env_file" "$python_bin" - <<'PY'
import os
import pathlib
import shlex

path = pathlib.Path(os.environ["DEV_ENV_FILE"])
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
    if key == "OPEN_WORK_HUB_ENV_PROFILE" and key in os.environ:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
  )"
}

dev_export_open_work_hub_desktop_installer_defaults() {
  local python_bin
  python_bin="$(dev_python_bin)"

  eval "$(
    ROOT_DIR="$ROOT_DIR" "$python_bin" - <<'PY'
import json
import os
import pathlib
import shlex

root = pathlib.Path(os.environ["ROOT_DIR"])
manifest = json.loads(
    (root / "packages" / "contracts" / "open-work-hub-desktop-update-feed.manifest.json").read_text(
        encoding="utf-8"
    )
)
feed_path_prefix = manifest["feedPathPrefix"]
win_env_name = None
win_default_url = None

for platform in manifest["platformOrder"]:
    config = manifest["platforms"][platform]
    env_name = config["installerUrlEnv"]
    default_url = f'{feed_path_prefix}/{platform}/{config["installerStableCopy"]}'
    if not os.environ.get(env_name):
        print(f"export {env_name}={shlex.quote(default_url)}")
    if platform == "win":
        win_env_name = env_name
        win_default_url = default_url

fallback_url = os.environ.get(str(win_env_name)) if win_env_name else win_default_url
if not fallback_url:
    fallback_url = win_default_url
if fallback_url and not os.environ.get("VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL"):
    print(f"export VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL={shlex.quote(fallback_url)}")
PY
  )"
}

dev_lower() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

if [[ "${OPEN_WORK_HUB_SKIP_DOTENV:-0}" != "1" ]]; then
  dev_load_dotenv "$ROOT_DIR/.env"
fi

export OPEN_WORK_HUB_DEV_API_COUNT="${OPEN_WORK_HUB_DEV_API_COUNT:-1}"
export OPEN_WORK_HUB_DEV_API_HOST="${OPEN_WORK_HUB_DEV_API_HOST:-0.0.0.0}"
export OPEN_WORK_HUB_INFRA_CONTAINER_PREFIX="${OPEN_WORK_HUB_INFRA_CONTAINER_PREFIX:-open-work-hub-dev}"
export OPEN_WORK_HUB_INFRA_BIND_HOST="${OPEN_WORK_HUB_INFRA_BIND_HOST:-0.0.0.0}"
export OPEN_WORK_HUB_INFRA_NGINX_PORT="${OPEN_WORK_HUB_INFRA_NGINX_PORT:-14200}"
export OPEN_WORK_HUB_INFRA_REDIS_PORT="${OPEN_WORK_HUB_INFRA_REDIS_PORT:-56380}"
export OPEN_WORK_HUB_DEV_REDIS_URL="${OPEN_WORK_HUB_DEV_REDIS_URL:-redis://127.0.0.1:${OPEN_WORK_HUB_INFRA_REDIS_PORT}/0}"
export OPEN_WORK_HUB_DEV_REDIS_RESULT_BACKEND="${OPEN_WORK_HUB_DEV_REDIS_RESULT_BACKEND:-redis://127.0.0.1:${OPEN_WORK_HUB_INFRA_REDIS_PORT}/1}"
export OPEN_WORK_HUB_DEV_COLLAB_REDIS_URL="${OPEN_WORK_HUB_DEV_COLLAB_REDIS_URL:-$OPEN_WORK_HUB_DEV_REDIS_URL}"
export OPEN_WORK_HUB_DEV_REALTIME_REDIS_URL="${OPEN_WORK_HUB_DEV_REALTIME_REDIS_URL:-$OPEN_WORK_HUB_DEV_REDIS_URL}"
export OPEN_WORK_HUB_DEV_WORKER_BROKER_URL="${OPEN_WORK_HUB_DEV_WORKER_BROKER_URL:-$OPEN_WORK_HUB_DEV_REDIS_URL}"
export OPEN_WORK_HUB_DEV_WORKER_RESULT_BACKEND="${OPEN_WORK_HUB_DEV_WORKER_RESULT_BACKEND:-$OPEN_WORK_HUB_DEV_REDIS_RESULT_BACKEND}"
export OPEN_WORK_HUB_INFRA_MINIO_PORT="${OPEN_WORK_HUB_INFRA_MINIO_PORT:-59010}"
export OPEN_WORK_HUB_INFRA_MINIO_CONSOLE_PORT="${OPEN_WORK_HUB_INFRA_MINIO_CONSOLE_PORT:-59011}"
export OPEN_WORK_HUB_INFRA_OPENSEARCH_PORT="${OPEN_WORK_HUB_INFRA_OPENSEARCH_PORT:-59210}"
export OPEN_WORK_HUB_INFRA_OPENSEARCH_PERF_PORT="${OPEN_WORK_HUB_INFRA_OPENSEARCH_PERF_PORT:-59610}"
export OPEN_WORK_HUB_INFRA_QDRANT_PORT="${OPEN_WORK_HUB_INFRA_QDRANT_PORT:-16333}"
export OPEN_WORK_HUB_INFRA_QDRANT_GRPC_PORT="${OPEN_WORK_HUB_INFRA_QDRANT_GRPC_PORT:-16334}"
export OPEN_WORK_HUB_LIVEKIT_PORT="${OPEN_WORK_HUB_LIVEKIT_PORT:-7880}"
export OPEN_WORK_HUB_LIVEKIT_RTC_TCP_PORT="${OPEN_WORK_HUB_LIVEKIT_RTC_TCP_PORT:-7881}"
export OPEN_WORK_HUB_LIVEKIT_RTC_PORT_RANGE_START="${OPEN_WORK_HUB_LIVEKIT_RTC_PORT_RANGE_START:-52000}"
export OPEN_WORK_HUB_LIVEKIT_RTC_PORT_RANGE_END="${OPEN_WORK_HUB_LIVEKIT_RTC_PORT_RANGE_END:-52100}"
export OPEN_WORK_HUB_INFRA_USE_LOCAL_MINIO="${OPEN_WORK_HUB_INFRA_USE_LOCAL_MINIO:-auto}"
export OPEN_WORK_HUB_DEV_BASE_URL="${OPEN_WORK_HUB_DEV_BASE_URL:-http://127.0.0.1:${OPEN_WORK_HUB_INFRA_NGINX_PORT}}"
export OPEN_WORK_HUB_DEV_RUNTIME_DIR="${OPEN_WORK_HUB_DEV_RUNTIME_DIR:-$ROOT_DIR/.dev}"
export OPEN_WORK_HUB_DEV_PID_DIR="${OPEN_WORK_HUB_DEV_PID_DIR:-$OPEN_WORK_HUB_DEV_RUNTIME_DIR/pids}"
export OPEN_WORK_HUB_DEV_LOG_DIR="${OPEN_WORK_HUB_DEV_LOG_DIR:-$OPEN_WORK_HUB_DEV_RUNTIME_DIR/logs}"
export OPEN_WORK_HUB_DEV_NGINX_CONF_TEMPLATE_PATH="${OPEN_WORK_HUB_DEV_NGINX_CONF_TEMPLATE_PATH:-$ROOT_DIR/ops/dev/nginx.conf.template}"
export OPEN_WORK_HUB_DEV_NGINX_CONF_PATH="${OPEN_WORK_HUB_DEV_NGINX_CONF_PATH:-$OPEN_WORK_HUB_DEV_RUNTIME_DIR/nginx.conf}"
export OPEN_WORK_HUB_ENV_PROFILE="${OPEN_WORK_HUB_ENV_PROFILE:-dev}"

export OPEN_WORK_HUB_POSTGRES_DSN="${OPEN_WORK_HUB_POSTGRES_DSN:-postgresql+psycopg://open_work_hub_dev:open_work_hub_dev@127.0.0.1:5432/open_work_hub_dev}"
export OPEN_WORK_HUB_API_COLLAB_REDIS_URL="$OPEN_WORK_HUB_DEV_COLLAB_REDIS_URL"
export OPEN_WORK_HUB_API_REALTIME_REDIS_URL="$OPEN_WORK_HUB_DEV_REALTIME_REDIS_URL"
export OPEN_WORK_HUB_WORKER_BROKER_URL="$OPEN_WORK_HUB_DEV_WORKER_BROKER_URL"
export OPEN_WORK_HUB_WORKER_RESULT_BACKEND="$OPEN_WORK_HUB_DEV_WORKER_RESULT_BACKEND"
export OPEN_WORK_HUB_MINIO_ENDPOINT="${OPEN_WORK_HUB_MINIO_ENDPOINT:-http://127.0.0.1:${OPEN_WORK_HUB_INFRA_MINIO_PORT}}"
export OPEN_WORK_HUB_MINIO_ACCESS_KEY="${OPEN_WORK_HUB_MINIO_ACCESS_KEY:-open_work_hub_dev_minio}"
export OPEN_WORK_HUB_MINIO_SECRET_KEY="${OPEN_WORK_HUB_MINIO_SECRET_KEY:-open_work_hub_dev_minio}"
export OPEN_WORK_HUB_MINIO_BUCKET="${OPEN_WORK_HUB_MINIO_BUCKET:-open-work-hub-dev}"
export OPEN_WORK_HUB_OPENSEARCH_URL="${OPEN_WORK_HUB_OPENSEARCH_URL:-http://127.0.0.1:${OPEN_WORK_HUB_INFRA_OPENSEARCH_PORT}}"
export OPEN_WORK_HUB_OPENSEARCH_INDEX_PREFIX="${OPEN_WORK_HUB_OPENSEARCH_INDEX_PREFIX:-open-work-hub-dev}"
export OPEN_WORK_HUB_RAG_QDRANT_URL="${OPEN_WORK_HUB_RAG_QDRANT_URL:-http://127.0.0.1:${OPEN_WORK_HUB_INFRA_QDRANT_PORT}}"
export OPEN_WORK_HUB_RAG_QDRANT_API_KEY="${OPEN_WORK_HUB_RAG_QDRANT_API_KEY:-open_work_hub_dev_qdrant}"
export OPEN_WORK_HUB_RAG_QDRANT_COLLECTION_PREFIX="${OPEN_WORK_HUB_RAG_QDRANT_COLLECTION_PREFIX:-open-work-hub-dev-rag}"
export OPEN_WORK_HUB_LIVEKIT_URL="${OPEN_WORK_HUB_LIVEKIT_URL:-ws://127.0.0.1:${OPEN_WORK_HUB_LIVEKIT_PORT}}"
export OPEN_WORK_HUB_LIVEKIT_PUBLIC_URL="${OPEN_WORK_HUB_LIVEKIT_PUBLIC_URL:-}"
export OPEN_WORK_HUB_LIVEKIT_API_KEY="${OPEN_WORK_HUB_LIVEKIT_API_KEY:-devkey}"
export OPEN_WORK_HUB_LIVEKIT_API_SECRET="${OPEN_WORK_HUB_LIVEKIT_API_SECRET:-devsecret-devsecret-devsecret-0001}"
export OPEN_WORK_HUB_LLM_HEALTHCHECK_ON_STARTUP="${OPEN_WORK_HUB_LLM_HEALTHCHECK_ON_STARTUP:-0}"
export OPEN_WORK_HUB_LLM_REQUIRED="${OPEN_WORK_HUB_LLM_REQUIRED:-0}"
export OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN="${OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN:-1}"
dev_export_open_work_hub_desktop_installer_defaults

dev_docker() {
  case "$OPEN_WORK_HUB_ENV_PROFILE" in
    local|dev|"")
      if docker info >/dev/null 2>&1; then
        docker "$@"
      elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
        sudo -n docker "$@"
      else
        docker "$@"
      fi
      ;;
    prod|production)
      echo "[dev] OPEN_WORK_HUB_ENV_PROFILE=$OPEN_WORK_HUB_ENV_PROFILE is not supported for dev docker commands" >&2
      return 1
      ;;
    *)
      echo "[dev] invalid OPEN_WORK_HUB_ENV_PROFILE: $OPEN_WORK_HUB_ENV_PROFILE (expected local, dev, prod)" >&2
      return 1
      ;;
  esac
}

dev_docker_available() {
  dev_docker info >/dev/null 2>&1
}

dev_compose_file() {
  case "$OPEN_WORK_HUB_ENV_PROFILE" in
    local|dev|"")
      printf '%s/ops/compose/open-work-hub-dev.infra.yml\n' "$ROOT_DIR"
      ;;
    prod|production)
      echo "[dev] OPEN_WORK_HUB_ENV_PROFILE=$OPEN_WORK_HUB_ENV_PROFILE is not supported for dev compose commands" >&2
      return 1
      ;;
    *)
      echo "[dev] invalid OPEN_WORK_HUB_ENV_PROFILE: $OPEN_WORK_HUB_ENV_PROFILE (expected local, dev, prod)" >&2
      return 1
      ;;
  esac
}

dev_api_port() {
  local index="${1:?instance index is required}"
  printf '%s\n' "$((8000 + index))"
}

dev_api_name() {
  local index="${1:?instance index is required}"
  printf 'dev-api-%s\n' "$index"
}

dev_ensure_runtime_dirs() {
  mkdir -p "$OPEN_WORK_HUB_DEV_RUNTIME_DIR" "$OPEN_WORK_HUB_DEV_PID_DIR" "$OPEN_WORK_HUB_DEV_LOG_DIR"
}

dev_detect_api_upstream_host() {
  dev_docker run --rm --add-host=dev-host:host-gateway nginx:1.27-alpine \
    sh -lc "grep -m1 -E '^[0-9]+(\\.[0-9]+){3}[[:space:]]+dev-host([[:space:]]|\$)' /etc/hosts | awk '{print \$1}'"
}

dev_render_nginx_conf() {
  dev_ensure_runtime_dirs
  local upstream_host
  local listen_port
  upstream_host="$(dev_detect_api_upstream_host)"
  listen_port="80"
  if [[ -z "$upstream_host" ]]; then
    echo "[dev] failed to detect Docker host gateway IPv4 for nginx upstream" >&2
    return 1
  fi

  DEV_NGINX_TEMPLATE="$OPEN_WORK_HUB_DEV_NGINX_CONF_TEMPLATE_PATH" \
  DEV_NGINX_OUTPUT="$OPEN_WORK_HUB_DEV_NGINX_CONF_PATH" \
  DEV_API_UPSTREAM_HOST="$upstream_host" \
  DEV_NGINX_LISTEN_PORT="$listen_port" \
  python3 - <<'PY'
import os
from pathlib import Path

template = Path(os.environ["DEV_NGINX_TEMPLATE"]).read_text(encoding="utf-8")
rendered = (
    template
    .replace("__OPEN_WORK_HUB_DEV_API_UPSTREAM_HOST__", os.environ["DEV_API_UPSTREAM_HOST"])
    .replace("__OPEN_WORK_HUB_DEV_NGINX_LISTEN_PORT__", os.environ["DEV_NGINX_LISTEN_PORT"])
)
Path(os.environ["DEV_NGINX_OUTPUT"]).write_text(rendered, encoding="utf-8")
PY
}

dev_use_local_minio() {
  case "$(dev_lower "$OPEN_WORK_HUB_INFRA_USE_LOCAL_MINIO")" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if [[ "$OPEN_WORK_HUB_MINIO_ENDPOINT" == *"127.0.0.1:${OPEN_WORK_HUB_INFRA_MINIO_PORT}"* ]] || \
         [[ "$OPEN_WORK_HUB_MINIO_ENDPOINT" == *"localhost:${OPEN_WORK_HUB_INFRA_MINIO_PORT}"* ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[dev] invalid OPEN_WORK_HUB_INFRA_USE_LOCAL_MINIO: $OPEN_WORK_HUB_INFRA_USE_LOCAL_MINIO" >&2
      return 1
      ;;
  esac
}
