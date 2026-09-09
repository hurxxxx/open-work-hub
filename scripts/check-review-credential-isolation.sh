#!/usr/bin/env bash
# Run as the installation administrator, after provisioning the two service users.
set -Eeuo pipefail
runner_user="${1:-gitlab-runner}"
evidence_home="$(getent passwd owh-review-evidence | cut -d: -f6)"
[[ -n "$evidence_home" && "$evidence_home" != / ]] || exit 2
fixture="$(sudo -H -u owh-review-evidence mktemp "$evidence_home/access-probe.XXXXXX")"
trap 'sudo -H -u owh-review-evidence rm -f -- "$fixture"' EXIT
printf 'synthetic-credential-for-access-test\n' | sudo -H -u owh-review-evidence tee "$fixture" >/dev/null
sudo -H -u "$runner_user" python3 - "$fixture" <<'PY'
import sys
try:
    with open(sys.argv[1], encoding='utf-8') as file:
        file.read()
except PermissionError:
    pass
else:
    raise SystemExit('FAIL: Runner can read evidence credentials')
PY
if sudo -H -u "$runner_user" sudo -n -H -u owh-review-evidence /usr/bin/cat "$fixture" >/dev/null 2>&1; then
  echo 'FAIL: Runner has unrestricted evidence-account sudo access' >&2
  exit 1
fi
if sudo -H -u "$runner_user" sudo -n -H -u owh-review-evidence /usr/local/libexec/open-work-hub-review-evidence unexpected-argument >/dev/null 2>&1; then
  echo 'FAIL: evidence helper accepted command arguments' >&2
  exit 1
fi
sudo -H -u "$runner_user" test ! -r "$evidence_home/.config/glab-cli/config.yml"
echo 'PASS: synthetic credential read denied; evidence sudo boundary enforced.'
