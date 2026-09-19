#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="${1:?Usage: bash scripts/build-codex-console.sh /absolute/new/release-directory}"
if [[ "$RELEASE_DIR" != /* || -e "$RELEASE_DIR" ]]; then
  echo 'Choose an absolute, new release directory. Existing releases are never overwritten.' >&2
  exit 1
fi

pnpm --dir "$ROOT_DIR/apps/codex-console-web" build
mkdir -p "$RELEASE_DIR/apps/codex-console-api" "$RELEASE_DIR/apps/codex-console-web"
cp -a "$ROOT_DIR/apps/codex-console-web/dist" "$RELEASE_DIR/apps/codex-console-web/"
tar -C "$ROOT_DIR/apps/codex-console-api" --exclude=__pycache__ -cf - \
  src migrations pyproject.toml uv.lock alembic.ini \
  | tar -C "$RELEASE_DIR/apps/codex-console-api" -xf -
uv sync --frozen --no-dev --directory "$RELEASE_DIR/apps/codex-console-api"
echo 'Release built. Configure the dedicated database and origin before starting the service.'
