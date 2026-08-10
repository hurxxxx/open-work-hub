from __future__ import annotations

from typing import TYPE_CHECKING

from ai_do_api.domains.legacy_issues.dataset_records import DATASET_DEFINITIONS

if TYPE_CHECKING:
    from ai_do_api.domains.legacy_issues.ai_search import LegacyIssueAssistantSearchPlan


COMMON_EVIDENCE_VALUE_KEYS = (
    "legacy_issue_number",
    "row_no",
    "vehicle_model",
    "item",
    "sub_item",
    "defect_type",
    "problem",
    "symptom",
    "cause",
    "countermeasure",
    "action",
    "reflection_result",
    "design_reflected",
    "check_result",
    "notes",
)

COMPACT_EVIDENCE_VALUE_KEYS = (
    "legacy_issue_number",
    "vehicle_model",
    "item",
    "sub_item",
    "defect_type",
    "problem",
    "symptom",
    "cause",
    "countermeasure",
    "action",
    "reflection_result",
)


def selected_legacy_issue_evidence_values(
    values: dict[str, str],
    *,
    plan: LegacyIssueAssistantSearchPlan | None = None,
    matched_field_keys: tuple[str, ...] = (),
    base_keys: tuple[str, ...] = COMMON_EVIDENCE_VALUE_KEYS,
    max_value_length: int = 1200,
    fallback_limit: int = 12,
) -> dict[str, str]:
    dynamic_keys = _dynamic_plan_field_keys(plan)
    keys = _ordered_unique((*base_keys, *matched_field_keys, *dynamic_keys))
    selected = {
        key: str(values[key])[:max_value_length]
        for key in keys
        if key in values and str(values[key]).strip()
    }
    if selected:
        return selected
    return {
        key: str(value)[:max_value_length]
        for key, value in list(values.items())[:fallback_limit]
        if str(value).strip()
    }


def _dynamic_plan_field_keys(
    plan: LegacyIssueAssistantSearchPlan | None,
) -> tuple[str, ...]:
    if plan is None:
        return ()
    alias_map = _field_alias_map()
    field_refs = (
        *getattr(plan, "field_hints", ()),
        *getattr(plan, "related_field_expansions", ()),
    )
    keys: list[str] = []
    for field_ref in field_refs:
        normalized = _normalize_field_ref(field_ref)
        if not normalized:
            continue
        key = alias_map.get(normalized)
        if key:
            keys.append(key)
    return tuple(_ordered_unique(keys))


def _field_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for definition in DATASET_DEFINITIONS.values():
        for field in definition.fields:
            for alias in (
                field.key,
                field.key.replace("_", " "),
                field.label_ko,
                field.label_en,
                *field.aliases,
            ):
                normalized = _normalize_field_ref(alias)
                if normalized:
                    aliases[normalized] = field.key
    return aliases


def _normalize_field_ref(value: object) -> str:
    return " ".join(str(value).replace("_", " ").split()).casefold()


def _ordered_unique(items: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return tuple(result)


__all__ = [
    "COMPACT_EVIDENCE_VALUE_KEYS",
    "COMMON_EVIDENCE_VALUE_KEYS",
    "selected_legacy_issue_evidence_values",
]
