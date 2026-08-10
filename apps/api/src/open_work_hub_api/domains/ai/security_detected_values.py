from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import re
from collections.abc import Iterable, Mapping

from sqlalchemy.orm import Session

from open_work_hub_api.domains.ai.boundary_safety import detect_external_payload_text_spans
from open_work_hub_api.domains.ai.models import AiSecurityDetectedValue
from open_work_hub_api.domains.ai.security_policy import (
    SENSITIVE_IDENTIFIER_ENTITY_TYPES,
    CUSTOM_BLOCK_ENTITY_TYPE,
    HARD_EXTERNAL_TRANSFER_BLOCKERS,
    MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS,
    UNKNOWN_EXTERNAL_ENTITY_BLOCKER,
    normalize_custom_block_terms,
)
from open_work_hub_api.domains.auth.models import AuditLog
from open_work_hub_api.domains.auth.security import new_id

MAX_DETECTED_VALUE_LENGTH = 1000


@dataclass(frozen=True)
class AiSecurityDetectedValueInput:
    detector: str
    entity_type: str
    blocker_type: str
    detected_value: str | None = None
    occurrence_count: int = 1


def collect_ai_security_detected_values(
    texts: Iterable[str],
    *,
    custom_block_terms: Iterable[str] = (),
    privacy_filter_entity_types: Iterable[str] = (),
    privacy_filter_match_count: int = 0,
) -> tuple[AiSecurityDetectedValueInput, ...]:
    normalized_texts = tuple(text or "" for text in texts)
    inputs: list[AiSecurityDetectedValueInput] = []

    for span in detect_external_payload_text_spans(normalized_texts):
        try:
            value = normalized_texts[span.text_index][span.start : span.end]
        except IndexError:
            continue
        if not value:
            continue
        entity_type = _normalize_identifier(span.entity_type)
        inputs.append(
            AiSecurityDetectedValueInput(
                detector="regex",
                entity_type=entity_type,
                blocker_type=_blocker_type_for_entity(entity_type),
                detected_value=_truncate_detected_value(value),
            )
        )

    for term in normalize_custom_block_terms(list(custom_block_terms)):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for text in normalized_texts:
            for match in pattern.finditer(text):
                value = match.group(0)
                if value:
                    inputs.append(
                        AiSecurityDetectedValueInput(
                            detector="custom_block_term",
                            entity_type=CUSTOM_BLOCK_ENTITY_TYPE,
                            blocker_type=CUSTOM_BLOCK_ENTITY_TYPE,
                            detected_value=_truncate_detected_value(value),
                        )
                    )

    privacy_counts = Counter(
        _normalize_identifier(value) for value in privacy_filter_entity_types if value
    )
    if privacy_filter_match_count > 0 and not privacy_counts:
        privacy_counts["privacy_filter"] = int(privacy_filter_match_count)
    for entity_type, count in privacy_counts.items():
        inputs.append(
            AiSecurityDetectedValueInput(
                detector="privacy_filter",
                entity_type=entity_type,
                blocker_type=_blocker_type_for_entity(entity_type),
                detected_value=None,
                occurrence_count=max(1, int(count)),
            )
        )

    return _coalesce_detected_values(inputs)


def record_ai_security_detected_values(
    db: Session,
    *,
    audit_log: AuditLog,
    payload: Mapping[str, object],
    detected_values: Iterable[Mapping[str, object] | AiSecurityDetectedValueInput],
) -> None:
    rows = _coalesce_detected_values(_detected_value_input(item) for item in detected_values)
    for item in rows:
        db.add(
            AiSecurityDetectedValue(
                id=new_id(),
                audit_log_id=audit_log.id,
                actor_user_id=audit_log.actor_user_id,
                workspace_id=_payload_string(payload, "workspace_id"),
                action=audit_log.action,
                source=_payload_string(payload, "source"),
                app_id=_payload_string(payload, "app_id"),
                task_kind=_payload_string(payload, "task_kind"),
                capability=_payload_string(payload, "capability"),
                provider=_payload_string(payload, "provider"),
                reason_code=(
                    _payload_string(payload, "policy_reason")
                    or _payload_string(payload, "ai_security_policy_reason")
                    or _payload_string(payload, "decision_reason")
                    or None
                ),
                detector=item.detector,
                entity_type=item.entity_type,
                blocker_type=item.blocker_type,
                detected_value=item.detected_value,
                value_hash=(
                    _detected_value_hash(item.detected_value)
                    if item.detected_value is not None
                    else None
                ),
                occurrence_count=max(1, item.occurrence_count),
                created_at=audit_log.created_at,
            )
        )


def serialize_detected_values(
    values: Iterable[AiSecurityDetectedValueInput],
) -> list[dict[str, object]]:
    return [
        {
            "detector": item.detector,
            "entity_type": item.entity_type,
            "blocker_type": item.blocker_type,
            "detected_value": item.detected_value,
            "occurrence_count": item.occurrence_count,
        }
        for item in values
    ]


def _coalesce_detected_values(
    values: Iterable[AiSecurityDetectedValueInput],
) -> tuple[AiSecurityDetectedValueInput, ...]:
    counts: dict[tuple[str, str, str, str | None], int] = {}
    for value in values:
        detector = _normalize_identifier(value.detector) or "unknown"
        entity_type = _normalize_identifier(value.entity_type) or "unknown"
        blocker_type = _normalize_identifier(value.blocker_type) or _blocker_type_for_entity(
            entity_type
        )
        detected_value = (
            _truncate_detected_value(value.detected_value)
            if value.detected_value is not None
            else None
        )
        key = (detector, entity_type, blocker_type, detected_value)
        counts[key] = counts.get(key, 0) + max(1, int(value.occurrence_count or 1))
    return tuple(
        AiSecurityDetectedValueInput(
            detector=detector,
            entity_type=entity_type,
            blocker_type=blocker_type,
            detected_value=detected_value,
            occurrence_count=count,
        )
        for (detector, entity_type, blocker_type, detected_value), count in counts.items()
    )


def _detected_value_input(
    value: Mapping[str, object] | AiSecurityDetectedValueInput,
) -> AiSecurityDetectedValueInput:
    if isinstance(value, AiSecurityDetectedValueInput):
        return value
    detected_value = value.get("detected_value")
    occurrence_count = value.get("occurrence_count")
    return AiSecurityDetectedValueInput(
        detector=str(value.get("detector") or "unknown"),
        entity_type=str(value.get("entity_type") or "unknown"),
        blocker_type=str(value.get("blocker_type") or ""),
        detected_value=detected_value if isinstance(detected_value, str) else None,
        occurrence_count=(
            int(occurrence_count)
            if isinstance(occurrence_count, int | float) and not isinstance(occurrence_count, bool)
            else 1
        ),
    )


def _blocker_type_for_entity(entity_type: str) -> str:
    normalized = _normalize_identifier(entity_type)
    if normalized.startswith("pii:"):
        return "pii"
    if normalized in SENSITIVE_IDENTIFIER_ENTITY_TYPES:
        return "sensitive_identifier"
    if normalized in HARD_EXTERNAL_TRANSFER_BLOCKERS:
        return normalized
    if normalized in MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS:
        return normalized
    if normalized == CUSTOM_BLOCK_ENTITY_TYPE:
        return CUSTOM_BLOCK_ENTITY_TYPE
    return UNKNOWN_EXTERNAL_ENTITY_BLOCKER


def _detected_value_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_identifier(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _payload_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _truncate_detected_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) <= MAX_DETECTED_VALUE_LENGTH:
        return stripped
    return stripped[:MAX_DETECTED_VALUE_LENGTH]
