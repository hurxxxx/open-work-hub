#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_path="open-alm/open-alm"
mode="${1:---apply}"
postgres_major="18"
cluster_name="open_alm_ci"
cluster_port="55432"
postgres_max_locks_per_transaction="1024"
postgres_max_wal_size="8GB"
postgres_checkpoint_timeout="1min"
postgres_checkpoint_completion_target="0"
cluster_dsn_host="ci-postgres.internal"
validation_network="open-alm-validation"
validation_subnet="172.29.250.0/24"
cluster_listen_address="172.29.250.1"
cluster_data_dir="/data/postgres/${postgres_major}/${cluster_name}"
cluster_unit_name="postgresql@${postgres_major}-${cluster_name}.service"
cluster_systemd_drop_in_source="${repo_root}/ops/systemd/system/${cluster_unit_name}.d/network-online.conf"
cluster_systemd_drop_in_target="/etc/systemd/system/${cluster_unit_name}.d/network-online.conf"
ci_role="open_alm_ci_validation"
analysis_role="open_alm_analysis_reader"
current_branch=""

ci_postgres_setting_lines() {
  printf '%s\n' \
    "fsync=off" \
    "synchronous_commit=off" \
    "full_page_writes=off" \
    "wal_compression=on" \
    "max_wal_size=${postgres_max_wal_size}" \
    "checkpoint_timeout=${postgres_checkpoint_timeout}" \
    "checkpoint_completion_target=${postgres_checkpoint_completion_target}"
}

rotation_runner_cleanup_action() {
  local pause_changed="$1"
  local credentials_mutated="$2"
  local host_mutated="$3"
  local rotation_succeeded="$4"

  if [[ "$pause_changed" != "1" ]]; then
    echo "no-change"
  elif [[ "$rotation_succeeded" == "1" ||
          ( "$credentials_mutated" != "1" && "$host_mutated" != "1" ) ]]; then
    echo "restore-active"
  else
    echo "keep-paused"
  fi
}

ci_variable_write_action() {
  local variable_count="$1"

  case "$variable_count" in
    0)
      echo "set"
      ;;
    1)
      echo "update"
      ;;
    *)
      echo "Expected zero or one isolated PostgreSQL CI variable before rotation." >&2
      return 2
      ;;
  esac
}

case "$mode" in
  --apply)
    current_branch="$(git -C "$repo_root" branch --show-current)"
    if [[ "$current_branch" != "dev" ]]; then
      echo "Refusing CI PostgreSQL configuration from branch ${current_branch:-<detached>}; use clean dev after merge." >&2
      exit 2
    fi
    if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
      echo "Refusing CI PostgreSQL configuration from a dirty checkout." >&2
      exit 2
    fi
    source "$repo_root/scripts/ci/control-plane-lock.sh"
    acquire_open_alm_ci_control_plane_lock
    git -C "$repo_root" fetch --quiet origin dev
    local_dev_sha="$(git -C "$repo_root" rev-parse HEAD)"
    remote_dev_sha="$(git -C "$repo_root" rev-parse origin/dev)"
    if [[ "$local_dev_sha" != "$remote_dev_sha" ]]; then
      echo "Refusing CI PostgreSQL configuration: local dev is not origin/dev." >&2
      exit 2
    fi
    ;;
  --validate-only)
    ;;
  --test-rotation-cleanup-action)
    if [[ "$#" -ne 5 ]]; then
      echo "Usage: $0 --test-rotation-cleanup-action <pause-changed> <credentials-mutated> <host-mutated> <rotation-succeeded>" >&2
      exit 2
    fi
    rotation_runner_cleanup_action "$2" "$3" "$4" "$5"
    exit 0
    ;;
  --test-ci-variable-write-action)
    if [[ "$#" -ne 2 ]]; then
      echo "Usage: $0 --test-ci-variable-write-action <variable-count>" >&2
      exit 2
    fi
    ci_variable_write_action "$2"
    exit 0
    ;;
  --test-postgres-settings)
    if [[ "$#" -ne 1 ]]; then
      echo "Usage: $0 --test-postgres-settings" >&2
      exit 2
    fi
    ci_postgres_setting_lines
    exit 0
    ;;
  --test-postgres-systemd-drop-in)
    if [[ "$#" -ne 1 ]]; then
      echo "Usage: $0 --test-postgres-systemd-drop-in" >&2
      exit 2
    fi
    cat "$cluster_systemd_drop_in_source"
    exit 0
    ;;
  *)
    echo "Usage: $0 [--apply|--validate-only|--test-postgres-settings|--test-postgres-systemd-drop-in]" >&2
    exit 2
    ;;
esac

if [[ "$mode" == "--validate-only" ]]; then
  echo "Validated the isolated native CI PostgreSQL provisioning contract."
  exit 0
fi
assert_source_freshness() {
  local current_head current_remote
  if [[ -n "$(git -C "$repo_root" status --porcelain)" ]]; then
    echo "CI PostgreSQL source checkout changed during rotation." >&2
    return 1
  fi
  git -C "$repo_root" fetch --quiet origin dev
  current_head="$(git -C "$repo_root" rev-parse HEAD)"
  current_remote="$(git -C "$repo_root" rev-parse origin/dev)"
  if [[ "$current_head" != "$local_dev_sha" ||
        "$current_remote" != "$local_dev_sha" ]]; then
    echo "CI PostgreSQL source SHA changed during rotation." >&2
    return 1
  fi
}
for command_name in \
  docker glab jq openssl pg_createcluster pg_ctlcluster pg_lsclusters psql sudo systemctl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}." >&2
    exit 2
  fi
done
if ! docker network inspect "$validation_network" |
  jq -e \
    --arg name "$validation_network" \
    --arg subnet "$validation_subnet" \
    --arg gateway "$cluster_listen_address" '
      length == 1
      and .[0].Name == $name
      and .[0].Driver == "bridge"
      and .[0].IPAM.Config == [{Subnet: $subnet, Gateway: $gateway}]
    ' >/dev/null; then
  echo "Install the isolated validation Docker network before CI PostgreSQL." >&2
  exit 2
fi
if ! sudo -n true; then
  echo "Passwordless sudo is required to provision the isolated native CI PostgreSQL cluster." >&2
  exit 2
fi
project_id="$(
  glab api "projects/${project_path//\//%2F}" |
    jq -r '.id // empty'
)"
if [[ -z "$project_id" ]]; then
  echo "Unable to resolve the GitLab project before CI PostgreSQL rotation." >&2
  exit 2
fi
if ! bash "$repo_root/scripts/codex-review-ci.sh" \
  --validate-gitlab-ci-variable-sources \
  "$project_path" \
  "" \
  project-before-provision; then
  echo "Refusing PostgreSQL rotation while unapproved CI variable sources exist." >&2
  exit 2
fi
validation_runner_ids="$(
  glab api "projects/${project_id}/runners?per_page=100" |
    jq -r '.[] | select(.description == "open-alm-validation-docker-runner") | .id'
)"
if [[ "$(wc -w <<<"$validation_runner_ids")" -ne 1 ]]; then
  echo "Expected exactly one validation runner before PostgreSQL rotation." >&2
  exit 2
fi
validation_runner_id="$validation_runner_ids"
validation_runner_json="$(glab api "runners/${validation_runner_id}")"
if ! jq -e '
  .description == "open-alm-validation-docker-runner"
  and (.status == "online" or .status == "paused")
  and .online == true
  and .tag_list == ["open-alm-validation"]
  and .locked == true
  and .run_untagged == false
  and .runner_type == "project_type"
  and (.paused | type) == "boolean"
' >/dev/null <<<"$validation_runner_json"; then
  echo "The validation runner is not in an auditable state for PostgreSQL rotation." >&2
  exit 2
fi
validation_runner_was_paused="$(jq -r '.paused | tostring' <<<"$validation_runner_json")"
validation_runner_pause_changed=0
credentials_mutated=0
host_mutated=0
rotation_succeeded=0
hba_temp=""
credentials_dir=""
cleanup() {
  local runner_cleanup_action
  if [[ -n "$hba_temp" ]]; then
    rm -f "$hba_temp"
  fi
  if [[ -n "$credentials_dir" ]]; then
    rm -rf "$credentials_dir"
  fi
  runner_cleanup_action="$(
    rotation_runner_cleanup_action \
      "$validation_runner_pause_changed" \
      "$credentials_mutated" \
      "$host_mutated" \
      "$rotation_succeeded"
  )"
  case "$runner_cleanup_action" in
    restore-active)
      glab api --method PUT "runners/${validation_runner_id}" \
        --field paused=false >/dev/null 2>&1 || true
      ;;
    keep-paused)
      echo "PostgreSQL rotation did not converge; validation runner remains paused." >&2
      ;;
  esac
}
trap cleanup EXIT

if [[ "$validation_runner_was_paused" == "false" ]]; then
  validation_runner_pause_changed=1
  glab api --method PUT "runners/${validation_runner_id}" \
    --field paused=true >/dev/null
fi
if ! glab api "runners/${validation_runner_id}" |
  jq -e '.paused == true' >/dev/null; then
  echo "The validation runner did not enter paused state." >&2
  exit 2
fi
echo "Waiting 60 seconds for in-flight GitLab long-poll requests to quiesce."
sleep 60
zero_streak=0
for _attempt in $(seq 1 1800); do
  if ! glab api "runners/${validation_runner_id}" |
    jq -e '.paused == true' >/dev/null; then
    echo "The validation runner left paused state during PostgreSQL rotation." >&2
    exit 2
  fi
  running_jobs="$(
    glab api "runners/${validation_runner_id}/jobs?status=running&per_page=100"
  )"
  if ! jq -e 'type == "array"' >/dev/null <<<"$running_jobs"; then
    echo "Unable to verify validation runner jobs before PostgreSQL rotation." >&2
    exit 2
  fi
  if [[ "$(jq 'length' <<<"$running_jobs")" -eq 0 ]]; then
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
  echo "The validation runner did not reach stable idle before PostgreSQL rotation." >&2
  exit 2
fi
assert_source_freshness

existing_cluster="$(
  pg_lsclusters --no-header |
    awk -v major="$postgres_major" -v cluster="$cluster_name" \
      '$1 == major && $2 == cluster { print $0 }'
)"
cluster_created=0
if [[ -z "$existing_cluster" ]]; then
  host_mutated=1
  sudo install -d -o postgres -g postgres -m 700 "$cluster_data_dir"
  sudo pg_createcluster "$postgres_major" "$cluster_name" \
    --datadir "$cluster_data_dir" \
    --port "$cluster_port" \
    --start-conf=auto >/dev/null
  cluster_created=1
else
  existing_owner="$(awk '{print $5}' <<<"$existing_cluster")"
  existing_port="$(awk '{print $3}' <<<"$existing_cluster")"
  existing_data_dir="$(awk '{print $6}' <<<"$existing_cluster")"
  if [[ "$existing_owner" != "postgres" ||
        "$existing_port" != "$cluster_port" ||
        "$existing_data_dir" != "$cluster_data_dir" ]]; then
    echo "Existing CI PostgreSQL cluster does not match the isolated port/data contract." >&2
    exit 2
  fi
fi

host_mutated=1
postgresql_conf="/etc/postgresql/${postgres_major}/${cluster_name}/postgresql.conf"
pg_hba_conf="/etc/postgresql/${postgres_major}/${cluster_name}/pg_hba.conf"
sudo install -d -o root -g root -m 755 "$(dirname "$cluster_systemd_drop_in_target")"
sudo install -o root -g root -m 644 \
  "$cluster_systemd_drop_in_source" \
  "$cluster_systemd_drop_in_target"
sudo systemctl daemon-reload
sudo sed -i \
  -E "s/^[#[:space:]]*listen_addresses[[:space:]]*=.*/listen_addresses = '127.0.0.1,${cluster_listen_address}'/" \
  "$postgresql_conf"
if ! sudo grep -Eq "^listen_addresses = '127\\.0\\.0\\.1,${cluster_listen_address//./\\.}'$" \
  "$postgresql_conf"; then
  echo "Unable to set the isolated CI PostgreSQL listener." >&2
  exit 2
fi
sudo sed -i \
  -E "s/^[#[:space:]]*max_locks_per_transaction[[:space:]]*=.*/max_locks_per_transaction = ${postgres_max_locks_per_transaction}/" \
  "$postgresql_conf"
if ! sudo grep -Eq \
  "^max_locks_per_transaction = ${postgres_max_locks_per_transaction}$" \
  "$postgresql_conf"; then
  echo "Unable to set the isolated CI PostgreSQL lock table capacity." >&2
  exit 2
fi
# This cluster is isolated, contains no durable data, and can be reprovisioned
# after a host crash or corruption. Avoid forcing hundreds of thousands of
# test-only relation files through durable checkpoints after per-test
# TRUNCATE + pg_restore isolation.
while IFS= read -r setting; do
  setting_name="${setting%%=*}"
  setting_value="${setting#*=}"
  sudo sed -i \
    -E "s/^[#[:space:]]*${setting_name}[[:space:]]*=.*/${setting_name} = ${setting_value}/" \
    "$postgresql_conf"
  if ! sudo grep -Eq "^${setting_name} = ${setting_value}$" "$postgresql_conf"; then
    echo "Unable to set isolated CI PostgreSQL ${setting_name}." >&2
    exit 2
  fi
done < <(ci_postgres_setting_lines)

hba_temp="$(mktemp)"
credentials_dir="$(mktemp -d)"
chmod 600 "$hba_temp"
chmod 700 "$credentials_dir"
printf '%s\n' \
  "# Managed by Open ALM scripts/configure-ci-validation-env.sh" \
  "local all postgres peer" \
  "local all all scram-sha-256" \
  "host all ${ci_role} 127.0.0.1/32 scram-sha-256" \
  "host all ${ci_role} ${validation_subnet} scram-sha-256" \
  >"$hba_temp"
sudo install -o postgres -g postgres -m 600 "$hba_temp" "$pg_hba_conf"

if [[ "$cluster_created" -eq 1 ]]; then
  sudo pg_ctlcluster "$postgres_major" "$cluster_name" start
else
  sudo pg_ctlcluster "$postgres_major" "$cluster_name" restart
fi
cluster_status="$(
  pg_lsclusters --no-header |
    awk -v major="$postgres_major" -v cluster="$cluster_name" \
      '$1 == major && $2 == cluster { print $4 }'
)"
if [[ "$cluster_status" != "online" ]]; then
  echo "The isolated CI PostgreSQL cluster did not become online." >&2
  exit 2
fi
for dependency_property in Wants After; do
  dependency_value="$(
    systemctl show "$cluster_unit_name" \
      --property "$dependency_property" \
      --value
  )"
  for required_dependency in network-online.target docker.service; do
    if [[ " $dependency_value " != *" $required_dependency "* ]]; then
      echo \
        "The isolated CI PostgreSQL ${dependency_property} contract is missing ${required_dependency}." \
        >&2
      exit 2
    fi
  done
done
configured_max_locks="$(
  sudo -n -u postgres psql \
    --cluster "${postgres_major}/${cluster_name}" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command "SHOW max_locks_per_transaction;"
)"
if [[ "$configured_max_locks" != "$postgres_max_locks_per_transaction" ]]; then
  echo "The isolated CI PostgreSQL lock table capacity did not converge." >&2
  exit 2
fi
configured_test_settings="$(
  sudo -n -u postgres psql \
    --cluster "${postgres_major}/${cluster_name}" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command "
      SELECT name || '=' || setting
      FROM pg_settings
      WHERE name IN (
        'checkpoint_completion_target',
        'checkpoint_timeout',
        'fsync',
        'full_page_writes',
        'max_wal_size',
        'synchronous_commit',
        'wal_compression'
      )
      ORDER BY name;
    "
)"
expected_test_settings="$(
  printf '%s\n' \
    "checkpoint_completion_target=0" \
    "checkpoint_timeout=60" \
    "fsync=off" \
    "full_page_writes=off" \
    "max_wal_size=8192" \
    "synchronous_commit=off" \
    "wal_compression=pglz"
)"
if [[ "$configured_test_settings" != "$expected_test_settings" ]]; then
  echo "The isolated CI PostgreSQL test workload settings did not converge." >&2
  exit 2
fi

ci_password="$(openssl rand -hex 32)"
bootstrap_sql="$credentials_dir/bootstrap.sql"
umask 077
{
  printf '%s\n' \
    "DO \$bootstrap\$" \
    "BEGIN" \
    "  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '${ci_role}') THEN" \
    "    CREATE ROLE ${ci_role} LOGIN NOSUPERUSER NOCREATEROLE CREATEDB NOREPLICATION NOBYPASSRLS;" \
    "  END IF;" \
    "  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = '${analysis_role}') THEN" \
    "    CREATE ROLE ${analysis_role} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS;" \
    "  END IF;" \
    "END" \
    "\$bootstrap\$;" \
    "ALTER ROLE ${ci_role} WITH LOGIN INHERIT NOSUPERUSER NOCREATEROLE CREATEDB NOREPLICATION NOBYPASSRLS PASSWORD '${ci_password}';" \
    "ALTER ROLE ${analysis_role} WITH NOLOGIN NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS;" \
    "GRANT ${analysis_role} TO ${ci_role};" \
    "ALTER ROLE ${ci_role} SET statement_timeout = '15min';" \
    "ALTER ROLE ${ci_role} SET lock_timeout = '2min';" \
    "ALTER ROLE ${ci_role} SET idle_in_transaction_session_timeout = '2min';" \
    "CREATE EXTENSION IF NOT EXISTS vector;" \
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
} >"$bootstrap_sql"
credentials_mutated=1
sudo -n -u postgres psql \
  --cluster "${postgres_major}/${cluster_name}" \
  --dbname template1 \
  --set ON_ERROR_STOP=1 \
  --quiet \
  <"$bootstrap_sql" >/dev/null

postgres_dsn_file="$credentials_dir/OPEN_ALM_CI_POSTGRES_DSN"
printf 'postgresql+psycopg://%s:%s@%s:%s/postgres' \
  "$ci_role" "$ci_password" "$cluster_dsn_host" "$cluster_port" \
  >"$postgres_dsn_file"
chmod 600 "$postgres_dsn_file"
unset ci_password

ci_variable_count="$(
  glab api --paginate \
    "projects/${project_id}/variables?per_page=100" |
    jq -s 'add | length'
)"
ci_variable_action="$(ci_variable_write_action "$ci_variable_count")"
case "$ci_variable_action" in
  set)
    glab variable set OPEN_ALM_CI_POSTGRES_DSN \
      --repo "$project_path" \
      --scope ci-validation \
      --raw \
      --masked \
      --hidden \
      --description "Isolated native CI PostgreSQL cluster; no dev or production data" \
      <"$postgres_dsn_file" >/dev/null
    ;;
  update)
    glab variable update OPEN_ALM_CI_POSTGRES_DSN \
      --repo "$project_path" \
      --scope ci-validation \
      --raw \
      --masked \
      --description "Isolated native CI PostgreSQL cluster; no dev or production data" \
      <"$postgres_dsn_file" >/dev/null
    ;;
esac

if ! bash "$repo_root/scripts/codex-review-ci.sh" \
  --validate-gitlab-ci-variable-sources "$project_path"; then
  echo "GitLab CI variable sources did not converge to the isolated allowlist." >&2
  exit 2
fi

role_contract="$(
  PGPASSWORD="$(sed -E 's#^[^:]+://[^:]+:([^@]+)@.*#\1#' "$postgres_dsn_file")" \
  psql \
    --host 127.0.0.1 \
    --port "$cluster_port" \
    --username "$ci_role" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command "SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls FROM pg_roles WHERE rolname = current_user;"
)"
if [[ "$role_contract" != "t|t|f|f|t|f|f" ]]; then
  echo "The CI PostgreSQL role does not match the non-superuser CREATEDB contract." >&2
  exit 2
fi
analysis_role_contract="$(
  sudo -n -u postgres psql \
    --cluster "${postgres_major}/${cluster_name}" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command "SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls FROM pg_roles WHERE rolname = '${analysis_role}';"
)"
if [[ "$analysis_role_contract" != "f|f|f|f|f|f|f" ]]; then
  echo "The CI analysis reader role does not match its no-login privilege contract." >&2
  exit 2
fi

rotation_succeeded=1
if [[ "$validation_runner_pause_changed" -eq 1 ]]; then
  glab api --method PUT "runners/${validation_runner_id}" \
    --field paused=false >/dev/null
  if [[ "$(glab api "runners/${validation_runner_id}" | jq -r '.paused | tostring')" != "false" ]]; then
    echo "The validation runner did not return to its pre-rotation active state." >&2
    exit 2
  fi
  validation_runner_pause_changed=0
fi

echo "Configured isolated native PostgreSQL ${postgres_major}/${cluster_name} on port ${cluster_port}; no shared dev-service credentials were uploaded."
