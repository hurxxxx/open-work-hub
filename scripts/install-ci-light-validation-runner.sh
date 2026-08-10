#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_path="dwdcc/ai-do"
runner_name="ai-do-validation-light-docker-runner"
validation_tag="ai-do-validation-light"
validation_image="ai-do-validation:node25-python312-pg18-api-a3e8c22a3552-worker-3149583cef20-node-e7c57b3bacf9-484482bced42"
validation_image_id="sha256:89345c7907b296ea557a61e9a4c956ee9915c3fb9b611b3923f36bcc4c65d526"
gitlab_runner_version="18.11.2"
helper_image_repository="registry.gitlab.com/gitlab-org/gitlab-runner/gitlab-runner-helper"
helper_image_manifest_digest="sha256:39e9155b72aff010f55a8bbfdb94fedeb0824de18612795d8b901ac4b42d99f5"
helper_image_local_id="sha256:39e9155b72aff010f55a8bbfdb94fedeb0824de18612795d8b901ac4b42d99f5"
helper_image="${helper_image_repository}:x86_64-v${gitlab_runner_version}"
helper_image_pinned="${helper_image_repository}@${helper_image_manifest_digest}"
validation_network="ai-do-validation-light"
validation_subnet="172.29.251.0/24"
validation_gateway="172.29.251.1"
egress_source="$repo_root/ops/ci/ai-do-ci-validation-egress.sh"
egress_service_source="$repo_root/ops/ci/ai-do-ci-validation-egress.service"
egress_target="/usr/local/sbin/ai-do-ci-validation-egress"
egress_service_target="/etc/systemd/system/ai-do-ci-validation-egress.service"
runner_config_file="${GITLAB_RUNNER_CONFIG_FILE:-/home/dwdcc/.gitlab-runner/config.toml}"
current_branch="$(git -C "$repo_root" branch --show-current)"

if [[ "$current_branch" != "dev" ]]; then
  echo "Refusing to install the light validation runner from branch ${current_branch:-<detached>}; use clean dev after merge." >&2
  exit 2
fi
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "Refusing to install the light validation runner from a dirty checkout." >&2
  exit 2
fi
source "$repo_root/scripts/ci/control-plane-lock.sh"
acquire_ai_do_ci_control_plane_lock

git -C "$repo_root" fetch --quiet origin dev
local_head="$(git -C "$repo_root" rev-parse HEAD)"
remote_head="$(git -C "$repo_root" rev-parse origin/dev)"
if [[ "$local_head" != "$remote_head" ]]; then
  echo "Refusing to install the light validation runner: local dev is not origin/dev (${local_head} != ${remote_head})." >&2
  exit 2
fi
assert_source_freshness() {
  local current_head current_remote
  if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
    echo "Light validation runner source checkout changed during installation." >&2
    return 1
  fi
  git -C "$repo_root" fetch --quiet origin dev
  current_head="$(git -C "$repo_root" rev-parse HEAD)"
  current_remote="$(git -C "$repo_root" rev-parse origin/dev)"
  if [[ "$current_head" != "$local_head" || "$current_remote" != "$local_head" ]]; then
    echo "Light validation runner source SHA changed during installation." >&2
    return 1
  fi
}

for command_name in awk docker gitlab-runner glab jq python3 sed sha256sum sudo systemctl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Refusing to install the light validation runner: ${command_name} is unavailable." >&2
    exit 2
  fi
done
if ! sudo -n true; then
  echo "Passwordless sudo is required to install the validation egress policy." >&2
  exit 2
fi
actual_gitlab_runner_version="$(
  gitlab-runner --version |
    awk '/^Version:/ {print $2; exit}'
)"
if [[ "$actual_gitlab_runner_version" != "$gitlab_runner_version" ]]; then
  echo "GitLab Runner ${gitlab_runner_version} is required for the pinned helper image." >&2
  exit 2
fi

bash -n "$repo_root/ops/ci/ai-do-ci-validation-egress.sh"
bash "$repo_root/scripts/codex-review-ci.sh" \
  --validate-gitlab-ci-contract "$repo_root/ops/ci/ci-first.gitlab-ci.yml" >/dev/null

project_json="$(glab api "projects/${project_path//\//%2F}")"
project_id="$(jq -r '.id // empty' <<<"$project_json")"
if [[ -z "$project_id" ]]; then
  echo "Refusing to install the light validation runner: GitLab project id was not resolved." >&2
  exit 2
fi
runner_details="$(
  glab api "projects/${project_id}/runners?per_page=100" |
    jq -r '.[].id' |
    while IFS= read -r runner_id; do
      glab api "runners/${runner_id}"
    done |
    jq -s '.'
)"
if [[ "$(
  jq '[.[] | select(
    .description == "ai-do-validation-docker-runner"
    and .status == "online"
    and .tag_list == ["ai-do-validation"]
    and .paused == false
    and .locked == true
    and .run_untagged == false
    and .runner_type == "project_type"
  )] | length' <<<"$runner_details"
)" -ne 1 ]]; then
  echo "Expected exactly one steady-state heavy validation runner before light runner installation." >&2
  exit 2
fi
if [[ "$(
  jq '[.[] | select(
    .description == "ai-do-local-codex-runner"
    and (.status == "online" or .status == "paused")
    and .tag_list == ["codex-local"]
    and (.paused | type) == "boolean"
    and .locked == true
    and .run_untagged == false
    and .runner_type == "project_type"
  )] | length' <<<"$runner_details"
)" -ne 1 ]]; then
  echo "Expected exactly one steady-state Codex runner before light runner installation." >&2
  exit 2
fi
if jq -e --arg description "$runner_name" \
  '.[] | select(.description == $description)' \
  >/dev/null <<<"$runner_details"; then
  echo "Refusing to create a duplicate ${runner_name}." >&2
  exit 2
fi
if gitlab-runner list 2>&1 | grep -F "$runner_name" >/dev/null; then
  echo "Refusing to reuse an existing local GitLab Runner registration named ${runner_name}." >&2
  exit 2
fi
validation_runner_id="$(
  jq -r '
    .[]
    | select(.description == "ai-do-validation-docker-runner")
    | .id
  ' <<<"$runner_details"
)"
codex_runner_id="$(
  jq -r '
    .[]
    | select(.description == "ai-do-local-codex-runner")
    | .id
  ' <<<"$runner_details"
)"
previous_validation_paused="$(
  jq -r '
    .[]
    | select(.description == "ai-do-validation-docker-runner")
    | .paused
  ' <<<"$runner_details"
)"
previous_codex_paused="$(
  jq -r '
    .[]
    | select(.description == "ai-do-local-codex-runner")
    | .paused
  ' <<<"$runner_details"
)"

if [[ "$(docker image inspect --format '{{.Id}}' "$validation_image")" != "$validation_image_id" ]]; then
  echo "The pinned validation image is unavailable locally." >&2
  exit 2
fi
helper_image_metadata="$(docker image inspect "$helper_image")"
if [[ "$(jq -r '.[0].Id' <<<"$helper_image_metadata")" != "$helper_image_local_id" ]] ||
   ! jq -e \
     --arg pinned "$helper_image_pinned" \
     '.[0].RepoDigests | index($pinned) != null' \
     >/dev/null <<<"$helper_image_metadata"; then
  echo "The GitLab Runner helper image does not match its pinned local identity." >&2
  exit 2
fi

runner_id=""
local_registration_created=0
registration_complete=0
runner_config_candidate=""
existing_runners_paused=0
existing_pause_persist=0
cleanup_failed_installation() {
  if [[ "$registration_complete" -eq 0 && -n "$runner_id" ]]; then
    if [[ "$local_registration_created" -eq 1 ]]; then
      gitlab-runner unregister --name "$runner_name" >/dev/null 2>&1 || true
    fi
    glab api --method DELETE "runners/${runner_id}" >/dev/null 2>&1 || true
  fi
  if [[ "$existing_runners_paused" -eq 1 && "$existing_pause_persist" -eq 0 ]]; then
    glab api --method PUT "runners/${validation_runner_id}" \
      --field "paused=${previous_validation_paused}" >/dev/null 2>&1 || true
    glab api --method PUT "runners/${codex_runner_id}" \
      --field "paused=${previous_codex_paused}" >/dev/null 2>&1 || true
  fi
  if [[ -n "$runner_config_candidate" ]]; then
    rm -f "$runner_config_candidate"
  fi
}
trap cleanup_failed_installation EXIT

existing_runners_paused=1
for existing_runner_id in "$validation_runner_id" "$codex_runner_id"; do
  glab api --method PUT "runners/${existing_runner_id}" \
    --field paused=true >/dev/null
  if ! glab api "runners/${existing_runner_id}" |
    jq -e '.paused == true' >/dev/null; then
    echo "Existing CI runner ${existing_runner_id} did not enter paused state." >&2
    exit 2
  fi
done
echo "Waiting 60 seconds for in-flight GitLab long-poll requests to quiesce."
sleep 60
zero_streak=0
for _attempt in $(seq 1 1800); do
  running_total=0
  for existing_runner_id in "$validation_runner_id" "$codex_runner_id"; do
    if ! glab api "runners/${existing_runner_id}" |
      jq -e '.paused == true' >/dev/null; then
      echo "Existing CI runner ${existing_runner_id} left paused state." >&2
      exit 2
    fi
    running_jobs="$(
      glab api "runners/${existing_runner_id}/jobs?status=running&per_page=100"
    )"
    if ! jq -e 'type == "array"' >/dev/null <<<"$running_jobs"; then
      echo "Unable to verify jobs for existing CI runner ${existing_runner_id}." >&2
      exit 2
    fi
    running_total="$((running_total + $(jq 'length' <<<"$running_jobs")))"
  done
  if [[ "$running_total" -eq 0 ]]; then
    zero_streak="$((zero_streak + 1))"
    if [[ "$zero_streak" -ge 3 ]]; then
      break
    fi
  else
    zero_streak=0
  fi
  sleep 2
done
if [[ "$zero_streak" -lt 3 ]]; then
  echo "Existing CI runners did not reach a stable idle state." >&2
  exit 2
fi
assert_source_freshness

validation_network_json=""
if ! validation_network_json="$(
  docker network inspect "$validation_network" 2>/dev/null
)"; then
  docker network create \
    --driver bridge \
    --subnet "$validation_subnet" \
    --gateway "$validation_gateway" \
    "$validation_network" >/dev/null
  validation_network_json="$(docker network inspect "$validation_network")"
fi
if ! jq -e \
  --arg name "$validation_network" \
  --arg subnet "$validation_subnet" \
  --arg gateway "$validation_gateway" '
    length == 1
    and .[0].Name == $name
    and .[0].Driver == "bridge"
    and .[0].Internal == false
    and .[0].Attachable == false
    and .[0].IPAM.Config == [{Subnet: $subnet, Gateway: $gateway}]
  ' >/dev/null <<<"$validation_network_json"; then
  echo "Light validation Docker network does not match the isolated subnet contract." >&2
  exit 2
fi

sudo install -o root -g root -m 700 "$egress_source" "$egress_target"
sudo install -o root -g root -m 644 \
  "$egress_service_source" "$egress_service_target"
sudo systemctl daemon-reload
if ! sudo systemctl is-active --quiet ai-do-ci-validation-egress.service; then
  echo "The heavy validation egress service must already be active." >&2
  exit 2
fi
sudo systemctl enable ai-do-ci-validation-egress.service >/dev/null
sudo "$egress_target" --apply-light
sudo "$egress_target" --check

runner_registration="$(
  glab api --method POST user/runners \
    --field runner_type=project_type \
    --field "project_id=${project_id}" \
    --raw-field "description=${runner_name}" \
    --raw-field "tag_list=${validation_tag}" \
    --field run_untagged=false \
    --field locked=true \
    --raw-field access_level=not_protected \
    --field maximum_timeout=3600
)"
runner_id="$(jq -r '.id // empty' <<<"$runner_registration")"
runner_token="$(jq -r '.token // empty' <<<"$runner_registration")"
if [[ -z "$runner_id" || -z "$runner_token" ]]; then
  echo "GitLab did not return the light validation runner id and authentication token." >&2
  exit 2
fi
glab api --method PUT "runners/${runner_id}" --field paused=true >/dev/null

origin_url="$(git -C "$repo_root" remote get-url origin)"
gitlab_url="$(sed -E 's#^(https?://[^/]+)/.*#\1#' <<<"$origin_url")"
if [[ ! "$gitlab_url" =~ ^https?:// ]]; then
  echo "Unable to derive the GitLab HTTP(S) URL from origin." >&2
  exit 2
fi

gitlab-runner register \
  --non-interactive \
  --url "$gitlab_url" \
  --token "$runner_token" \
  --name "$runner_name" \
  --executor docker \
  --limit 1 \
  --request-concurrency 2 \
  --docker-image "$validation_image" \
  --docker-privileged=false \
  --docker-disable-cache=true \
  --docker-disable-entrypoint-overwrite=true \
  --docker-cap-drop ALL \
  --docker-security-opt no-new-privileges:true \
  --docker-network-mode "$validation_network" \
  --docker-services-limit 0 \
  --docker-memory 8g \
  --docker-cpus 4 \
  --docker-shm-size 1073741824 \
  --docker-pull-policy never \
  --docker-allowed-pull-policies never \
  --docker-allowed-images "$validation_image"
local_registration_created=1
unset runner_token

runner_config_candidate="$(
  mktemp --tmpdir="$(dirname "$runner_config_file")" .config.toml.XXXXXX
)"
if ! /usr/bin/python3 -I - \
  "$runner_config_file" \
  "$runner_config_candidate" \
  "$runner_name" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
candidate_path = Path(sys.argv[2])
runner_name = sys.argv[3]
source = config_path.read_text(encoding="utf-8")
sections = source.split("[[runners]]")
matches = [
    index
    for index, section in enumerate(sections)
    if f'name = "{runner_name}"' in section
]
if len(matches) != 1:
    raise SystemExit("Expected exactly one light runner config section.")
index = matches[0]
section = sections[index]
service_limits = re.findall(
    r"(?m)^\s*services_limit\s*=\s*(-?\d+)\s*$",
    section,
)
if service_limits == []:
    docker_header = "  [runners.docker]\n"
    if section.count(docker_header) != 1:
        raise SystemExit("Light runner Docker config is not in the expected state.")
    section = section.replace(
        docker_header,
        f"{docker_header}    services_limit = 0\n",
        1,
    )
elif service_limits != ["0"]:
    raise SystemExit("Light runner service limit is not fail-closed.")
sections[index] = section
candidate_path.write_text("[[runners]]".join(sections), encoding="utf-8")
PY
then
  exit 2
fi
chmod 600 "$runner_config_candidate"
mv -f "$runner_config_candidate" "$runner_config_file"
runner_config_candidate=""

if ! /usr/bin/python3 -I - "$runner_config_file" "$runner_name" "$validation_image" <<'PY'
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

config = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
matches = [
    runner
    for runner in config.get("runners", [])
    if runner.get("name") == sys.argv[2]
]
if len(matches) != 1:
    raise SystemExit("Expected exactly one local light validation runner.")
runner = matches[0]
docker = runner.get("docker", {})
checks = {
    "executor": runner.get("executor") == "docker",
    "limit": runner.get("limit") == 1,
    "request_concurrency": runner.get("request_concurrency") == 2,
    "image": docker.get("image") == sys.argv[3],
    "privileged": docker.get("privileged") is False,
    "disable_cache": docker.get("disable_cache") is True,
    "cap_drop": docker.get("cap_drop") == ["ALL"],
    "security_opt": "no-new-privileges:true" in docker.get("security_opt", []),
    "network_mode": docker.get("network_mode") == "ai-do-validation-light",
    "extra_hosts": docker.get("extra_hosts") in (None, []),
    "allowed_images": docker.get("allowed_images") == [sys.argv[3]],
    "allowed_services": docker.get("allowed_services") in (None, []),
    "services_limit": docker.get("services_limit") == 0,
    "memory": docker.get("memory") == "8g",
    "cpus": docker.get("cpus") == "4",
    "shm_size": docker.get("shm_size") == 1073741824,
    "pull_policy": docker.get("pull_policy") == ["never"],
    "allowed_pull_policies": docker.get("allowed_pull_policies") == ["never"],
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit(
        "Light validation runner local isolation contract failed: "
        + ", ".join(failed)
    )
PY
then
  exit 2
fi

runner_json="{}"
for _attempt in $(seq 1 30); do
  runner_json="$(glab api "runners/${runner_id}")"
  if jq -e '
    (.contacted_at | type) == "string"
    and .contacted_at != ""
  ' >/dev/null <<<"$runner_json"; then
    break
  fi
  sleep 2
done
if ! jq -e '
  .description == "ai-do-validation-light-docker-runner"
  and (.status == "paused" or .status == "online")
  and (.contacted_at | type) == "string"
  and .contacted_at != ""
  and .tag_list == ["ai-do-validation-light"]
  and .paused == true
  and .locked == true
  and .run_untagged == false
  and .access_level == "not_protected"
  and .runner_type == "project_type"
' >/dev/null <<<"$runner_json"; then
  echo "Light validation runner metadata does not match the paused project-runner contract." >&2
  exit 2
fi

assert_source_freshness
registration_complete=1
existing_pause_persist=1
trap - EXIT
echo "Installed ${runner_name} (${runner_id}); all CI runners remain paused for atomic promotion."
