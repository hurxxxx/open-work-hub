"""AI egress security policy resolution.

This module intentionally returns metadata only. Raw prompts, document content,
and custom term hits are never persisted by callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_alm_api.core.settings import is_production_like_environment
from open_alm_api.domains.ai.boundary_safety import ExternalPayloadSafetyDecision
from open_alm_api.domains.ai.models import (
    AiSecurityDataProtectionSettings,
    AiSecurityExternalTransferException,
    AiSecurityPolicyRule,
)
from open_alm_api.domains.auth.models import OrgUnit, User


AiSecurityPolicyEffect = Literal[
    "inherit",
    "block_external",
    "mask_and_send",
    "audit_only",
]
AiSecurityExternalTransferBlocker = Literal[
    "internal_context",
    "blocking_sensitivity_label",
    "company_sensitive_entity",
    "policy_block_external",
    "pii",
    "credential",
    "internal_url",
    "security_document",
    "custom_block_term",
    "unknown_external_entity",
]
AiSecurityDataProtectionAction = Literal["block", "mask_and_send"]
AiSecurityExternalAppAction = Literal["block", "mask_and_send"]

DATA_PROTECTION_SETTINGS_ID = "global"
CUSTOM_BLOCK_ENTITY_TYPE = "custom_block_term"
POLICY_BLOCK_EXTERNAL_REASON = "ai_security_policy_block_external"
POLICY_MASK_AND_SEND_REASON = "ai_security_policy_mask_and_send"
POLICY_AUDIT_ONLY_REASON = "ai_security_policy_audit_only"
CUSTOM_BLOCK_REASON = "custom_block_term_blocked"
EXTERNAL_TRANSFER_EXCEPTION_REASON = "external_transfer_exception_allowed"
POLICY_BLOCK_EXTERNAL_BLOCKER = "policy_block_external"
UNKNOWN_EXTERNAL_ENTITY_BLOCKER = "unknown_external_entity"
AI_SECURITY_LLM_CAPABILITY = "llm"
DEFAULT_DATA_PROTECTION_ACTION: AiSecurityDataProtectionAction = "block"
DEFAULT_EXTERNAL_APP_ACTION: AiSecurityExternalAppAction = "block"
AI_SECURITY_ENFORCEMENT_DISABLED_REASON = "ai_security_enforcement_disabled"
AI_SECURITY_ENFORCEMENT_REQUIRED_REASON = "ai_security_enforcement_required"

_EFFECTS: frozenset[str] = frozenset({"inherit", "block_external", "mask_and_send", "audit_only"})
_EXTERNAL_TRANSFER_BLOCKERS: frozenset[str] = frozenset(
    {
        "internal_context",
        "blocking_sensitivity_label",
        "company_sensitive_entity",
        POLICY_BLOCK_EXTERNAL_BLOCKER,
        "pii",
        "credential",
        "internal_url",
        "security_document",
        CUSTOM_BLOCK_ENTITY_TYPE,
        UNKNOWN_EXTERNAL_ENTITY_BLOCKER,
    }
)
EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS: frozenset[str] = frozenset(
    {
        "internal_context",
        "blocking_sensitivity_label",
        "company_sensitive_entity",
        POLICY_BLOCK_EXTERNAL_BLOCKER,
        "pii",
        "internal_url",
        "security_document",
    }
)
HARD_EXTERNAL_TRANSFER_BLOCKERS: frozenset[str] = frozenset(
    {
        "credential",
        CUSTOM_BLOCK_ENTITY_TYPE,
        UNKNOWN_EXTERNAL_ENTITY_BLOCKER,
    }
)
MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS: frozenset[str] = frozenset(
    {
        "company_sensitive_entity",
        "pii",
        "internal_url",
        "security_document",
    }
)
_DATA_PROTECTION_ACTIONS: frozenset[str] = frozenset({"block", "mask_and_send"})
_EXTERNAL_APP_ACTIONS: frozenset[str] = frozenset({"block", "mask_and_send"})
COMPANY_SENSITIVE_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "order_id",
        "product_code",
        "customer",
        "price",
        "cost",
        "contract",
    }
)
_CONSERVATIVE_EFFECT_RANK: dict[AiSecurityPolicyEffect, int] = {
    "block_external": 5,
    "mask_and_send": 4,
    "audit_only": 3,
    "inherit": 2,
}


@dataclass(frozen=True)
class AiSecurityPolicyContext:
    workspace_id: str | None = None
    actor_user_id: str | None = None
    org_unit_id: str | None = None
    app_id: str | None = None
    task_kind: str | None = None
    capability: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class AiSecurityPolicyDecision:
    effect: AiSecurityPolicyEffect = "inherit"
    reason_code: str = "no_matching_rule"
    rule_id: str | None = None
    rule_name: str | None = None
    matched_scope: dict[str, str] = field(default_factory=dict)
    audit_only: bool = False
    custom_block_terms: tuple[str, ...] = ()
    custom_block_term_count: int = 0

    @property
    def blocks_external(self) -> bool:
        return self.effect == "block_external" or self.custom_block_term_count > 0


@dataclass(frozen=True)
class AiSecurityExternalTransferExceptionDecision:
    allowed: bool = False
    reason_code: str = "no_matching_external_transfer_exception"
    exception_id: str | None = None
    exception_name: str | None = None
    matched_scope: dict[str, str] = field(default_factory=dict)
    allowed_blocker_types: tuple[str, ...] = ()
    matched_blocker_types: tuple[str, ...] = ()
    hard_blocker_types: tuple[str, ...] = ()
    expires_at: datetime | None = None


@dataclass(frozen=True)
class _RuleMatch:
    rule: AiSecurityPolicyRule
    effect: AiSecurityPolicyEffect
    score: int
    matched_scope: dict[str, str]


@dataclass(frozen=True)
class _ExceptionMatch:
    exception: AiSecurityExternalTransferException
    score: int
    matched_scope: dict[str, str]
    allowed_blocker_types: tuple[str, ...]


def normalize_ai_security_effect(value: object) -> AiSecurityPolicyEffect:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"local_only", "deny"}:
        return "block_external"
    if normalized == "external_allowed":
        return "inherit"
    if normalized in _EFFECTS:
        return normalized  # type: ignore[return-value]
    return "inherit"


def normalize_custom_block_terms(values: object) -> list[str]:
    if not isinstance(values, list | tuple | set):
        return []
    normalized: list[str] = []
    for value in values:
        term = str(value or "").strip()
        if len(term) < 2:
            continue
        if term not in normalized:
            normalized.append(term)
    return normalized[:200]


def normalize_external_transfer_blockers(values: object) -> list[str]:
    if not isinstance(values, list | tuple | set):
        return []
    normalized: list[str] = []
    for value in values:
        blocker = str(value or "").strip().lower().replace("-", "_")
        if blocker == "policy_local_only":
            blocker = POLICY_BLOCK_EXTERNAL_BLOCKER
        if blocker not in _EXTERNAL_TRANSFER_BLOCKERS or blocker in normalized:
            continue
        normalized.append(blocker)
    return normalized[:20]


def normalize_ai_security_task_kinds(values: object) -> list[str]:
    if not isinstance(values, list | tuple | set):
        return []
    normalized: list[str] = []
    for value in values:
        task_kind = _clean_token(value)
        if task_kind is None or len(task_kind) > 128 or task_kind in normalized:
            continue
        normalized.append(task_kind)
    return normalized[:50]


def default_ai_security_blocker_actions() -> dict[str, AiSecurityDataProtectionAction]:
    return {
        blocker: DEFAULT_DATA_PROTECTION_ACTION
        for blocker in sorted(MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS)
    }


def default_ai_security_external_app_blocker_actions() -> dict[str, AiSecurityExternalAppAction]:
    return {
        blocker: DEFAULT_EXTERNAL_APP_ACTION
        for blocker in sorted(MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS)
    }


def default_ai_security_external_app_actions() -> dict[str, dict[str, AiSecurityExternalAppAction]]:
    return {}


def normalize_ai_security_blocker_actions(
    values: object,
) -> dict[str, AiSecurityDataProtectionAction]:
    normalized = default_ai_security_blocker_actions()
    if not isinstance(values, dict):
        return normalized
    for key, raw_action in values.items():
        blocker = str(key or "").strip().lower().replace("-", "_")
        if blocker not in MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS:
            continue
        action = str(raw_action or "").strip().lower().replace("-", "_")
        if action == "local_only":
            action = "block"
        if action not in _DATA_PROTECTION_ACTIONS:
            continue
        normalized[blocker] = action  # type: ignore[assignment]
    return normalized


def normalize_ai_security_external_app_blocker_actions(
    values: object,
) -> dict[str, AiSecurityExternalAppAction]:
    normalized = default_ai_security_external_app_blocker_actions()
    if not isinstance(values, dict):
        return normalized
    for key, raw_action in values.items():
        blocker = str(key or "").strip().lower().replace("-", "_")
        if blocker not in MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS:
            continue
        action = str(raw_action or "").strip().lower().replace("-", "_")
        if action not in _EXTERNAL_APP_ACTIONS:
            continue
        normalized[blocker] = action  # type: ignore[assignment]
    return normalized


def normalize_ai_security_external_app_actions(
    values: object,
) -> dict[str, dict[str, AiSecurityExternalAppAction]]:
    if not isinstance(values, dict):
        return default_ai_security_external_app_actions()
    normalized: dict[str, dict[str, AiSecurityExternalAppAction]] = {}
    for raw_app_id, raw_actions in values.items():
        app_id = _clean_app_id(raw_app_id)
        if app_id is None or len(app_id) > 64:
            continue
        normalized[app_id] = normalize_ai_security_external_app_blocker_actions(raw_actions)
        if len(normalized) >= 200:
            break
    return normalized


def get_ai_security_data_protection_settings(
    db: Session,
) -> AiSecurityDataProtectionSettings | None:
    return db.get(AiSecurityDataProtectionSettings, DATA_PROTECTION_SETTINGS_ID)


def get_or_create_ai_security_data_protection_settings(
    db: Session,
    *,
    updated_by: str | None = None,
) -> AiSecurityDataProtectionSettings:
    settings = get_ai_security_data_protection_settings(db)
    if settings is not None:
        return settings
    settings = AiSecurityDataProtectionSettings(
        id=DATA_PROTECTION_SETTINGS_ID,
        enforcement_enabled=False,
        enforcement_disabled_reason="",
        custom_block_terms_json=[],
        blocker_actions_json=default_ai_security_blocker_actions(),
        external_app_actions_json=default_ai_security_external_app_actions(),
        updated_by=updated_by,
    )
    db.add(settings)
    db.flush()
    return settings


def ai_security_enforcement_enabled(db: Session) -> bool:
    settings = get_ai_security_data_protection_settings(db)
    return settings is not None and settings.enforcement_enabled is True


def ai_security_enforcement_required(
    *,
    environment: str,
    enforcement_enabled: bool,
) -> bool:
    return is_production_like_environment(environment) and not enforcement_enabled


def resolve_ai_security_policy(
    db: Session,
    context: AiSecurityPolicyContext,
) -> AiSecurityPolicyDecision:
    resolved_context = _normalize_context(context)
    if not ai_security_enforcement_enabled(db):
        return AiSecurityPolicyDecision(reason_code=AI_SECURITY_ENFORCEMENT_DISABLED_REASON)
    settings = get_ai_security_data_protection_settings(db)
    global_terms = normalize_custom_block_terms(
        settings.custom_block_terms_json if settings is not None else []
    )
    org_unit_ids = _context_org_unit_ids(db, resolved_context)
    rules = db.scalars(_matching_rules_statement(resolved_context, org_unit_ids)).all()
    matches = [
        match
        for rule in rules
        if (match := _match_rule(rule, resolved_context, org_unit_ids)) is not None
    ]
    matches.sort(
        key=lambda item: (
            item.score,
            _CONSERVATIVE_EFFECT_RANK[item.effect],
            item.rule.created_at,
            item.rule.id,
        ),
        reverse=True,
    )

    effect_match = next((match for match in matches if match.effect != "inherit"), None)
    report_match = effect_match or (matches[0] if matches else None)
    effect = effect_match.effect if effect_match is not None else "inherit"
    reason_code = _reason_for_effect(effect, report_match is not None)
    terms = _dedupe_terms(
        [
            *global_terms,
            *[
                term
                for match in matches
                for term in normalize_custom_block_terms(match.rule.custom_block_terms_json)
            ],
        ]
    )
    return AiSecurityPolicyDecision(
        effect=effect,
        reason_code=reason_code,
        rule_id=report_match.rule.id if report_match is not None else None,
        rule_name=report_match.rule.name if report_match is not None else None,
        matched_scope=report_match.matched_scope if report_match is not None else {},
        audit_only=effect == "audit_only",
        custom_block_terms=tuple(terms),
    )


def evaluate_ai_security_policy(
    db: Session,
    context: AiSecurityPolicyContext,
    texts: list[str] | tuple[str, ...],
) -> AiSecurityPolicyDecision:
    decision = resolve_ai_security_policy(db, context)
    matched_terms = detect_custom_block_terms(texts, decision.custom_block_terms)
    if not matched_terms:
        return decision
    return replace(
        decision,
        custom_block_term_count=len(matched_terms),
        reason_code=CUSTOM_BLOCK_REASON,
    )


def external_transfer_blockers_from_safety(
    safety_decision: ExternalPayloadSafetyDecision,
    *,
    custom_block_term_count: int = 0,
    policy_block_external: bool = False,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if custom_block_term_count > 0:
        blockers.append(CUSTOM_BLOCK_ENTITY_TYPE)
    if policy_block_external:
        blockers.append(POLICY_BLOCK_EXTERNAL_BLOCKER)
    if safety_decision.reason_code == "internal_context_blocked":
        blockers.append("internal_context")
    if safety_decision.reason_code == "sensitivity_label_blocked":
        blockers.append("blocking_sensitivity_label")
    if safety_decision.reason_code == "pii_detected" or safety_decision.pii_hits:
        blockers.append("pii")
    for entity_type in safety_decision.blocked_entity_types:
        normalized = str(entity_type or "").strip().lower().replace("-", "_")
        if normalized.startswith("pii:"):
            blockers.append("pii")
        elif (
            normalized in EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS
            or normalized in HARD_EXTERNAL_TRANSFER_BLOCKERS
        ):
            blockers.append(normalized)
        elif normalized in COMPANY_SENSITIVE_ENTITY_TYPES:
            blockers.append("company_sensitive_entity")
        elif normalized:
            blockers.append(UNKNOWN_EXTERNAL_ENTITY_BLOCKER)
    return tuple(normalize_external_transfer_blockers(blockers))


def ai_security_data_protection_blocker_actions(
    db: Session,
) -> dict[str, AiSecurityDataProtectionAction]:
    settings = get_ai_security_data_protection_settings(db)
    return normalize_ai_security_blocker_actions(
        settings.blocker_actions_json if settings is not None else None
    )


def ai_security_external_app_actions(
    db: Session,
) -> dict[str, dict[str, AiSecurityExternalAppAction]]:
    settings = get_ai_security_data_protection_settings(db)
    return normalize_ai_security_external_app_actions(
        settings.external_app_actions_json if settings is not None else None
    )


def ai_security_external_app_action_for_blockers(
    db: Session,
    app_id: str | None,
    blocker_types: list[str] | tuple[str, ...],
) -> AiSecurityExternalAppAction | None:
    normalized_app_id = _clean_app_id(app_id)
    if normalized_app_id is None:
        return None
    blockers = tuple(normalize_external_transfer_blockers(blocker_types))
    if not blockers:
        return None
    actions_by_app = ai_security_external_app_actions(db)
    actions = actions_by_app.get(normalized_app_id)
    if actions is None:
        return None
    actionable_blockers = [blocker for blocker in blockers if blocker in actions]
    if not actionable_blockers:
        return None
    if len(actionable_blockers) != len(blockers):
        return "block"
    if all(actions[blocker] == "mask_and_send" for blocker in actionable_blockers):
        return "mask_and_send"
    return "block"


def hard_external_transfer_blockers(blocker_types: object) -> tuple[str, ...]:
    return tuple(
        blocker
        for blocker in normalize_external_transfer_blockers(blocker_types)
        if blocker in HARD_EXTERNAL_TRANSFER_BLOCKERS
    )


def resolve_ai_security_external_transfer_exception(
    db: Session,
    context: AiSecurityPolicyContext,
    blocker_types: list[str] | tuple[str, ...],
) -> AiSecurityExternalTransferExceptionDecision:
    resolved_context = _normalize_context(context)
    resolved_blockers = tuple(normalize_external_transfer_blockers(blocker_types))
    if not resolved_blockers:
        return AiSecurityExternalTransferExceptionDecision(
            reason_code="no_external_transfer_blocker"
        )

    hard_blockers = hard_external_transfer_blockers(resolved_blockers)
    if hard_blockers:
        return AiSecurityExternalTransferExceptionDecision(
            reason_code="hard_external_transfer_blocker",
            matched_blocker_types=resolved_blockers,
            hard_blocker_types=hard_blockers,
        )
    unsupported = tuple(
        blocker
        for blocker in resolved_blockers
        if blocker not in EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS
    )
    if unsupported:
        return AiSecurityExternalTransferExceptionDecision(
            reason_code="unsupported_external_transfer_blocker",
            matched_blocker_types=resolved_blockers,
        )

    org_unit_ids = _context_org_unit_ids(db, resolved_context)
    exceptions = db.scalars(_matching_exceptions_statement(resolved_context, org_unit_ids)).all()
    matches = [
        match
        for exception in exceptions
        if (
            match := _match_exception(
                exception,
                resolved_context,
                org_unit_ids,
                resolved_blockers,
            )
        )
        is not None
    ]
    matches.sort(
        key=lambda item: (
            item.score,
            item.exception.updated_at,
            item.exception.id,
        ),
        reverse=True,
    )
    if not matches:
        return AiSecurityExternalTransferExceptionDecision(
            reason_code="no_matching_external_transfer_exception",
            matched_blocker_types=resolved_blockers,
        )
    match = matches[0]
    return AiSecurityExternalTransferExceptionDecision(
        allowed=True,
        reason_code=EXTERNAL_TRANSFER_EXCEPTION_REASON,
        exception_id=match.exception.id,
        exception_name=match.exception.name,
        matched_scope=match.matched_scope,
        allowed_blocker_types=match.allowed_blocker_types,
        matched_blocker_types=resolved_blockers,
        expires_at=match.exception.expires_at,
    )


def detect_custom_block_terms(
    texts: list[str] | tuple[str, ...],
    terms: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    normalized_terms = normalize_custom_block_terms(list(terms))
    if not normalized_terms:
        return ()
    haystack = "\n".join(text or "" for text in texts).casefold()
    if not haystack:
        return ()
    return tuple(term for term in normalized_terms if term.casefold() in haystack)


def _task_kinds_from_scope(raw_task_kind: object, raw_task_kinds: object) -> tuple[str, ...]:
    normalized = normalize_ai_security_task_kinds(raw_task_kinds)
    if not normalized:
        legacy_task_kind = _clean_token(raw_task_kind)
        normalized = [legacy_task_kind] if legacy_task_kind else []
    return tuple(normalized)


def _normalize_context(context: AiSecurityPolicyContext) -> AiSecurityPolicyContext:
    return AiSecurityPolicyContext(
        workspace_id=_clean_identifier(context.workspace_id),
        actor_user_id=_clean_identifier(context.actor_user_id),
        org_unit_id=_clean_identifier(context.org_unit_id),
        app_id=_clean_app_id(context.app_id),
        task_kind=_clean_token(context.task_kind),
        capability=_clean_token(context.capability),
        provider=_clean_token(context.provider),
    )


def _matching_rules_statement(
    context: AiSecurityPolicyContext,
    org_unit_ids: tuple[str, ...],
) -> object:
    conditions = [AiSecurityPolicyRule.enabled.is_(True)]
    conditions.append(_nullable_match(AiSecurityPolicyRule.user_id, context.actor_user_id))
    conditions.append(_nullable_match(AiSecurityPolicyRule.workspace_id, context.workspace_id))
    conditions.append(_nullable_match(AiSecurityPolicyRule.app_id, context.app_id))
    conditions.append(_nullable_match(AiSecurityPolicyRule.capability, context.capability))
    conditions.append(_nullable_match(AiSecurityPolicyRule.provider, context.provider))
    if org_unit_ids:
        conditions.append(
            or_(
                AiSecurityPolicyRule.org_unit_id.is_(None),
                AiSecurityPolicyRule.org_unit_id.in_(org_unit_ids),
            )
        )
    else:
        conditions.append(AiSecurityPolicyRule.org_unit_id.is_(None))
    return select(AiSecurityPolicyRule).where(*conditions)


def _matching_exceptions_statement(
    context: AiSecurityPolicyContext,
    org_unit_ids: tuple[str, ...],
) -> object:
    now = datetime.now(UTC).replace(tzinfo=None)
    conditions = [
        AiSecurityExternalTransferException.enabled.is_(True),
        or_(
            AiSecurityExternalTransferException.expires_at.is_(None),
            AiSecurityExternalTransferException.expires_at > now,
        ),
    ]
    conditions.append(
        _nullable_match(AiSecurityExternalTransferException.user_id, context.actor_user_id)
    )
    conditions.append(
        _nullable_match(AiSecurityExternalTransferException.workspace_id, context.workspace_id)
    )
    conditions.append(_nullable_match(AiSecurityExternalTransferException.app_id, context.app_id))
    conditions.append(
        _nullable_match(AiSecurityExternalTransferException.capability, context.capability)
    )
    conditions.append(
        _nullable_match(AiSecurityExternalTransferException.provider, context.provider)
    )
    if org_unit_ids:
        conditions.append(
            or_(
                AiSecurityExternalTransferException.org_unit_id.is_(None),
                AiSecurityExternalTransferException.org_unit_id.in_(org_unit_ids),
            )
        )
    else:
        conditions.append(AiSecurityExternalTransferException.org_unit_id.is_(None))
    return select(AiSecurityExternalTransferException).where(*conditions)


def _match_rule(
    rule: AiSecurityPolicyRule,
    context: AiSecurityPolicyContext,
    org_unit_ids: tuple[str, ...],
) -> _RuleMatch | None:
    score = 0
    matched_scope: dict[str, str] = {}
    for attr_name, context_value, weight in (
        ("user_id", context.actor_user_id, 64),
        ("workspace_id", context.workspace_id, 16),
        ("app_id", context.app_id, 8),
        ("capability", context.capability, 2),
        ("provider", context.provider, 1),
    ):
        rule_value = getattr(rule, attr_name)
        if rule_value is None:
            continue
        if context_value != rule_value:
            return None
        score += weight
        matched_scope[attr_name] = rule_value

    task_kinds = _task_kinds_from_scope(rule.task_kind, rule.task_kinds_json)
    if task_kinds:
        if context.task_kind not in task_kinds:
            return None
        score += 4
        matched_scope["task_kind"] = context.task_kind or ""

    if rule.org_unit_id is not None:
        if rule.org_unit_id not in org_unit_ids:
            return None
        score += 32
        matched_scope["org_unit_id"] = rule.org_unit_id

    return _RuleMatch(
        rule=rule,
        effect=normalize_ai_security_effect(rule.effect),
        score=score,
        matched_scope=matched_scope,
    )


def _match_exception(
    exception: AiSecurityExternalTransferException,
    context: AiSecurityPolicyContext,
    org_unit_ids: tuple[str, ...],
    blocker_types: tuple[str, ...],
) -> _ExceptionMatch | None:
    allowed_blockers = tuple(
        blocker
        for blocker in normalize_external_transfer_blockers(exception.allowed_blocker_types_json)
        if blocker in EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS
    )
    if not set(blocker_types).issubset(set(allowed_blockers)):
        return None

    score = 0
    matched_scope: dict[str, str] = {}
    for attr_name, context_value, weight in (
        ("user_id", context.actor_user_id, 64),
        ("workspace_id", context.workspace_id, 16),
        ("app_id", context.app_id, 8),
        ("capability", context.capability, 2),
        ("provider", context.provider, 1),
    ):
        exception_value = getattr(exception, attr_name)
        if exception_value is None:
            continue
        if context_value != exception_value:
            return None
        score += weight
        matched_scope[attr_name] = exception_value

    task_kinds = _task_kinds_from_scope(exception.task_kind, exception.task_kinds_json)
    if task_kinds:
        if context.task_kind not in task_kinds:
            return None
        score += 4
        matched_scope["task_kind"] = context.task_kind or ""

    if exception.org_unit_id is not None:
        if exception.org_unit_id not in org_unit_ids:
            return None
        score += 32
        matched_scope["org_unit_id"] = exception.org_unit_id

    return _ExceptionMatch(
        exception=exception,
        score=score,
        matched_scope=matched_scope,
        allowed_blocker_types=allowed_blockers,
    )


def _context_org_unit_ids(db: Session, context: AiSecurityPolicyContext) -> tuple[str, ...]:
    start_org_unit_id = context.org_unit_id
    if start_org_unit_id is None and context.actor_user_id is not None:
        start_org_unit_id = db.scalar(
            select(User.primary_org_unit_id).where(User.id == context.actor_user_id)
        )
    if start_org_unit_id is None:
        return ()
    return _org_unit_ancestor_ids(db, start_org_unit_id)


def _org_unit_ancestor_ids(db: Session, org_unit_id: str) -> tuple[str, ...]:
    ids: list[str] = []
    current_id: str | None = org_unit_id
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        ids.append(current_id)
        current_id = db.scalar(select(OrgUnit.parent_id).where(OrgUnit.id == current_id))
    return tuple(ids)


def _nullable_match(column: object, value: str | None) -> object:
    if value is None:
        return column.is_(None)  # type: ignore[attr-defined]
    return or_(column.is_(None), column == value)  # type: ignore[attr-defined]


def _reason_for_effect(
    effect: AiSecurityPolicyEffect,
    matched_rule: bool,
) -> str:
    if effect == "block_external":
        return POLICY_BLOCK_EXTERNAL_REASON
    if effect == "mask_and_send":
        return POLICY_MASK_AND_SEND_REASON
    if effect == "audit_only":
        return POLICY_AUDIT_ONLY_REASON
    if matched_rule:
        return "ai_security_policy_inherited"
    return "no_matching_rule"


def _clean_identifier(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _clean_token(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized or None


def _clean_app_id(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _dedupe_terms(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


__all__ = [
    "AI_SECURITY_LLM_CAPABILITY",
    "COMPANY_SENSITIVE_ENTITY_TYPES",
    "CUSTOM_BLOCK_ENTITY_TYPE",
    "CUSTOM_BLOCK_REASON",
    "DATA_PROTECTION_SETTINGS_ID",
    "EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS",
    "EXTERNAL_TRANSFER_EXCEPTION_REASON",
    "HARD_EXTERNAL_TRANSFER_BLOCKERS",
    "MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS",
    "POLICY_AUDIT_ONLY_REASON",
    "POLICY_BLOCK_EXTERNAL_REASON",
    "POLICY_MASK_AND_SEND_REASON",
    "POLICY_BLOCK_EXTERNAL_BLOCKER",
    "AI_SECURITY_ENFORCEMENT_DISABLED_REASON",
    "AI_SECURITY_ENFORCEMENT_REQUIRED_REASON",
    "AiSecurityExternalTransferBlocker",
    "AiSecurityDataProtectionAction",
    "AiSecurityExternalAppAction",
    "AiSecurityExternalTransferExceptionDecision",
    "AiSecurityPolicyContext",
    "AiSecurityPolicyDecision",
    "AiSecurityPolicyEffect",
    "ai_security_enforcement_enabled",
    "ai_security_enforcement_required",
    "ai_security_data_protection_blocker_actions",
    "ai_security_external_app_action_for_blockers",
    "ai_security_external_app_actions",
    "default_ai_security_blocker_actions",
    "default_ai_security_external_app_actions",
    "default_ai_security_external_app_blocker_actions",
    "detect_custom_block_terms",
    "evaluate_ai_security_policy",
    "external_transfer_blockers_from_safety",
    "get_ai_security_data_protection_settings",
    "get_or_create_ai_security_data_protection_settings",
    "hard_external_transfer_blockers",
    "normalize_ai_security_effect",
    "normalize_ai_security_task_kinds",
    "normalize_custom_block_terms",
    "normalize_ai_security_blocker_actions",
    "normalize_ai_security_external_app_actions",
    "normalize_ai_security_external_app_blocker_actions",
    "normalize_external_transfer_blockers",
    "resolve_ai_security_external_transfer_exception",
    "resolve_ai_security_policy",
]
