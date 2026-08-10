#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
validation_image_helper="$repo_root/scripts/build-ci-validation-image.sh"
source "$validation_image_helper"
project_path="open-alm/open-alm"
runner_name="open-alm-validation-docker-runner"
validation_tag="open-alm-validation"
validation_image="$OPEN_ALM_VALIDATION_IMAGE"
validation_image_id="$OPEN_ALM_VALIDATION_IMAGE_ID"
gitlab_runner_version="18.11.2"
helper_image_repository="registry.gitlab.com/gitlab-org/gitlab-runner/gitlab-runner-helper"
helper_image_manifest_digest="sha256:39e9155b72aff010f55a8bbfdb94fedeb0824de18612795d8b901ac4b42d99f5"
helper_image_local_id="sha256:39e9155b72aff010f55a8bbfdb94fedeb0824de18612795d8b901ac4b42d99f5"
helper_image="${helper_image_repository}:x86_64-v${gitlab_runner_version}"
helper_image_pinned="${helper_image_repository}@${helper_image_manifest_digest}"
validation_network="open-alm-validation"
validation_subnet="172.29.250.0/24"
validation_gateway="172.29.250.1"
egress_source="$repo_root/ops/ci/open-alm-ci-validation-egress.sh"
egress_service_source="$repo_root/ops/ci/open-alm-ci-validation-egress.service"
egress_target="/usr/local/sbin/open-alm-ci-validation-egress"
egress_service_target="/etc/systemd/system/open-alm-ci-validation-egress.service"
redis_service_image="redis@sha256:5a77f0f4698389019f828f6387049ce1d5adbea204e56422aa7720dab7034287"
minio_service_image="minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
opensearch_service_image="open-alm-opensearch@sha256:fa1c515ec9913749d8cc7c76c66ac22c377ba9d4ac22132ee9a1749792f12d6d"
service_images=(
  "$redis_service_image"
  "$minio_service_image"
  "$opensearch_service_image"
)
docker_config_dir="$repo_root/.runtime/ci-validation-docker-config"
current_branch="$(git -C "$repo_root" branch --show-current)"

if [[ "$current_branch" != "dev" ]]; then
  echo "Refusing to install validation runner from branch ${current_branch:-<detached>}; use clean dev after merge." >&2
  exit 2
fi
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "Refusing to install validation runner from a dirty checkout." >&2
  exit 2
fi
bash "$validation_image_helper" --verify-source-only
source "$repo_root/scripts/ci/control-plane-lock.sh"
acquire_open_alm_ci_control_plane_lock

git -C "$repo_root" fetch --quiet origin dev
local_head="$(git -C "$repo_root" rev-parse HEAD)"
remote_head="$(git -C "$repo_root" rev-parse origin/dev)"
if [[ "$local_head" != "$remote_head" ]]; then
  echo "Refusing to install validation runner: local dev is not origin/dev (${local_head} != ${remote_head})." >&2
  exit 2
fi

for command_name in awk docker gitlab-runner glab jq sha256sum sudo systemctl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Refusing to install validation runner: ${command_name} is unavailable." >&2
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

project_json="$(glab api "projects/${project_path//\//%2F}")"
project_id="$(jq -r '.id // empty' <<<"$project_json")"
if [[ -z "$project_id" ]]; then
  echo "Refusing to install validation runner: GitLab project id was not resolved." >&2
  exit 2
fi
codex_runner_ids="$(
  glab api "projects/${project_id}/runners?per_page=100" |
    jq -r '.[] | select(.description == "open-alm-local-codex-runner") | .id'
)"
if [[ "$(wc -w <<<"$codex_runner_ids")" -ne 1 ]]; then
  echo "Expected exactly one transitional Codex runner before validation bootstrap." >&2
  exit 2
fi
codex_runner_id="$codex_runner_ids"
codex_runner_json="$(glab api "runners/${codex_runner_id}")"
if ! jq -e '
  .description == "open-alm-local-codex-runner"
  and .status == "online"
  and (.tag_list | sort) == ["open-alm-local", "codex-local"]
  and .paused == false
  and .locked == true
  and .run_untagged == false
  and .runner_type == "project_type"
' >/dev/null <<<"$codex_runner_json"; then
  echo "The transitional Codex runner is not in the expected pre-bootstrap state." >&2
  exit 2
fi

runner_id=""
registration_complete=0
local_registration_created=0
codex_runner_paused=0
legacy_pause_persist=0
cleanup_failed_installation() {
  if [[ "$registration_complete" -eq 0 && -n "$runner_id" ]]; then
    if [[ "$local_registration_created" -eq 1 ]]; then
      gitlab-runner unregister --name "$runner_name" >/dev/null 2>&1 || true
    fi
    glab api --method DELETE "runners/${runner_id}" >/dev/null 2>&1 || true
  fi
  if [[ "$codex_runner_paused" -eq 1 && "$legacy_pause_persist" -eq 0 ]]; then
    glab api --method PUT "runners/${codex_runner_id}" \
      --field paused=false >/dev/null 2>&1 || true
  fi
}
trap cleanup_failed_installation EXIT

glab api --method PUT "runners/${codex_runner_id}" \
  --field paused=true >/dev/null
codex_runner_paused=1
for _attempt in $(seq 1 60); do
  running_jobs="$(
    glab api "runners/${codex_runner_id}/jobs?status=running&per_page=100"
  )"
  if [[ "$(jq 'length' <<<"$running_jobs")" -eq 0 ]]; then
    break
  fi
  sleep 2
done
if [[ "$(jq 'length' <<<"$running_jobs")" -ne 0 ]]; then
  echo "The transitional shell runner did not drain before validation bootstrap." >&2
  exit 2
fi

bash "$repo_root/scripts/codex-review-ci.sh" \
  --validate-gitlab-ci-contract "$repo_root/.gitlab-ci.yml" >/dev/null

mkdir -p "$docker_config_dir"
docker --config "$docker_config_dir" pull "$helper_image_pinned"
docker --config "$docker_config_dir" tag "$helper_image_pinned" "$helper_image"
helper_image_metadata="$(
  docker --config "$docker_config_dir" image inspect "$helper_image"
)"
if [[ "$(jq -r '.[0].Id' <<<"$helper_image_metadata")" != "$helper_image_local_id" ]] ||
   ! jq -e \
     --arg pinned "$helper_image_pinned" \
     '.[0].RepoDigests | index($pinned) != null' \
     >/dev/null <<<"$helper_image_metadata"; then
  echo "The GitLab Runner helper image does not match its pinned local identity." >&2
  exit 2
fi
OPEN_ALM_VALIDATION_DOCKER_CONFIG="$docker_config_dir" \
  bash "$validation_image_helper"
for service_image in "${service_images[@]}"; do
  if ! docker --config "$docker_config_dir" image inspect "$service_image" >/dev/null; then
    echo "Required pinned CI service image is unavailable locally: ${service_image}." >&2
    exit 2
  fi
done

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
  echo "Validation Docker network does not match the isolated subnet contract." >&2
  exit 2
fi
sudo install -o root -g root -m 700 "$egress_source" "$egress_target"
sudo install -o root -g root -m 644 \
  "$egress_service_source" "$egress_service_target"
sudo systemctl daemon-reload
sudo systemctl enable --now open-alm-ci-validation-egress.service >/dev/null
sudo "$egress_target" --check

existing_validation_ids="$(
  glab api "projects/${project_id}/runners?per_page=100" |
    jq -r --arg description "$runner_name" \
      '.[] | select(.description == $description) | .id'
)"
if [[ -n "$existing_validation_ids" ]]; then
  echo "Refusing to create a duplicate ${runner_name}; remove or audit runner id(s): ${existing_validation_ids//$'\n'/, }." >&2
  exit 2
fi
if gitlab-runner list 2>&1 | grep -F "$runner_name" >/dev/null; then
  echo "Refusing to reuse an existing local GitLab Runner registration named ${runner_name}." >&2
  exit 2
fi

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
  echo "GitLab did not return the validation runner id and authentication token." >&2
  exit 2
fi

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
  --docker-extra-hosts "ci-postgres.internal:${validation_gateway}" \
  --docker-services-limit 3 \
  --docker-wait-for-services-timeout 120 \
  --docker-service-memory 2g \
  --docker-service-cpus 2 \
  --docker-memory 24g \
  --docker-cpus 8 \
  --docker-shm-size 2147483648 \
  --docker-pull-policy never \
  --docker-allowed-pull-policies never \
  --docker-allowed-images "$validation_image" \
  --docker-allowed-services "$redis_service_image" \
  --docker-allowed-services "$minio_service_image" \
  --docker-allowed-services "$opensearch_service_image"
local_registration_created=1
unset runner_token

validation_status=""
for _attempt in $(seq 1 15); do
  validation_status="$(
    glab api "runners/${runner_id}" | jq -r '.status // empty'
  )"
  if [[ "$validation_status" == "online" ]]; then
    break
  fi
  sleep 2
done
if [[ "$validation_status" != "online" ]]; then
  echo "Validation runner ${runner_id} was registered but did not become online." >&2
  exit 2
fi
validation_runner_json="$(glab api "runners/${runner_id}")"
if ! jq -e '
  .description == "open-alm-validation-docker-runner"
  and .status == "online"
  and .tag_list == ["open-alm-validation"]
  and .paused == false
  and .locked == true
  and .run_untagged == false
  and .access_level == "not_protected"
  and .runner_type == "project_type"
' >/dev/null <<<"$validation_runner_json"; then
  echo "Validation runner metadata does not match the isolated project-runner contract." >&2
  exit 2
fi
registration_complete=1
legacy_pause_persist=1
trap - EXIT

echo "Installed ${runner_name} (${runner_id}) with image ${validation_image}."
echo "The drained transitional Codex runner remains paused until CI-first promotion."
