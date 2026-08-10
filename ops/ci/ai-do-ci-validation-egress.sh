#!/usr/bin/env bash
set -Eeuo pipefail

mode="${1:---apply}"
validation_chain="AI_DO_CI_EGRESS"
validation_subnet="172.29.250.0/24"
validation_gateway="172.29.250.1"
light_chain="AI_DO_CI_LIGHT_EGRESS"
light_subnet="172.29.251.0/24"
light_gateway="172.29.251.1"
gitlab_subnet="128.1.0.0/16"
gitlab_host="128.1.253.101"
gitlab_port="8929"
postgres_port="55432"

for command_name in grep iptables wc; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}." >&2
    exit 2
  fi
done

validation_rules=(
  "-d ${validation_gateway}/32 -p tcp -m tcp --dport ${postgres_port} -j ACCEPT"
  "-d ${validation_gateway}/32 -j DROP"
  "-d ${validation_subnet} -j ACCEPT"
  "-d ${gitlab_host}/32 -p tcp -m tcp --dport ${gitlab_port} -j ACCEPT"
  "-d ${gitlab_subnet} -j DROP"
  "-d 10.0.0.0/8 -j DROP"
  "-d 172.16.0.0/12 -j DROP"
  "-d 192.168.0.0/16 -j DROP"
  "-d 169.254.0.0/16 -j DROP"
)
light_rules=(
  "-d ${light_gateway}/32 -j DROP"
  "-d ${light_subnet} -j ACCEPT"
  "-d ${gitlab_host}/32 -p tcp -m tcp --dport ${gitlab_port} -j ACCEPT"
  "-d ${gitlab_subnet} -j DROP"
  "-d 10.0.0.0/8 -j DROP"
  "-d 172.16.0.0/12 -j DROP"
  "-d 192.168.0.0/16 -j DROP"
  "-d 169.254.0.0/16 -j DROP"
)

check_policy() {
  local policy_chain="$1"
  local policy_subnet="$2"
  local policy_label="$3"
  local rules_name="$4"
  local jump_count rule
  local -n policy_rules="$rules_name"

  jump_count="$(
    iptables -t raw -S PREROUTING |
      grep -Fxc -- "-A PREROUTING -s ${policy_subnet} -j ${policy_chain}" ||
      true
  )"
  if [[ "$jump_count" -ne 1 ]] ||
     [[ "$(
       iptables -t raw -S PREROUTING |
         grep -Fc -- "-j ${policy_chain}" ||
         true
     )" -ne 1 ]]; then
    echo "${policy_label} egress policy must have exactly one raw PREROUTING jump." >&2
    return 1
  fi
  if [[ "$(iptables -t raw -S "$policy_chain" | wc -l)" -ne "$(( ${#policy_rules[@]} + 1 ))" ]]; then
    echo "${policy_label} egress policy contains unexpected rules." >&2
    return 1
  fi
  for rule in "${policy_rules[@]}"; do
    if ! iptables -t raw -C "$policy_chain" $rule; then
      echo "${policy_label} egress policy is missing an enforced destination rule." >&2
      return 1
    fi
  done
}

apply_policy() {
  local policy_chain="$1"
  local policy_subnet="$2"
  local rules_name="$3"
  local rule
  local -n policy_rules="$rules_name"

  iptables -t raw -N "$policy_chain" 2>/dev/null || true
  iptables -t raw -F "$policy_chain"
  while iptables -t raw -C PREROUTING \
    -s "$policy_subnet" -j "$policy_chain" 2>/dev/null; do
    iptables -t raw -D PREROUTING -s "$policy_subnet" -j "$policy_chain"
  done
  iptables -t raw -I PREROUTING 1 -s "$policy_subnet" -j "$policy_chain"
  for rule in "${policy_rules[@]}"; do
    iptables -t raw -A "$policy_chain" $rule
  done
}

case "$mode" in
  --check)
    check_policy "$validation_chain" "$validation_subnet" \
      "Validation" validation_rules
    check_policy "$light_chain" "$light_subnet" \
      "Light validation" light_rules
    ;;
  --apply)
    apply_policy "$validation_chain" "$validation_subnet" validation_rules
    apply_policy "$light_chain" "$light_subnet" light_rules
    check_policy "$validation_chain" "$validation_subnet" \
      "Validation" validation_rules
    check_policy "$light_chain" "$light_subnet" \
      "Light validation" light_rules
    ;;
  --apply-light)
    check_policy "$validation_chain" "$validation_subnet" \
      "Validation" validation_rules
    apply_policy "$light_chain" "$light_subnet" light_rules
    check_policy "$light_chain" "$light_subnet" \
      "Light validation" light_rules
    ;;
  *)
    echo "Usage: $0 [--apply|--apply-light|--check]" >&2
    exit 2
    ;;
esac
