#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: local-env-files.sh {status|install} --source PATH --target PATH [options]

Options:
  --force    Allow replacing a differing target; a mode-0600 backup is created.
  --dry-run  Report the intended install without writing.
  -h, --help Show this help.

The script reports only key names, counts, modes, and checksums. It never prints values.
It refuses to overwrite a Git-tracked target.
EOF
}

die() {
  echo "[local-env] $*" >&2
  exit 1
}

hash_file() {
  local file="${1:?file is required}"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  else
    shasum -a 256 "$file" | awk '{print $1}'
  fi
}

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
  ' "$file" | sort -u
}

file_mode() {
  local file="${1:?file is required}"
  stat -c '%a' "$file" 2>/dev/null || stat -f '%Lp' "$file"
}

relative_to_root() {
  python3 - "$ROOT_DIR" "$1" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = Path(sys.argv[2]).resolve()
try:
    print(path.relative_to(root))
except ValueError:
    pass
PY
}

refuse_tracked_target() {
  local target="${1:?target is required}"
  local relative
  relative="$(relative_to_root "$target")"
  if [[ -n "$relative" ]] && git -C "$ROOT_DIR" ls-files --error-unmatch -- "$relative" >/dev/null 2>&1; then
    die "refusing to overwrite Git-tracked target: $target"
  fi
}

print_status() {
  local source="${1:?source is required}"
  local target="${2:?target is required}"
  [[ -f "$source" ]] || die "source file not found: $source"

  local source_keys target_keys source_count source_sha target_count target_sha target_mode status
  source_keys="$(mktemp)"
  target_keys="$(mktemp)"
  parse_keys "$source" >"$source_keys"
  source_count="$(wc -l <"$source_keys" | tr -d ' ')"
  source_sha="$(hash_file "$source")"

  if [[ ! -f "$target" ]]; then
    printf '[local-env] status=missing_target source=%s source_keys=%s source_sha256=%s target=%s\n' \
      "$source" "$source_count" "$source_sha" "$target"
    rm -f "$source_keys" "$target_keys"
    return 0
  fi

  parse_keys "$target" >"$target_keys"
  target_count="$(wc -l <"$target_keys" | tr -d ' ')"
  target_sha="$(hash_file "$target")"
  target_mode="$(file_mode "$target")"
  if [[ "$source_sha" == "$target_sha" ]]; then
    status="match"
  else
    status="different"
  fi
  printf '[local-env] status=%s source=%s source_keys=%s source_sha256=%s target=%s target_keys=%s target_sha256=%s target_mode=%s\n' \
    "$status" "$source" "$source_count" "$source_sha" "$target" "$target_count" "$target_sha" "$target_mode"

  local only_source only_target
  only_source="$(comm -23 "$source_keys" "$target_keys" | paste -sd ',' -)"
  only_target="$(comm -13 "$source_keys" "$target_keys" | paste -sd ',' -)"
  printf '[local-env] only_source_keys=%s only_target_keys=%s\n' "${only_source:-0}" "${only_target:-0}"
  rm -f "$source_keys" "$target_keys"
}

COMMAND="${1:-}"
if [[ -z "$COMMAND" || "$COMMAND" == "-h" || "$COMMAND" == "--help" || "$COMMAND" == "help" ]]; then
  usage
  [[ -n "$COMMAND" ]] && exit 0
  exit 2
fi
shift

SOURCE=""
TARGET=""
FORCE=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="${2:?--source requires a path}"; shift 2 ;;
    --target) TARGET="${2:?--target requires a path}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n "$SOURCE" ]] || die "--source is required"
[[ -n "$TARGET" ]] || die "--target is required"
[[ ! -L "$SOURCE" && ! -L "$TARGET" ]] || die "source and target must not be symbolic links"

case "$COMMAND" in
  status)
    print_status "$SOURCE" "$TARGET"
    ;;
  install)
    [[ -f "$SOURCE" ]] || die "source file not found: $SOURCE"
    refuse_tracked_target "$TARGET"
    if [[ -f "$TARGET" ]] && [[ "$(hash_file "$SOURCE")" != "$(hash_file "$TARGET")" ]] && (( ! FORCE )); then
      die "target differs; rerun with --force only when replacement is explicitly intended"
    fi
    echo "[local-env] install source=$SOURCE target=$TARGET keys=$(parse_keys "$SOURCE" | wc -l | tr -d ' ') sha256=$(hash_file "$SOURCE") dry_run=$DRY_RUN"
    if (( DRY_RUN )); then
      exit 0
    fi
    mkdir -p "$(dirname "$TARGET")"
    if [[ -f "$TARGET" ]] && [[ "$(hash_file "$SOURCE")" != "$(hash_file "$TARGET")" ]]; then
      backup="${TARGET}.backup-$(date +%Y%m%d-%H%M%S)"
      install -m 600 "$TARGET" "$backup"
      echo "[local-env] backup=$backup mode=$(file_mode "$backup")"
    fi
    install -m 600 "$SOURCE" "$TARGET"
    echo "[local-env] installed target=$TARGET mode=$(file_mode "$TARGET") sha256=$(hash_file "$TARGET")"
    ;;
  *)
    die "unknown command: $COMMAND"
    ;;
esac
