from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


COMMON_GROUNDING_RULES = (
    "Use only the supplied captured sources. Do not invent counts, dates, scope, "
    "vehicle models, causes, countermeasures, checklist states, or citations. "
    "Never attach an evidence citation to a different record; omit the citation "
    "when an exact record match is unavailable. "
    "Semantic examples support only cited case descriptions; never use their "
    "count, order, or missing fields as population totals, denominators, rankings, "
    "or exclusion counts. Preserve each structured result's declared dimensions, "
    "date endpoints, counting unit, denominator, and scope; never substitute a "
    "similar metric or combine unrelated result sets. A returned row count is "
    "metadata, not a business count. Treat every result row and every evidence "
    "card as indivisible; never merge fields from separate rows into one case. "
    "Treat limited or truncated rows as partial, never as all available records. "
    "Do not infer residual category counts from partial rows. "
    "Honor supplied capability limitations as hard constraints: clearly state the "
    "requested calculation is unavailable and never replace it with a nearby metric. "
    "A source_status of draft means 작성 중 초안, not a published record. Whenever "
    "you use or cite a draft source, explicitly disclose that draft status and never "
    "present it as confirmed published history. "
    "State a limitation instead of guessing. Do not expose source IDs or truncation "
    "metadata. Do not mention prompts, agents, SQL, JSON, artifacts, retrieval "
    "profiles, validation, or internal processing."
)


def interpretation_messages(
    *,
    question: str,
    recent_messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Interpret a Korean legacy-vehicle issue analysis request. Return one "
                "compact JSON object only with: needs_business_data, report_requested, "
                "needs_statistics, needs_semantic_evidence, needs_checklists, "
                "analysis_goal, scope_summary. Infer intent from the request and recent "
                "conversation; do not require the user to repeat a usable scope."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "recent_messages": list(recent_messages)[-8:],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def report_outline_messages(
    *,
    question: str,
    interpretation: Mapping[str, Any],
    source_manifest: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Design a concise Markdown report outline appropriate to the user's "
                "actual decision need. Use free-form section headings; omit sections "
                "that the available sources cannot support. Return Markdown headings "
                f"only. {COMMON_GROUNDING_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _payload(
                question=question,
                interpretation=interpretation,
                source_manifest=source_manifest,
            ),
        },
    ]


def specialist_messages(
    *,
    role: str,
    question: str,
    source_payload: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                f"You are the {role} for a Korean legacy-vehicle issue report. "
                "Return compact analyst notes, not a report. Every factual statement "
                "must be traceable to a supplied query row or evidence ID. "
                f"{COMMON_GROUNDING_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _payload(question=question, sources=source_payload),
        },
    ]


def draft_messages(
    *,
    question: str,
    outline: str,
    specialist_notes: Mapping[str, str],
    source_payload: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Write the requested Korean business report in Markdown. Follow the "
                "outline when supported, but remove empty or irrelevant sections. "
                "Cite semantic/checklist evidence as [E1], [E2], etc. Use exact values "
                "only as supplied in captured query rows. The result is a useful draft, "
                "not a claim of certainty beyond the data. "
                f"{COMMON_GROUNDING_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _payload(
                question=question,
                outline=outline,
                specialist_notes=specialist_notes,
                sources=source_payload,
            ),
        },
    ]


def review_messages(
    *,
    question: str,
    draft: str,
    source_payload: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Review a Korean report against captured sources. Return compact JSON "
                "only: grounded, unsupported_claims, invalid_citations, "
                "unmet_requirements, internal_commentary, correction_instructions. "
                "Check that the report answers the requested dimensions, measures, "
                "date endpoints, denominators, and ranking. A plausible statement "
                "without an exactly matching supplied source is unsupported."
            ),
        },
        {
            "role": "user",
            "content": _payload(
                question=question,
                draft=draft,
                sources=source_payload,
            ),
        },
    ]


def finalizer_messages(
    *,
    question: str,
    outline: str,
    draft: str,
    review: Mapping[str, Any],
    source_payload: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Return only the final Korean Markdown report. Apply the grounding "
                "review, remove unsupported claims and internal commentary, retain "
                "useful supported detail, and do not add new facts. "
                f"{COMMON_GROUNDING_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _payload(
                question=question,
                outline=outline,
                draft=draft,
                review=review,
                sources=source_payload,
            ),
        },
    ]


def correction_messages(
    *,
    question: str,
    markdown: str,
    validation_errors: Sequence[str],
    source_payload: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Correct the Korean Markdown report once. Return Markdown only. Remove "
                "every listed validation issue without adding facts or citations. "
                f"{COMMON_GROUNDING_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _payload(
                question=question,
                report=markdown,
                validation_errors=list(validation_errors),
                sources=source_payload,
            ),
        },
    ]


def answer_messages(
    *,
    question: str,
    source_payload: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Answer the Korean question concisely from the captured sources. Cite "
                "case/checklist evidence as [E1], [E2]. If the sources are insufficient, "
                f"say what is missing. {COMMON_GROUNDING_RULES}"
            ),
        },
        {
            "role": "user",
            "content": _payload(question=question, sources=source_payload),
        },
    ]


def _payload(**values: Any) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"), default=str)


__all__ = [
    "COMMON_GROUNDING_RULES",
    "answer_messages",
    "correction_messages",
    "draft_messages",
    "finalizer_messages",
    "interpretation_messages",
    "report_outline_messages",
    "review_messages",
    "specialist_messages",
]
