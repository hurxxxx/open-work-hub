#!/usr/bin/env python3
import json
import sys

from manifest_utils import build_context_payload, load_all_domain_manifests, load_all_scenario_manifests, pick_scenario, resolve_domain_for_path


def main() -> int:
    args = sys.argv[1:]
    request_parts = []
    path_hint = ""

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
        request_parts.append(arg)
        i += 1

    request = " ".join(request_parts).strip()
    if not request and not path_hint:
        print("usage: select_scenario.py [--path <file-path>] '<request>'", file=sys.stderr)
        return 1

    scenario_manifests = load_all_scenario_manifests()
    domain_manifests = load_all_domain_manifests()

    domain_manifest = resolve_domain_for_path(path_hint, domain_manifests) if path_hint else None
    candidate_ids = None if domain_manifest is None else domain_manifest.get("scenario_candidates", [])
    if domain_manifest is not None and len(candidate_ids) > 1 and not request:
        print(
            f"domain '{domain_manifest['domain_id']}' maps to multiple scenarios; provide request text to disambiguate",
            file=sys.stderr
        )
        return 2
    scenario_manifest, confidence = pick_scenario(request, scenario_manifests, candidate_ids=candidate_ids)
    if domain_manifest is not None and len(candidate_ids) > 1 and confidence == "low":
        print(
            f"request is still ambiguous for domain '{domain_manifest['domain_id']}'; mention a scenario or domain-specific intent",
            file=sys.stderr
        )
        return 3

    payload = build_context_payload(scenario_manifest, domain_manifest, request)
    payload["confidence"] = confidence
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
