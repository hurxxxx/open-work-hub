#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="status"
TLS_EXPIRY_BREAK_GLASS=0
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WORKER_UNITS=(
  open-alm-prod-worker.service
  open-alm-prod-worker-realtime.service
  open-alm-prod-worker-long.service
  open-alm-prod-worker-patent.service
  open-alm-prod-worker-ai-graph.service
  open-alm-prod-worker-ppt.service
)
SEARCH_WRITER_UNITS=(
  open-alm-prod-api.service
  open-alm-prod-collab.service
  "${WORKER_UNITS[@]}"
  open-alm-prod-worker-beat.service
)
UNITS=(
  open-alm-privacy-filter.service
  open-alm-prod-infra.service
  "${SEARCH_WRITER_UNITS[@]}"
)

trim_prod_systemd_env_text() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

normalize_prod_systemd_env_value() {
  local value
  value="$(trim_prod_systemd_env_text "${1:-}")"
  case "$value" in
    \"*)
      value="${value#\"}"
      value="${value%%\"*}"
      ;;
    \'*)
      value="${value#\'}"
      value="${value%%\'*}"
      ;;
    *)
      value="${value%%#*}"
      value="$(trim_prod_systemd_env_text "$value")"
      ;;
  esac
  printf '%s' "$value"
}

load_prod_systemd_env_file() {
  local env_file="$ROOT_DIR/.env"
  local line key value
  if [[ ! -f "$env_file" ]]; then
    return 0
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(trim_prod_systemd_env_text "$line")"
    if [[ "$line" == export[[:space:]]* ]]; then
      line="$(trim_prod_systemd_env_text "${line#export}")"
    fi
    if [[ -z "$line" || "$line" == \#* || "$line" != *=* ]]; then
      continue
    fi
    key="${line%%=*}"
    value="${line#*=}"
    key="$(trim_prod_systemd_env_text "$key")"
    if [[ "$key" != OPEN_ALM_PROD_* && "$key" != OPEN_ALM_DRAWIO_PORT ]]; then
      continue
    fi
    value="$(normalize_prod_systemd_env_value "$value")"
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done <"$env_file"
}

load_prod_systemd_env_file

EXPECTED_ROOT="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_ROOT:-/projects/open-alm/prod}")"
EXPECTED_BRANCH="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_BRANCH:-main}")"
SMOKE_ATTEMPTS="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_SMOKE_ATTEMPTS:-30}")"
SMOKE_DELAY_SECONDS="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_SMOKE_DELAY_SECONDS:-2}")"
SMOKE_CELERY_TIMEOUT_SECONDS="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_SMOKE_CELERY_TIMEOUT_SECONDS:-5}")"
SMOKE_WEB_HOST="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_SMOKE_WEB_HOST:-}")"
SMOKE_WORKSPACE_PATH="$(normalize_prod_systemd_env_value "${OPEN_ALM_PROD_SMOKE_WORKSPACE_PATH:-}")"
DRAWIO_PORT="$(normalize_prod_systemd_env_value "${OPEN_ALM_DRAWIO_PORT:-18083}")"

require_prod_checkout_identity() {
  if [[ "${OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS:-0}" == "1" ]]; then
    return
  fi
  if [[ "$ROOT_DIR" != "$EXPECTED_ROOT" ]]; then
    echo "Refusing to manage production systemd units from unexpected checkout: $ROOT_DIR" >&2
    echo "Expected $EXPECTED_ROOT, or set OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS=1 for a deliberate break-glass operation." >&2
    exit 1
  fi
  local branch
  branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
  if [[ "$branch" != "$EXPECTED_BRANCH" ]]; then
    echo "Refusing to manage production systemd units from branch '$branch'; expected '$EXPECTED_BRANCH'." >&2
    echo "Set OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS=1 only for a deliberate rollback/break-glass operation." >&2
    exit 1
  fi
}

require_clean_prod_checkout() {
  require_prod_checkout_identity
  if [[ "${OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS:-0}" == "1" ]]; then
    return
  fi
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "Refusing to manage production systemd units with a dirty worktree." >&2
    git -C "$ROOT_DIR" status --short >&2
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
    "__OPEN_ALM_WORKER_QUEUE_NAMES__": celery_worker_queue_argument(),
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
    *sorted(template_dir.glob("open-alm-prod-*.service.template")),
]
for template in templates:
    if not template.exists():
        continue
    rendered = template.read_text(encoding="utf-8")
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    target = unit_dir / template.name.removesuffix(".template")
    target.write_text(rendered, encoding="utf-8")
PY
  systemctl --user daemon-reload
}

status_units() {
  systemctl --user --no-pager status "${UNITS[@]}"
}

assert_prod_health_payload() {
  HEALTH_JSON="$1" EXPECTED_REVISION="$2" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["HEALTH_JSON"])
if payload.get("environment") != "production":
    print("[prod-systemd] /healthz must report environment=production", file=sys.stderr)
    raise SystemExit(1)
if payload.get("instance_id") != "prod-api":
    print("[prod-systemd] /healthz must report instance_id=prod-api", file=sys.stderr)
    raise SystemExit(1)
if payload.get("runtime_revision") != os.environ["EXPECTED_REVISION"]:
    print("[prod-systemd] /healthz runtime revision is stale", file=sys.stderr)
    raise SystemExit(1)
PY
}

assert_prod_collab_health_payload() {
  HEALTH_JSON="$1" EXPECTED_REVISION="$2" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["HEALTH_JSON"])
if payload.get("environment") != "production":
    print("[prod-systemd] collab /healthz must report environment=production", file=sys.stderr)
    raise SystemExit(1)
if payload.get("instance_id") != "prod-collab":
    print("[prod-systemd] collab /healthz must report instance_id=prod-collab", file=sys.stderr)
    raise SystemExit(1)
if payload.get("runtime_revision") != os.environ["EXPECTED_REVISION"]:
    print("[prod-systemd] collab /healthz runtime revision is stale", file=sys.stderr)
    raise SystemExit(1)
PY
}

assert_prod_bootstrap_payload() {
  BOOTSTRAP_JSON="$1" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["BOOTSTRAP_JSON"])
if payload.get("dev_admin_login_available") is not False:
    print("[prod-systemd] bootstrap-status must disable dev admin login", file=sys.stderr)
    raise SystemExit(1)
PY
}

assert_worker_queues_consumed() {
  local python_path="$ROOT_DIR/apps/worker/src:$ROOT_DIR/apps/api/src"
  local expected_queues protected_queue legacy_queue active_queues_json worker_stats_json
  expected_queues="$(
    PYTHONPATH="$python_path" \
      "$ROOT_DIR/apps/worker/.venv/bin/python" -m open_alm_worker.queue_contract --celery-queues
  )"
  protected_queue="$(
    PYTHONPATH="$python_path" \
      "$ROOT_DIR/apps/worker/.venv/bin/python" -m open_alm_worker.queue_contract \
        --celery-queues --celery-queue-group patent
  )"
  legacy_queue="$(
    PYTHONPATH="$python_path" \
      "$ROOT_DIR/apps/worker/.venv/bin/python" - <<'PY'
from open_alm_worker.queue_contract import LEGACY_PATENT_PRIOR_ART_QUEUE

print(LEGACY_PATENT_PRIOR_ART_QUEUE)
PY
  )"
  active_queues_json="$(
    PYTHONPATH="$python_path" \
      "$ROOT_DIR/apps/worker/.venv/bin/python" -m celery \
        -A open_alm_worker.celery_app:celery_app inspect active_queues \
        --timeout="$SMOKE_CELERY_TIMEOUT_SECONDS" --json
  )"
  worker_stats_json="$(
    PYTHONPATH="$python_path" \
      "$ROOT_DIR/apps/worker/.venv/bin/python" -m celery \
        -A open_alm_worker.celery_app:celery_app inspect stats \
        --timeout="$SMOKE_CELERY_TIMEOUT_SECONDS" --json
  )"
  EXPECTED_QUEUES="$expected_queues" \
  PROTECTED_QUEUE="$protected_queue" \
  LEGACY_QUEUE="$legacy_queue" \
  ACTIVE_QUEUES_JSON="$active_queues_json" \
  WORKER_STATS_JSON="$worker_stats_json" \
  python3 - <<'PY'
import json
import os
import sys

expected = {queue.strip() for queue in os.environ["EXPECTED_QUEUES"].split(",") if queue.strip()}
try:
    payload = json.loads(os.environ["ACTIVE_QUEUES_JSON"])
except json.JSONDecodeError as exc:
    print(f"[prod-systemd] celery active_queues did not return JSON: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

if not isinstance(payload, dict) or not payload:
    print("[prod-systemd] celery active_queues returned no workers", file=sys.stderr)
    raise SystemExit(1)

active: set[str] = set()
owners: dict[str, set[str]] = {}
for worker_name, queues in payload.items():
    if not isinstance(queues, list):
        continue
    for queue in queues:
        if isinstance(queue, dict) and isinstance(queue.get("name"), str):
            active.add(queue["name"])
            owners.setdefault(queue["name"], set()).add(worker_name)

missing = sorted(expected - active)
if missing:
    print(
        "[prod-systemd] worker is not consuming expected queue(s): " + ", ".join(missing),
        file=sys.stderr,
    )
    raise SystemExit(1)

protected_queue = os.environ["PROTECTED_QUEUE"].strip()
legacy_queue = os.environ["LEGACY_QUEUE"].strip()
legacy_owners = owners.get(legacy_queue, set())
if legacy_owners:
    print(
        "[prod-systemd] stale worker is still consuming the legacy patent queue",
        file=sys.stderr,
    )
    raise SystemExit(1)
protected_owners = owners.get(protected_queue, set())
if len(protected_owners) != 1:
    print(
        "[prod-systemd] protected patent queue must have exactly one consumer",
        file=sys.stderr,
    )
    raise SystemExit(1)
protected_owner = next(iter(protected_owners))
if not protected_owner.startswith("open-alm-prod-worker-patent@"):
    print(
        "[prod-systemd] protected patent queue has an unauthorized consumer",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    stats = json.loads(os.environ["WORKER_STATS_JSON"])
except json.JSONDecodeError as exc:
    print(f"[prod-systemd] celery stats did not return JSON: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
worker_stats = stats.get(protected_owner, {}) if isinstance(stats, dict) else {}
pool = worker_stats.get("pool", {}) if isinstance(worker_stats, dict) else {}
if pool.get("max-concurrency") != 1:
    print(
        "[prod-systemd] protected patent worker must run with concurrency 1",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
}

assert_unit_runtime_revisions() {
  local expected_revision="${1:?revision is required}"
  local unit pid
  for unit in "${SEARCH_WRITER_UNITS[@]}"; do
    pid="$(systemctl --user show "$unit" --property MainPID --value)"
    if [[ ! "$pid" =~ ^[1-9][0-9]*$ || ! -r "/proc/$pid/environ" ]]; then
      echo "[prod-systemd] cannot inspect runtime revision for $unit" >&2
      return 1
    fi
    if ! tr '\0' '\n' <"/proc/$pid/environ" |
      grep -Fqx "OPEN_ALM_RUNTIME_REVISION=$expected_revision"; then
      echo "[prod-systemd] stale runtime revision detected for $unit" >&2
      return 1
    fi
  done
}

curl_optional_prod_smoke_path() {
  local path="${1:-}"
  if [[ -z "$path" ]]; then
    return 0
  fi
  if [[ "$path" != /* ]]; then
    echo "OPEN_ALM_PROD_SMOKE_WORKSPACE_PATH must start with '/': $path" >&2
    return 2
  fi
  curl -fsSI "http://127.0.0.1:8000${path}" >/dev/null
}

curl_required_prod_smoke_head() {
  local path="${1:?path is required}"
  if ! curl -fsSI "http://127.0.0.1:8000${path}" >/dev/null; then
    echo "[prod-systemd] required smoke path did not return 2xx: ${path}" >&2
    return 1
  fi
}

fetch_prod_bootstrap_payload() {
  if [[ -n "$SMOKE_WEB_HOST" ]]; then
    curl -fsS -H "Host: $SMOKE_WEB_HOST" \
      http://127.0.0.1:8000/api/v1/auth/bootstrap-status
    return
  fi
  curl -fsS http://127.0.0.1:8000/api/v1/auth/bootstrap-status
}

assert_drawio_container_healthy() {
  local health_status
  health_status="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' \
      open-alm-prod-drawio \
      2>/dev/null
  )" || return $?
  [[ "$health_status" == "healthy" ]]
}

assert_prod_tls_ready() {
  if (( TLS_EXPIRY_BREAK_GLASS )); then
    echo "[prod-systemd] WARNING: one-shot TLS expiry break-glass enabled; checking with a 0-day expiry threshold." >&2
    python3 "$ROOT_DIR/scripts/check_live_tls_expiry.py" --threshold-days=0
    return
  fi
  python3 "$ROOT_DIR/scripts/check_live_tls_expiry.py"
}

smoke_once() {
  local health_json collab_health_json bootstrap_json
  local expected_revision
  local worker_unit
  systemctl --user is-active --quiet open-alm-privacy-filter.service || return $?
  systemctl --user is-active --quiet open-alm-prod-api.service || return $?
  systemctl --user is-active --quiet open-alm-prod-collab.service || return $?
  for worker_unit in "${WORKER_UNITS[@]}"; do
    systemctl --user is-active --quiet "$worker_unit" || return $?
  done
  systemctl --user is-active --quiet open-alm-prod-worker-beat.service || return $?
  expected_revision="$(git -C "$ROOT_DIR" rev-parse HEAD)" || return $?
  assert_unit_runtime_revisions "$expected_revision" || return $?
  curl -fsS http://127.0.0.1:18081/healthz >/dev/null || return $?
  health_json="$(curl -fsS http://127.0.0.1:8000/healthz)" || return $?
  assert_prod_health_payload "$health_json" "$expected_revision" || return $?
  curl -fsS http://127.0.0.1:8000/readyz >/dev/null || return $?
  collab_health_json="$(curl -fsS http://127.0.0.1:8009/healthz)" || return $?
  assert_prod_collab_health_payload "$collab_health_json" "$expected_revision" || return $?
  curl -fsS http://127.0.0.1:8009/readyz >/dev/null || return $?
  assert_drawio_container_healthy || return $?
  curl -fsS "http://127.0.0.1:${DRAWIO_PORT}/" >/dev/null || return $?
  curl_required_prod_smoke_head / || return $?
  curl_optional_prod_smoke_path "$SMOKE_WORKSPACE_PATH" || return $?
  bootstrap_json="$(fetch_prod_bootstrap_payload)" || return $?
  assert_prod_bootstrap_payload "$bootstrap_json" || return $?
  assert_worker_queues_consumed || return $?
}

smoke() {
  local attempt=1
  assert_prod_tls_ready || return $?
  while true; do
    if smoke_once; then
      echo "[prod-systemd] smoke ok"
      return 0
    fi

    if (( attempt >= SMOKE_ATTEMPTS )); then
      echo "[prod-systemd] smoke failed after $SMOKE_ATTEMPTS attempt(s)" >&2
      return 1
    fi

    echo "[prod-systemd] smoke not ready (attempt $attempt/$SMOKE_ATTEMPTS); retrying in ${SMOKE_DELAY_SECONDS}s" >&2
    sleep "$SMOKE_DELAY_SECONDS"
    attempt=$((attempt + 1))
  done
}

dump_stacks() {
  local unit
  for unit in open-alm-prod-api.service open-alm-prod-collab.service; do
    echo "[prod-systemd] requesting Python stack dump from $unit via SIGUSR1" >&2
    systemctl --user kill --kill-who=main --signal=SIGUSR1 "$unit"
  done
}

rollback_patent_queue() {
  OPEN_ALM_API_AUTO_MIGRATE=0 \
    "$ROOT_DIR/apps/api/.venv/bin/python" \
    "$ROOT_DIR/apps/api/scripts/rollback_patent_prior_art_queue.py"
}

rollback_patent_worker() {
  local unit="open-alm-prod-worker-patent.service"
  local writer
  systemctl --user stop "${SEARCH_WRITER_UNITS[@]}"
  for writer in "${SEARCH_WRITER_UNITS[@]}"; do
    if systemctl --user is-active --quiet "$writer"; then
      echo "[prod-systemd] rollback requires inactive search writer: $writer" >&2
      return 1
    fi
  done
  rollback_patent_queue
  systemctl --user disable "$unit"
  rm -f "$UNIT_DIR/$unit"
  systemctl --user daemon-reload
  systemctl --user reset-failed "$unit" >/dev/null 2>&1 || true
}

usage() {
  echo "Usage: $0 {install|render|start|stop|restart|quiesce-search-writers|resume-search-writers|status|log|smoke [--tls-expiry-break-glass]|dump-stacks|rollback-patent-worker}" >&2
}

parse_command_args() {
  COMMAND="${1:-status}"
  if (($#)); then
    shift
  fi
  TLS_EXPIRY_BREAK_GLASS=0
  while (($#)); do
    case "$1" in
      --tls-expiry-break-glass)
        TLS_EXPIRY_BREAK_GLASS=1
        ;;
      *)
        usage
        return 2
        ;;
    esac
    shift
  done
  if (( TLS_EXPIRY_BREAK_GLASS )) && [[ "$COMMAND" != "smoke" ]]; then
    echo "--tls-expiry-break-glass is supported only with the smoke command." >&2
    usage
    return 2
  fi
}

main() {
  parse_command_args "$@" || return $?
  case "$COMMAND" in
    install)
      require_clean_prod_checkout
      render_units
      systemctl --user enable "${UNITS[@]}"
      ;;
    render)
      require_clean_prod_checkout
      render_units
      ;;
    start)
      require_clean_prod_checkout
      systemctl --user start "${UNITS[@]}"
      ;;
    stop)
      require_prod_checkout_identity
      systemctl --user stop "${UNITS[@]}"
      ;;
    quiesce-search-writers)
      require_prod_checkout_identity
      systemctl --user stop "${SEARCH_WRITER_UNITS[@]}"
      ;;
    resume-search-writers)
      require_clean_prod_checkout
      systemctl --user start "${SEARCH_WRITER_UNITS[@]}"
      ;;
    restart)
      require_clean_prod_checkout
      render_units
      systemctl --user restart "${UNITS[@]}"
      ;;
    status)
      require_prod_checkout_identity
      status_units
      ;;
    log|logs)
      require_prod_checkout_identity
      journalctl --user -fu "${UNITS[@]}"
      ;;
    smoke)
      require_prod_checkout_identity
      smoke
      ;;
    dump-stacks)
      require_prod_checkout_identity
      dump_stacks
      ;;
    rollback-patent-worker)
      require_prod_checkout_identity
      rollback_patent_worker
      ;;
    *)
      usage
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
