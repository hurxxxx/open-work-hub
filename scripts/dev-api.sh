#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/dev-env.sh"

TARGET="${1:?instance index or port is required}"

if [[ "$TARGET" =~ ^[0-9]+$ ]] && (( TARGET >= 8000 )); then
  PORT="$TARGET"
  INSTANCE_INDEX="$((PORT - 8000))"
else
  INSTANCE_INDEX="$TARGET"
  PORT="$(dev_api_port "$INSTANCE_INDEX")"
fi

INSTANCE_ID="${2:-$(dev_api_name "$INSTANCE_INDEX")}"

export DOOWON_API_INSTANCE_ID="$INSTANCE_ID"

if [[ "${DOOWON_API_AUTO_MIGRATE:-}" == "" ]]; then
  if [[ "$PORT" == "8001" ]]; then
    export DOOWON_API_AUTO_MIGRATE=1
  else
    export DOOWON_API_AUTO_MIGRATE=0
  fi
fi

cd "$ROOT_DIR/apps/api"
exec "$ROOT_DIR/apps/api/.venv/bin/python" -m uvicorn ai_do_api.main:app --app-dir src --host 127.0.0.1 --port "$PORT"
