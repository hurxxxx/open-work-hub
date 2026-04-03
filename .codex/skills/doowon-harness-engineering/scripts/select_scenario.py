#!/usr/bin/env python3
import json
import sys


SCENARIOS = {
    "documents-rag": {
        "keywords": ["document", "rag", "search", "citation", "retrieval", "문서", "검색", "근거"],
        "must_read": [
            "docs/agents/context-loading-policy.md",
            "docs/agents/agent-operating-standard.md",
            "docs/harness/scenarios/documents-rag.md"
        ]
    },
    "plm-query": {
        "keywords": ["plm", "sql", "bom", "query", "validator", "품목", "도면"],
        "must_read": [
            "docs/agents/context-loading-policy.md",
            "docs/agents/agent-operating-standard.md",
            "docs/harness/scenarios/plm-query.md"
        ]
    },
    "draft-generation": {
        "keywords": ["draft", "template", "docx", "pdf", "초안", "템플릿", "내보내기"],
        "must_read": [
            "docs/agents/context-loading-policy.md",
            "docs/agents/agent-operating-standard.md",
            "docs/harness/scenarios/draft-generation.md"
        ]
    },
    "ocr-pipeline": {
        "keywords": ["ocr", "layout", "scan", "image", "pdf", "표", "추출"],
        "must_read": [
            "docs/agents/context-loading-policy.md",
            "docs/agents/agent-operating-standard.md",
            "docs/harness/scenarios/ocr-pipeline.md"
        ]
    },
    "wiki-pms": {
        "keywords": ["wiki", "pms", "task", "issue", "summary", "작업", "이슈", "위키"],
        "must_read": [
            "docs/agents/context-loading-policy.md",
            "docs/agents/agent-operating-standard.md",
            "docs/harness/scenarios/wiki-pms.md"
        ]
    }
}


def main() -> int:
    request = " ".join(sys.argv[1:]).strip().lower()
    if not request:
        print("usage: select_scenario.py '<request>'", file=sys.stderr)
        return 1

    scored = []
    for scenario_id, meta in SCENARIOS.items():
        score = sum(1 for keyword in meta["keywords"] if keyword in request)
        scored.append((score, scenario_id, meta))

    scored.sort(reverse=True)
    score, scenario_id, meta = scored[0]
    payload = {
        "scenario_id": scenario_id,
        "confidence": "high" if score >= 2 else "medium" if score == 1 else "low",
        "must_read_docs": meta["must_read"],
        "optional_support_docs": [
            "docs/harness/eval-regression-spec.md",
            "docs/harness/service-runtime-harness.md",
            "docs/ops/release-gates-and-alerts.md"
        ],
        "do_not_load_by_default": [
            path["must_read"][-1]
            for key, path in SCENARIOS.items()
            if key != scenario_id
        ]
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
