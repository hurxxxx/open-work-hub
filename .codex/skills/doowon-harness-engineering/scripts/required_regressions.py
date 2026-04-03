#!/usr/bin/env python3
import json
import sys


REQUIREMENTS = {
    "documents-rag": {
        "datasets": ["golden", "adversarial", "shadow"],
        "gate_metrics": {
            "citation_completeness": ">= 0.98",
            "groundedness": ">= 0.90",
            "retrieval_relevance": ">= 0.80",
            "nDCG@10": ">= 0.72",
            "acl_violations": "= 0"
        }
    },
    "plm-query": {
        "datasets": ["golden", "adversarial", "shadow"],
        "gate_metrics": {
            "unsafe_sql_block_rate": "= 1.00",
            "approved_query_success_rate": ">= 0.95",
            "summary_fidelity": ">= 0.90",
            "acl_violations": "= 0"
        }
    },
    "draft-generation": {
        "datasets": ["golden", "shadow"],
        "gate_metrics": {
            "template_field_fill_rate": ">= 0.95",
            "citation_block_attachment": ">= 0.98",
            "unsupported_claim_rate": "<= 0.05",
            "export_success_rate": ">= 0.99"
        }
    },
    "ocr-pipeline": {
        "datasets": ["golden", "adversarial", "drift"],
        "gate_metrics": {
            "parse_completeness": ">= 0.95",
            "table_extraction_f1": ">= 0.85",
            "catastrophic_failure_rate": "<= 0.01",
            "page_latency_p95": "<= 8s"
        }
    },
    "wiki-pms": {
        "datasets": ["golden", "adversarial", "shadow"],
        "gate_metrics": {
            "action_classification_accuracy": ">= 0.95",
            "schema_validity": ">= 0.99",
            "unauthorized_mutation_block_rate": "= 1.00",
            "summary_groundedness": ">= 0.92"
        }
    }
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: required_regressions.py <scenario-id>", file=sys.stderr)
        return 1

    scenario_id = sys.argv[1]
    requirement = REQUIREMENTS.get(scenario_id)
    if requirement is None:
        print(f"unknown scenario: {scenario_id}", file=sys.stderr)
        return 2

    print(json.dumps({"scenario_id": scenario_id, **requirement}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
