#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/dev-env.sh"

if [[ -n "${HOME:-}" && -d "$HOME/.local/bin" ]]; then
  case ":${PATH:-}:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:${PATH:-}" ;;
  esac
fi

if [[ "$(basename "$ROOT_DIR")" == "prod" && "${OPEN_WORK_HUB_ALLOW_PROD_DEV_SH:-0}" != "1" ]]; then
  echo "Refusing to run dev.sh from the production checkout." >&2
  echo "Use ./prod.sh for production, or set OPEN_WORK_HUB_ALLOW_PROD_DEV_SH=1 explicitly for one-off diagnostics." >&2
  exit 1
fi

# The Nx daemon is unstable in this environment; use direct Nx execution.
export NX_DAEMON=false
# dev-env.sh already loads the checkout .env. Letting Nx load .env.local again
# can make the API process disagree with scripts/dev-smoke.sh.
export NX_LOAD_DOT_ENV_FILES=false
WEB_DEV_PORT="${OPEN_WORK_HUB_WEB_DEV_PORT:-4200}"
API_DEV_PORT="${OPEN_WORK_HUB_API_DEV_PORT:-8001}"
export OPEN_WORK_HUB_WEB_DEV_PORT="$WEB_DEV_PORT"
export OPEN_WORK_HUB_WEB_API_PROXY_TARGET="${OPEN_WORK_HUB_WEB_API_PROXY_TARGET:-http://127.0.0.1:${API_DEV_PORT}}"

usage() {
  cat <<'EOF'
Usage: ./dev.sh [options]

Options:
  --with-worker  Start the Celery worker in addition to web and api.
  --web-only     Start only the frontend dev server.
  --api-only     Start only the FastAPI dev server.
  --no-infra     Skip starting the dev docker infra (redis, etc).
  --minimal-infra
                 Start only PostgreSQL and Redis and disable optional startup dependencies.
  --status       Show repo-managed dev server status for the selected projects and exit.
  --stop         Stop repo-managed dev servers for the selected projects and exit.
  --restart      Stop repo-managed dev servers for the selected projects, then start them again.
  --reset-nx     Reset the Nx daemon before starting servers.
  --plain-logs   Use raw Nx stream logs instead of the default readable local format.
  -h, --help     Show this help message.

Defaults:
  - Starts `web` and `api`
  - Boots the dev docker infra (redis/search/vector; postgres/minio when OPEN_WORK_HUB_INFRA_USE_LOCAL_* is on)
    so features like the docs collab relay can reach redis at 127.0.0.1:56380
  - `--minimal-infra` is intended for authentication and core UI smoke tests;
    storage, AI, search, video, and RAG-dependent features remain unavailable
  - Uses `dynamic-legacy` Nx output for readable local logs
  - Stops all child servers when you press Ctrl+C or close the session
    (docker infra keeps running across sessions; stop it with `scripts/infra-stack.sh dev stop`)
  - Stop only the minimal containers with `pnpm dev:infra:minimal:down`
EOF
}

declare -a projects=("web" "api")
with_worker=0
status_only=0
stop_only=0
restart=0
reset_nx=0
infra_enabled=1
minimal_infra=0
output_style="dynamic-legacy"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-worker)
      with_worker=1
      ;;
    --web-only)
      projects=("web")
      ;;
    --api-only)
      projects=("api")
      ;;
    --no-infra)
      infra_enabled=0
      ;;
    --minimal-infra)
      minimal_infra=1
      ;;
    --status)
      status_only=1
      ;;
    --stop)
      stop_only=1
      ;;
    --restart)
      restart=1
      ;;
    --reset-nx)
      reset_nx=1
      ;;
    --plain-logs)
      output_style="stream"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if (( minimal_infra )); then
  export OPEN_WORK_HUB_INFRA_USE_LOCAL_POSTGRES=1
  export OPEN_WORK_HUB_INFRA_USE_LOCAL_MINIO=0
  export OPEN_WORK_HUB_POSTGRES_DSN="postgresql+psycopg://${OPEN_WORK_HUB_INFRA_POSTGRES_USER}:${OPEN_WORK_HUB_INFRA_POSTGRES_PASSWORD}@127.0.0.1:${OPEN_WORK_HUB_INFRA_POSTGRES_PORT}/${OPEN_WORK_HUB_INFRA_POSTGRES_DB}"
  export OPEN_WORK_HUB_API_OBJECT_STORAGE_REQUIRED=0
  export OPEN_WORK_HUB_API_SEED_DEV_LOGIN_ACCOUNT=1
  export OPEN_WORK_HUB_API_VIDEO_CHAT_ENABLED=false
  export OPEN_WORK_HUB_LLM_HEALTHCHECK_ON_STARTUP=false
  export OPEN_WORK_HUB_LLM_REQUIRED=false
  export OPEN_WORK_HUB_OPF_ENABLED=false
  export OPEN_WORK_HUB_OPF_HEALTHCHECK_ON_STARTUP=false
  export OPEN_WORK_HUB_OPF_REQUIRED=false
  export OPEN_WORK_HUB_RAG_ENABLED=false
  export OPEN_WORK_HUB_RAG_PRELOAD_ON_STARTUP=false
  export OPEN_WORK_HUB_HERMES_ENABLED=false
  export OPEN_WORK_HUB_API_RECORDING_SPOOL_DIR="$OPEN_WORK_HUB_DEV_RUNTIME_DIR/recording-spool"
fi

if (( with_worker )); then
  projects+=("worker")
fi

project_csv="$(IFS=,; echo "${projects[*]}")"
parallelism="${#projects[@]}"

find_listener() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tail -n +2 || true
}

show_project_status() {
  local project="$1"
  local listeners=""
  local process_lines=""

  case "$project" in
    web)
      listeners="$(find_listener "$WEB_DEV_PORT")"
      if [[ -n "$listeners" ]]; then
        echo "web    running  http://localhost:${WEB_DEV_PORT}"
        echo "$listeners"
      else
        echo "web    stopped"
      fi
      ;;
    api)
      listeners="$(find_listener "$API_DEV_PORT")"
      if [[ -n "$listeners" ]]; then
        echo "api    running  http://127.0.0.1:${API_DEV_PORT}/docs"
        echo "$listeners"
      else
        echo "api    stopped"
      fi
      ;;
    worker)
      process_lines="$(pgrep -af "celery -A open_work_hub_worker.celery_app:celery_app worker" || true)"
      if [[ -n "$process_lines" ]]; then
        echo "worker running"
        echo "$process_lines"
      else
        echo "worker stopped"
      fi
      ;;
  esac
}

project_selected() {
  local needle="$1"
  local project
  for project in "${projects[@]}"; do
    if [[ "$project" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

require_free_port() {
  local port="$1"
  local label="$2"
  local listeners
  listeners="$(find_listener "$port")"

  if [[ -n "$listeners" ]]; then
    echo "Cannot start ${label}: port ${port} is already in use." >&2
    echo >&2
    echo "$listeners" >&2
    echo >&2
    echo "Stop the existing process before running ./dev.sh again; no fallback port will be selected." >&2
    exit 1
  fi
}

run_api_migration_preflight() {
  if [[ "${OPEN_WORK_HUB_DEV_API_MIGRATION_PREFLIGHT:-1}" == "0" ]]; then
    return 0
  fi

  local auto_migrate
  auto_migrate="$(printf '%s' "${OPEN_WORK_HUB_API_AUTO_MIGRATE:-1}" | tr '[:upper:]' '[:lower:]')"
  case "$auto_migrate" in
    1|true|yes) ;;
    *) return 0 ;;
  esac

  echo "Checking API migrations before starting dev server..."
  (
    cd "$ROOT_DIR/apps/api"
    OPEN_WORK_HUB_API_AUTO_MIGRATE=0 uv run --python 3.12 alembic upgrade head
  )
  export OPEN_WORK_HUB_API_AUTO_MIGRATE=0
}

kill_if_running() {
  local pid="$1"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

start_dev_infra() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker CLI not found; skipping dev infra startup." >&2
    return 0
  fi
  if ! dev_docker_available; then
    echo "Docker daemon not reachable; skipping dev infra startup." >&2
    return 0
  fi

  local desired=()
  if (( minimal_infra )); then
    desired=(postgres redis)
  else
    desired=(redis opensearch qdrant)
    if [[ "$(printf '%s' "${OPEN_WORK_HUB_API_VIDEO_CHAT_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')" != "false" ]]; then
      desired+=(livekit)
    fi
    if [[ "$(dev_lower "${OPEN_WORK_HUB_HERMES_ENABLED:-false}")" == "true" ]]; then
      if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
        echo "OPENROUTER_API_KEY is required when Hermes is enabled." >&2
        exit 1
      fi
      desired+=(hermes-bootstrap hermes-gateway hermes-dashboard)
    fi
    if dev_use_local_postgres; then
      desired+=(postgres)
    fi
    if dev_use_local_minio; then
      desired+=(minio)
    fi
  fi

  # Stop dev-nginx only when it is configured to collide with the web dev server.
  local dev_nginx_container="${OPEN_WORK_HUB_INFRA_CONTAINER_PREFIX:-open-work-hub-dev}-nginx"
  local dev_nginx_port="${OPEN_WORK_HUB_INFRA_NGINX_PORT:-14200}"
  local web_in_projects=0
  local project
  for project in "${projects[@]}"; do
    if [[ "$project" == "web" ]]; then
      web_in_projects=1
      break
    fi
  done
  if (( web_in_projects )) && [[ "$dev_nginx_port" == "$WEB_DEV_PORT" ]]; then
    if dev_docker inspect "$dev_nginx_container" >/dev/null 2>&1; then
      echo "Neutralizing ${dev_nginx_container} (conflicts with web dev server on ${WEB_DEV_PORT})..."
      dev_docker update --restart=no "$dev_nginx_container" >/dev/null 2>&1 || true
      dev_docker stop "$dev_nginx_container" >/dev/null 2>&1 || true
    fi
  fi

  # If a service's host port is already bound (e.g., a sibling repo's compose
  # project started redis under the same fixed container name), reuse it
  # instead of colliding on `docker compose up`.
  local redis_port="${OPEN_WORK_HUB_INFRA_REDIS_PORT:-56380}"
  local postgres_port="${OPEN_WORK_HUB_INFRA_POSTGRES_PORT:-55433}"
  local minio_port="${OPEN_WORK_HUB_INFRA_MINIO_PORT:-59010}"
  local opensearch_port="${OPEN_WORK_HUB_INFRA_OPENSEARCH_PORT:-59210}"
  local qdrant_port="${OPEN_WORK_HUB_INFRA_QDRANT_PORT:-16333}"
  local livekit_port="${OPEN_WORK_HUB_LIVEKIT_PORT:-7880}"
  local hermes_runtime_port="${OPEN_WORK_HUB_HERMES_RUNTIME_PORT:-18642}"
  local hermes_management_port="${OPEN_WORK_HUB_HERMES_MANAGEMENT_PORT:-19119}"
  local services=()
  local skipped=()
  local svc
  for svc in "${desired[@]}"; do
    local port=""
    case "$svc" in
      redis) port="$redis_port" ;;
      postgres) port="$postgres_port" ;;
      minio) port="$minio_port" ;;
      opensearch) port="$opensearch_port" ;;
      qdrant) port="$qdrant_port" ;;
      livekit) port="$livekit_port" ;;
      hermes-bootstrap|hermes-gateway) port="$hermes_runtime_port" ;;
      hermes-dashboard) port="$hermes_management_port" ;;
    esac
    if [[ -n "$port" && -n "$(find_listener "$port")" ]]; then
      skipped+=("${svc}(:${port})")
    else
      services+=("$svc")
    fi
  done

  if (( ${#skipped[@]} > 0 )); then
    echo "Reusing already-running infra: ${skipped[*]}"
  fi

  if (( ${#services[@]} == 0 )); then
    return 0
  fi

  echo "Starting dev infra: ${services[*]}"
  local compose_file
  local compose_env_file
  compose_file="$(dev_compose_file)"
  compose_env_file="$(dev_compose_env_file)"
  if ! dev_docker compose --env-file "$compose_env_file" -f "$compose_file" up -d "${services[@]}"; then
    echo "Failed to start dev infra via docker compose." >&2
    exit 1
  fi

  # PING-verify redis only if we just started it via this compose project.
  # If we're reusing an existing redis, the port-listener check above already
  # confirmed it's bound; `compose exec redis` would not address it anyway.
  local started_redis=0
  local started_postgres=0
  for svc in "${services[@]}"; do
    [[ "$svc" == "redis" ]] && started_redis=1
    [[ "$svc" == "postgres" ]] && started_postgres=1
  done
  if (( started_redis )); then
    local attempts=0
    while (( attempts < 30 )); do
      if dev_docker compose --env-file "$compose_env_file" -f "$compose_file" exec -T redis redis-cli ping >/dev/null 2>&1; then
        break
      fi
      attempts=$((attempts + 1))
      sleep 0.3
    done
    if (( attempts == 30 )); then
      echo "Warning: redis did not respond to PING within ~9s; continuing anyway." >&2
    fi
  fi
  if (( started_postgres )); then
    local attempts=0
    while (( attempts < 60 )); do
      if dev_docker compose --env-file "$compose_env_file" -f "$compose_file" exec -T postgres \
        pg_isready -U "$OPEN_WORK_HUB_INFRA_POSTGRES_USER" -d "$OPEN_WORK_HUB_INFRA_POSTGRES_DB" >/dev/null 2>&1; then
        break
      fi
      attempts=$((attempts + 1))
      sleep 0.5
    done
    if (( attempts == 60 )); then
      echo "PostgreSQL did not become ready within 30s." >&2
      exit 1
    fi
  fi
}

stop_project_processes() {
  local project="$1"
  local stopped=0

  case "$project" in
    web)
      local web_pid
      web_pid="$(lsof -tiTCP:"$WEB_DEV_PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
      if [[ -n "$web_pid" ]]; then
        kill_if_running "$web_pid"
        stopped=1
      fi
      ;;
    api)
      local api_pid
      api_pid="$(lsof -tiTCP:"$API_DEV_PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
      if [[ -n "$api_pid" ]]; then
        kill_if_running "$api_pid"
        stopped=1
      fi
      ;;
    worker)
      pgrep -af "celery -A open_work_hub_worker.celery_app:celery_app" 2>/dev/null | while read -r pid args; do
        if [[ "$args" == *"$ROOT_DIR/apps/worker"* ]]; then
          kill_if_running "$pid"
          stopped=1
        fi
      done
      ;;
  esac

  if (( stopped )); then
    sleep 1
  fi
}

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "Ignoring active virtualenv: ${VIRTUAL_ENV}"
  echo "This repo uses project-local environments via uv; dev.sh will unset VIRTUAL_ENV."
  unset VIRTUAL_ENV
fi

unset PYTHONHOME

if (( stop_only || restart || reset_nx )); then
  for project in "${projects[@]}"; do
    stop_project_processes "$project"
  done
fi

if (( reset_nx )); then
  pnpm exec nx reset >/dev/null
fi

if (( stop_only )); then
  echo "Stopped repo-managed dev servers for: ${project_csv}"
  exit 0
fi

if (( status_only )); then
  echo "Open Work Hub dev server status"
  echo "  projects : ${project_csv}"
  echo
  for project in "${projects[@]}"; do
    show_project_status "$project"
    echo
  done
  exit 0
fi

if (( infra_enabled )); then
  start_dev_infra
fi

# The provider credential belongs to the isolated Hermes containers. API,
# worker, web, and migration subprocesses only receive Hermes control tokens.
unset OPENROUTER_API_KEY

for project in "${projects[@]}"; do
  case "$project" in
    web)
      require_free_port "$WEB_DEV_PORT" "web dev server"
      ;;
    api)
      require_free_port "$API_DEV_PORT" "api dev server"
      ;;
  esac
done

if project_selected api; then
  run_api_migration_preflight
fi

cat <<EOF
Starting Open Work Hub development servers
  projects : ${project_csv}
  web      : http://localhost:${WEB_DEV_PORT}
  api      : http://127.0.0.1:${API_DEV_PORT}/docs

Press Ctrl+C to stop all running servers.
EOF

cleanup() {
  trap - INT TERM EXIT

  for project in "${projects[@]}"; do
    stop_project_processes "$project"
  done
}

handle_interrupt() {
  cleanup
  exit 130
}

trap handle_interrupt INT TERM
trap cleanup EXIT

pnpm exec nx run-many -t dev --projects="$project_csv" --parallel="$parallelism" --outputStyle="$output_style"
