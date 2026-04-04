#!/usr/bin/env python3
import json
import sys

from manifest_utils import build_context_payload, load_all_domain_manifests, load_all_scenario_manifests, pick_scenario, resolve_domain_for_path


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(
            "usage: select_context_docs.py <scenario-id> [surface] | --path <file-path> [surface] | --domain <domain-id> [request-or-surface]",
            file=sys.stderr
        )
        return 1

    scenario_manifests = load_all_scenario_manifests()
    domain_manifests = load_all_domain_manifests()

    scenario_id = ""
    domain_id = ""
    path_hint = ""
    trailing = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--path":
            if i + 1 >= len(args):
                print("missing value for --path", file=sys.stderr)
                return 1
            path_hint = args[i + 1]
            i += 2
            continue
        if arg == "--domain":
            if i + 1 >= len(args):
                print("missing value for --domain", file=sys.stderr)
                return 1
            domain_id = args[i + 1]
            i += 2
            continue
        if not scenario_id and arg in scenario_manifests:
            scenario_id = arg
        else:
            trailing.append(arg)
        i += 1

    surface = " ".join(trailing).strip()
    domain_manifest = None
    if path_hint:
        domain_manifest = resolve_domain_for_path(path_hint, domain_manifests)
    elif domain_id:
        domain_manifest = domain_manifests.get(domain_id)
        if domain_manifest is None:
            print(f"unknown domain: {domain_id}", file=sys.stderr)
            return 2

    if scenario_id:
        scenario_manifest = scenario_manifests.get(scenario_id)
        if scenario_manifest is None:
            print(f"unknown scenario: {scenario_id}", file=sys.stderr)
            return 2
    else:
        candidate_ids = None if domain_manifest is None else domain_manifest.get("scenario_candidates", [])
        if domain_manifest is not None and len(candidate_ids) > 1 and not surface:
            print(
                f"domain '{domain_manifest['domain_id']}' maps to multiple scenarios; provide a scenario id or request text",
                file=sys.stderr
            )
            return 3
        scenario_manifest, confidence = pick_scenario(surface, scenario_manifests, candidate_ids=candidate_ids)
        if domain_manifest is not None and len(candidate_ids) > 1 and confidence == "low":
            print(
                f"request is still ambiguous for domain '{domain_manifest['domain_id']}'; provide a scenario id",
                file=sys.stderr
            )
            return 4

    payload = build_context_payload(scenario_manifest, domain_manifest, surface)
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
