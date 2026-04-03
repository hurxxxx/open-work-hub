#!/usr/bin/env python3
import json
import sys


BASE_DOCS = [
    "docs/agents/context-loading-policy.md",
    "docs/agents/agent-operating-standard.md"
]

SCENARIO_DOCS = {
    "documents-rag": "docs/harness/scenarios/documents-rag.md",
    "plm-query": "docs/harness/scenarios/plm-query.md",
    "draft-generation": "docs/harness/scenarios/draft-generation.md",
    "ocr-pipeline": "docs/harness/scenarios/ocr-pipeline.md",
    "wiki-pms": "docs/harness/scenarios/wiki-pms.md"
}

OPTIONAL_DOCS = {
    "eval": "docs/harness/eval-regression-spec.md",
    "runtime": "docs/harness/service-runtime-harness.md",
    "release": "docs/ops/release-gates-and-alerts.md",
    "architecture": "docs/architecture/system-blueprint.md",
    "workflow": "docs/ops/sprint-workflow.md"
}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: select_context_docs.py <scenario-id> [surface]", file=sys.stderr)
        return 1

    scenario_id = sys.argv[1]
    surface = sys.argv[2] if len(sys.argv) > 2 else ""
    scenario_doc = SCENARIO_DOCS.get(scenario_id)
    if scenario_doc is None:
        print(f"unknown scenario: {scenario_id}", file=sys.stderr)
        return 2

    optional = []
    lowered = surface.lower()
    if any(token in lowered for token in ["prompt", "workflow", "retrieval", "guardrail", "trace", "export", "eval"]):
        optional.append(OPTIONAL_DOCS["eval"])
    if any(token in lowered for token in ["runtime", "service", "llm", "ocr", "generation", "online-eval"]):
        optional.append(OPTIONAL_DOCS["runtime"])
    if any(token in lowered for token in ["release", "gate", "scorecard", "alert", "ops"]):
        optional.append(OPTIONAL_DOCS["release"])
    if any(token in lowered for token in ["architecture", "package", "module", "boundary", "repo"]):
        optional.append(OPTIONAL_DOCS["architecture"])
    if any(token in lowered for token in ["workflow-habit", "retro", "checkpoint", "learn"]):
        optional.append(OPTIONAL_DOCS["workflow"])

    avoid = sorted(path for key, path in SCENARIO_DOCS.items() if key != scenario_id)
    payload = {
        "scenario_id": scenario_id,
        "must_read_docs": BASE_DOCS + [scenario_doc],
        "optional_support_docs": sorted(dict.fromkeys(optional)),
        "do_not_load_by_default": avoid
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
