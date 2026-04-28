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

echo "[dev] checking api instances"
for instance in $(seq 1 "$DOOWON_DEV_API_COUNT"); do
  port="$(dev_api_port "$instance")"
  expected_id="$(dev_api_name "$instance")"
  actual_id="$(api_health_payload "$port" | api_instance_id_from_health)"
  if [[ "$actual_id" != "$expected_id" ]]; then
    echo "[dev] unexpected instance id on port ${port}: expected ${expected_id}, got ${actual_id}" >&2
    exit 1
  fi
done

echo "[dev] checking nginx static shell"
curl -fsSI "$DOOWON_DEV_BASE_URL/" | grep -iq "200 OK"
curl -fsSI "$DOOWON_DEV_BASE_URL/w/hq/meeting/example" | grep -iq "200 OK"

echo "[dev] checking nginx api proxy"
bootstrap_json="$(curl -fsS "$DOOWON_DEV_BASE_URL/api/v1/auth/bootstrap-status")"
dev_admin_login_available="$(printf '%s' "$bootstrap_json" | bootstrap_field 'dev_admin_login_available')"
dev_login_accounts_count="$(printf '%s' "$bootstrap_json" | bootstrap_accounts_count)"
if [[ "$dev_admin_login_available" != "True" && "$dev_admin_login_available" != "true" ]]; then
  echo "[dev] dev admin login is not available through nginx" >&2
  exit 1
fi
if (( dev_login_accounts_count < 1 )); then
  echo "[dev] expected seeded dev login accounts in bootstrap status" >&2
  exit 1
fi

echo "[dev] checking nginx load balancing headers"
seen_ids="$(
  for _ in $(seq 1 24); do
    curl -fsS -D - -o /dev/null "$DOOWON_DEV_BASE_URL/api/v1/auth/bootstrap-status" \
      | tr -d '\r' \
      | awk -F': ' 'tolower($1)=="x-doowon-instance-id"{print $2}'
  done | sort -u
)"
seen_count="$(printf '%s\n' "$seen_ids" | sed '/^$/d' | wc -l | tr -d ' ')"
if (( seen_count < 2 )); then
  echo "[dev] expected nginx to hit multiple api instances, saw: ${seen_ids:-<none>}" >&2
  exit 1
fi
printf '[dev] nginx observed instances:\n%s\n' "$seen_ids"

echo "[dev] checking dev-login and standard login"
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"account_key":"platform-admin"}' \
  "$DOOWON_DEV_BASE_URL/api/v1/auth/dev-login" >/dev/null
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"email":"platform-admin@aidoo.local","password":"Aidoo!dev1234"}' \
  "$DOOWON_DEV_BASE_URL/api/v1/auth/login" >/dev/null

echo "[dev] smoke checks passed"
