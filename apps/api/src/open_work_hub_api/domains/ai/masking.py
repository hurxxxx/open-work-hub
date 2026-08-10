from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.ai.boundary_safety import (
    ExternalPayloadSafetyDecision,
    ExternalPayloadTextSpan,
    detect_external_payload_text_spans,
    evaluate_external_payload_safety,
)
from open_work_hub_api.domains.ai.privacy_filter import (
    PrivacyFilterDetection,
    detect_privacy_filter_spans,
)
from open_work_hub_api.domains.ai.security_policy import (
    CUSTOM_BLOCK_ENTITY_TYPE,
    HARD_EXTERNAL_TRANSFER_BLOCKERS,
    MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS,
    POLICY_MASK_AND_SEND_REASON,
    SENSITIVE_IDENTIFIER_ENTITY_TYPES,
    UNKNOWN_EXTERNAL_ENTITY_BLOCKER,
    external_transfer_blockers_from_safety,
    hard_external_transfer_blockers,
    normalize_external_transfer_blockers,
)


EXTERNAL_PAYLOAD_MASKED_REASON = "external_payload_masked"
HARD_EXTERNAL_TRANSFER_BLOCKER_REASON = "hard_external_transfer_blocker"
MASKING_UNSUPPORTED_BLOCKER_REASON = "masking_unsupported_blocker"
MASKING_UNSUPPORTED_CONTENT_REASON = "masking_unsupported_content"
MASKING_POST_CHECK_FAILED_REASON = "masked_payload_still_sensitive"


@dataclass(frozen=True)
class PayloadMaskSpan:
    text_index: int
    start: int
    end: int
    entity_type: str
    blocker_type: str
    source: str


@dataclass(frozen=True)
class ExternalPayloadMaskingResult:
    allowed: bool
    reason_code: str
    mask_applied: bool = False
    masked_texts: tuple[str, ...] = ()
    masked_entity_types: tuple[str, ...] = ()
    masked_text_count: int = 0
    blocker_types: tuple[str, ...] = ()
    hard_blocker_types: tuple[str, ...] = ()
    pii_hits: tuple[str, ...] = ()
    privacy_filter_status: str = "disabled"
    privacy_filter_used: bool = False
    privacy_filter_enabled: bool = False
    privacy_filter_entity_types: tuple[str, ...] = ()
    privacy_filter_match_count: int = 0


def evaluate_external_payload_masking(
    texts: list[str] | tuple[str, ...],
    *,
    safety_decision: ExternalPayloadSafetyDecision,
    custom_block_term_count: int = 0,
    unsupported_content: bool = False,
    settings: Settings | None = None,
) -> ExternalPayloadMaskingResult:
    normalized_texts = tuple(text or "" for text in texts)
    original_blockers = external_transfer_blockers_from_safety(
        safety_decision,
        custom_block_term_count=custom_block_term_count,
    )
    original_hard_blockers = hard_external_transfer_blockers(original_blockers)
    if original_hard_blockers:
        return _blocked_result(
            reason_code=HARD_EXTERNAL_TRANSFER_BLOCKER_REASON,
            texts=normalized_texts,
            blocker_types=original_blockers,
            hard_blocker_types=original_hard_blockers,
        )

    unsupported_original = _unsupported_mask_blockers(original_blockers)
    if unsupported_original:
        return _blocked_result(
            reason_code=MASKING_UNSUPPORTED_BLOCKER_REASON,
            texts=normalized_texts,
            blocker_types=original_blockers,
        )

    privacy_detection = detect_privacy_filter_spans(normalized_texts, settings=settings)
    if privacy_detection.status != "ok":
        return _blocked_result(
            reason_code=f"privacy_filter_{privacy_detection.status}",
            texts=normalized_texts,
            blocker_types=original_blockers,
            privacy_detection=privacy_detection,
        )

    spans = (
        *_regex_mask_spans(normalized_texts),
        *_privacy_filter_mask_spans(privacy_detection),
    )
    span_blockers = tuple(
        normalize_external_transfer_blockers([span.blocker_type for span in spans])
    )
    blocker_types = tuple(
        normalize_external_transfer_blockers((*original_blockers, *span_blockers))
    )
    hard_blockers = tuple(
        blocker for blocker in blocker_types if blocker in HARD_EXTERNAL_TRANSFER_BLOCKERS
    )
    if hard_blockers:
        return _blocked_result(
            reason_code=HARD_EXTERNAL_TRANSFER_BLOCKER_REASON,
            texts=normalized_texts,
            blocker_types=blocker_types,
            hard_blocker_types=hard_blockers,
            privacy_detection=privacy_detection,
        )

    unsupported_blockers = _unsupported_mask_blockers(blocker_types)
    if unsupported_blockers:
        return _blocked_result(
            reason_code=MASKING_UNSUPPORTED_BLOCKER_REASON,
            texts=normalized_texts,
            blocker_types=blocker_types,
            privacy_detection=privacy_detection,
        )

    if not spans:
        return ExternalPayloadMaskingResult(
            allowed=True,
            reason_code=POLICY_MASK_AND_SEND_REASON,
            masked_texts=normalized_texts,
            blocker_types=blocker_types,
            pii_hits=privacy_detection.pii_hits,
            privacy_filter_status=privacy_detection.status,
            privacy_filter_used=privacy_detection.used,
            privacy_filter_enabled=privacy_detection.enabled,
            privacy_filter_entity_types=_privacy_filter_entity_types(privacy_detection),
            privacy_filter_match_count=len(privacy_detection.spans),
        )
    if unsupported_content:
        return _blocked_result(
            reason_code=MASKING_UNSUPPORTED_CONTENT_REASON,
            texts=normalized_texts,
            blocker_types=blocker_types,
            privacy_detection=privacy_detection,
        )

    masked_texts = _apply_mask_spans(normalized_texts, spans)
    post_safety = evaluate_external_payload_safety(
        list(masked_texts),
        content_origin=safety_decision.content_origin,
        source_kinds=safety_decision.source_kinds,
        sensitivity_labels=safety_decision.sensitivity_labels,
    )
    post_blockers = external_transfer_blockers_from_safety(post_safety)
    if post_blockers:
        return _blocked_result(
            reason_code=MASKING_POST_CHECK_FAILED_REASON,
            texts=normalized_texts,
            blocker_types=tuple(
                normalize_external_transfer_blockers((*blocker_types, *post_blockers))
            ),
            privacy_detection=privacy_detection,
        )

    post_privacy = detect_privacy_filter_spans(masked_texts, settings=settings)
    if post_privacy.status != "ok":
        return _blocked_result(
            reason_code=f"privacy_filter_{post_privacy.status}",
            texts=normalized_texts,
            blocker_types=blocker_types,
            privacy_detection=post_privacy,
        )
    if post_privacy.blocker_types:
        return _blocked_result(
            reason_code=MASKING_POST_CHECK_FAILED_REASON,
            texts=normalized_texts,
            blocker_types=tuple(
                normalize_external_transfer_blockers((*blocker_types, *post_privacy.blocker_types))
            ),
            privacy_detection=post_privacy,
        )

    masked_entity_types = _dedupe_tuple(span.entity_type for span in spans)
    return ExternalPayloadMaskingResult(
        allowed=True,
        reason_code=EXTERNAL_PAYLOAD_MASKED_REASON,
        mask_applied=True,
        masked_texts=masked_texts,
        masked_entity_types=masked_entity_types,
        masked_text_count=sum(
            1 for original, masked in zip(normalized_texts, masked_texts) if original != masked
        ),
        blocker_types=blocker_types,
        pii_hits=_dedupe_tuple((*safety_decision.pii_hits, *privacy_detection.pii_hits)),
        privacy_filter_status=post_privacy.status,
        privacy_filter_used=privacy_detection.used or post_privacy.used,
        privacy_filter_enabled=privacy_detection.enabled or post_privacy.enabled,
        privacy_filter_entity_types=_privacy_filter_entity_types(privacy_detection),
        privacy_filter_match_count=len(privacy_detection.spans),
    )


def _regex_mask_spans(texts: tuple[str, ...]) -> tuple[PayloadMaskSpan, ...]:
    spans: list[PayloadMaskSpan] = []
    for span in detect_external_payload_text_spans(texts):
        classified = _classify_external_payload_span(span)
        if classified is not None:
            spans.append(classified)
    return tuple(spans)


def _privacy_filter_mask_spans(
    detection: PrivacyFilterDetection,
) -> tuple[PayloadMaskSpan, ...]:
    return tuple(
        PayloadMaskSpan(
            text_index=span.text_index,
            start=span.start,
            end=span.end,
            entity_type=span.entity_type,
            blocker_type=span.blocker_type,
            source="privacy_filter",
        )
        for span in detection.spans
    )


def _classify_external_payload_span(span: ExternalPayloadTextSpan) -> PayloadMaskSpan | None:
    entity_type = span.entity_type.strip().lower().replace("-", "_")
    if entity_type.startswith("pii:"):
        blocker_type = "pii"
    elif entity_type in SENSITIVE_IDENTIFIER_ENTITY_TYPES:
        blocker_type = "sensitive_identifier"
    elif entity_type in HARD_EXTERNAL_TRANSFER_BLOCKERS:
        blocker_type = entity_type
    elif entity_type in MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS:
        blocker_type = entity_type
    elif entity_type == CUSTOM_BLOCK_ENTITY_TYPE:
        blocker_type = CUSTOM_BLOCK_ENTITY_TYPE
    elif entity_type:
        blocker_type = UNKNOWN_EXTERNAL_ENTITY_BLOCKER
    else:
        return None
    return PayloadMaskSpan(
        text_index=span.text_index,
        start=span.start,
        end=span.end,
        entity_type=entity_type,
        blocker_type=blocker_type,
        source="regex",
    )


def _apply_mask_spans(
    texts: tuple[str, ...],
    spans: tuple[PayloadMaskSpan, ...],
) -> tuple[str, ...]:
    by_text_index: dict[int, list[PayloadMaskSpan]] = {}
    for span in spans:
        if span.start < span.end:
            by_text_index.setdefault(span.text_index, []).append(span)

    masked = list(texts)
    for text_index, text_spans in by_text_index.items():
        text = masked[text_index]
        ranges = _merged_ranges(text_spans)
        for start, end, blocker_type in reversed(ranges):
            text = f"{text[:start]}[masked:{blocker_type}]{text[end:]}"
        masked[text_index] = text
    return tuple(masked)


def _merged_ranges(spans: list[PayloadMaskSpan]) -> list[tuple[int, int, str]]:
    ordered = sorted(spans, key=lambda span: (span.start, span.end))
    ranges: list[tuple[int, int, str]] = []
    for span in ordered:
        blocker_type = _placeholder_blocker(span.blocker_type)
        if not ranges or span.start > ranges[-1][1]:
            ranges.append((span.start, span.end, blocker_type))
            continue
        start, end, existing_blocker = ranges[-1]
        ranges[-1] = (
            start,
            max(end, span.end),
            _more_restrictive_placeholder(existing_blocker, blocker_type),
        )
    return ranges


def _placeholder_blocker(blocker_type: str) -> str:
    if blocker_type == "sensitive_identifier":
        return "sensitive_identifier"
    if blocker_type in {"pii", "internal_url", "security_document", "credential"}:
        return blocker_type
    return "sensitive"


def _more_restrictive_placeholder(left: str, right: str) -> str:
    order = {
        "credential": 5,
        "security_document": 4,
        "internal_url": 3,
        "sensitive_identifier": 2,
        "pii": 1,
    }
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _unsupported_mask_blockers(blockers: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        blocker
        for blocker in normalize_external_transfer_blockers(list(blockers))
        if blocker not in MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS
    )


def _blocked_result(
    *,
    reason_code: str,
    texts: tuple[str, ...],
    blocker_types: tuple[str, ...],
    hard_blocker_types: tuple[str, ...] = (),
    privacy_detection: PrivacyFilterDetection | None = None,
) -> ExternalPayloadMaskingResult:
    return ExternalPayloadMaskingResult(
        allowed=False,
        reason_code=reason_code,
        masked_texts=texts,
        blocker_types=tuple(normalize_external_transfer_blockers(blocker_types)),
        hard_blocker_types=tuple(normalize_external_transfer_blockers(hard_blocker_types)),
        pii_hits=privacy_detection.pii_hits if privacy_detection is not None else (),
        privacy_filter_status=privacy_detection.status
        if privacy_detection is not None
        else "disabled",
        privacy_filter_used=privacy_detection.used if privacy_detection is not None else False,
        privacy_filter_enabled=privacy_detection.enabled
        if privacy_detection is not None
        else False,
        privacy_filter_entity_types=(
            _privacy_filter_entity_types(privacy_detection) if privacy_detection is not None else ()
        ),
        privacy_filter_match_count=(
            len(privacy_detection.spans) if privacy_detection is not None else 0
        ),
    )


def _privacy_filter_entity_types(
    detection: PrivacyFilterDetection,
) -> tuple[str, ...]:
    return _dedupe_tuple(span.entity_type for span in detection.spans)


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in out:
            out.append(normalized)
    return tuple(out)
