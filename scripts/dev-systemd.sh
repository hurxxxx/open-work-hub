#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="${1:-status}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WORKER_UNITS=(
  open-alm-dev-worker.service
  open-alm-dev-worker-realtime.service
  open-alm-dev-worker-long.service
  open-alm-dev-worker-patent.service
  open-alm-dev-worker-ai-graph.service
  open-alm-dev-worker-ppt.service
  open-alm-dev-worker-beat.service
)
UNITS=(
  open-alm-privacy-filter.service
  open-alm-dev-app.service
  "${WORKER_UNITS[@]}"
)
SEARCH_WRITER_UNITS=(
  open-alm-dev-app.service
  "${WORKER_UNITS[@]}"
)

require_non_prod_checkout() {
  if [[ "$(basename "$ROOT_DIR")" == "prod" && "${OPEN_ALM_ALLOW_PROD_CHECKOUT_DEV_COMMANDS:-0}" != "1" ]]; then
    echo "Refusing to manage development systemd units from the production checkout." >&2
    exit 1
  fi
}

render_units() {
  mkdir -p "$UNIT_DIR" "$ROOT_DIR/.runtime"
  ROOT_DIR="$ROOT_DIR" UNIT_DIR="$UNIT_DIR" python3 - <<'PY'
import os
import subprocess
import sys
from pathlib import Path

root = Path(os.environ["ROOT_DIR"]).resolve()
unit_dir = Path(os.environ["UNIT_DIR"])
template_dir = root / "ops" / "systemd" / "user"
sys.path.insert(0, str(root / "apps" / "worker" / "src"))
from open_alm_worker.queue_contract import (
    celery_worker_group_concurrency,
    celery_worker_queue_argument,
)

runtime_revision = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    text=True,
).strip()
replacements = {
    "__OPEN_ALM_ROOT__": str(root),
    "__OPEN_ALM_API_PYTHON__": str(root / "apps" / "api" / ".venv" / "bin" / "python"),
    "__OPEN_ALM_WORKER_DEFAULT_QUEUE_NAMES__": celery_worker_queue_argument("default"),
    "__OPEN_ALM_WORKER_DEFAULT_CONCURRENCY__": str(celery_worker_group_concurrency("default")),
    "__OPEN_ALM_WORKER_REALTIME_QUEUE_NAMES__": celery_worker_queue_argument("realtime"),
    "__OPEN_ALM_WORKER_REALTIME_CONCURRENCY__": str(celery_worker_group_concurrency("realtime")),
    "__OPEN_ALM_WORKER_LONG_QUEUE_NAMES__": celery_worker_queue_argument("long"),
    "__OPEN_ALM_WORKER_LONG_CONCURRENCY__": str(celery_worker_group_concurrency("long")),
    "__OPEN_ALM_WORKER_PATENT_QUEUE_NAMES__": celery_worker_queue_argument("patent"),
    "__OPEN_ALM_WORKER_PATENT_CONCURRENCY__": str(celery_worker_group_concurrency("patent")),
    "__OPEN_ALM_WORKER_AI_GRAPH_QUEUE_NAMES__": celery_worker_queue_argument("ai_graph"),
    "__OPEN_ALM_WORKER_AI_GRAPH_CONCURRENCY__": str(celery_worker_group_concurrency("ai_graph")),
    "__OPEN_ALM_WORKER_PPT_QUEUE_NAMES__": celery_worker_queue_argument("ppt"),
    "__OPEN_ALM_WORKER_PPT_CONCURRENCY__": str(celery_worker_group_concurrency("ppt")),
    "__OPEN_ALM_RUNTIME_REVISION__": runtime_revision,
}
templates = [
    template_dir / "open-alm-privacy-filter.service.template",
    template_dir / "open-alm-dev-app.service.template",
    template_dir / "open-alm-dev-worker.service.template",
    template_dir / "open-alm-dev-worker-realtime.service.template",
    template_dir / "open-alm-dev-worker-long.service.template",
    template_dir / "open-alm-dev-worker-patent.service.template",
    template_dir / "open-alm-dev-worker-ai-graph.service.template",
    template_dir / "open-alm-dev-worker-ppt.service.template",
    template_dir / "open-alm-dev-worker-beat.service.template",
]
for template in templates:
    rendered = template.read_text(encoding="utf-8")
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    (unit_dir / template.name.removesuffix(".template")).write_text(
        rendered,
        encoding="utf-8",
    )
PY
  systemctl --user daemon-reload
}

rollback_patent_queue() {
  (
    cd "$ROOT_DIR/apps/api"
    OPEN_ALM_API_AUTO_MIGRATE=0 \
      uv run --frozen --python 3.12 python scripts/rollback_patent_prior_art_queue.py
  )
}

quiesce_search_writers() {
  local writer
  systemctl --user stop "${SEARCH_WRITER_UNITS[@]}"
  for writer in "${SEARCH_WRITER_UNITS[@]}"; do
    if systemctl --user is-active --quiet "$writer"; then
      echo "[dev-systemd] queue cutover requires inactive search writer: $writer" >&2
      return 1
    fi
  done
}

run_api_command() {
  (
    cd "$ROOT_DIR/apps/api"
    OPEN_ALM_API_AUTO_MIGRATE=0 uv run --frozen --python 3.12 "$@"
  )
}

activate_dev_runtime() {
  local systemctl_action="$1"
  render_units
  quiesce_search_writers
  run_api_command alembic upgrade head
  run_api_command python "$ROOT_DIR/scripts/check-alembic-state.py"
  run_api_command python scripts/reconcile_patent_prior_art_queue.py
  systemctl --user "$systemctl_action" "${UNITS[@]}"
}

rollback_patent_worker() {
  local unit="open-alm-dev-worker-patent.service"
  quiesce_search_writers
  rollback_patent_queue
  systemctl --user disable "$unit"
  rm -f "$UNIT_DIR/$unit"
  systemctl --user daemon-reload
  systemctl --user reset-failed "$unit" >/dev/null 2>&1 || true
}

case "$COMMAND" in
  install)
    require_non_prod_checkout
    render_units
    systemctl --user enable "${UNITS[@]}"
    ;;
  render)
    require_non_prod_checkout
    render_units
    ;;
  start)
    require_non_prod_checkout
    activate_dev_runtime start
    ;;
  stop)
    require_non_prod_checkout
    systemctl --user stop "${UNITS[@]}"
    ;;
  restart)
    require_non_prod_checkout
    activate_dev_runtime restart
    ;;
  status)
    require_non_prod_checkout
    systemctl --user --no-pager status "${UNITS[@]}"
    ;;
  log|logs)
    require_non_prod_checkout
    journalctl --user -fu "${UNITS[@]}"
    ;;
  rollback-patent-worker)
    require_non_prod_checkout
    rollback_patent_worker
    ;;
  *)
    echo "Usage: $0 {install|render|start|stop|restart|status|log|rollback-patent-worker}" >&2
    exit 2
    ;;
esac
