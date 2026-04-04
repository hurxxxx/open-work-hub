#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIO_DIR = REPO_ROOT / "docs" / "harness" / "manifests" / "scenarios"
DOMAIN_DIR = REPO_ROOT / "docs" / "agents" / "manifests" / "domain-rule-manifests"

BASE_DOCS = [
    "agents.md",
    "docs/agents/context-loading-policy.md",
    "docs/agents/agent-operating-standard.md"
]

OPTIONAL_DOCS = {
    "eval": "docs/harness/eval-regression-spec.md",
    "runtime": "docs/harness/service-runtime-harness.md",
    "trace": "docs/harness/trace-and-scorecard-spec.md",
    "release": "docs/ops/release-gates-and-alerts.md",
    "architecture": "docs/architecture/system-blueprint.md",
    "workflow": "docs/ops/sprint-workflow.md",
    "mapping": "docs/agents/domain-context-mapping.md"
}


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def dedupe(items):
    return list(dict.fromkeys(items))


def load_json(relative_path: str) -> dict:
    with (REPO_ROOT / relative_path).open("r", encoding="utf-8") as fp:
        return json.load(fp)


def load_all_scenario_manifests() -> dict:
    manifests = {}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        manifests[payload["scenario_id"]] = payload
    return manifests


def load_all_domain_manifests() -> dict:
    manifests = {}
    for path in sorted(DOMAIN_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        manifests[payload["domain_id"]] = payload
    return manifests


def resolve_domain_for_path(file_path: str, domain_manifests: dict) -> Optional[dict]:
    normalized = normalize_path(file_path)
    best_match = None
    best_length = -1

    for payload in domain_manifests.values():
        for prefix in payload.get("path_prefixes", []):
            normalized_prefix = normalize_path(prefix)
            if normalized == normalized_prefix or normalized.startswith(normalized_prefix):
                if len(normalized_prefix) > best_length:
                    best_match = payload
                    best_length = len(normalized_prefix)
    return best_match


def score_scenarios(request: str, scenario_manifests: dict, candidate_ids=None):
    normalized_request = request.lower().strip()
    if candidate_ids is None:
        candidate_ids = list(scenario_manifests.keys())

    scored = []
    for scenario_id in candidate_ids:
        manifest = scenario_manifests[scenario_id]
        keywords = manifest.get("keywords", [])
        score = 0
        for keyword in keywords:
            if keyword.lower() in normalized_request:
                score += 1
        if scenario_id in normalized_request:
            score += 2
        scored.append((score, scenario_id, manifest))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return scored


def pick_scenario(request: str, scenario_manifests: dict, candidate_ids=None):
    request = request.strip()
    candidates = candidate_ids or list(scenario_manifests.keys())
    if len(candidates) == 1 and not request:
        scenario_id = candidates[0]
        return scenario_manifests[scenario_id], "high"

    scored = score_scenarios(request, scenario_manifests, candidate_ids=candidates)
    top_score, _, _ = scored[0]
    confidence = "high" if top_score >= 2 else "medium" if top_score == 1 else "low"
    return scored[0][2], confidence


def optional_docs_for_surface(surface: str):
    lowered = surface.lower()
    optional = []
    if any(token in lowered for token in ["prompt", "workflow", "retrieval", "guardrail", "trace", "export", "eval"]):
        optional.append(OPTIONAL_DOCS["eval"])
        optional.append(OPTIONAL_DOCS["trace"])
    if any(token in lowered for token in ["runtime", "service", "llm", "ocr", "generation", "online-eval"]):
        optional.append(OPTIONAL_DOCS["runtime"])
    if any(token in lowered for token in ["release", "gate", "scorecard", "alert", "ops"]):
        optional.append(OPTIONAL_DOCS["release"])
    if any(token in lowered for token in ["architecture", "package", "module", "boundary", "repo"]):
        optional.append(OPTIONAL_DOCS["architecture"])
    if any(token in lowered for token in ["workflow-habit", "retro", "checkpoint", "learn"]):
        optional.append(OPTIONAL_DOCS["workflow"])
    return dedupe(optional)


def build_context_payload(scenario_manifest: dict, domain_manifest: Optional[dict], surface: str):
    must_read = list(BASE_DOCS)
    optional = list(scenario_manifest.get("optional_support_docs", []))
    avoid = list(scenario_manifest.get("do_not_load_by_default", []))

    if domain_manifest is not None:
        must_read.extend(domain_manifest.get("must_read_docs", []))
        optional.extend(domain_manifest.get("optional_support_docs", []))
        avoid.extend(domain_manifest.get("do_not_load_by_default", []))
        optional.append(OPTIONAL_DOCS["mapping"])

    must_read.extend(scenario_manifest.get("must_read_docs", []))
    optional.extend(optional_docs_for_surface(surface))
    must_read = dedupe(must_read)
    optional = [item for item in dedupe(optional) if item not in must_read]

    payload = {
        "scenario_id": scenario_manifest["scenario_id"],
        "resolved_domain": None if domain_manifest is None else domain_manifest["domain_id"],
        "must_read_docs": must_read,
        "optional_support_docs": optional,
        "do_not_load_by_default": dedupe(avoid),
        "expected_artifacts": scenario_manifest.get("expected_artifacts", [])
    }
    return payload
