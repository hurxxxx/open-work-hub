#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT

contract_repo="$temporary_root/repo"
mkdir -p \
  "$contract_repo/apps/api" \
  "$contract_repo/packages/contracts" \
  "$contract_repo/packages/core-web" \
  "$contract_repo/packages/ui" \
  "$contract_repo/scripts/ci"
cp "$repo_root/apps/api/pyproject.toml" "$contract_repo/apps/api/"
cp "$repo_root/apps/api/uv.lock" "$contract_repo/apps/api/"
cp "$repo_root/package.json" "$contract_repo/"
cp "$repo_root/pnpm-lock.yaml" "$contract_repo/"
cp "$repo_root/pnpm-workspace.yaml" "$contract_repo/"
cp \
  "$repo_root/packages/contracts/package.json" \
  "$contract_repo/packages/contracts/"
cp \
  "$repo_root/packages/core-web/package.json" \
  "$contract_repo/packages/core-web/"
cp "$repo_root/packages/ui/package.json" "$contract_repo/packages/ui/"
cp "$repo_root/scripts/ci/run-api-pytest.sh" "$contract_repo/scripts/ci/"
wrapper="$contract_repo/scripts/ci/run-api-pytest.sh"

dependency_sha256="$(
  {
    sha256sum "$contract_repo/apps/api/pyproject.toml" | awk '{print $1}'
    sha256sum "$contract_repo/apps/api/uv.lock" | awk '{print $1}'
  } | sha256sum | awk '{print $1}'
)"

fake_python_source="$temporary_root/fake-python"
cat >"$fake_python_source" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s|%s\n' "${UV_OFFLINE:-}" "$*" >>"$FAKE_PYTHON_LOG"
exit "${FAKE_PYTHON_STATUS:-0}"
EOF
chmod +x "$fake_python_source"

image_venv="$temporary_root/image-venv"
mkdir -p "$image_venv/bin"
cp "$fake_python_source" "$image_venv/bin/python"
image_dependency_file="$temporary_root/image-dependency.sha256"
printf '%s\n' "$dependency_sha256" >"$image_dependency_file"
image_node_modules="$temporary_root/image-node-modules"
mkdir -p "$image_node_modules"
image_node_dependency_file="$temporary_root/image-node-dependency.sha256"
node_dependency_sha256="$(
  {
    sha256sum "$contract_repo/package.json" | awk '{print $1}'
    sha256sum "$contract_repo/pnpm-lock.yaml" | awk '{print $1}'
    sha256sum "$contract_repo/pnpm-workspace.yaml" | awk '{print $1}'
    sha256sum "$contract_repo/packages/contracts/package.json" | awk '{print $1}'
    sha256sum "$contract_repo/packages/core-web/package.json" | awk '{print $1}'
    sha256sum "$contract_repo/packages/ui/package.json" | awk '{print $1}'
  } | sha256sum | awk '{print $1}'
)"
printf '%s\n' "$node_dependency_sha256" >"$image_node_dependency_file"

offline_log="$temporary_root/offline.log"
FAKE_PYTHON_LOG="$offline_log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  bash "$wrapper" standard tests/test_example.py
test "$(readlink "$contract_repo/node_modules")" = "$image_node_modules"
grep -F \
  '1|-m pytest -q -m not slow and not external_integration and not migration -n 8 --dist worksteal --durations 50 --durations-min 1 tests/test_example.py' \
  "$offline_log" >/dev/null

load_log="$temporary_root/load.log"
FAKE_PYTHON_LOG="$load_log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  OPEN_ALM_API_PYTEST_WORKERS=7 \
  OPEN_ALM_API_PYTEST_SCHEDULER=load \
  OPEN_ALM_API_PYTEST_MAXSCHEDCHUNK=4 \
  bash "$wrapper" standard tests/test_example.py
grep -F \
  '1|-m pytest -q -m not slow and not external_integration and not migration -n 7 --dist load --maxschedchunk 4 --durations 50 --durations-min 1 tests/test_example.py' \
  "$load_log" >/dev/null
if grep -F -- '--maxschedchunk' "$offline_log" >/dev/null; then
  echo "worksteal must not receive the load-only maxschedchunk option" >&2
  exit 1
fi

if FAKE_PYTHON_LOG="$temporary_root/invalid-scheduler.log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  OPEN_ALM_API_PYTEST_SCHEDULER=invalid \
  bash "$wrapper" standard tests/test_example.py \
  >"$temporary_root/invalid-scheduler.out" \
  2>"$temporary_root/invalid-scheduler.err"; then
  echo "expected an invalid pytest scheduler to fail" >&2
  exit 1
fi
grep -F \
  'OPEN_ALM_API_PYTEST_SCHEDULER must be load or worksteal.' \
  "$temporary_root/invalid-scheduler.err" >/dev/null

FAKE_PYTHON_STATUS=5 \
  FAKE_PYTHON_LOG="$offline_log" \
  OPEN_ALM_API_ALLOW_EMPTY=1 \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  bash "$wrapper" standard tests/test_external_only.py

printf '%064d\n' 0 >"$image_dependency_file"
if FAKE_PYTHON_LOG="$offline_log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  bash "$wrapper" standard tests/test_example.py \
  >"$temporary_root/mismatch.out" 2>"$temporary_root/mismatch.err"; then
  echo "expected the offline dependency mismatch to fail" >&2
  exit 1
fi
grep -F 'Offline API dependency mismatch:' "$temporary_root/mismatch.err" >/dev/null

printf '%s\n' "$dependency_sha256" >"$image_dependency_file"
printf '%064d\n' 0 >"$image_node_dependency_file"
if FAKE_PYTHON_LOG="$offline_log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  bash "$wrapper" standard tests/test_example.py \
  >"$temporary_root/node-mismatch.out" \
  2>"$temporary_root/node-mismatch.err"; then
  echo "expected the offline Node dependency mismatch to fail" >&2
  exit 1
fi
grep -F \
  'API Node dependency mismatch:' \
  "$temporary_root/node-mismatch.err" >/dev/null
printf '%s\n' "$node_dependency_sha256" >"$image_node_dependency_file"

fake_bin="$temporary_root/fake-bin"
mkdir -p "$fake_bin"
cat >"$fake_bin/uv" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >>"$FAKE_UV_LOG"
mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
cp "$FAKE_PYTHON_SOURCE" "$UV_PROJECT_ENVIRONMENT/bin/python"
chmod +x "$UV_PROJECT_ENVIRONMENT/bin/python"
EOF
chmod +x "$fake_bin/uv"

bootstrap_venv="$temporary_root/bootstrap/api-${dependency_sha256}"
bootstrap_log="$temporary_root/bootstrap.log"
bootstrap_python_log="$temporary_root/bootstrap-python.log"
PATH="$fake_bin:$PATH" \
  FAKE_UV_LOG="$bootstrap_log" \
  FAKE_PYTHON_SOURCE="$fake_python_source" \
  FAKE_PYTHON_LOG="$bootstrap_python_log" \
  OPEN_ALM_API_DEPENDENCY_MODE=bootstrap \
  OPEN_ALM_API_BOOTSTRAP_VENV="$bootstrap_venv" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  OPEN_ALM_API_PREPARE_ONLY=1 \
  bash "$wrapper" standard
grep -F \
  "sync --directory $contract_repo/apps/api --frozen --python 3.12 --group dev --no-install-project" \
  "$bootstrap_log" >/dev/null
test "$(<"$bootstrap_venv/.open-alm-api-dependency-sha256")" = "$dependency_sha256"

PATH="$fake_bin:$PATH" \
  FAKE_UV_LOG="$bootstrap_log" \
  FAKE_PYTHON_SOURCE="$fake_python_source" \
  FAKE_PYTHON_LOG="$bootstrap_python_log" \
  OPEN_ALM_API_DEPENDENCY_MODE=bootstrap \
  OPEN_ALM_API_BOOTSTRAP_VENV="$bootstrap_venv" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  OPEN_ALM_API_PREPARE_ONLY=1 \
  bash "$wrapper" standard
test "$(wc -l <"$bootstrap_log")" -eq 1

external_log="$temporary_root/external.log"
printf '%s\n' "$dependency_sha256" >"$image_dependency_file"
FAKE_PYTHON_LOG="$external_log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  OPEN_ALM_API_TEST_RUN_ID=contract-test \
  bash "$wrapper" external tests/test_external.py
grep -F \
  '1|-m pytest -q -m external_integration tests/test_external.py' \
  "$external_log" >/dev/null
grep -F \
  '1|tests/integration_infra.py cleanup-current' \
  "$external_log" >/dev/null

cleanup_only_log="$temporary_root/cleanup-only.log"
FAKE_PYTHON_LOG="$cleanup_only_log" \
  OPEN_ALM_API_IMAGE_VENV="$image_venv" \
  OPEN_ALM_API_IMAGE_DEPENDENCY_FILE="$image_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE="$image_node_dependency_file" \
  OPEN_ALM_API_IMAGE_NODE_MODULES="$image_node_modules" \
  OPEN_ALM_API_TEST_RUN_ID=contract-test \
  OPEN_ALM_API_CLEANUP_ONLY=1 \
  bash "$wrapper" external
test "$(wc -l <"$cleanup_only_log")" -eq 1
grep -F \
  '1|tests/integration_infra.py cleanup-current' \
  "$cleanup_only_log" >/dev/null

bash "$repo_root/scripts/ci/prepare-validation-runtime.test.sh"

echo "run-api-pytest contract tests passed"
