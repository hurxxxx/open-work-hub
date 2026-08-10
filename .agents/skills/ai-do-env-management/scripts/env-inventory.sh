#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-}"
if [[ -z "$ROOT_DIR" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
fi
ROOT_DIR="$(cd "$ROOT_DIR" && pwd)"

PROJECT_PATH="${AI_DO_GITLAB_PROJECT_PATH:-dwdcc%2Fai-do}"
REPO_NAME="${AI_DO_GITLAB_REPO:-dwdcc/ai-do}"

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
      if (key != "") print key
    }
  ' "$file"
}

print_env_file_summary() {
  local label="${1:?label is required}"
  local file="${2:?file is required}"
  if [[ ! -f "$file" ]]; then
    printf '[env] %-10s missing: %s\n' "$label" "$file"
    return 0
  fi

  local tmp
  tmp="$(mktemp)"
  parse_keys "$file" >"$tmp"
  local total unique duplicates
  total="$(wc -l <"$tmp" | tr -d ' ')"
  unique="$(sort -u "$tmp" | wc -l | tr -d ' ')"
  duplicates="$(sort "$tmp" | uniq -d | paste -sd ',' -)"
  if [[ -n "$duplicates" ]]; then
    printf '[env] %-10s keys=%s unique=%s duplicates=%s file=%s\n' "$label" "$total" "$unique" "$duplicates" "$file"
  else
    printf '[env] %-10s keys=%s unique=%s duplicates=0 file=%s\n' "$label" "$total" "$unique" "$file"
  fi
  rm -f "$tmp"
}

print_json_projection() {
  local kind="${1:?kind is required}"
  python3 -c '
import json
import sys

kind = sys.argv[1]
data = json.load(sys.stdin)
if kind == "variables":
    rows = [
        {
            "key": item.get("key"),
            "variable_type": item.get("variable_type"),
            "environment_scope": item.get("environment_scope"),
            "protected": item.get("protected"),
            "masked": item.get("masked"),
            "hidden": item.get("hidden"),
            "raw": item.get("raw"),
        }
        for item in data
    ]
    rows.sort(key=lambda row: str(row.get("key")))
elif kind == "secure_files":
    rows = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "created_at": item.get("created_at"),
            "checksum": item.get("checksum"),
        }
        for item in data
    ]
    rows.sort(key=lambda row: str(row.get("name")))
else:
    rows = data
print(json.dumps(rows, indent=2, ensure_ascii=True))
' "$kind"
}

print_gitlab_metadata() {
  if ! command -v glab >/dev/null 2>&1; then
    echo "[gitlab] glab not installed; skipping GitLab metadata"
    return 0
  fi
  if ! glab auth status >/dev/null 2>&1; then
    echo "[gitlab] glab is not authenticated; skipping GitLab metadata"
    return 0
  fi

  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  echo "[gitlab] CI/CD variables metadata for $REPO_NAME (values omitted)"
  if glab api "projects/${PROJECT_PATH}/variables?per_page=100" >"$tmp"; then
    print_json_projection variables <"$tmp"
  else
    echo "[gitlab] unable to list CI/CD variables"
  fi

  echo "[gitlab] Secure Files metadata for $REPO_NAME (contents omitted)"
  if glab api "projects/${PROJECT_PATH}/secure_files?per_page=100" >"$tmp"; then
    print_json_projection secure_files <"$tmp"
  else
    echo "[gitlab] unable to list Secure Files"
  fi
}

print_env_file_summary current "$ROOT_DIR/.env"
print_env_file_summary example "$ROOT_DIR/.env.example"
print_env_file_summary dev "$ROOT_DIR/../dev/.env"
print_env_file_summary prod "$ROOT_DIR/../prod/.env"

if [[ -f "$ROOT_DIR/scripts/check-env-contract.py" ]]; then
  (cd "$ROOT_DIR" && python3 scripts/check-env-contract.py)
else
  echo "[env-contract] missing scripts/check-env-contract.py"
fi

print_gitlab_metadata
