#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND="${1:-status}"
shift || true

usage() {
  cat <<'EOF'
Usage: ./prod.sh {install|render|start|stop|restart|status|log|logs|smoke|infra}

Commands:
  install  Render and enable user-level ai-do-prod-* systemd units.
  render   Re-render user-level ai-do-prod-* systemd units.
  start    Start production systemd units.
  stop     Stop production systemd units.
  restart  Re-render and restart production systemd units.
  status   Show production systemd unit status.
  log      Follow production systemd logs.
  smoke    Run production API smoke checks.
  infra    Run production infra compose command. Defaults to ps.
EOF
}

case "$COMMAND" in
  install|render|start|stop|restart|status|smoke)
    exec "$ROOT_DIR/scripts/prod-systemd.sh" "$COMMAND" "$@"
    ;;
  log|logs)
    exec "$ROOT_DIR/scripts/prod-systemd.sh" log "$@"
    ;;
  infra)
    infra_command="${1:-ps}"
    shift || true
    exec "$ROOT_DIR/scripts/infra-stack.sh" prod "$infra_command" "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
