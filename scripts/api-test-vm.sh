#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AIDOO_ENV_PROFILE=vm

cd "$ROOT_DIR/apps/api"
exec uv run --python 3.12 --group dev python -m pytest "$@"
