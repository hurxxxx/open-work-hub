#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/apps/api"

uv run ruff check \
  src/aidoo_api/domains/admin/router.py \
  src/aidoo_api/domains/ai/router.py \
  src/aidoo_api/domains/ai/runtime/external_egress.py \
  src/aidoo_api/domains/ai/runtime/external_adapters.py \
  src/aidoo_api/domains/ai/runtime/metrics.py \
  tests/ai_runtime_mock_harness.py \
  tests/test_ai_runtime_admin.py \
  tests/test_ai_runtime_contracts.py \
  tests/test_ai_runtime_external_egress.py \
  tests/test_ai_runtime_mock_e2e.py \
  tests/test_ai_runtime_settings.py

uv run --python 3.12 --group dev python -m pytest \
  tests/test_ai_runtime_admin.py \
  tests/test_ai_runtime_contracts.py \
  tests/test_ai_runtime_external_egress.py \
  tests/test_ai_runtime_settings.py \
  tests/test_ai_runtime_mock_e2e.py \
  tests/test_ai_stream.py \
  "$@"
