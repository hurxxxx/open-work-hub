#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_project_path="dwdcc/ai-do"
ci_project_path="dwdcc/ai-do-ci"
ci_project_name="ai-do-ci"
staged_ci_file="ops/ci/ci-first.gitlab-ci.yml"
external_ci_file=".gitlab-ci.yml"
installed_codex_runner="${CODEX_REVIEW_RUNNER_SCRIPT:-/home/dwdcc/.local/bin/ai-do-codex-review-ci}"
runner_config_file="${GITLAB_RUNNER_CONFIG_FILE:-/home/dwdcc/.gitlab-runner/config.toml}"
runner_service="${GITLAB_RUNNER_SERVICE:-ai-do-codex-gitlab-runner.service}"
installed_egress_policy="/usr/local/sbin/ai-do-ci-validation-egress"
validation_image="ai-do-validation:node25-python312-pg18-api-a3e8c22a3552-worker-3149583cef20-node-e7c57b3bacf9-484482bced42"
validation_image_id="sha256:89345c7907b296ea557a61e9a4c956ee9915c3fb9b611b3923f36bcc4c65d526"
previous_validation_image="ai-do-validation:node25-python312-pg18-api-a3e8c22a3552-worker-3149583cef20-node-006af39bdce4-484482bced42"
gitlab_runner_version="18.11.2"
helper_image_repository="registry.gitlab.com/gitlab-org/gitlab-runner/gitlab-runner-helper"
helper_image_manifest_digest="sha256:39e9155b72aff010f55a8bbfdb94fedeb0824de18612795d8b901ac4b42d99f5"
helper_image_local_id="sha256:39e9155b72aff010f55a8bbfdb94fedeb0824de18612795d8b901ac4b42d99f5"
helper_image="${helper_image_repository}:x86_64-v${gitlab_runner_version}"
helper_image_pinned="${helper_image_repository}@${helper_image_manifest_digest}"
current_branch="$(git -C "$repo_root" branch --show-current)"

encoded_project_path() {
  sed 's#/#%2F#g' <<<"$1"
}

if [[ "$current_branch" != "dev" ]]; then
  echo "Refusing CI control-plane promotion from branch ${current_branch:-<detached>}; use clean dev after merge." >&2
  exit 2
fi
if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  echo "Refusing CI control-plane promotion from a dirty checkout." >&2
  exit 2
fi
source "$repo_root/scripts/ci/control-plane-lock.sh"
acquire_ai_do_ci_control_plane_lock

git -C "$repo_root" fetch --quiet origin dev
source_sha="$(git -C "$repo_root" rev-parse HEAD)"
remote_sha="$(git -C "$repo_root" rev-parse origin/dev)"
if [[ "$source_sha" != "$remote_sha" ]]; then
  echo "Refusing CI control-plane promotion: local dev is not origin/dev (${source_sha} != ${remote_sha})." >&2
  exit 2
fi

for command_name in awk base64 cmp docker gitlab-runner glab install jq kill mktemp mv python3 sha256sum sudo systemctl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Refusing CI control-plane promotion: ${command_name} is unavailable." >&2
    exit 2
  fi
done
actual_gitlab_runner_version="$(
  gitlab-runner --version |
    awk '/^Version:/ {print $2; exit}'
)"
if [[ "$actual_gitlab_runner_version" != "$gitlab_runner_version" ]]; then
  echo "GitLab Runner ${gitlab_runner_version} is required for the pinned helper image." >&2
  exit 2
fi

bash -n "$repo_root/scripts/codex-review-ci.sh"
bash -n "$repo_root/scripts/build-ci-validation-image.sh"
bash -n "$repo_root/scripts/install-ci-validation-runner.sh"
bash -n "$repo_root/scripts/install-ci-light-validation-runner.sh"
bash -n "$repo_root/ops/ci/ai-do-ci-validation-egress.sh"
bash "$repo_root/scripts/codex-review-ci.sh" \
  --validate-gitlab-ci-contract "$repo_root/$staged_ci_file" |
  grep -Fx "feature-codex-release-v1" >/dev/null
glab ci lint "$repo_root/$staged_ci_file" --include-jobs >/dev/null
bash "$repo_root/scripts/build-ci-validation-image.sh"

source_project_encoded="$(encoded_project_path "$source_project_path")"
source_project_json="$(glab api "projects/${source_project_encoded}")"
source_project_id="$(jq -r '.id // empty' <<<"$source_project_json")"
namespace_id="$(jq -r '.namespace.id // empty' <<<"$source_project_json")"
if [[ -z "$source_project_id" || -z "$namespace_id" ]]; then
  echo "Unable to resolve the source GitLab project and namespace." >&2
  exit 2
fi

runner_details="$(
  glab api "projects/${source_project_id}/runners?per_page=100" |
    jq -r '.[].id' |
    while IFS= read -r runner_id; do
      glab api "runners/${runner_id}"
    done |
    jq -s '.'
)"
if [[ "$(
  jq '[.[] | select(
    .description == "ai-do-validation-docker-runner"
    and (.status == "paused" or .status == "online")
    and .tag_list == ["ai-do-validation"]
    and (.paused | type) == "boolean"
    and .locked == true
    and .run_untagged == false
    and .access_level == "not_protected"
    and .runner_type == "project_type"
  )] | length' <<<"$runner_details"
)" -ne 1 ]]; then
  echo "Expected exactly one trusted, project-scoped validation runner." >&2
  exit 2
fi
if [[ "$(
  jq '[.[] | select(
    .description == "ai-do-validation-light-docker-runner"
    and (.status == "paused" or .status == "online")
    and .tag_list == ["ai-do-validation-light"]
    and (.paused | type) == "boolean"
    and .locked == true
    and .run_untagged == false
    and .access_level == "not_protected"
    and .runner_type == "project_type"
  )] | length' <<<"$runner_details"
)" -ne 1 ]]; then
  echo "Expected exactly one trusted light validation runner." >&2
  exit 2
fi
if [[ "$(
  jq '[.[] | select(
    .description == "ai-do-local-codex-runner"
    and (.status == "paused" or .status == "online")
    and (
      (.tag_list | sort) == ["ai-do-local", "codex-local"]
      or .tag_list == ["codex-local"]
    )
    and (.paused | type) == "boolean"
    and .locked == true
    and .run_untagged == false
    and .runner_type == "project_type"
  )] | length' <<<"$runner_details"
)" -ne 1 ]]; then
  echo "Expected one trusted transitional or steady-state Codex runner." >&2
  exit 2
fi
codex_runner_id="$(
  jq -r '
    .[]
    | select(.description == "ai-do-local-codex-runner")
    | .id
  ' <<<"$runner_details"
)"
validation_runner_id="$(
  jq -r '
    .[]
    | select(.description == "ai-do-validation-docker-runner")
    | .id
  ' <<<"$runner_details"
)"
light_runner_id="$(
  jq -r '
    .[]
    | select(.description == "ai-do-validation-light-docker-runner")
    | .id
  ' <<<"$runner_details"
)"
codex_runner_json="$(
  jq -c --argjson runner_id "$codex_runner_id" '
    .[] | select(.id == $runner_id)
  ' <<<"$runner_details"
)"
validation_runner_json="$(
  jq -c --argjson runner_id "$validation_runner_id" '
    .[] | select(.id == $runner_id)
  ' <<<"$runner_details"
)"
light_runner_json="$(
  jq -c --argjson runner_id "$light_runner_id" '
    .[] | select(.id == $runner_id)
  ' <<<"$runner_details"
)"
control_plane_runner_ids=(
  "$validation_runner_id"
  "$light_runner_id"
  "$codex_runner_id"
)
previous_codex_tags_csv="$(jq -r '.tag_list | join(",")' <<<"$codex_runner_json")"
previous_codex_paused="$(jq -r '.paused | tostring' <<<"$codex_runner_json")"
previous_validation_paused="$(
  jq -r '.paused | tostring' <<<"$validation_runner_json"
)"
previous_light_paused="$(jq -r '.paused | tostring' <<<"$light_runner_json")"

previous_ci_config_path="$(jq -r '.ci_config_path // empty' <<<"$source_project_json")"
previous_pipeline_gate="$(
  jq -r '(.only_allow_merge_if_pipeline_succeeds // false) | tostring' \
    <<<"$source_project_json"
)"
previous_discussion_gate="$(
  jq -r '(.only_allow_merge_if_all_discussions_are_resolved // false) | tostring' \
    <<<"$source_project_json"
)"
previous_skipped_pipeline_gate="$(
  jq -r '(.allow_merge_on_skipped_pipeline // false) | tostring' \
    <<<"$source_project_json"
)"
previous_shared_runners="$(
  jq -r '(.shared_runners_enabled // true) | tostring' <<<"$source_project_json"
)"
previous_public_jobs="$(jq -r '(.public_jobs // true) | tostring' <<<"$source_project_json")"
previous_fork_parent_pipelines="$(
  jq -r '(.ci_allow_fork_pipelines_to_run_in_parent_project // false) | tostring' \
    <<<"$source_project_json"
)"

assert_source_freshness() {
  local current_head current_remote
  if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
    echo "CI control-plane source checkout changed during promotion." >&2
    return 1
  fi
  git -C "$repo_root" fetch --quiet origin dev
  current_head="$(git -C "$repo_root" rev-parse HEAD)"
  current_remote="$(git -C "$repo_root" rev-parse origin/dev)"
  if [[ "$current_head" != "$source_sha" || "$current_remote" != "$source_sha" ]]; then
    echo "CI control-plane source SHA changed during promotion." >&2
    return 1
  fi
}

pause_runner() {
  local runner_id="$1"
  local runner_json

  if ! glab api --method PUT "runners/${runner_id}" \
    --field paused=true >/dev/null; then
    echo "Unable to pause CI runner ${runner_id}." >&2
    return 1
  fi
  if ! runner_json="$(glab api "runners/${runner_id}")" ||
     ! jq -e '.paused == true' >/dev/null <<<"$runner_json"; then
    echo "CI runner ${runner_id} did not enter the paused state." >&2
    return 1
  fi
}

pause_runners() {
  local runner_id
  for runner_id in "$@"; do
    pause_runner "$runner_id"
  done
}

assert_runners_quiescent() {
  local runner_id runner_json running_jobs
  for runner_id in "$@"; do
    if ! runner_json="$(glab api "runners/${runner_id}")" ||
       ! jq -e '.paused == true' >/dev/null <<<"$runner_json"; then
      echo "CI runner ${runner_id} is not verifiably paused." >&2
      return 1
    fi
    if ! running_jobs="$(
      glab api "runners/${runner_id}/jobs?status=running&per_page=100"
    )" ||
       ! jq -e 'type == "array" and length == 0' >/dev/null <<<"$running_jobs"; then
      echo "CI runner ${runner_id} is not verifiably idle." >&2
      return 1
    fi
  done
}

drain_runners() {
  local runner_id running_jobs
  local zero_streak=0
  local running_total=0

  echo "Waiting 60 seconds for in-flight GitLab long-poll requests to quiesce."
  sleep 60
  for _attempt in $(seq 1 1800); do
    running_total=0
    for runner_id in "$@"; do
      if ! glab api "runners/${runner_id}" |
        jq -e '.paused == true' >/dev/null; then
        echo "CI runner ${runner_id} left the paused state while draining." >&2
        return 1
      fi
      if ! running_jobs="$(
        glab api "runners/${runner_id}/jobs?status=running&per_page=100"
      )" ||
         ! jq -e 'type == "array"' >/dev/null <<<"$running_jobs"; then
        echo "Unable to verify running jobs for CI runner ${runner_id}." >&2
        return 1
      fi
      running_total="$((running_total + $(jq 'length' <<<"$running_jobs")))"
    done
    if [[ "$running_total" -eq 0 ]]; then
      zero_streak="$((zero_streak + 1))"
      if [[ "$zero_streak" -ge 3 ]]; then
        return 0
      fi
    else
      zero_streak=0
    fi
    sleep 2
  done
  echo "Paused CI runners did not reach a stable idle state before mutation." >&2
  return 1
}

wait_for_runner_service_pid() {
  local previous_pid="$1"
  local new_pid

  for _attempt in $(seq 1 900); do
    if ! new_pid="$(
      systemctl --user show "$runner_service" --property MainPID --value
    )"; then
      sleep 1
      continue
    fi
    if systemctl --user is-active --quiet "$runner_service" &&
       [[ "$new_pid" =~ ^[1-9][0-9]*$ ]] &&
       [[ "$new_pid" != "$previous_pid" ]]; then
      return 0
    fi
    sleep 2
  done
  echo "GitLab Runner did not cross the service process barrier." >&2
  return 1
}

restart_runner_service() {
  local previous_pid restart_policy
  assert_runners_quiescent "${control_plane_runner_ids[@]}"
  if ! previous_pid="$(
    systemctl --user show "$runner_service" --property MainPID --value
  )" ||
     [[ ! "$previous_pid" =~ ^[1-9][0-9]*$ ]] ||
     ! systemctl --user is-active --quiet "$runner_service"; then
    echo "Unable to read the GitLab Runner service PID." >&2
    return 1
  fi
  restart_policy="$(
    systemctl --user show "$runner_service" --property Restart --value
  )"
  if [[ "$restart_policy" != "always" ]]; then
    echo "GitLab Runner service must use Restart=always for graceful reload." >&2
    return 1
  fi
  if ! systemctl --user kill --kill-whom=main --signal=SIGQUIT "$runner_service"; then
    echo "Unable to gracefully stop the GitLab Runner service." >&2
    return 1
  fi
  wait_for_runner_service_pid "$previous_pid"
}

recover_runner_service() {
  assert_runners_quiescent "${control_plane_runner_ids[@]}"
  if systemctl --user is-active --quiet "$runner_service"; then
    restart_runner_service
    return
  fi
  if ! systemctl --user start "$runner_service"; then
    echo "Unable to start the GitLab Runner service during rollback." >&2
    return 1
  fi
  wait_for_runner_service_pid 0
}

atomic_replace_runner_config() {
  local source_file="$1"
  local config_dir
  config_dir="$(dirname "$runner_config_file")"
  runner_config_candidate="$(
    mktemp --tmpdir="$config_dir" .config.toml.XXXXXX
  )"
  if ! install -m 600 "$source_file" "$runner_config_candidate" ||
     ! mv -f "$runner_config_candidate" "$runner_config_file"; then
    rm -f "$runner_config_candidate"
    runner_config_candidate=""
    return 1
  fi
  runner_config_candidate=""
}

settings_changed=0
codex_runner_changed=0
validation_runner_changed=0
light_runner_changed=0
codex_wrapper_backup=""
codex_wrapper_backed_up=0
runner_config_backup=""
runner_config_backed_up=0
runner_config_candidate=""
runner_config_rendered=""
promotion_complete=0
rollback_incomplete_promotion() {
  local rollback_failed=0
  local rollback_runners_drained=1
  if [[ "$promotion_complete" -eq 1 ]]; then
    return
  fi

  if ! pause_runner "$validation_runner_id"; then
    rollback_runners_drained=0
    rollback_failed=1
  fi
  if ! pause_runner "$light_runner_id"; then
    rollback_runners_drained=0
    rollback_failed=1
  fi
  if ! pause_runner "$codex_runner_id"; then
    rollback_runners_drained=0
    rollback_failed=1
  fi
  if [[ "$rollback_runners_drained" -eq 1 ]] &&
     ! drain_runners "${control_plane_runner_ids[@]}"; then
    rollback_runners_drained=0
    rollback_failed=1
  fi

  if [[ "$rollback_runners_drained" -eq 1 ]] &&
     [[ "$runner_config_backed_up" -eq 1 ]]; then
    if ! atomic_replace_runner_config "$runner_config_backup" ||
       ! recover_runner_service; then
      rollback_failed=1
      rollback_runners_drained=0
    fi
  fi

  if [[ "$rollback_runners_drained" -eq 1 ]] &&
     [[ "$codex_wrapper_backed_up" -eq 1 ]]; then
    install -m 700 "$codex_wrapper_backup" "$installed_codex_runner" ||
      rollback_failed=1
  fi

  if [[ "$rollback_runners_drained" -eq 1 ]] &&
     [[ "$settings_changed" -eq 1 ]]; then
    glab api --method PUT "projects/${source_project_id}" \
      --raw-field "ci_config_path=${previous_ci_config_path}" \
      --field "only_allow_merge_if_pipeline_succeeds=${previous_pipeline_gate}" \
      --field "only_allow_merge_if_all_discussions_are_resolved=${previous_discussion_gate}" \
      --field "allow_merge_on_skipped_pipeline=${previous_skipped_pipeline_gate}" \
      --field "shared_runners_enabled=${previous_shared_runners}" \
      --field "public_jobs=${previous_public_jobs}" \
      --field "ci_allow_fork_pipelines_to_run_in_parent_project=${previous_fork_parent_pipelines}" \
      >/dev/null 2>&1 || rollback_failed=1
  fi

  if [[ "$rollback_runners_drained" -eq 1 ]]; then
    glab api --method PUT "runners/${codex_runner_id}" \
      --raw-field "tag_list=${previous_codex_tags_csv}" \
      --field paused=true \
      --field run_untagged=false \
      --field locked=true >/dev/null 2>&1 || rollback_failed=1
    glab api --method PUT "runners/${validation_runner_id}" \
      --field paused=true \
      --field run_untagged=false \
      --field locked=true >/dev/null 2>&1 || rollback_failed=1
    glab api --method PUT "runners/${light_runner_id}" \
      --field paused=true \
      --field run_untagged=false \
      --field locked=true >/dev/null 2>&1 || rollback_failed=1
  fi

  if [[ "$rollback_runners_drained" -eq 1 ]] &&
     [[ "$rollback_failed" -eq 0 ]]; then
    glab api --method PUT "runners/${codex_runner_id}" \
      --field "paused=${previous_codex_paused}" >/dev/null 2>&1 ||
      rollback_failed=1
    glab api --method PUT "runners/${validation_runner_id}" \
      --field "paused=${previous_validation_paused}" >/dev/null 2>&1 ||
      rollback_failed=1
    glab api --method PUT "runners/${light_runner_id}" \
      --field "paused=${previous_light_paused}" >/dev/null 2>&1 ||
      rollback_failed=1
  fi

  if [[ -n "$codex_wrapper_backup" ]]; then
    rm -f "$codex_wrapper_backup"
  fi
  if [[ -n "$runner_config_backup" ]]; then
    rm -f "$runner_config_backup"
  fi
  if [[ -n "$runner_config_candidate" ]]; then
    rm -f "$runner_config_candidate"
  fi
  if [[ -n "$runner_config_rendered" ]]; then
    rm -f "$runner_config_rendered"
  fi
  if [[ "$rollback_failed" -ne 0 ]]; then
    glab api --method PUT "runners/${codex_runner_id}" \
      --field paused=true >/dev/null 2>&1 || true
    glab api --method PUT "runners/${validation_runner_id}" \
      --field paused=true >/dev/null 2>&1 || true
    glab api --method PUT "runners/${light_runner_id}" \
      --field paused=true >/dev/null 2>&1 || true
    echo "CI promotion rollback was incomplete; all runners remain fail-closed paused." >&2
  fi
}
trap rollback_incomplete_promotion EXIT

assert_source_freshness
pause_runner "$validation_runner_id"
validation_runner_changed=1
pause_runner "$light_runner_id"
light_runner_changed=1
pause_runner "$codex_runner_id"
codex_runner_changed=1
drain_runners "${control_plane_runner_ids[@]}"
if [[ ! -x "$installed_codex_runner" ]]; then
  echo "The installed Codex runner is unavailable for atomic promotion." >&2
  exit 2
fi
codex_wrapper_backup="$(mktemp)"
install -m 700 "$installed_codex_runner" "$codex_wrapper_backup"
codex_wrapper_backed_up=1
bash "$repo_root/scripts/install-codex-review-runner.sh"
if ! cmp -s "$repo_root/scripts/codex-review-ci.sh" "$installed_codex_runner"; then
  echo "The merged Codex runner was not installed exactly during promotion." >&2
  exit 2
fi
if ! sudo -n test -x "$installed_egress_policy" ||
   ! sudo -n cmp -s \
     "$repo_root/ops/ci/ai-do-ci-validation-egress.sh" \
     "$installed_egress_policy" ||
   ! sudo -n "$installed_egress_policy" --check; then
  echo "Install and verify the merged validation egress policy before promotion." >&2
  exit 2
fi
if [[ "$(docker image inspect --format '{{.Id}}' "$validation_image")" != "$validation_image_id" ]]; then
  echo "The validation image does not match its pinned image ID after shell-runner drain." >&2
  exit 2
fi
if ! docker image inspect "$previous_validation_image" >/dev/null; then
  echo "The previous validation image is unavailable for rollback." >&2
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

runner_config_backup="$(mktemp)"
install -m 600 "$runner_config_file" "$runner_config_backup"
runner_config_backed_up=1
runner_config_rendered="$(mktemp)"
if ! /usr/bin/python3 -I - \
  "$runner_config_file" \
  "$runner_config_rendered" \
  "$previous_validation_image" \
  "$validation_image" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
candidate_path = Path(sys.argv[2])
previous_image = sys.argv[3]
validation_image = sys.argv[4]
source = config_path.read_text(encoding="utf-8")
runner_sections = source.split("[[runners]]")
heavy_sections = [
    index
    for index, section in enumerate(runner_sections)
    if 'name = "ai-do-validation-docker-runner"' in section
]
light_sections = [
    index
    for index, section in enumerate(runner_sections)
    if 'name = "ai-do-validation-light-docker-runner"' in section
]
codex_sections = [
    index
    for index, section in enumerate(runner_sections)
    if 'name = "ai-do-local-codex-runner"' in section
]
if (
    len(heavy_sections) != 1
    or len(light_sections) != 1
    or len(codex_sections) != 1
):
    print(
        "Expected exactly one Codex, heavy, and light runner section.",
        file=sys.stderr,
    )
    raise SystemExit(1)
section_index = heavy_sections[0]
section = runner_sections[section_index]
previous_count = section.count(previous_image)
validation_count = section.count(validation_image)
if previous_count == 2 and validation_count == 0:
    section = section.replace(previous_image, validation_image)
elif previous_count == 0 and validation_count == 2:
    pass
else:
    print(
        "Validation runner image transition is not in an exact known state.",
        file=sys.stderr,
    )
    raise SystemExit(1)
request_lines = re.findall(r"(?m)^\s*request_concurrency\s*=\s*(\d+)\s*$", section)
if request_lines == []:
    limit_line = "  limit = 1\n"
    if section.count(limit_line) != 1:
        print(
            "Validation runner limit is not in the expected transition state.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    section = section.replace(
        limit_line,
        f"{limit_line}  request_concurrency = 2\n",
        1,
    )
elif request_lines != ["2"]:
    print(
        "Validation runner request concurrency is not in an exact known state.",
        file=sys.stderr,
    )
    raise SystemExit(1)
runner_sections[section_index] = section
light_section_index = light_sections[0]
light_section = runner_sections[light_section_index]
light_previous_count = light_section.count(previous_image)
light_validation_count = light_section.count(validation_image)
if light_previous_count == 2 and light_validation_count == 0:
    light_section = light_section.replace(previous_image, validation_image)
elif light_previous_count == 0 and light_validation_count == 2:
    pass
else:
    print(
        "Light validation runner image transition is not in an exact known state.",
        file=sys.stderr,
    )
    raise SystemExit(1)
runner_sections[light_section_index] = light_section
codex_index = codex_sections[0]
codex_section = runner_sections[codex_index]
codex_limit_lines = re.findall(
    r"(?m)^\s*limit\s*=\s*(\d+)\s*$",
    codex_section,
)
if codex_limit_lines == []:
    name_line = '  name = "ai-do-local-codex-runner"\n'
    if codex_section.count(name_line) != 1:
        print("Codex runner name is not in the expected state.", file=sys.stderr)
        raise SystemExit(1)
    codex_section = codex_section.replace(
        name_line,
        f"{name_line}  limit = 2\n",
        1,
    )
elif codex_limit_lines != ["2"]:
    print("Codex runner limit is not in the exact known state.", file=sys.stderr)
    raise SystemExit(1)
runner_sections[codex_index] = codex_section
source = "[[runners]]".join(runner_sections)
if source.count(previous_image) != 0 or source.count(validation_image) != 4:
    print(
        "Validation images are not confined to the two Docker runners.",
        file=sys.stderr,
    )
    raise SystemExit(1)
candidate_path.write_text(source, encoding="utf-8")
PY
then
  rm -f "$runner_config_rendered"
  runner_config_rendered=""
  exit 2
fi
assert_runners_quiescent "${control_plane_runner_ids[@]}"
atomic_replace_runner_config "$runner_config_rendered"
rm -f "$runner_config_rendered"
runner_config_rendered=""
restart_runner_service

if ! /usr/bin/python3 -I - \
  "$runner_config_file" \
  "ai-do-validation-docker-runner" \
  "$validation_image" \
  "ai-do-validation-light-docker-runner" \
  "redis@sha256:5a77f0f4698389019f828f6387049ce1d5adbea204e56422aa7720dab7034287" \
  "minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e" \
  "ai-do-opensearch@sha256:fa1c515ec9913749d8cc7c76c66ac22c377ba9d4ac22132ee9a1749792f12d6d" <<'PY'
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

config_path = Path(sys.argv[1])
runner_name = sys.argv[2]
validation_image = sys.argv[3]
light_runner_name = sys.argv[4]
allowed_services = sys.argv[5:]
try:
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
except Exception as error:
    print(f"Unable to validate GitLab Runner config: {error}", file=sys.stderr)
    raise SystemExit(1)

matches = [
    runner
    for runner in config.get("runners", [])
    if runner.get("name") == runner_name
]
if len(matches) != 1:
    print("Expected exactly one local validation runner configuration.", file=sys.stderr)
    raise SystemExit(1)
runner = matches[0]
docker = runner.get("docker", {})
checks = {
    "executor": runner.get("executor") == "docker",
    "image": docker.get("image") == validation_image,
    "helper_image": docker.get("helper_image") in (None, ""),
    "privileged": docker.get("privileged") is False,
    "disable_cache": docker.get("disable_cache") is True,
    "cap_drop": docker.get("cap_drop") == ["ALL"],
    "security_opt": "no-new-privileges:true" in docker.get("security_opt", []),
    "limit": runner.get("limit") == 1,
    "request_concurrency": runner.get("request_concurrency") == 2,
    "network_mode": docker.get("network_mode") == "ai-do-validation",
    "extra_hosts": docker.get("extra_hosts") == ["ci-postgres.internal:172.29.250.1"],
    "allowed_images": docker.get("allowed_images") == [validation_image],
    "pull_policy": docker.get("pull_policy") == ["never"],
    "allowed_pull_policies": docker.get("allowed_pull_policies") == ["never"],
    "allowed_services": docker.get("allowed_services") == allowed_services,
    "services_limit": docker.get("services_limit") == 3,
    "service_memory": docker.get("service_memory") == "2g",
    "service_cpus": docker.get("service_cpus") == "2",
    "wait_for_services_timeout": docker.get("wait_for_services_timeout") == 120,
    "no_source_network_flags": runner.get("environment", []) in (None, []),
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    print(
        f"Validation runner local isolation contract failed: {', '.join(failed)}",
        file=sys.stderr,
    )
    raise SystemExit(1)

light_matches = [
    candidate
    for candidate in config.get("runners", [])
    if candidate.get("name") == light_runner_name
]
if len(light_matches) != 1:
    print(
        "Expected exactly one local light validation runner configuration.",
        file=sys.stderr,
    )
    raise SystemExit(1)
light_runner = light_matches[0]
light_docker = light_runner.get("docker", {})
light_checks = {
    "global_concurrent": config.get("concurrent", 0) >= 4,
    "executor": light_runner.get("executor") == "docker",
    "image": light_docker.get("image") == validation_image,
    "helper_image": light_docker.get("helper_image") in (None, ""),
    "privileged": light_docker.get("privileged") is False,
    "disable_cache": light_docker.get("disable_cache") is True,
    "cap_drop": light_docker.get("cap_drop") == ["ALL"],
    "security_opt": (
        "no-new-privileges:true" in light_docker.get("security_opt", [])
    ),
    "limit": light_runner.get("limit") == 1,
    "request_concurrency": light_runner.get("request_concurrency") == 2,
    "network_mode": (
        light_docker.get("network_mode") == "ai-do-validation-light"
    ),
    "extra_hosts": light_docker.get("extra_hosts") in (None, []),
    "allowed_images": light_docker.get("allowed_images") == [validation_image],
    "pull_policy": light_docker.get("pull_policy") == ["never"],
    "allowed_pull_policies": (
        light_docker.get("allowed_pull_policies") == ["never"]
    ),
    "allowed_services": light_docker.get("allowed_services") in (None, []),
    "services_limit": light_docker.get("services_limit") == 0,
    "memory": light_docker.get("memory") == "8g",
    "cpus": light_docker.get("cpus") == "4",
    "shm_size": light_docker.get("shm_size") == 1073741824,
    "no_source_network_flags": (
        light_runner.get("environment", []) in (None, [])
    ),
}
failed = [name for name, ok in light_checks.items() if not ok]
if failed:
    print(
        "Light validation runner local isolation contract failed: "
        + ", ".join(failed),
        file=sys.stderr,
    )
    raise SystemExit(1)

codex_matches = [
    candidate
    for candidate in config.get("runners", [])
    if candidate.get("name") == "ai-do-local-codex-runner"
]
if len(codex_matches) != 1 or codex_matches[0].get("limit") != 2:
    print("Codex runner capacity reservation contract failed.", file=sys.stderr)
    raise SystemExit(1)
PY
then
  exit 2
fi

post_restart_runner_state="$(
  {
    glab api "runners/${validation_runner_id}"
    glab api "runners/${light_runner_id}"
    glab api "runners/${codex_runner_id}"
  } | jq -s '.'
)"
if ! jq -e '
  length == 3
  and all(.paused == true)
  and ([.[].id] | unique | length == 3)
' >/dev/null <<<"$post_restart_runner_state"; then
  echo "All CI runners must remain paused across the config reload barrier." >&2
  exit 2
fi

if ! bash "$repo_root/scripts/codex-review-ci.sh" \
  --validate-gitlab-ci-variable-sources "$source_project_path"; then
  echo "CI variable sources must expose only the isolated PostgreSQL DSN." >&2
  exit 2
fi

ci_project_encoded="$(encoded_project_path "$ci_project_path")"
ci_project_json=""
if ! ci_project_json="$(glab api "projects/${ci_project_encoded}" 2>/dev/null)"; then
  ci_project_json="$(
    glab api --method POST projects \
      --raw-field "name=${ci_project_name}" \
      --raw-field "path=${ci_project_name}" \
      --field "namespace_id=${namespace_id}" \
      --raw-field visibility=internal \
      --field initialize_with_readme=true \
      --raw-field default_branch=main \
      --field issues_enabled=false \
      --field merge_requests_enabled=false \
      --field wiki_enabled=false \
      --field snippets_enabled=false
  )"
fi
ci_project_id="$(jq -r '.id // empty' <<<"$ci_project_json")"
resolved_ci_project_path="$(jq -r '.path_with_namespace // empty' <<<"$ci_project_json")"
if [[ -z "$ci_project_id" || "$resolved_ci_project_path" != "$ci_project_path" ]]; then
  echo "Unable to resolve the protected ${ci_project_path} project." >&2
  exit 2
fi

protected_branch_json=""
if ! protected_branch_json="$(
  glab api "projects/${ci_project_id}/protected_branches/main" 2>/dev/null
)"; then
  if ! protected_branch_json="$(
    glab api --method POST "projects/${ci_project_id}/protected_branches" \
      --raw-field name=main \
      --field push_access_level=40 \
      --field merge_access_level=40 \
      --field allow_force_push=false 2>/dev/null
  )"; then
    for _attempt in $(seq 1 10); do
      if protected_branch_json="$(
        glab api "projects/${ci_project_id}/protected_branches/main" 2>/dev/null
      )"; then
        break
      fi
      sleep 1
    done
  fi
fi
if ! jq -e '
  (.allow_force_push == false)
  and ([.push_access_levels[]?.access_level] | length > 0)
  and ([.push_access_levels[]?.access_level] | all(. >= 40))
' >/dev/null <<<"$protected_branch_json"; then
  echo "The external CI main branch is not protected for Maintainer-only writes." >&2
  exit 2
fi

ci_file_api="projects/${ci_project_id}/repository/files/.gitlab-ci.yml"
ci_file_json=""
ci_action="create"
ci_last_commit_id=""
existing_ci_sha256=""
if ci_file_json="$(glab api "${ci_file_api}?ref=main" 2>/dev/null)"; then
  ci_action="update"
  ci_last_commit_id="$(jq -r '.last_commit_id // empty' <<<"$ci_file_json")"
  existing_ci_sha256="$(jq -r '.content_sha256 // empty' <<<"$ci_file_json")"
fi
desired_ci_sha256="$(sha256sum "$repo_root/$staged_ci_file" | awk '{print $1}')"
assert_source_freshness
assert_runners_quiescent "${control_plane_runner_ids[@]}"
if [[ "$existing_ci_sha256" == "$desired_ci_sha256" ]]; then
  ci_commit_sha="$(
    glab api "projects/${ci_project_id}/repository/branches/main" |
      jq -r '.commit.id // empty'
  )"
else
  ci_content="$(base64 --wrap=0 "$repo_root/$staged_ci_file")"
  ci_commit_payload="$(
    jq -n \
      --arg branch main \
      --arg message "chore(ci): promote ai-do ${source_sha} [skip ci]" \
      --arg action "$ci_action" \
      --arg file_path "$external_ci_file" \
      --arg content "$ci_content" \
      --arg last_commit_id "$ci_last_commit_id" '
        {
          branch: $branch,
          commit_message: $message,
          actions: [
            ({
              action: $action,
              file_path: $file_path,
              content: $content,
              encoding: "base64"
            } + if $last_commit_id == ""
                 then {}
                 else {last_commit_id: $last_commit_id}
               end)
          ]
        }
      '
  )"
  unset ci_content
  ci_commit_json="$(
    glab api --method POST "projects/${ci_project_id}/repository/commits" \
      --input - <<<"$ci_commit_payload"
  )"
  unset ci_commit_payload
  ci_commit_sha="$(jq -r '.id // empty' <<<"$ci_commit_json")"
fi
if [[ ! "$ci_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "The promoted CI configuration commit SHA could not be resolved." >&2
  exit 2
fi
promoted_ci_file_json="$(
  glab api "${ci_file_api}?ref=${ci_commit_sha}"
)"
if [[ "$(jq -r '.content_sha256 // empty' <<<"$promoted_ci_file_json")" != "$desired_ci_sha256" ]]; then
  echo "The pinned external CI commit does not contain the staged configuration." >&2
  exit 2
fi

ci_config_path="${external_ci_file}@${ci_project_path}:${ci_commit_sha}"

settings_changed=1
glab api --method PUT "projects/${source_project_id}" \
  --raw-field "ci_config_path=${ci_config_path}" \
  --field only_allow_merge_if_pipeline_succeeds=true \
  --field only_allow_merge_if_all_discussions_are_resolved=true \
  --field allow_merge_on_skipped_pipeline=false \
  --field shared_runners_enabled=false \
  --field public_jobs=false \
  --field ci_allow_fork_pipelines_to_run_in_parent_project=false >/dev/null

updated_project_json="$(glab api "projects/${source_project_id}")"
if ! jq -e \
  --arg ci_config_path "$ci_config_path" '
    .ci_config_path == $ci_config_path
    and .only_allow_merge_if_pipeline_succeeds == true
    and .only_allow_merge_if_all_discussions_are_resolved == true
    and .allow_merge_on_skipped_pipeline == false
    and .shared_runners_enabled == false
    and .public_jobs == false
    and .ci_allow_fork_pipelines_to_run_in_parent_project == false
  ' >/dev/null <<<"$updated_project_json"; then
  echo "GitLab project settings did not converge to the protected CI contract." >&2
  exit 2
fi

glab api --method PUT "runners/${validation_runner_id}" \
  --field paused=false \
  --field run_untagged=false \
  --field locked=true >/dev/null
validation_runner_changed=1
updated_validation_runner_json="$(glab api "runners/${validation_runner_id}")"
if ! jq -e '
  .description == "ai-do-validation-docker-runner"
  and .status == "online"
  and .tag_list == ["ai-do-validation"]
  and .paused == false
' >/dev/null <<<"$updated_validation_runner_json"; then
  echo "The validation runner did not return online after image promotion." >&2
  exit 2
fi

glab api --method PUT "runners/${light_runner_id}" \
  --field paused=false \
  --field run_untagged=false \
  --field locked=true >/dev/null
light_runner_changed=1
updated_light_runner_json="$(glab api "runners/${light_runner_id}")"
if ! jq -e '
  .description == "ai-do-validation-light-docker-runner"
  and .status == "online"
  and .tag_list == ["ai-do-validation-light"]
  and .paused == false
' >/dev/null <<<"$updated_light_runner_json"; then
  echo "The light validation runner did not return online after promotion." >&2
  exit 2
fi

glab api --method PUT "runners/${codex_runner_id}" \
  --raw-field 'tag_list=codex-local' \
  --field paused=false \
  --field run_untagged=false \
  --field locked=true >/dev/null
codex_runner_changed=1
updated_codex_runner_json="$(glab api "runners/${codex_runner_id}")"
if ! jq -e '
  .description == "ai-do-local-codex-runner"
  and .status == "online"
  and .tag_list == ["codex-local"]
  and .paused == false
' >/dev/null <<<"$updated_codex_runner_json"; then
  echo "The Codex runner did not converge to the codex-local-only contract." >&2
  exit 2
fi

rm -f "$codex_wrapper_backup"
codex_wrapper_backup=""
codex_wrapper_backed_up=0
rm -f "$runner_config_backup"
runner_config_backup=""
runner_config_backed_up=0
promotion_complete=1
trap - EXIT
echo "Promoted ${ci_config_path}; pipeline, discussion, and dedicated-runner merge gates are active."
