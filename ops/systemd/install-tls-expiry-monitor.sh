#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: ops/systemd/install-tls-expiry-monitor.sh [--apply] [--replace]

Without --apply, validates the assets and prints a non-mutating install plan.
--replace allows --apply to back up and replace differing installed assets.
EOF
}

apply=0
replace=0
while (($#)); do
  case "$1" in
    --apply)
      apply=1
      ;;
    --replace)
      replace=1
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

if (( replace && ! apply )); then
  echo "--replace requires --apply." >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd -- "$script_dir/../.." && pwd)"
checker="$root_dir/scripts/check_live_tls_expiry.py"
service="$script_dir/system/ai-do-tls-expiry-check.service"
timer="$script_dir/system/ai-do-tls-expiry-check.timer"

for source_file in "$checker" "$service" "$timer"; do
  if [[ ! -f "$source_file" ]]; then
    echo "Missing deployment asset: $source_file" >&2
    exit 1
  fi
done

CHECKER_SOURCE="$checker" python3 - <<'PY'
import os
from pathlib import Path

source = Path(os.environ["CHECKER_SOURCE"])
compile(source.read_text(encoding="utf-8"), str(source), "exec")
PY
systemd-analyze verify "$service" "$timer"

checker_target="/usr/local/libexec/ai-do/check_live_tls_expiry.py"
service_target="/etc/systemd/system/ai-do-tls-expiry-check.service"
timer_target="/etc/systemd/system/ai-do-tls-expiry-check.timer"

if (( ! apply )); then
  cat <<EOF
[tls-expiry-monitor] dry-run: assets validated; no files or systemd state changed.
[tls-expiry-monitor] install targets:
  $checker_target
  $service_target
  $timer_target
[tls-expiry-monitor] rerun with --apply to install and enable ai-do-tls-expiry-check.timer.
EOF
  exit 0
fi

sudo -n true

sources=("$checker" "$service" "$timer")
targets=("$checker_target" "$service_target" "$timer_target")
for index in "${!sources[@]}"; do
  if sudo -n test -e "${targets[$index]}" \
    && ! sudo -n cmp -s "${sources[$index]}" "${targets[$index]}" \
    && (( ! replace )); then
    echo "Refusing to overwrite differing installed asset: ${targets[$index]}" >&2
    echo "Review the diff, then rerun with --apply --replace to back it up first." >&2
    exit 1
  fi
done

backup_dir=""
if (( replace )); then
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="/var/backups/ai-do/tls-expiry-monitor/$timestamp"
  sudo -n install -d -o root -g root -m 0700 "$backup_dir"
  for index in "${!sources[@]}"; do
    if sudo -n test -e "${targets[$index]}" \
      && ! sudo -n cmp -s "${sources[$index]}" "${targets[$index]}"; then
      sudo -n cp --preserve=all -- "${targets[$index]}" "$backup_dir/"
    fi
  done
fi

sudo -n install -d -o root -g root -m 0755 /usr/local/libexec/ai-do
sudo -n install -o root -g root -m 0644 "$checker" "$checker_target"
sudo -n install -o root -g root -m 0644 "$service" "$service_target"
sudo -n install -o root -g root -m 0644 "$timer" "$timer_target"
sudo -n systemctl daemon-reload
sudo -n systemd-analyze verify "$service_target" "$timer_target"
sudo -n systemctl enable --now ai-do-tls-expiry-check.timer
sudo -n systemctl start ai-do-tls-expiry-check.service
sudo -n systemctl is-enabled --quiet ai-do-tls-expiry-check.timer
sudo -n systemctl is-active --quiet ai-do-tls-expiry-check.timer
sudo -n systemctl show ai-do-tls-expiry-check.service \
  --property=Result \
  --property=ExecMainStatus \
  --no-pager

echo "[tls-expiry-monitor] installed and verified."
if [[ -n "$backup_dir" ]]; then
  echo "[tls-expiry-monitor] replaced assets were backed up under $backup_dir."
fi
