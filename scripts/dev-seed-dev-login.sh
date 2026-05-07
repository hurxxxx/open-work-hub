#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/dev-env.sh"

cd "$ROOT_DIR/apps/api"
PYTHONPATH="$ROOT_DIR/apps/api/src${PYTHONPATH:+:$PYTHONPATH}" exec "$ROOT_DIR/apps/api/.venv/bin/python" - <<'PY'
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_engine
from ai_do_api.domains.auth.access import ensure_dev_login_seed_data


with Session(get_engine()) as session:
    ensure_dev_login_seed_data(session)
PY
