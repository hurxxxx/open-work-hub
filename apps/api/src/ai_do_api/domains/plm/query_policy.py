"""PLM query template selection and validation policy."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, TypedDict


class _WorkspaceScope(Protocol):
    id: str


class PlmAccessPolicy(Protocol):
    workspace: _WorkspaceScope

    def can_access_scope(self, scope_kind: str | None, scope_id: str | None) -> bool:
        ...


class PlmQueryPolicyError(ValueError):
    def __init__(self, status_code: int, code: str, **params: object) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.params = params


class PlmSqlTemplate(TypedDict):
    sql: str
    access_scope_kind: str
    access_scope_id: str | None


@dataclass(frozen=True)
class PlmQueryPreview:
    sql: str
    warnings: tuple[str, ...]


_FORBIDDEN_SQL_TOKENS = frozenset(
    {
        "alter",
        "call",
        "create",
        "delete",
        "drop",
        "execute",
        "insert",
        "merge",
        "truncate",
        "update",
    }
)
_ALLOWED_PLM_TABLES = frozenset({"vw_release_delay"})
_PLM_SQL_TEMPLATES: dict[str, PlmSqlTemplate] = {
    "release_delay": {
        "sql": (
            "select item_code, status, owner from vw_release_delay "
            "where status = 'Delayed' order by owner"
        ),
        "access_scope_kind": "workspace",
        "access_scope_id": None,
    }
}


def build_plm_query_preview(policy: PlmAccessPolicy) -> PlmQueryPreview:
    template = _PLM_SQL_TEMPLATES["release_delay"]
    ensure_plm_template_access(policy, template)
    validate_read_only_plm_sql(template["sql"])
    return PlmQueryPreview(
        sql=template["sql"],
        warnings=("read_only_allowlist",),
    )


def ensure_plm_template_access(
    policy: PlmAccessPolicy,
    template: PlmSqlTemplate,
) -> None:
    scope_id = template["access_scope_id"] or policy.workspace.id
    if policy.can_access_scope(template["access_scope_kind"], scope_id):
        return
    raise PlmQueryPolicyError(403, "plm.access_scope_denied")


def validate_read_only_plm_sql(sql: str) -> None:
    normalized = " ".join(sql.strip().lower().split())
    if not normalized.startswith("select "):
        raise PlmQueryPolicyError(422, "plm.sql_read_only_required")
    if ";" in normalized:
        raise PlmQueryPolicyError(422, "plm.sql_single_statement_required")
    tokens = set(re.findall(r"[a-z_][a-z0-9_]*", normalized))
    forbidden = tokens & _FORBIDDEN_SQL_TOKENS
    if forbidden:
        raise PlmQueryPolicyError(
            422,
            "plm.sql_forbidden_token",
            token=sorted(forbidden)[0],
        )
    referenced_tables = set(re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", normalized))
    if not referenced_tables or not referenced_tables <= _ALLOWED_PLM_TABLES:
        raise PlmQueryPolicyError(422, "plm.sql_table_not_allowed")
