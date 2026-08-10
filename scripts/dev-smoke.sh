#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/dev-env.sh"

api_health_payload() {
  local port="${1:?port is required}"
  curl -fsS "http://127.0.0.1:${port}/healthz"
}

api_instance_id_from_health() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)["instance_id"])'
}

bootstrap_field() {
  local field="${1:?field is required}"
  DEV_BOOTSTRAP_FIELD="$field" python3 -c 'import json,os,sys; data=json.load(sys.stdin); print(data[os.environ["DEV_BOOTSTRAP_FIELD"]])'
}

bootstrap_accounts_count() {
  python3 -c 'import json,sys; print(len(json.load(sys.stdin)["dev_login_accounts"]))'
}

DEV_MANAGED_WORKER_UNITS=(
  ai-do-dev-worker.service
  ai-do-dev-worker-realtime.service
  ai-do-dev-worker-long.service
  ai-do-dev-worker-patent.service
  ai-do-dev-worker-ai-graph.service
  ai-do-dev-worker-ppt.service
)
DEV_MANAGED_REVISION_UNITS=(
  ai-do-dev-app.service
  "${DEV_MANAGED_WORKER_UNITS[@]}"
  ai-do-dev-worker-beat.service
)

dev_managed_runtime_check_enabled() {
  case "${AI_DO_DEV_MANAGED_RUNTIME_CHECK:-auto}" in
    1|true|yes|on)
      return 0
      ;;
    0|false|no|off)
      return 1
      ;;
    auto)
      if command -v systemctl >/dev/null 2>&1 &&
        systemctl --user is-active --quiet ai-do-dev-app.service; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "[dev] AI_DO_DEV_MANAGED_RUNTIME_CHECK must be auto, 1, or 0" >&2
      return 2
      ;;
  esac
}

assert_dev_unit_runtime_revisions() {
  local expected_revision="${1:?revision is required}"
  local unit pid
  for unit in "${DEV_MANAGED_REVISION_UNITS[@]}"; do
    if ! systemctl --user is-active --quiet "$unit"; then
      echo "[dev] managed runtime unit is not active: $unit" >&2
      return 1
    fi
    pid="$(systemctl --user show "$unit" --property MainPID --value)"
    if [[ ! "$pid" =~ ^[1-9][0-9]*$ || ! -r "/proc/$pid/environ" ]]; then
      echo "[dev] cannot inspect runtime revision for $unit" >&2
      return 1
    fi
    if ! tr '\0' '\n' <"/proc/$pid/environ" |
      grep -Fqx "AI_DO_RUNTIME_REVISION=$expected_revision"; then
      echo "[dev] stale runtime revision detected for $unit" >&2
      return 1
    fi
  done
}

assert_dev_api_runtime_revisions() {
  local expected_revision="${1:?revision is required}"
  local instance port actual_revision
  for instance in $(seq 1 "$AI_DO_DEV_API_COUNT"); do
    port="$(dev_api_port "$instance")"
    actual_revision="$(
      api_health_payload "$port" |
        python3 -c 'import json,sys; print(json.load(sys.stdin).get("runtime_revision", ""))'
    )"
    if [[ "$actual_revision" != "$expected_revision" ]]; then
      echo "[dev] api on port $port is running a stale runtime revision" >&2
      return 1
    fi
  done
}

assert_dev_worker_queues_consumed() {
  local worker_python="$ROOT_DIR/apps/worker/.venv/bin/python"
  local python_path="$ROOT_DIR/apps/worker/src:$ROOT_DIR/apps/api/src"
  local expected_queues protected_queue legacy_queue legacy_queue_length
  local active_queues_json worker_stats_json
  if [[ ! -x "$worker_python" ]]; then
    echo "[dev] managed worker Python is unavailable: $worker_python" >&2
    return 1
  fi
  expected_queues="$(
    PYTHONPATH="$python_path" \
      "$worker_python" -m ai_do_worker.queue_contract --celery-queues
  )"
  protected_queue="$(
    PYTHONPATH="$python_path" \
      "$worker_python" -m ai_do_worker.queue_contract \
        --celery-queues --celery-queue-group patent
  )"
  legacy_queue="$(
    PYTHONPATH="$python_path" "$worker_python" - <<'PY'
from ai_do_worker.queue_contract import LEGACY_PATENT_PRIOR_ART_QUEUE

print(LEGACY_PATENT_PRIOR_ART_QUEUE)
PY
  )"
  legacy_queue_length="$(
    LEGACY_QUEUE="$legacy_queue" PYTHONPATH="$python_path" \
      "$worker_python" - <<'PY'
import os
import sys

from redis import Redis

from ai_do_worker.settings import get_settings

broker = Redis.from_url(
    get_settings().broker_url,
    socket_connect_timeout=5,
    socket_timeout=5,
)
try:
    print(int(broker.llen(os.environ["LEGACY_QUEUE"])))
except Exception as exc:
    print(
        "[dev] could not inspect the legacy patent queue: "
        f"{type(exc).__name__}",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc
finally:
    broker.close()
PY
  )"
  if [[ "$legacy_queue_length" != "0" ]]; then
    echo "[dev] legacy patent queue still contains $legacy_queue_length message(s)" >&2
    return 1
  fi
  active_queues_json="$(
    PYTHONPATH="$python_path" \
      "$worker_python" -m celery \
        -A ai_do_worker.celery_app:celery_app inspect active_queues \
        --timeout=5 --json
  )"
  worker_stats_json="$(
    PYTHONPATH="$python_path" \
      "$worker_python" -m celery \
        -A ai_do_worker.celery_app:celery_app inspect stats \
        --timeout=5 --json
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
protected_queue = os.environ["PROTECTED_QUEUE"].strip()
expected.add(protected_queue)
legacy_queue = os.environ["LEGACY_QUEUE"].strip()
try:
    payload = json.loads(os.environ["ACTIVE_QUEUES_JSON"])
except json.JSONDecodeError as exc:
    print(f"[dev] celery active_queues did not return JSON: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
if not isinstance(payload, dict) or not payload:
    print("[dev] celery active_queues returned no workers", file=sys.stderr)
    raise SystemExit(1)

active: set[str] = set()
owners: dict[str, set[str]] = {}
for worker_name, queues in payload.items():
    if not isinstance(queues, list):
        continue
    for queue in queues:
        if isinstance(queue, dict) and isinstance(queue.get("name"), str):
            queue_name = queue["name"]
            active.add(queue_name)
            owners.setdefault(queue_name, set()).add(worker_name)

missing = sorted(expected - active)
if missing:
    print(
        "[dev] managed worker is not consuming expected queue(s): " + ", ".join(missing),
        file=sys.stderr,
    )
    raise SystemExit(1)

legacy_owners = owners.get(legacy_queue, set())
if legacy_owners:
    print(
        "[dev] stale worker is still consuming the legacy patent queue",
        file=sys.stderr,
    )
    raise SystemExit(1)

protected_owners = owners.get(protected_queue, set())
if len(protected_owners) != 1:
    print("[dev] protected patent queue must have exactly one consumer", file=sys.stderr)
    raise SystemExit(1)
protected_owner = next(iter(protected_owners))
if not protected_owner.startswith("ai-do-dev-worker-patent@"):
    print("[dev] protected patent queue has an unauthorized consumer", file=sys.stderr)
    raise SystemExit(1)

try:
    stats = json.loads(os.environ["WORKER_STATS_JSON"])
except json.JSONDecodeError as exc:
    print(f"[dev] celery stats did not return JSON: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
worker_stats = stats.get(protected_owner, {}) if isinstance(stats, dict) else {}
pool = worker_stats.get("pool", {}) if isinstance(worker_stats, dict) else {}
if pool.get("max-concurrency") != 1:
    print("[dev] protected patent worker must run with concurrency 1", file=sys.stderr)
    raise SystemExit(1)
PY
}

run_managed_dev_runtime_checks() {
  local expected_revision
  expected_revision="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  echo "[dev] checking managed worker revisions and queue ownership"
  assert_dev_unit_runtime_revisions "$expected_revision"
  assert_dev_api_runtime_revisions "$expected_revision"
  assert_dev_worker_queues_consumed
}

main() {
  local instance port expected_id actual_id
  local web_shell_base_url bootstrap_json dev_admin_login_available
  local dev_login_accounts_count seen_ids seen_count managed_check_status

  echo "[dev] checking api instances"
  for instance in $(seq 1 "$AI_DO_DEV_API_COUNT"); do
    port="$(dev_api_port "$instance")"
    expected_id="$(dev_api_name "$instance")"
    if [[ "$AI_DO_DEV_API_COUNT" == "1" ]]; then
      expected_id="${AI_DO_API_INSTANCE_ID:-dev-api}"
    fi
    actual_id="$(api_health_payload "$port" | api_instance_id_from_health)"
    if [[ "$actual_id" != "$expected_id" ]]; then
      echo "[dev] unexpected instance id on port ${port}: expected ${expected_id}, got ${actual_id}" >&2
      return 1
    fi
  done

  web_shell_base_url="${AI_DO_DEV_WEB_BASE_URL:-http://127.0.0.1:${AI_DO_WEB_DEV_PORT:-4200}}"
  echo "[dev] checking web shell"
  curl -fsSI "$web_shell_base_url/" | grep -iq "200 OK"
  curl -fsSI "$web_shell_base_url/w/hq/meeting/example" | grep -iq "200 OK"

  echo "[dev] checking nginx api proxy"
  bootstrap_json="$(curl -fsS "$AI_DO_DEV_BASE_URL/api/v1/auth/bootstrap-status")"
  dev_admin_login_available="$(printf '%s' "$bootstrap_json" | bootstrap_field 'dev_admin_login_available')"
  dev_login_accounts_count="$(printf '%s' "$bootstrap_json" | bootstrap_accounts_count)"
  if [[ "$dev_admin_login_available" != "True" && "$dev_admin_login_available" != "true" ]]; then
    echo "[dev] dev admin login is not available through nginx" >&2
    return 1
  fi
  if (( dev_login_accounts_count < 1 )); then
    echo "[dev] expected seeded dev login accounts in bootstrap status" >&2
    return 1
  fi

  if (( AI_DO_DEV_API_COUNT > 1 )); then
    echo "[dev] checking nginx load balancing headers"
    seen_ids="$(
      for _ in $(seq 1 24); do
        curl -fsS -D - -o /dev/null "$AI_DO_DEV_BASE_URL/api/v1/auth/bootstrap-status" \
          | tr -d '\r' \
          | awk -F': ' 'tolower($1)=="x-doowon-instance-id"{print $2}'
      done | sort -u
    )"
    seen_count="$(printf '%s\n' "$seen_ids" | sed '/^$/d' | wc -l | tr -d ' ')"
    if (( seen_count < 2 )); then
      echo "[dev] expected nginx to hit multiple api instances, saw: ${seen_ids:-<none>}" >&2
      return 1
    fi
    printf '[dev] nginx observed instances:\n%s\n' "$seen_ids"
  else
    echo "[dev] single api instance configured; skipping load balancing check"
  fi

  echo "[dev] checking dev-login"
  curl -fsS \
    -H 'Content-Type: application/json' \
    -d '{"account_key":"administrator"}' \
    "$AI_DO_DEV_BASE_URL/api/v1/auth/dev-login" >/dev/null

  if [[ "${AI_DO_DEV_SMOKE_STANDARD_LOGIN:-0}" == "1" ]]; then
    echo "[dev] checking standard login"
    curl -fsS \
      -H 'Content-Type: application/json' \
      -d '{"login_id":"admin","password":"AI-DO!dev1234"}' \
      "$AI_DO_DEV_BASE_URL/api/v1/auth/login" >/dev/null
  fi

  if dev_managed_runtime_check_enabled; then
    run_managed_dev_runtime_checks
  else
    managed_check_status=$?
    if (( managed_check_status != 1 )); then
      return "$managed_check_status"
    fi
    echo "[dev] unmanaged local runtime; skipping managed worker checks"
  fi

  echo "[dev] smoke checks passed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
