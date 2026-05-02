#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/dev-env.sh"
COMMAND="${1:-up}"

cd "$ROOT_DIR"
COMPOSE_FILE="$(dev_compose_file)"

case "$COMMAND" in
  up|start)
    dev_render_nginx_conf
    services=(redis nginx)
    if dev_use_local_postgres; then
      services=(postgres "${services[@]}")
    fi
    if dev_use_local_minio; then
      services=(minio "${services[@]}")
    fi
    dev_docker compose -f "$COMPOSE_FILE" up -d "${services[@]}"
    ;;
  down|stop)
    dev_docker compose -f "$COMPOSE_FILE" down
    ;;
  logs)
    dev_docker compose -f "$COMPOSE_FILE" logs -f
    ;;
  ps|status)
    dev_docker compose -f "$COMPOSE_FILE" ps
    ;;
  *)
    echo "Usage: $0 {up|down|logs|ps|start|stop|status}" >&2
    exit 1
    ;;
esac
