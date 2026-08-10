#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --host <ssh-host> --profile <profile> [--verify-haproxy]" >&2
}

host=""
profile=""
verify_haproxy="0"
while (($#)); do
  case "$1" in
    --host)
      host="${2:-}"
      shift 2
      ;;
    --profile)
      profile="${2:-}"
      shift 2
      ;;
    --node)
      # Compatibility for the existing two DGX deployment commands.
      profile="dgx-spark-${2:-}"
      shift 2
      ;;
    --verify-haproxy)
      verify_haproxy="1"
      shift
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$host" || ! "$profile" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  usage
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
watchdog="${script_dir}/system/open-alm-local-ai-backend-watchdog"
service="${script_dir}/system/open-alm-local-ai-backend-watchdog.service"
timer="${script_dir}/system/open-alm-local-ai-backend-watchdog.timer"
resource_guard="${script_dir}/system/open-alm-local-ai-backend-resource-guard.conf"
node_env="${script_dir}/system/open-alm-local-ai-backend-watchdog-${profile}.env"

for source_file in "$watchdog" "$service" "$timer" "$resource_guard" "$node_env"; do
  if [[ ! -f "$source_file" ]]; then
    echo "missing deployment asset: $source_file" >&2
    exit 1
  fi
done

remote_dir="$(ssh "$host" 'mktemp -d /tmp/open-alm-local-ai-guard.XXXXXX')"
if [[ ! "$remote_dir" =~ ^/tmp/open-alm-local-ai-guard\.[A-Za-z0-9]+$ ]]; then
  echo "unexpected remote staging path: $remote_dir" >&2
  exit 1
fi

cleanup() {
  ssh "$host" "rm -f -- '$remote_dir'/open-alm-local-ai-backend-*; rmdir -- '$remote_dir'" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp -q "$watchdog" "$service" "$timer" "$resource_guard" \
  "${host}:${remote_dir}/"
scp -q "$node_env" \
  "${host}:${remote_dir}/open-alm-local-ai-backend-watchdog-profile.env"

ssh "$host" bash -s -- "$remote_dir" "$verify_haproxy" <<'REMOTE'
set -euo pipefail
remote_dir="$1"
verify_haproxy="$2"

sudo install -o root -g root -m 0755 \
  "$remote_dir/open-alm-local-ai-backend-watchdog" \
  /usr/local/sbin/open-alm-local-ai-backend-watchdog
sudo install -o root -g root -m 0644 \
  "$remote_dir/open-alm-local-ai-backend-watchdog.service" \
  /etc/systemd/system/open-alm-local-ai-backend-watchdog.service
sudo install -o root -g root -m 0644 \
  "$remote_dir/open-alm-local-ai-backend-watchdog.timer" \
  /etc/systemd/system/open-alm-local-ai-backend-watchdog.timer
sudo install -d -o root -g root -m 0755 \
  /etc/systemd/system/open-alm-local-ai-backend.service.d \
  /etc/open-alm
sudo install -o root -g root -m 0644 \
  "$remote_dir/open-alm-local-ai-backend-resource-guard.conf" \
  /etc/systemd/system/open-alm-local-ai-backend.service.d/resource-guard.conf
sudo install -o root -g root -m 0644 \
  "$remote_dir/open-alm-local-ai-backend-watchdog-profile.env" \
  /etc/open-alm/inference-gateway-watchdog.env

sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/open-alm-local-ai-backend-watchdog.service \
  /etc/systemd/system/open-alm-local-ai-backend-watchdog.timer
sudo systemctl enable --now open-alm-local-ai-backend-watchdog.timer
sudo systemctl start open-alm-local-ai-backend-watchdog.service
systemctl is-active open-alm-local-ai-backend.service
systemctl is-active open-alm-local-ai-backend-watchdog.timer
systemctl show open-alm-local-ai-backend-watchdog.service -p Result -p ExecMainStatus

if [[ "$verify_haproxy" == "1" ]]; then
  sudo grep -Fq 'timeout queue 30s' /etc/haproxy/haproxy.cfg
  sudo grep -Fq \
    'default-server inter 5s fall 2 rise 1 maxconn 4 maxqueue 16' \
    /etc/haproxy/haproxy.cfg
  sudo haproxy -c -f /etc/haproxy/haproxy.cfg
fi
REMOTE
