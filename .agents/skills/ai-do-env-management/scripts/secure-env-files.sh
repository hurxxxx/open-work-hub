#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
REPO_NAME="${AI_DO_GITLAB_REPO:-dwdcc/ai-do}"
PROJECT_PATH="${AI_DO_GITLAB_PROJECT_PATH:-dwdcc%2Fai-do}"

usage() {
  cat <<'EOF'
Usage: secure-env-files.sh {status|upload|download} [options]

Options:
  --profile local|production     Select the canonical Secure File profile.
  --secure-file-name NAME        Override the Secure File name.
  --source PATH                  Local file for status/upload.
  --target PATH                  Local path for download.
  --repo OWNER/REPO              GitLab repository for glab securefile commands.
  --project-path GROUP%2FREPO    URL-encoded GitLab project path for metadata API.
  --dry-run                      Print intended write actions without changing files.
  -h, --help                     Show this help.

Profiles:
  production -> .env.production, default source /projects/ai-do/prod/.env
  local      -> .env.local,      default source $PWD/.env.local

The script never prints env values. It reports file names, ids, key counts,
checksums, and drift status only.
EOF
}

die() {
  echo "[secure-env] $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

hash_file() {
  local file="${1:?file is required}"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  else
    shasum -a 256 "$file" | awk '{print $1}'
  fi
}

key_count() {
  local file="${1:?file is required}"
  awk '
    /^[[:space:]]*($|#)/ { next }
    {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      eq = index(line, "=")
      if (eq == 0) next
      key = substr(line, 1, eq - 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      if (key ~ /^[A-Za-z_][A-Za-z0-9_]*$/) print key
    }
  ' "$file" | sort -u | wc -l | tr -d ' '
}

secure_file_name_for_profile() {
  case "$1" in
    production) echo ".env.production" ;;
    local) echo ".env.local" ;;
    "") die "--profile or --secure-file-name is required" ;;
    *) die "unknown profile: $1" ;;
  esac
}

default_source_for_profile() {
  case "$1" in
    production) echo "/projects/ai-do/prod/.env" ;;
    local) echo "$ROOT_DIR/.env.local" ;;
    *) echo "" ;;
  esac
}

default_target_for_profile() {
  case "$1" in
    production) echo "/projects/ai-do/prod/.env" ;;
    local) echo "$ROOT_DIR/.env.local" ;;
    *) echo "" ;;
  esac
}

require_glab() {
  require_command glab
  glab auth status >/dev/null 2>&1 || die "glab is not authenticated"
}

remote_rows() {
  local name="${1:?name is required}"
  glab api "projects/${PROJECT_PATH}/secure_files?per_page=100" |
    SECURE_FILE_NAME="$name" python3 -c '
import json
import os
import sys

name = os.environ["SECURE_FILE_NAME"]
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as exc:
    raise SystemExit(f"invalid GitLab Secure Files JSON: {exc}") from exc

for item in data:
    if item.get("name") == name:
        print(
            "\t".join(
                str(item.get(field) or "")
                for field in ("id", "checksum", "created_at")
            )
        )
'
}

load_remote_rows() {
  local name="${1:?name is required}"
  mapfile -t REMOTE_ROWS < <(remote_rows "$name")
}

print_status() {
  local name="${1:?name is required}"
  local source="${2:-}"
  load_remote_rows "$name"

  local local_sha="missing"
  local keys="missing"
  if [[ -n "$source" && -f "$source" ]]; then
    local_sha="$(hash_file "$source")"
    keys="$(key_count "$source")"
  fi

  local remote_count="${#REMOTE_ROWS[@]}"
  local remote_id="missing"
  local remote_sha="missing"
  local created_at="missing"
  if (( remote_count > 0 )); then
    IFS=$'\t' read -r remote_id remote_sha created_at <<<"${REMOTE_ROWS[0]}"
  fi

  local status="unknown"
  if [[ "$local_sha" == "missing" && "$remote_sha" == "missing" ]]; then
    status="missing_local_and_remote"
  elif [[ "$local_sha" == "missing" ]]; then
    status="missing_local"
  elif [[ "$remote_sha" == "missing" ]]; then
    status="missing_remote"
  elif (( remote_count > 1 )); then
    status="duplicate_remote"
  elif [[ "$local_sha" == "$remote_sha" ]]; then
    status="match"
  else
    status="different"
  fi

  printf '[secure-env] file=%s source=%s keys=%s local_sha256=%s remote_count=%s remote_id=%s remote_checksum=%s created_at=%s status=%s\n' \
    "$name" "${source:-unset}" "$keys" "$local_sha" "$remote_count" "$remote_id" "$remote_sha" "$created_at" "$status"
}

remove_remote_matches() {
  local name="${1:?name is required}"
  local dry_run="${2:?dry_run is required}"
  load_remote_rows "$name"
  local row id checksum created_at
  for row in "${REMOTE_ROWS[@]}"; do
    IFS=$'\t' read -r id checksum created_at <<<"$row"
    if [[ "$dry_run" == "1" ]]; then
      echo "[secure-env] dry-run remove id=$id file=$name checksum=$checksum"
    else
      echo "[secure-env] removing id=$id file=$name checksum=$checksum"
      glab securefile remove "$id" -y -R "$REPO_NAME" >/dev/null
    fi
  done
}

upload_file() {
  local name="${1:?name is required}"
  local source="${2:?source is required}"
  local dry_run="${3:?dry_run is required}"
  [[ -f "$source" ]] || die "source file not found: $source"

  local sha keys
  sha="$(hash_file "$source")"
  keys="$(key_count "$source")"
  echo "[secure-env] upload candidate file=$name source=$source keys=$keys sha256=$sha"
  remove_remote_matches "$name" "$dry_run"

  if [[ "$dry_run" == "1" ]]; then
    echo "[secure-env] dry-run create file=$name source=$source"
    return 0
  fi

  glab securefile create "$name" "$source" -R "$REPO_NAME" >/dev/null
  print_status "$name" "$source"
}

download_file() {
  local name="${1:?name is required}"
  local target="${2:?target is required}"
  local dry_run="${3:?dry_run is required}"
  load_remote_rows "$name"
  (( ${#REMOTE_ROWS[@]} == 1 )) || die "expected exactly one remote Secure File named $name; found ${#REMOTE_ROWS[@]}"

  local id checksum created_at
  IFS=$'\t' read -r id checksum created_at <<<"${REMOTE_ROWS[0]}"
  echo "[secure-env] download candidate file=$name id=$id checksum=$checksum target=$target"
  if [[ "$dry_run" == "1" ]]; then
    echo "[secure-env] dry-run download file=$name target=$target"
    return 0
  fi

  local tmp_dir tmp_file backup
  tmp_dir="$(mktemp -d)"
  tmp_file="$tmp_dir/$name"
  trap 'rm -rf "$tmp_dir"' RETURN
  glab securefile download "$id" --path "$tmp_file" -R "$REPO_NAME" >/dev/null

  mkdir -p "$(dirname "$target")"
  if [[ -f "$target" ]]; then
    backup="${target}.backup-$(date +%Y%m%d-%H%M%S)"
    cp "$target" "$backup"
    chmod 600 "$backup"
    echo "[secure-env] backed up existing target to $backup"
  fi
  install -m 600 "$tmp_file" "$target"
  echo "[secure-env] installed file=$name target=$target sha256=$(hash_file "$target") keys=$(key_count "$target")"
}

COMMAND="${1:-}"
if [[ -z "$COMMAND" ]]; then
  usage
  exit 2
fi
if [[ "$COMMAND" == "-h" || "$COMMAND" == "--help" || "$COMMAND" == "help" ]]; then
  usage
  exit 0
fi
shift || true

PROFILE=""
SECURE_FILE_NAME=""
SOURCE=""
TARGET=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --secure-file-name)
      SECURE_FILE_NAME="${2:-}"
      shift 2
      ;;
    --source)
      SOURCE="${2:-}"
      shift 2
      ;;
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --repo)
      REPO_NAME="${2:-}"
      shift 2
      ;;
    --project-path)
      PROJECT_PATH="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if [[ -z "$SECURE_FILE_NAME" ]]; then
  SECURE_FILE_NAME="$(secure_file_name_for_profile "$PROFILE")"
fi
if [[ -z "$SOURCE" ]]; then
  SOURCE="$(default_source_for_profile "$PROFILE")"
fi
if [[ -z "$TARGET" ]]; then
  TARGET="$(default_target_for_profile "$PROFILE")"
fi

case "$COMMAND" in
  status)
    require_glab
    print_status "$SECURE_FILE_NAME" "$SOURCE"
    ;;
  upload)
    require_glab
    upload_file "$SECURE_FILE_NAME" "$SOURCE" "$DRY_RUN"
    ;;
  download)
    require_glab
    download_file "$SECURE_FILE_NAME" "$TARGET" "$DRY_RUN"
    ;;
  *)
    die "unknown command: $COMMAND"
    ;;
esac
