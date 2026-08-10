from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ai_do_api.domains.plm.query_policy import (
    PlmQueryPolicyError,
    build_plm_query_preview,
    validate_read_only_plm_sql,
)


@dataclass(frozen=True)
class _Workspace:
    id: str


@dataclass
class _AccessPolicy:
    allowed: bool = True
    workspace: _Workspace = field(default_factory=lambda: _Workspace(id="workspace-1"))
    calls: list[tuple[str | None, str | None]] = field(default_factory=list)

    def can_access_scope(self, scope_kind: str | None, scope_id: str | None) -> bool:
        self.calls.append((scope_kind, scope_id))
        return self.allowed


def test_plm_query_policy_returns_read_only_allowlisted_preview() -> None:
    policy = _AccessPolicy()

    preview = build_plm_query_preview(policy)

    assert preview.sql.startswith("select ")
    assert "vw_release_delay" in preview.sql
    assert preview.warnings == ("read_only_allowlist",)
    assert policy.calls == [("workspace", "workspace-1")]


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("update vw_release_delay set status = 'Done'", "plm.sql_read_only_required"),
        (
            "select * from vw_release_delay; drop table users",
            "plm.sql_single_statement_required",
        ),
        ("select * from pms_tasks", "plm.sql_table_not_allowed"),
    ],
)
def test_plm_sql_validator_rejects_write_or_non_allowlisted_sql(
    sql: str,
    code: str,
) -> None:
    with pytest.raises(PlmQueryPolicyError) as exc_info:
        validate_read_only_plm_sql(sql)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == code


def test_plm_query_policy_denies_inaccessible_template_scope() -> None:
    policy = _AccessPolicy(allowed=False)

    with pytest.raises(PlmQueryPolicyError) as exc_info:
        build_plm_query_preview(policy)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "plm.access_scope_denied"
    assert policy.calls == [("workspace", "workspace-1")]
