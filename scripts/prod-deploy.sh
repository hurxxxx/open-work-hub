#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

trim_prod_deploy_env_text() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

normalize_prod_deploy_env_value() {
  local value
  value="$(trim_prod_deploy_env_text "${1:-}")"
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
      value="$(trim_prod_deploy_env_text "$value")"
      ;;
  esac
  printf '%s' "$value"
}

load_prod_deploy_env_file() {
  local env_file="$ROOT_DIR/.env"
  local line key value
  if [[ ! -f "$env_file" ]]; then
    return 0
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(trim_prod_deploy_env_text "$line")"
    if [[ "$line" == export[[:space:]]* ]]; then
      line="$(trim_prod_deploy_env_text "${line#export}")"
    fi
    if [[ -z "$line" || "$line" == \#* || "$line" != *=* ]]; then
      continue
    fi
    key="${line%%=*}"
    value="${line#*=}"
    key="$(trim_prod_deploy_env_text "$key")"
    if [[ "$key" != OPEN_ALM_PROD_* \
      && "$key" != OPEN_ALM_POSTGRES_DSN \
      && "$key" != OPEN_ALM_IMAGE_ENABLED \
      && "$key" != OPEN_ALM_DRAWIO_PORT \
      && "$key" != OPEN_ALM_DRAWIO_SERVER_URL ]]; then
      continue
    fi
    value="$(normalize_prod_deploy_env_value "$value")"
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done <"$env_file"
}

load_prod_deploy_env_file

EXPECTED_ROOT="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_ROOT:-/projects/open-alm/prod}")"
EXPECTED_BRANCH="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_BRANCH:-main}")"
EXPECTED_REMOTE_REF="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_REMOTE_REF:-origin/$EXPECTED_BRANCH}")"
BACKUP_ROOT="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_BACKUP_ROOT:-/projects/open-alm/backups/prod}")"
POSTGRES_DSN="$(normalize_prod_deploy_env_value "${OPEN_ALM_POSTGRES_DSN:-}")"
KEYWORD_REINDEX_WORKSPACE_KEYS="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS:-}")"
KEYWORD_REINDEX_ALL_ACTIVE="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE:-0}")"
RELEASE_GATE_ADAPTERS="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS:-}")"
SKIP_RELEASE_GATES="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_SKIP_RELEASE_GATES:-0}")"
IMAGE_ENABLED="$(normalize_prod_deploy_env_value "${OPEN_ALM_IMAGE_ENABLED:-false}")"
MODEL_SETTINGS_CUTOVER_ENV_FILE="$(normalize_prod_deploy_env_value "${OPEN_ALM_PROD_MODEL_SETTINGS_CUTOVER_ENV_FILE:-$ROOT_DIR/.env}")"
DRY_RUN=0
TLS_EXPIRY_BREAK_GLASS=0
STAGED_FRONTEND_DIR=""
FRONTEND_BUILD_ID=""
API_STOPPED=0
SEARCH_WRITERS_QUIESCED=0
ACTIVATION_STARTED=0
FRONTEND_PROMOTED=0
DEPLOY_LOCK_FD=""

usage() {
  cat >&2 <<'EOF'
Usage: scripts/prod-deploy.sh [--dry-run] [--keyword-reindex-all-active] [--tls-expiry-break-glass]

Runs the production release flow from /projects/open-alm/prod:
  1. print git state
  2. validate the public TLS certificate expiry and SAN contract
  3. install locked dependencies
  4. validate the Alembic revision graph
  5. build and validate the web app in a staging directory
  6. quiesce all production writer units while keeping production infra available
  7. create and verify the native Postgres rollback backup from the quiesced state
  8. run Alembic migrations explicitly; destructive migrations fail closed in-migration
  9. verify the database Alembic revision matches the repository head
  10. run configured pre-activation release gate adapters
  11. promote the staged web build and restart units
  12. run production smoke, post-activation gates, and final smoke

Options:
  --dry-run                      Print the planned flow without changing services.
  --keyword-reindex-all-active   Rebuild and smoke every active workspace keyword index.
  --tls-expiry-break-glass       One-shot override of only the 30-day TLS expiry window.
                                 Expired, untrusted, wrong-host, or missing-SAN certificates still fail.

Release gates:
  OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS configures comma-separated gate adapters.
  Gate adapters declare pre_activate or post_activate execution phases.
  keyword_dataset_scope runs in pre_activate while search writers are quiesced.
  llm_provider_settings_cutover imports legacy external LLM settings before activation.
  image_model_settings_cutover drains and validates image settings before activation.
  OPEN_ALM_IMAGE_ENABLED=true requires image_model_settings_cutover and cannot bypass gates.
  OPEN_ALM_PROD_MODEL_SETTINGS_CUTOVER_ENV_FILE may point to a one-shot file under .runtime/.
  OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS configures keyword_dataset_scope workspaces.
  OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE=1 or --keyword-reindex-all-active selects every active workspace.
  OPEN_ALM_PROD_SKIP_RELEASE_GATES=1 is required to deliberately bypass all gates.
  OPEN_ALM_PROD_REMOTE_REF defaults to origin/<OPEN_ALM_PROD_BRANCH> for stale-check protection.

Database migration safety:
  The N+2 Knowledge physical-retirement migration performs its fail-closed
  preflight in the same transaction before dropping the retired tables.
  No separate Knowledge audit-script release gate runs after migration.
EOF
}

require_prod_checkout() {
  if [[ "${OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS:-0}" == "1" ]]; then
    return
  fi
  if [[ "$ROOT_DIR" != "$EXPECTED_ROOT" ]]; then
    echo "Refusing to deploy production from unexpected checkout: $ROOT_DIR" >&2
    echo "Expected $EXPECTED_ROOT, or set OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS=1 for a deliberate dry-run/break-glass operation." >&2
    exit 1
  fi
  local branch
  branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
  if [[ "$branch" != "$EXPECTED_BRANCH" ]]; then
    echo "Refusing to deploy production from branch '$branch'; expected '$EXPECTED_BRANCH'." >&2
    echo "Set OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS=1 only for a deliberate rollback/break-glass operation." >&2
    exit 1
  fi
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "Refusing to deploy production with a dirty worktree." >&2
    git -C "$ROOT_DIR" status --short >&2
    exit 1
  fi
  require_synced_prod_checkout
}

require_synced_prod_checkout() {
  local remote_name="${EXPECTED_REMOTE_REF%%/*}"
  local remote_branch="${EXPECTED_REMOTE_REF#*/}"
  if [[ -z "$remote_name" || "$remote_name" == "$EXPECTED_REMOTE_REF" ]]; then
    echo "OPEN_ALM_PROD_REMOTE_REF must be a remote ref such as origin/$EXPECTED_BRANCH; got '$EXPECTED_REMOTE_REF'." >&2
    exit 1
  fi
  if [[ -z "$remote_branch" || "$remote_branch" == "$EXPECTED_REMOTE_REF" ]]; then
    echo "OPEN_ALM_PROD_REMOTE_REF must include a branch path such as origin/$EXPECTED_BRANCH; got '$EXPECTED_REMOTE_REF'." >&2
    exit 1
  fi

  if ! git -C "$ROOT_DIR" fetch --quiet "$remote_name" "${remote_branch}:refs/remotes/${remote_name}/${remote_branch}"; then
    echo "Refusing to deploy production because '$EXPECTED_REMOTE_REF' could not be fetched." >&2
    exit 1
  fi

  local head_sha remote_sha
  head_sha="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  remote_sha="$(git -C "$ROOT_DIR" rev-parse --verify "${EXPECTED_REMOTE_REF}^{commit}")"
  if [[ "$head_sha" != "$remote_sha" ]]; then
    echo "Refusing to deploy production because HEAD is not synced with $EXPECTED_REMOTE_REF." >&2
    echo "HEAD: $head_sha" >&2
    echo "$EXPECTED_REMOTE_REF: $remote_sha" >&2
    exit 1
  fi
}

run_step() {
  local label="${1:?label is required}"
  shift
  printf '\n[prod-deploy] %s\n' "$label"
  printf '[prod-deploy] $'
  printf ' %q' "$@"
  printf '\n'
  if (( DRY_RUN )); then
    return 0
  fi
  "$@"
}

run_shell_step() {
  local label="${1:?label is required}"
  local command="${2:?command is required}"
  printf '\n[prod-deploy] %s\n' "$label"
  printf '[prod-deploy] $ %s\n' "$command"
  if (( DRY_RUN )); then
    return 0
  fi
  bash -lc "$command"
}

run_prod_tls_preflight() {
  if (( TLS_EXPIRY_BREAK_GLASS )); then
    run_step \
      "Validate public TLS certificate readiness" \
      python3 "$ROOT_DIR/scripts/check_live_tls_expiry.py" --threshold-days=0
    return
  fi
  run_step \
    "Validate public TLS certificate readiness" \
    python3 "$ROOT_DIR/scripts/check_live_tls_expiry.py"
}

run_prod_smoke_step() {
  local label="${1:?label is required}"
  if (( TLS_EXPIRY_BREAK_GLASS )); then
    run_step \
      "$label" \
      bash "$ROOT_DIR/scripts/prod-systemd.sh" smoke --tls-expiry-break-glass
    return
  fi
  run_step "$label" bash "$ROOT_DIR/scripts/prod-systemd.sh" smoke
}

run_postgres_backup_step() {
  local backup_file="${1:?backup file is required}"
  printf '\n[prod-deploy] Back up production Postgres\n'
  printf '[prod-deploy] $ pg_dump -Fc -f %q <OPEN_ALM_POSTGRES_DSN>\n' "$backup_file"
  if (( DRY_RUN )); then
    return 0
  fi
  if [[ -z "$POSTGRES_DSN" ]]; then
    echo "OPEN_ALM_POSTGRES_DSN is required for production Postgres backups." >&2
    return 2
  fi
  OPEN_ALM_POSTGRES_DSN="$POSTGRES_DSN" OPEN_ALM_BACKUP_FILE="$backup_file" python3 - <<'PY'
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from urllib.parse import parse_qsl, unquote, urlsplit


raw_dsn = os.environ.get("OPEN_ALM_POSTGRES_DSN", "").strip()
backup_file = os.environ["OPEN_ALM_BACKUP_FILE"]
if "://" not in raw_dsn:
    sys.exit("OPEN_ALM_POSTGRES_DSN must be a PostgreSQL URL.")

scheme, rest = raw_dsn.split("://", 1)
if scheme in {"postgresql+psycopg", "postgresql+asyncpg", "postgres"}:
    dsn = f"postgresql://{rest}"
elif scheme == "postgresql":
    dsn = raw_dsn
else:
    sys.exit("OPEN_ALM_POSTGRES_DSN must use a PostgreSQL scheme.")

parsed = urlsplit(dsn)
host = parsed.hostname or ""
port = str(parsed.port or 5432)
user = unquote(parsed.username or "")
password = unquote(parsed.password or "")
database = unquote(parsed.path.lstrip("/"))
if not host or not user or not database:
    sys.exit("OPEN_ALM_POSTGRES_DSN must include host, user, and database.")

env = os.environ.copy()
env.update(
    {
        "PGHOST": host,
        "PGPORT": port,
        "PGUSER": user,
        "PGDATABASE": database,
    }
)
if password:
    env["PGPASSWORD"] = password

query = dict(parse_qsl(parsed.query, keep_blank_values=True))
sslmode = query.get("sslmode")
if sslmode:
    env["PGSSLMODE"] = sslmode

subprocess.run(["pg_dump", "-Fc", "-f", backup_file], env=env, check=True)
os.chmod(backup_file, 0o600)
if os.path.getsize(backup_file) <= 0:
    sys.exit("Production PostgreSQL backup is empty.")
subprocess.run(
    ["pg_restore", "-l", backup_file],
    env=env,
    stdout=subprocess.DEVNULL,
    check=True,
)
digest = hashlib.sha256()
with open(backup_file, "rb") as backup_stream:
    for chunk in iter(lambda: backup_stream.read(1024 * 1024), b""):
        digest.update(chunk)
print(
    "[prod-deploy] backup verified: "
    f"size={os.path.getsize(backup_file)} mode=600 sha256={digest.hexdigest()}"
)
PY
}

require_frontend_release_path() {
  local candidate="${1:?frontend release path is required}"
  local root_real expected_release_root release_root candidate_real
  root_real="$(realpath -e "$ROOT_DIR")" || return 2
  expected_release_root="$root_real/dist/apps"
  release_root="$(realpath -m "$ROOT_DIR/dist/apps")"
  if [[ "$release_root" != "$expected_release_root" ]]; then
    echo "Refusing symlinked frontend release root: $release_root" >&2
    return 2
  fi
  candidate_real="$(realpath -m "$candidate")"
  if [[ "$candidate_real" != "$release_root"/* ]]; then
    echo "Refusing frontend release operation outside $release_root: $candidate_real" >&2
    return 2
  fi
}

remove_frontend_release_dir() {
  local target="${1:?frontend release path is required}"
  require_frontend_release_path "$target" || return $?
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf -- "$target"
  fi
}

validate_frontend_build() {
  local build_dir="${1:?frontend build directory is required}"
  local expected_build_id="${2:?frontend build id is required}"
  require_frontend_release_path "$build_dir" || return $?
  FRONTEND_BUILD_DIR="$build_dir" FRONTEND_BUILD_ID="$expected_build_id" python3 - <<'PY'
import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


root = Path(os.environ["FRONTEND_BUILD_DIR"]).resolve()
expected_build_id = os.environ["FRONTEND_BUILD_ID"]


def fail(message: str) -> None:
    raise SystemExit(f"[prod-deploy] {message}")


def require_artifact(relative: str) -> None:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        fail(f"invalid frontend build artifact path: {relative}")
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        fail(f"missing frontend build artifact: {relative}")


index_path = root / "index.html"
manifest_path = root / ".vite" / "manifest.json"
build_id_path = root / ".open-alm-build-id"
for required in (index_path, manifest_path, build_id_path, root / "assets"):
    if not required.exists():
        fail(f"missing frontend build artifact: {required.relative_to(root)}")
if build_id_path.read_text(encoding="utf-8").strip() != expected_build_id:
    fail("frontend build id does not match the staged release")

try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"invalid frontend build manifest: {exc}")
if not isinstance(manifest, dict) or not manifest:
    fail("frontend build manifest is empty")

has_entry = False
for key, record in manifest.items():
    if not isinstance(record, dict):
        fail(f"invalid frontend manifest record: {key}")
    has_entry = has_entry or record.get("isEntry") is True
    file_value = record.get("file")
    if isinstance(file_value, str):
        require_artifact(file_value)
    for field in ("css", "assets"):
        values = record.get(field, [])
        if not isinstance(values, list):
            fail(f"invalid frontend manifest field: {key}.{field}")
        for value in values:
            if not isinstance(value, str):
                fail(f"invalid frontend manifest artifact: {key}.{field}")
            require_artifact(value)
    for field in ("imports", "dynamicImports"):
        values = record.get(field, [])
        if not isinstance(values, list):
            fail(f"invalid frontend manifest field: {key}.{field}")
        for value in values:
            if value not in manifest:
                fail(f"missing frontend manifest reference: {value}")
if not has_entry:
    fail("frontend build manifest has no entry")


class IndexReferenceParser(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for name, value in attrs:
            if name not in {"src", "href"} or not value:
                continue
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or value.startswith(("#", "data:")):
                continue
            relative = parsed.path.lstrip("/")
            if relative:
                require_artifact(relative)


parser = IndexReferenceParser()
parser.feed(index_path.read_text(encoding="utf-8"))
PY
}

cleanup_staged_frontend_build() {
  if [[ -n "$STAGED_FRONTEND_DIR" && -e "$STAGED_FRONTEND_DIR" ]]; then
    remove_frontend_release_dir "$STAGED_FRONTEND_DIR"
  fi
}

cleanup_prod_deploy() {
  local status="${1:-0}"
  trap - EXIT INT TERM
  if ! cleanup_staged_frontend_build; then
    echo "Failed to clean staged frontend build." >&2
    if (( status == 0 )); then
      status=1
    fi
  fi
  if (( SEARCH_WRITERS_QUIESCED && ! ACTIVATION_STARTED )); then
    echo "[prod-deploy] Pre-activation deployment did not complete; keeping search-writing app units quiesced and the staged frontend inactive." >&2
    if ! bash "$ROOT_DIR/scripts/prod-systemd.sh" quiesce-search-writers; then
      echo "Failed to enforce fail-closed state for production search-writing app units." >&2
    fi
    status=1
  elif (( ACTIVATION_STARTED && ! FRONTEND_PROMOTED )); then
    echo "[prod-deploy] Frontend promotion did not complete; keeping search-writing app units fail-closed." >&2
    if (( ! SEARCH_WRITERS_QUIESCED )); then
      if systemctl --user stop open-alm-prod-api.service; then
        API_STOPPED=1
      else
        echo "Failed to enforce fail-closed state for open-alm-prod-api.service." >&2
      fi
    fi
    status=1
  elif (( SEARCH_WRITERS_QUIESCED )); then
    echo "[prod-deploy] Restoring search-writing app units after interrupted activation" >&2
    if bash "$ROOT_DIR/scripts/prod-systemd.sh" resume-search-writers; then
      SEARCH_WRITERS_QUIESCED=0
      API_STOPPED=0
    else
      echo "Failed to restore production search-writing app units." >&2
      status=1
    fi
  elif (( API_STOPPED )); then
    echo "[prod-deploy] Restoring production API after interrupted activation" >&2
    if systemctl --user start open-alm-prod-api.service; then
      API_STOPPED=0
    else
      echo "Failed to restore open-alm-prod-api.service." >&2
      status=1
    fi
  fi
  return "$status"
}

acquire_prod_deploy_lock() {
  local lock_path
  lock_path="$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-path open-alm-prod-deploy.lock)" || return 2
  exec {DEPLOY_LOCK_FD}>"$lock_path"
  if ! flock -n "$DEPLOY_LOCK_FD"; then
    echo "Another production deployment is already running for $ROOT_DIR." >&2
    return 2
  fi
}

run_frontend_build_step() {
  local release_timestamp="${1:?release timestamp is required}"
  local release_root="$ROOT_DIR/dist/apps"
  local commit
  commit="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD)"
  FRONTEND_BUILD_ID="${commit}-${release_timestamp}"
  STAGED_FRONTEND_DIR="$release_root/.web-staging-${release_timestamp}-$$"

  printf '\n[prod-deploy] Build production web assets in staging\n'
  printf '[prod-deploy] $ VITE_OPEN_ALM_BUILD_ID=%q pnpm exec nx build web --skip-nx-cache --args=--outDir=...\n' "$FRONTEND_BUILD_ID"
  if (( DRY_RUN )); then
    return 0
  fi
  mkdir -p "$release_root" || return $?
  remove_frontend_release_dir "$STAGED_FRONTEND_DIR" || return $?
  if ! VITE_OPEN_ALM_BUILD_ID="$FRONTEND_BUILD_ID" \
    pnpm exec nx build web --skip-nx-cache \
      --args="--outDir=$STAGED_FRONTEND_DIR --manifest=.vite/manifest.json"; then
    cleanup_staged_frontend_build
    return 1
  fi
  printf '%s\n' "$FRONTEND_BUILD_ID" >"$STAGED_FRONTEND_DIR/.open-alm-build-id"
  if ! validate_frontend_build "$STAGED_FRONTEND_DIR" "$FRONTEND_BUILD_ID"; then
    cleanup_staged_frontend_build
    return 1
  fi
}

promote_frontend_build() {
  local staged_dir="${1:?staged frontend directory is required}"
  local live_dir="${2:?live frontend directory is required}"
  local previous_dir="${3:?previous frontend directory is required}"
  require_frontend_release_path "$staged_dir" || return $?
  require_frontend_release_path "$live_dir" || return $?
  require_frontend_release_path "$previous_dir" || return $?
  [[ -d "$staged_dir" ]] || {
    echo "Staged frontend build does not exist: $staged_dir" >&2
    return 2
  }

  remove_frontend_release_dir "$previous_dir" || return $?
  if [[ -e "$live_dir" ]]; then
    mv -- "$live_dir" "$previous_dir" || return $?
  fi
  if ! mv -- "$staged_dir" "$live_dir"; then
    if [[ -e "$previous_dir" && ! -e "$live_dir" ]]; then
      if ! mv -- "$previous_dir" "$live_dir"; then
        echo "Failed to restore the prior frontend after promotion failure." >&2
      fi
    fi
    return 1
  fi
}

promote_frontend_build_step() {
  local live_dir="$ROOT_DIR/dist/apps/web"
  local previous_dir="$ROOT_DIR/dist/apps/.web-previous"
  printf '\n[prod-deploy] Promote staged frontend build\n'
  printf '[prod-deploy] $ promote %q -> %q\n' "$STAGED_FRONTEND_DIR" "$live_dir"
  if (( DRY_RUN )); then
    return 0
  fi
  if ! promote_frontend_build "$STAGED_FRONTEND_DIR" "$live_dir" "$previous_dir"; then
    return 1
  fi
  FRONTEND_PROMOTED=1
  STAGED_FRONTEND_DIR=""
}

print_git_state() {
  local branch commit dirty
  branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
  commit="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    dirty="dirty"
  else
    dirty="clean"
  fi
  printf '[prod-deploy] root: %s\n' "$ROOT_DIR"
  printf '[prod-deploy] branch: %s\n' "$branch"
  printf '[prod-deploy] commit: %s\n' "$commit"
  printf '[prod-deploy] worktree: %s\n' "$dirty"
}

workspace_key_args() {
  local value="${1:-}"
  local args=()
  local key
  IFS=',' read -ra keys <<<"$value"
  for key in "${keys[@]}"; do
    key="${key//[[:space:]]/}"
    if [[ -n "$key" ]]; then
      args+=(--workspace-key "$key")
    fi
  done
  if [[ "${#args[@]}" -eq 0 ]]; then
    return 0
  fi
  printf ' %q' "${args[@]}"
}

keyword_reindex_args() {
  local workspace_args
  workspace_args="$(workspace_key_args "$KEYWORD_REINDEX_WORKSPACE_KEYS")"
  if [[ -n "$workspace_args" ]]; then
    printf '%s' "$workspace_args"
    return
  fi
  if [[ "$KEYWORD_REINDEX_ALL_ACTIVE" == "1" ]]; then
    printf '%s' " --all-active"
  fi
}

normalized_csv_items() {
  local value="${1:-}"
  local items=()
  local item
  local first=1
  IFS=',' read -ra items <<<"$value"
  for item in "${items[@]}"; do
    item="${item//[[:space:]]/}"
    if [[ -z "$item" ]]; then
      continue
    fi
    if (( first )); then
      first=0
    else
      printf ','
    fi
    printf '%s' "$item"
  done
}

configured_release_gate_adapters() {
  local adapters
  adapters="$(normalized_csv_items "$RELEASE_GATE_ADAPTERS")"
  if [[ -n "$adapters" ]]; then
    printf '%s' "$adapters"
    return
  fi
  if [[ -n "$(keyword_reindex_args)" ]]; then
    printf '%s' "keyword_dataset_scope"
  fi
}

dispatch_release_gate_adapter() {
  local phase="${1:-}"
  local adapter="${2:-}"
  local explicit_adapters="${3:-0}"
  adapter="${adapter//[[:space:]]/}"
  case "$adapter" in
    "")
      return 0
      ;;
    keyword_dataset_scope)
      case "$phase" in
        validate)
          validate_keyword_dataset_scope_gate "$explicit_adapters"
          ;;
        pre_activate)
          run_keyword_dataset_scope_gate
          ;;
        post_activate)
          return 0
          ;;
        *)
          echo "Unsupported production release gate phase: $phase" >&2
          return 2
          ;;
      esac
      ;;
    llm_provider_settings_cutover)
      case "$phase" in
        validate)
          validate_model_settings_cutover_env_file
          ;;
        pre_activate)
          run_llm_provider_settings_cutover_gate
          ;;
        post_activate)
          return 0
          ;;
        *)
          echo "Unsupported production release gate phase: $phase" >&2
          return 2
          ;;
      esac
      ;;
    image_model_settings_cutover)
      case "$phase" in
        validate)
          validate_model_settings_cutover_env_file
          ;;
        pre_activate)
          run_image_model_settings_cutover_gate
          ;;
        post_activate)
          return 0
          ;;
        *)
          echo "Unsupported production release gate phase: $phase" >&2
          return 2
          ;;
      esac
      ;;
    *)
      echo "Unsupported production release gate adapter: $adapter" >&2
      return 2
      ;;
  esac
}

validate_release_gate_configuration() {
  local adapters
  adapters="$(configured_release_gate_adapters)"
  case "${IMAGE_ENABLED,,}" in
    1|true|yes|on)
      if [[ "$SKIP_RELEASE_GATES" == "1" ]]; then
        echo "OPEN_ALM_IMAGE_ENABLED=true cannot bypass production release gates." >&2
        return 2
      fi
      if ! csv_contains "$adapters" "image_model_settings_cutover"; then
        echo "OPEN_ALM_IMAGE_ENABLED=true requires the image_model_settings_cutover release gate adapter." >&2
        return 2
      fi
      ;;
    0|false|no|off)
      ;;
    *)
      echo "OPEN_ALM_IMAGE_ENABLED must be a boolean value." >&2
      return 2
      ;;
  esac
  if [[ "$SKIP_RELEASE_GATES" == "1" ]]; then
    return 0
  fi
  if [[ -n "$RELEASE_GATE_ADAPTERS" && -z "$(normalized_csv_items "$RELEASE_GATE_ADAPTERS")" ]]; then
    echo "OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS must contain at least one release gate adapter name, or set OPEN_ALM_PROD_SKIP_RELEASE_GATES=1 for a deliberate bypass." >&2
    return 2
  fi
  if [[ -n "$KEYWORD_REINDEX_WORKSPACE_KEYS" && -z "$(workspace_key_args "$KEYWORD_REINDEX_WORKSPACE_KEYS")" ]]; then
    echo "OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS must contain at least one workspace key when set." >&2
    return 2
  fi
  if [[ "$KEYWORD_REINDEX_ALL_ACTIVE" != "0" && "$KEYWORD_REINDEX_ALL_ACTIVE" != "1" ]]; then
    echo "OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE must be 0 or 1." >&2
    return 2
  fi
  if [[ "$KEYWORD_REINDEX_ALL_ACTIVE" == "1" && -n "$(workspace_key_args "$KEYWORD_REINDEX_WORKSPACE_KEYS")" ]]; then
    echo "OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE/--keyword-reindex-all-active and OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS are mutually exclusive." >&2
    return 2
  fi
  if [[ -z "$adapters" ]]; then
    echo "Production release gates are not configured." >&2
    echo "Set OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS, OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS, --keyword-reindex-all-active, or OPEN_ALM_PROD_SKIP_RELEASE_GATES=1 for a deliberate bypass." >&2
    return 2
  fi

  local adapter
  local explicit_adapters=0
  local status
  if [[ -n "$(normalized_csv_items "$RELEASE_GATE_ADAPTERS")" ]]; then
    explicit_adapters=1
  fi
  IFS=',' read -ra adapter_list <<<"$adapters"
  for adapter in "${adapter_list[@]}"; do
    dispatch_release_gate_adapter validate "$adapter" "$explicit_adapters"
    status=$?
    if (( status != 0 )); then
      return "$status"
    fi
  done
}

csv_contains() {
  local csv="${1:-}"
  local expected="${2:?expected item is required}"
  local items=()
  local item
  IFS=',' read -ra items <<<"$csv"
  for item in "${items[@]}"; do
    item="${item//[[:space:]]/}"
    if [[ "$item" == "$expected" ]]; then
      return 0
    fi
  done
  return 1
}

validate_model_settings_cutover_env_file() {
  local root_real candidate_real
  root_real="$(realpath -e "$ROOT_DIR")" || return 2
  candidate_real="$(realpath -e "$MODEL_SETTINGS_CUTOVER_ENV_FILE")" || {
    echo "Production model settings cutover env file is unavailable." >&2
    return 2
  }
  if [[ ! -f "$candidate_real" || ! -r "$candidate_real" ]]; then
    echo "Production model settings cutover env file must be a readable regular file." >&2
    return 2
  fi
  if [[ "$candidate_real" != "$root_real/.env" \
    && "$candidate_real" != "$root_real"/.runtime/* ]]; then
    echo "Production model settings cutover env file must be .env or a file under .runtime/." >&2
    return 2
  fi
}

run_llm_provider_settings_cutover_gate() {
  local env_file_arg
  printf -v env_file_arg '%q' "$MODEL_SETTINGS_CUTOVER_ENV_FILE"
  run_shell_step \
    "Preview legacy external LLM provider settings cutover" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/import_legacy_llm_provider_settings.py --env-file $env_file_arg"
  run_shell_step \
    "Apply legacy external LLM provider settings cutover" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/import_legacy_llm_provider_settings.py --env-file $env_file_arg --apply"
  run_shell_step \
    "Verify external LLM provider settings cutover idempotency" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/import_legacy_llm_provider_settings.py --env-file $env_file_arg --apply"
}

run_image_model_settings_cutover_gate() {
  local env_file_arg
  printf -v env_file_arg '%q' "$MODEL_SETTINGS_CUTOVER_ENV_FILE"
  run_shell_step \
    "Require an idle image generation queue before settings cutover" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/check_image_model_settings_cutover.py --jobs-only"
  run_shell_step \
    "Preview legacy image model settings cutover" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/import_legacy_image_model_settings.py --env-file $env_file_arg"
  run_shell_step \
    "Apply legacy image model settings cutover" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/import_legacy_image_model_settings.py --env-file $env_file_arg --apply"
  run_shell_step \
    "Verify image model settings cutover idempotency" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/import_legacy_image_model_settings.py --env-file $env_file_arg --apply"
  run_shell_step \
    "Validate image model settings readiness after cutover" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/check_image_model_settings_cutover.py"
}

run_release_gates() {
  local phase="${1:-}"
  case "$phase" in
    pre_activate|post_activate)
      ;;
    *)
      echo "Unsupported production release gate phase: $phase" >&2
      return 2
      ;;
  esac
  local adapters
  adapters="$(configured_release_gate_adapters)"
  if [[ "$SKIP_RELEASE_GATES" == "1" ]]; then
    printf '\n[prod-deploy] Release gate phase %s: deliberately bypassed by OPEN_ALM_PROD_SKIP_RELEASE_GATES=1\n' "$phase"
    return 0
  fi
  if [[ -z "$adapters" ]]; then
    echo "Production release gates are not configured." >&2
    echo "Set OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS, OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS, --keyword-reindex-all-active, or OPEN_ALM_PROD_SKIP_RELEASE_GATES=1 for a deliberate bypass." >&2
    return 2
  fi

  local adapter
  local explicit_adapters=0
  local status
  if [[ -n "$(normalized_csv_items "$RELEASE_GATE_ADAPTERS")" ]]; then
    explicit_adapters=1
  fi
  IFS=',' read -ra adapter_list <<<"$adapters"
  for adapter in "${adapter_list[@]}"; do
    dispatch_release_gate_adapter "$phase" "$adapter" "$explicit_adapters"
    status=$?
    if (( status != 0 )); then
      return "$status"
    fi
  done
}

validate_keyword_dataset_scope_gate() {
  local explicit_adapters="${1:-0}"
  if [[ "$explicit_adapters" == "1" ]] && [[ -z "$(keyword_reindex_args)" ]]; then
    echo "Configure OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS or --keyword-reindex-all-active for release gate adapter keyword_dataset_scope." >&2
    return 2
  fi
}

run_keyword_dataset_scope_gate() {
  local keyword_args
  keyword_args="$(keyword_reindex_args)"
  if [[ -z "$keyword_args" ]]; then
    echo "Configure OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS or --keyword-reindex-all-active for release gate adapter keyword_dataset_scope." >&2
    return 2
  fi
  run_shell_step \
    "Rebuild keyword search index for dataset-scoped release gate" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m open_alm_api.backfill_keyword_search${keyword_args}"
  run_shell_step \
    "Smoke dataset-scoped keyword search release gate" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m open_alm_api.smoke_keyword_dataset_scope${keyword_args}"
}

main() {
  while (($#)); do
    case "$1" in
      --)
        ;;
      --dry-run)
        DRY_RUN=1
        ;;
      --keyword-reindex-all-active)
        KEYWORD_REINDEX_ALL_ACTIVE=1
        ;;
      --tls-expiry-break-glass)
        TLS_EXPIRY_BREAK_GLASS=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage
        exit 2
        ;;
    esac
    shift
  done

  if (( TLS_EXPIRY_BREAK_GLASS )); then
    echo "[prod-deploy] WARNING: one-shot TLS expiry break-glass enabled; the 30-day window is reduced to 0 days for this invocation only." >&2
    echo "[prod-deploy] WARNING: certificate trust, hostname, required SANs, and actual expiry remain fail-closed." >&2
  fi

  acquire_prod_deploy_lock
  trap 'cleanup_prod_deploy "$?"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  require_prod_checkout
  validate_release_gate_configuration

  local timestamp backup_dir backup_file post_activation_status
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="$BACKUP_ROOT/$timestamp"
  backup_file="$backup_dir/postgres.dump"

  print_git_state
  printf '[prod-deploy] backup directory: %s\n' "$backup_dir"

  run_prod_tls_preflight
  run_step "Install locked production dependencies" pnpm install --frozen-lockfile
  run_shell_step \
    "Sync production API Python dependencies" \
    "cd '$ROOT_DIR/apps/api' && uv sync --python 3.12 --frozen --no-dev"
  run_shell_step \
    "Sync production worker Python dependencies" \
    "cd '$ROOT_DIR/apps/worker' && uv sync --python 3.12 --frozen --no-dev"
  run_shell_step \
    "Validate Alembic revision graph" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python '$ROOT_DIR/scripts/check-alembic-state.py' --graph-only"
  run_step "Create backup directory" install -d -m 700 "$BACKUP_ROOT" "$backup_dir"
  run_frontend_build_step "$timestamp"
  run_step \
    "Install production systemd units before migration quiesce" \
    bash "$ROOT_DIR/scripts/prod-systemd.sh" install
  if (( ! DRY_RUN )); then
    SEARCH_WRITERS_QUIESCED=1
    API_STOPPED=1
  fi
  run_step \
    "Quiesce all production writer units before rollback backup and database migration" \
    bash "$ROOT_DIR/scripts/prod-systemd.sh" quiesce-search-writers
  run_postgres_backup_step "$backup_file"
  run_shell_step \
    "Run Alembic migrations" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 alembic upgrade head"
  run_shell_step \
    "Verify Alembic database revision" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python '$ROOT_DIR/scripts/check-alembic-state.py'"
  run_shell_step \
    "Fence and republish patent prior-art jobs onto the protected queue" \
    "cd '$ROOT_DIR/apps/api' && OPEN_ALM_API_AUTO_MIGRATE=0 uv run --python 3.12 python scripts/reconcile_patent_prior_art_queue.py"
  run_release_gates pre_activate
  if (( ! DRY_RUN )); then
    ACTIVATION_STARTED=1
  fi
  if ! promote_frontend_build_step; then
    return 1
  fi
  run_step "Restart production systemd units" bash "$ROOT_DIR/scripts/prod-systemd.sh" restart
  if (( ! DRY_RUN )); then
    SEARCH_WRITERS_QUIESCED=0
    API_STOPPED=0
  fi
  run_prod_smoke_step "Wait for production smoke checks after activation"
  printf '\n[prod-deploy] Monitor this console until post-activation gates and final smoke complete.\n'
  if run_release_gates post_activate; then
    :
  else
    post_activation_status=$?
    echo "[prod-deploy] Post-activation release gate failed. Production services remain active, but this deployment is not complete. Preserve this console log and investigate the reported reason." >&2
    return "$post_activation_status"
  fi
  run_prod_smoke_step "Wait for final production smoke checks"

  printf '\n[prod-deploy] deployment flow complete\n'
  printf '[prod-deploy] backup: %s\n' "$backup_file"
  trap - EXIT INT TERM
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
