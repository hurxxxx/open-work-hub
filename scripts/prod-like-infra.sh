#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/prod-like-env.sh"
COMMAND="${1:-up}"

cd "$ROOT_DIR"

case "$COMMAND" in
  up|start)
    prodlike_render_nginx_conf
    services=(redis nginx)
    if prodlike_use_local_postgres; then
      services=(postgres "${services[@]}")
    fi
    if prodlike_use_local_minio; then
      services=(minio "${services[@]}")
    fi
    docker compose -f compose.prod-like.yml up -d "${services[@]}"
    ;;
  down|stop)
    docker compose -f compose.prod-like.yml down
    ;;
  logs)
    docker compose -f compose.prod-like.yml logs -f
    ;;
  ps|status)
    docker compose -f compose.prod-like.yml ps
    ;;
  *)
    echo "Usage: $0 {up|down|logs|ps|start|stop|status}" >&2
    exit 1
    ;;
esac
