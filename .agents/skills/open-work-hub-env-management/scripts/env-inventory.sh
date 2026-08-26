#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
INCLUDE_GITLAB=0

usage() {
  echo "Usage: env-inventory.sh [--root PATH] [--gitlab]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_DIR="$(cd "${2:?--root requires a path}" && pwd)"
      shift 2
      ;;
    --gitlab)
      INCLUDE_GITLAB=1
      shift
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
done

parse_keys() {
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
  ' "$file"
}

print_env_file_summary() {
  local label="${1:?label is required}"
  local file="${2:?file is required}"
  if [[ ! -f "$file" ]]; then
    printf '[env] %-8s missing file=%s\n' "$label" "$file"
    return 0
  fi

  local key_file total unique duplicates
  key_file="$(mktemp)"
  parse_keys "$file" >"$key_file"
  total="$(wc -l <"$key_file" | tr -d ' ')"
  unique="$(sort -u "$key_file" | wc -l | tr -d ' ')"
  duplicates="$(sort "$key_file" | uniq -d | paste -sd ',' -)"
  rm -f "$key_file"

  printf '[env] %-8s keys=%s unique=%s duplicates=%s file=%s\n' \
    "$label" "$total" "$unique" "${duplicates:-0}" "$file"
}

print_env_file_summary example "$ROOT_DIR/.env.example"
print_env_file_summary runtime "$ROOT_DIR/.env"
print_env_file_summary local "$ROOT_DIR/.env.local"

if [[ -f "$ROOT_DIR/scripts/check-env-contract.py" ]]; then
  (cd "$ROOT_DIR" && python3 scripts/check-env-contract.py)
else
  echo "[env-contract] missing scripts/check-env-contract.py"
fi

if (( INCLUDE_GITLAB )); then
  if ! command -v glab >/dev/null 2>&1; then
    echo "[gitlab] glab not installed; CI metadata skipped"
  elif ! glab auth status >/dev/null 2>&1; then
    echo "[gitlab] glab not authenticated; CI metadata skipped"
  else
    echo "[gitlab] CI variable metadata (values redacted)"
    glab variable list --per-page 100 --output json \
      --jq 'map({key, variable_type, environment_scope, protected, masked, raw})'
    echo "[gitlab] Secure file metadata (contents unavailable)"
    glab securefile list --per-page 100
  fi
fi
