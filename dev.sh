#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# The Nx daemon is unstable in this environment; use direct Nx execution.
export NX_DAEMON=false

usage() {
  cat <<'EOF'
Usage: ./dev.sh [options]

Options:
  --with-worker  Start the Celery worker in addition to web and api.
  --web-only     Start only the frontend dev server.
  --api-only     Start only the FastAPI dev server.
  --no-infra     Skip starting the dev docker infra (redis, etc).
  --status       Show repo-managed dev server status for the selected projects and exit.
  --stop         Stop repo-managed dev servers for the selected projects and exit.
  --restart      Stop repo-managed dev servers for the selected projects, then start them again.
  --reset-nx     Reset the Nx daemon before starting servers.
  --plain-logs   Use raw Nx stream logs instead of the default readable local format.
  -h, --help     Show this help message.

Defaults:
  - Starts `web` and `api`
  - Boots the dev docker infra (redis; postgres/minio when DOOWON_DEV_USE_LOCAL_* is on)
    so features like the docs collab relay can reach redis at 127.0.0.1:56379
  - Uses `dynamic-legacy` Nx output for readable local logs
  - Stops all child servers when you press Ctrl+C or close the session
    (docker infra keeps running across sessions; stop it with `docker compose -f compose.dev.yml stop`)
EOF
}

declare -a projects=("web" "api")
with_worker=0
status_only=0
stop_only=0
restart=0
reset_nx=0
infra_enabled=1
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
      listeners="$(find_listener 4200)"
      if [[ -n "$listeners" ]]; then
        echo "web    running  http://localhost:4200"
        echo "$listeners"
      else
        echo "web    stopped"
      fi
      ;;
    api)
      listeners="$(find_listener 8000)"
      if [[ -n "$listeners" ]]; then
        echo "api    running  http://127.0.0.1:8000/docs"
        echo "$listeners"
      else
        echo "api    stopped"
      fi
      ;;
    worker)
      process_lines="$(pgrep -af "celery -A ai_do_worker.celery_app:celery_app worker" || true)"
      if [[ -n "$process_lines" ]]; then
        echo "worker running"
        echo "$process_lines"
      else
        echo "worker stopped"
      fi
      ;;
  esac
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
    echo "Stop the existing process or change the port before running ./dev.sh again." >&2
    exit 1
  fi
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

  local desired=(redis)
  case "${DOOWON_DEV_USE_LOCAL_POSTGRES:-}" in
    1|true|yes|on) desired+=(postgres) ;;
  esac
  case "${DOOWON_DEV_USE_LOCAL_MINIO:-}" in
    1|true|yes|on) desired+=(minio) ;;
  esac

  # dev-nginx binds to 4200 (IPv6) and collides with the web dev server (IPv4).
  # Since macOS resolves localhost to ::1 first, browsers would hit nginx and 502.
  # Stop it defensively and clear its restart policy so Docker Desktop doesn't
  # bring it back under us.
  local web_in_projects=0
  local project
  for project in "${projects[@]}"; do
    if [[ "$project" == "web" ]]; then
      web_in_projects=1
      break
    fi
  done
  if (( web_in_projects )); then
    if dev_docker inspect doowon-dev-nginx >/dev/null 2>&1; then
      echo "Neutralizing dev-nginx (conflicts with web dev server on 4200)..."
      dev_docker update --restart=no doowon-dev-nginx >/dev/null 2>&1 || true
      dev_docker stop doowon-dev-nginx >/dev/null 2>&1 || true
    fi
  fi

  # If a service's host port is already bound (e.g., a sibling repo's compose
  # project started redis under the same fixed container name), reuse it
  # instead of colliding on `docker compose up`.
  local redis_port="${DOOWON_DEV_REDIS_PORT:-56379}"
  local postgres_port="${DOOWON_DEV_POSTGRES_PORT:-55432}"
  local minio_port="${DOOWON_DEV_MINIO_PORT:-59000}"
  local services=()
  local skipped=()
  local svc
  for svc in "${desired[@]}"; do
    local port=""
    case "$svc" in
      redis) port="$redis_port" ;;
      postgres) port="$postgres_port" ;;
      minio) port="$minio_port" ;;
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
  if ! dev_docker compose -f compose.dev.yml up -d "${services[@]}"; then
    echo "Failed to start dev infra via docker compose." >&2
    exit 1
  fi

  # PING-verify redis only if we just started it via this compose project.
  # If we're reusing an existing redis, the port-listener check above already
  # confirmed it's bound; `compose exec redis` would not address it anyway.
  local started_redis=0
  for svc in "${services[@]}"; do
    [[ "$svc" == "redis" ]] && started_redis=1
  done
  if (( started_redis )); then
    local attempts=0
    while (( attempts < 30 )); do
      if dev_docker compose -f compose.dev.yml exec -T redis redis-cli ping >/dev/null 2>&1; then
        return 0
      fi
      attempts=$((attempts + 1))
      sleep 0.3
    done
    echo "Warning: redis did not respond to PING within ~9s; continuing anyway." >&2
  fi
}

stop_project_processes() {
  local project="$1"
  local stopped=0

  case "$project" in
    web)
      local web_pid
      web_pid="$(lsof -tiTCP:4200 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
      if [[ -n "$web_pid" ]]; then
        kill_if_running "$web_pid"
        stopped=1
      fi
      pkill -TERM -f "pnpm exec nx dev web" 2>/dev/null || true
      pkill -TERM -f "nx.js dev web" 2>/dev/null || true
      ;;
    api)
      pkill -TERM -f "uvicorn ai_do_api.main:app" 2>/dev/null || true
      pkill -TERM -f "pnpm exec nx dev api" 2>/dev/null || true
      stopped=1
      ;;
    worker)
      pkill -TERM -f "celery -A ai_do_worker.celery_app:celery_app worker" 2>/dev/null || true
      pkill -TERM -f "pnpm exec nx dev worker" 2>/dev/null || true
      stopped=1
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
  echo "AI-DO dev server status"
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

for project in "${projects[@]}"; do
  case "$project" in
    web)
      require_free_port 4200 "web dev server"
      ;;
    api)
      require_free_port 8000 "api dev server"
      ;;
  esac
done

cat <<EOF
Starting AI-DO development servers
  projects : ${project_csv}
  web      : http://localhost:4200
  api      : http://127.0.0.1:8000/docs

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
