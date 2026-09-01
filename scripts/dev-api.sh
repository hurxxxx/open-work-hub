#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/dev-env.sh"
unset OPENROUTER_API_KEY

TARGET="${1:?instance index or port is required}"

if [[ "$TARGET" =~ ^[0-9]+$ ]] && (( TARGET >= 8000 )); then
  PORT="$TARGET"
  INSTANCE_INDEX="$((PORT - 8000))"
else
  INSTANCE_INDEX="$TARGET"
  PORT="$(dev_api_port "$INSTANCE_INDEX")"
fi

INSTANCE_ID="${2:-$(dev_api_name "$INSTANCE_INDEX")}"

export OPEN_WORK_HUB_API_INSTANCE_ID="$INSTANCE_ID"

if [[ "${OPEN_WORK_HUB_API_AUTO_MIGRATE:-}" == "" ]]; then
  if [[ "$PORT" == "8001" ]]; then
    export OPEN_WORK_HUB_API_AUTO_MIGRATE=1
  else
    export OPEN_WORK_HUB_API_AUTO_MIGRATE=0
  fi
fi

cd "$ROOT_DIR/apps/api"
exec "$ROOT_DIR/apps/api/.venv/bin/python" -m uvicorn open_work_hub_api.main:app --app-dir src --host "$OPEN_WORK_HUB_DEV_API_HOST" --port "$PORT"
