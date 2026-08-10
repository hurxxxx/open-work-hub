from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ai_do_api.domains.ai.gateway import (
    AiGatewayContextPack,
    AiGatewayDecision,
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.legacy_issues.analysis_generated_sql import (
    GeneratedSqlPolicyError,
    ValidatedGeneratedSql,
    validate_generated_counting_unit,
    validate_generated_sql,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
)
from ai_do_api.domains.legacy_issues.task_kinds import (
    LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_WORKLOAD_ID,
)


class GeneratedSqlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1, max_length=20_000)
    title: str = Field(min_length=1, max_length=160)
    shape: Literal["scalar", "table", "bar", "time_series", "crosstab", "detail"]


@dataclass(frozen=True, slots=True)
class LegacyIssueGeneratedSqlPlan:
    title: str
    shape: str
    validated_sql: ValidatedGeneratedSql
    data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES


class LegacyIssueGeneratedSqlError(RuntimeError):
    pass


def plan_legacy_issue_generated_sql(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    logical_columns: list[dict[str, Any]],
    audit_entity_id: str | None,
    family_id: str | None = None,
    data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES,
    counting_unit: AnalysisCountingUnit | None = None,
) -> tuple[LegacyIssueGeneratedSqlPlan, list[AiGatewayDecision]]:
    allowed_columns = {
        str(column.get("key") or "").strip()
        for column in logical_columns
        if str(column.get("key") or "").strip()
    }
    messages = _messages(
        question=question,
        logical_columns=logical_columns,
        family_id=family_id,
        data_source=data_source,
        counting_unit=counting_unit,
    )
    decisions: list[AiGatewayDecision] = []
    last_reason = "generated_sql_invalid"
    for attempt in range(2):
        attempt_messages = list(messages)
        if attempt:
            attempt_messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "repair_required": True,
                            "validation_error": last_reason,
                            "instruction": (
                                "Return a corrected JSON object only. Keep the same requested "
                                "analysis and use only visible_records."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        result = execute_llm(
            LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_WORKLOAD_ID,
            LlmWorkloadContext(
                source="legacy_issues.analysis_sql_fallback",
                workspace_id=workspace.id,
                actor_user_id=user.id,
                app_id="legacy-issues",
            ),
            db,
            messages=attempt_messages,
            context_pack=AiGatewayContextPack(
                messages=attempt_messages,
                context_strategy="legacy_issue_guarded_sql_fallback",
                estimated_input_tokens=_estimate_tokens(attempt_messages),
            ),
            audit_entity_id=audit_entity_id,
            max_tokens=4_096,
            temperature=0,
        )
        decisions.append(result.decision)
        try:
            payload = GeneratedSqlPayload.model_validate(_parse_json_object(result.completion.text))
            validated = validate_generated_sql(
                payload.sql,
                allowed_columns=allowed_columns,
            )
            validate_generated_counting_unit(
                validated.sql,
                counting_unit=counting_unit,
            )
        except (GeneratedSqlPolicyError, ValidationError, ValueError) as exc:
            last_reason = str(exc)[:120] or "generated_sql_invalid"
            continue
        return (
            LegacyIssueGeneratedSqlPlan(
                title=payload.title,
                shape=payload.shape,
                validated_sql=validated,
                data_source=data_source,
            ),
            decisions,
        )
    raise LegacyIssueGeneratedSqlError(last_reason)


def _messages(
    *,
    question: str,
    logical_columns: list[dict[str, Any]],
    family_id: str | None,
    data_source: AnalysisDataSource,
    counting_unit: AnalysisCountingUnit | None = None,
) -> list[dict[str, Any]]:
    counting_semantics = (
        "Each visible row is one checklist item. For checklist item counts use "
        "COUNT(DISTINCT stable_record_id). For a request about the number of checklists "
        "or checklist documents, including counts grouped by status, vehicle, or module, "
        "use COUNT(DISTINCT checklist_id). Never label an item count as a checklist or "
        "document count."
        if data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
        else (
            "Each visible row is one master issue record. Count distinct stable_record_id "
            "for issue-record counts."
        )
    )
    if counting_unit == AnalysisCountingUnit.CHECKLIST_ITEMS:
        counting_semantics += (
            " The grounded counting_unit is checklist_items; use item-row counts and do not "
            "substitute distinct checklist document counts."
        )
    elif counting_unit == AnalysisCountingUnit.CHECKLISTS:
        counting_semantics += (
            " The grounded counting_unit is checklists; use COUNT(DISTINCT checklist_id) "
            "and do not substitute item-row counts."
        )
    return [
        {
            "role": "system",
            "content": (
                "You generate one PostgreSQL read-only analysis query. Return exactly one JSON "
                "object and no markdown. Query only the logical relation visible_records. "
                "Use only the supplied logical columns. Never reference physical tables, schemas, "
                "catalogs, files, network functions, session functions, or write statements. "
                "Do not use WITH/CTE clauses; use inline derived subqueries when multiple query "
                "levels are required. Prefer exact aggregates. A semantic search candidate count "
                "is never a total population count. For date arithmetic use the supplied "
                "*__date helper columns; they are validated DATE values and malformed source "
                "dates have already become NULL. Do not use SELECT * or COUNT(*); name every "
                "column and count DISTINCT stable_record_id (falling back to record_id when "
                "needed). Qualify columns whenever a SELECT has multiple sources. "
                + counting_semantics
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "selected_query_family": family_id,
                    "data_source": data_source.value,
                    "counting_unit": (counting_unit.value if counting_unit is not None else None),
                    "relation": "visible_records",
                    "columns": logical_columns,
                    "response_schema": {
                        "sql": "single SELECT query; inline derived subqueries are allowed",
                        "title": "short result title in the user's language",
                        "shape": ("scalar | table | bar | time_series | crosstab | detail"),
                    },
                },
                ensure_ascii=False,
            ),
        },
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
    raise ValueError("generated_sql_response_invalid")


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    size = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, size // 4)


__all__ = [
    "GeneratedSqlPayload",
    "LegacyIssueGeneratedSqlError",
    "LegacyIssueGeneratedSqlPlan",
    "plan_legacy_issue_generated_sql",
]
