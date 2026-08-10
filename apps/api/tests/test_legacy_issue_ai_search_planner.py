from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

from open_alm_api.domains.legacy_issues import ai_search_planner
from open_alm_api.domains.legacy_issues.ai_search import (
    sanitize_legacy_issue_search_plan,
)


def test_search_planner_budgets_compact_json_output(monkeypatch) -> None:
    execute = Mock(
        return_value=SimpleNamespace(
            completion=SimpleNamespace(
                text=json.dumps(
                    {
                        "intent": "investigate",
                        "datasets": ["common-master"],
                        "primary_keywords": ["냉매 소음"],
                        "keywords": ["유동음"],
                        "supporting_keywords": [],
                        "field_hints": ["symptom"],
                        "report_focus": ["원인"],
                        "related_field_expansions": [],
                    },
                    ensure_ascii=False,
                )
            ),
            decision=None,
        )
    )
    monkeypatch.setattr(ai_search_planner, "execute_llm", execute)

    plan, decision = ai_search_planner.plan_legacy_issue_search(
        cast(Any, object()),
        workspace=cast(Any, SimpleNamespace(id=uuid4())),
        user=cast(Any, SimpleNamespace(id=uuid4())),
        question="냉매 소음 원인 사례",
        requested_dataset_keys=("common-master",),
        audit_entity_id=None,
        source="test",
        context_strategy="test",
    )

    assert plan.primary_keywords == ("냉매 소음",)
    assert decision is None
    assert execute.call_args.kwargs["max_tokens"] == 2_048
    system_prompt = execute.call_args.kwargs["messages"][0]["content"]
    assert "at most 8 primary_keywords" in system_prompt
    assert "12 supporting_keywords" in system_prompt


def test_search_plan_sanitizer_enforces_prompt_budget_contract() -> None:
    values = [f"term-{index}" for index in range(20)]

    plan = sanitize_legacy_issue_search_plan(
        question="범용 검색",
        dataset_keys=None,
        primary_keywords=values,
        keywords=values,
        supporting_keywords=values,
        field_hints=values,
        report_focus=values,
        related_field_expansions=[
            "symptom",
            "cause",
            "countermeasure",
            "vehicle_model",
            "applied",
        ],
    )

    assert len(plan.primary_keywords) == 8
    assert len(plan.keywords) == 12
    assert len(plan.supporting_keywords) == 12
    assert len(plan.field_hints) == 8
    assert len(plan.report_focus) == 6
    assert len(plan.related_field_expansions) == 4
    assert all(
        len(value) <= 80
        for values_for_field in (
            plan.primary_keywords,
            plan.keywords,
            plan.supporting_keywords,
            plan.field_hints,
            plan.report_focus,
            plan.related_field_expansions,
        )
        for value in values_for_field
    )
