from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from open_alm_api.domains.ai.gateway import (
    AiGatewayContextPack,
    AiGatewayDecision,
    LlmWorkloadContext,
    execute_llm,
)
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    sanitize_legacy_issue_search_plan,
)
from open_alm_api.domains.legacy_issues.dataset_records import DATASET_DEFINITIONS
from open_alm_api.domains.legacy_issues.task_kinds import LEGACY_ISSUE_ASSISTANT_TASK_KIND


logger = logging.getLogger(__name__)


def plan_legacy_issue_search(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    requested_dataset_keys: tuple[str, ...] | None,
    audit_entity_id: str | None,
    source: str,
    context_strategy: str,
) -> tuple[LegacyIssueAssistantSearchPlan, AiGatewayDecision | None]:
    fallback = sanitize_legacy_issue_search_plan(
        question=question,
        dataset_keys=list(requested_dataset_keys) if requested_dataset_keys else None,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a legacy vehicle issue retrieval planner. Return only compact JSON. "
                "Return exactly one valid JSON object: no markdown, no code fence, no "
                "reasoning, no prose before or after the JSON. "
                "Do not write SQL. Select allowed datasets, normalized search keywords, "
                "synonyms, field hints, intent, and report focus for server-side retrieval. "
                "The retrieval engine will not apply a domain synonym dictionary or keyword "
                "heuristics. User questions can be Korean, English, mixed-language, abbreviated, "
                "compound, colloquial, or translated from another language. You must decide the "
                "canonical technical terms, decomposed terms, aliases, translations, likely field "
                "names, and conservative near-synonyms that should be searched for this specific "
                "question. Prefer same-language technical equivalents and dataset-field value "
                "forms before broad translations. If the question is Korean, primary_keywords "
                "should be mostly concise Hangul technical defect/state terms; put English "
                "translations in keywords or supporting_keywords unless they are established "
                "acronyms used in the data. Before "
                "adding translated English terms, include concise same-language technical nouns, "
                "morphological variants, and alternate terms that historical records are likely "
                "to use for the same target condition. Put terms "
                "that directly express the user's target in primary_keywords. Put broader, "
                "adjacent, or contextual recall terms in supporting_keywords. Use keywords for "
                "other useful normalized terms only when they are still discriminative for the "
                "requested defect or situation. Do not include generic administrative words, "
                "product family nouns, dataset names, or common report words just because they "
                "appear in the question. Do not let broad supporting terms redefine the target "
                "set. Do not invent causes, vehicle models, records, or conclusions. Keep every "
                "string under 80 characters and keep the arrays small: at most 8 "
                "primary_keywords, 12 keywords, 12 supporting_keywords, 8 field_hints, "
                "6 report_focus entries, and 4 related_field_expansions."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "requested_dataset_keys": list(requested_dataset_keys or ()),
                    "allowed_datasets": _dataset_catalog_payload(),
                    "response_schema": {
                        "intent": "short label",
                        "datasets": ["allowed dataset key"],
                        "primary_keywords": [
                            "same-language direct target terms that satisfy the request if found"
                        ],
                        "keywords": [
                            "canonical term",
                            "decomposed term",
                            "alias or conservative synonym",
                        ],
                        "supporting_keywords": [
                            "broader or adjacent terms used only to improve recall"
                        ],
                        "field_hints": ["field key or label"],
                        "report_focus": ["analysis angle"],
                        "related_field_expansions": [
                            (
                                "allowed field key to use for second-pass retrieval of other "
                                "records sharing values found in first-pass evidence"
                            )
                        ],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        result = execute_llm(
            LEGACY_ISSUE_ASSISTANT_TASK_KIND,
            LlmWorkloadContext(
                source=source,
                workspace_id=workspace.id,
                actor_user_id=user.id,
                app_id="legacy-issues",
            ),
            db,
            messages=messages,
            context_pack=AiGatewayContextPack(
                messages=messages,
                context_strategy=context_strategy,
                estimated_input_tokens=_estimate_tokens(messages),
            ),
            audit_entity_id=audit_entity_id,
            max_tokens=2_048,
            temperature=0,
        )
        completion = result.completion
        decision = result.decision
        payload = _parse_json_object(completion.text)
    except Exception:
        logger.exception("Legacy issue search planning failed; using conservative fallback.")
        return fallback, None
    plan = sanitize_legacy_issue_search_plan(
        question=question,
        dataset_keys=payload.get("datasets") if isinstance(payload, dict) else None,
        primary_keywords=(payload.get("primary_keywords") if isinstance(payload, dict) else None),
        keywords=payload.get("keywords") if isinstance(payload, dict) else None,
        supporting_keywords=(
            payload.get("supporting_keywords") if isinstance(payload, dict) else None
        ),
        field_hints=payload.get("field_hints") if isinstance(payload, dict) else None,
        intent=payload.get("intent") if isinstance(payload, dict) else None,
        report_focus=payload.get("report_focus") if isinstance(payload, dict) else None,
        related_field_expansions=(
            payload.get("related_field_expansions") if isinstance(payload, dict) else None
        ),
    )
    if requested_dataset_keys:
        requested = tuple(key for key in requested_dataset_keys if key in DATASET_DEFINITIONS)
        if requested:
            plan = sanitize_legacy_issue_search_plan(
                question=question,
                dataset_keys=requested,
                primary_keywords=plan.primary_keywords,
                keywords=plan.keywords,
                supporting_keywords=plan.supporting_keywords,
                field_hints=plan.field_hints,
                intent=plan.intent,
                report_focus=plan.report_focus,
                related_field_expansions=plan.related_field_expansions,
            )
    return plan, decision


def _dataset_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "key": definition.key,
            "title_ko": definition.title_ko,
            "title_en": definition.title_en,
            "fields": [
                {
                    "key": field.key,
                    "label_ko": field.label_ko,
                    "label_en": field.label_en,
                }
                for field in definition.fields
            ],
        }
        for definition in DATASET_DEFINITIONS.values()
    ]


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    payload = json.loads(stripped)
    return payload if isinstance(payload, dict) else {}


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    size = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, size // 4)


__all__ = ["plan_legacy_issue_search"]
