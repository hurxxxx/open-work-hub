#!/usr/bin/env python3
import json
import sys

from manifest_utils import load_json


def format_threshold(metric: str, threshold):
    if metric.endswith("_rate") and isinstance(threshold, (int, float)):
        if threshold in (0, 1):
            operator = "="
        else:
            operator = ">="
        return f"{operator} {threshold:.2f}" if isinstance(threshold, float) else f"{operator} {threshold}"
    if metric.startswith("unsupported_") or metric.startswith("catastrophic_") or metric.endswith("_p95"):
        operator = "<="
    elif isinstance(threshold, (int, float)) and threshold == 0:
        operator = "="
    else:
        operator = ">="
    return f"{operator} {threshold}"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: required_regressions.py <scenario-id>", file=sys.stderr)
        return 1

    scenario_id = sys.argv[1]
    try:
        requirement = load_json(f"docs/harness/manifests/eval-suites/{scenario_id}.json")
    except FileNotFoundError:
        print(f"unknown scenario: {scenario_id}", file=sys.stderr)
        return 2

    payload = {
        "scenario_id": scenario_id,
        "eval_profile": requirement["eval_profile"],
        "runner": requirement["runner"]["primary"],
        "promptfoo_config": requirement["promptfoo_config"],
        "datasets": [item["name"] for item in requirement["datasets"]],
        "release_blocking_datasets": [item["name"] for item in requirement["datasets"] if item["required_for_release"]],
        "gate_metrics": {
            item["metric"]: format_threshold(item["metric"], item["threshold"])
            for item in requirement["graders"]
        }
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
