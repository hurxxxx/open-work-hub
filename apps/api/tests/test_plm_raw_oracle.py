from __future__ import annotations

from pathlib import Path

import pytest

from open_alm_api.domains.plm import raw_oracle
from open_alm_api.domains.plm.raw_oracle import (
    PLM_INTERNAL_ROWNUM_COLUMN,
    PlmRawColumn,
    PlmRawOracleError,
    PlmRawQueryResult,
    build_raw_query_sql,
    build_table_rows_sql,
    strip_internal_rownum_column,
    validate_raw_select_sql,
)


class _PlmSettings:
    def __init__(
        self,
        *,
        host: str = "plm.example.internal",
        port: int = 1521,
        sid: str = "PLM",
        user: str = "plm_user",
        password: str = "plm-password",
        ojdbc_jar: str = "",
    ) -> None:
        self.plm_oracle_host = host
        self.plm_oracle_port = port
        self.plm_oracle_sid = sid
        self.plm_oracle_user = user
        self.plm_oracle_password = password
        self.plm_ojdbc_jar = ojdbc_jar


def _patch_plm_settings(
    monkeypatch: pytest.MonkeyPatch,
    settings: _PlmSettings,
) -> None:
    monkeypatch.setattr(raw_oracle, "get_settings", lambda: settings)


def test_plm_raw_select_validator_accepts_plain_select() -> None:
    assert validate_raw_select_sql(" select * from infodba.viewpart ") == (
        "select * from infodba.viewpart"
    )


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("update infodba.viewpart set name = 'x'", "plm.sql_read_only_required"),
        ("select * from infodba.viewpart; select 1 from dual", "plm.sql_single_statement_required"),
        ("select * from infodba.viewpart -- hidden", "plm.sql_comments_not_allowed"),
        ("select * from infodba.viewpart where exists (delete from x)", "plm.sql_forbidden_token"),
    ],
)
def test_plm_raw_select_validator_rejects_unsafe_sql(sql: str, code: str) -> None:
    with pytest.raises(PlmRawOracleError) as exc_info:
        validate_raw_select_sql(sql)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == code


def test_build_table_rows_sql_validates_oracle_identifiers() -> None:
    with pytest.raises(PlmRawOracleError) as exc_info:
        build_table_rows_sql("infodba", "viewpart where 1=1", limit=100, offset=0)

    assert exc_info.value.code == "plm.object_name_invalid"


def test_load_connection_info_reads_typed_plm_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_plm_settings(
        monkeypatch,
        _PlmSettings(
            host="10.0.0.15",
            port=1522,
            sid="TC",
            user="readonly",
            password="secret",
        ),
    )

    connection = raw_oracle.load_connection_info()

    assert connection.jdbc_url == "jdbc:oracle:thin:@10.0.0.15:1522:TC"
    assert connection.user == "readonly"
    assert connection.password == "secret"


def test_load_connection_info_requires_plm_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_plm_settings(monkeypatch, _PlmSettings(host="", sid="", user="", password=""))

    with pytest.raises(PlmRawOracleError) as exc_info:
        raw_oracle.load_connection_info()

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "plm.connection_config_missing"
    assert "OPEN_ALM_PLM_ORACLE_HOST" in exc_info.value.params["keys"]
    assert "OPEN_ALM_PLM_ORACLE_PASSWORD" in exc_info.value.params["keys"]


def test_resolve_ojdbc_jar_prefers_configured_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configured_jar = tmp_path / "configured-ojdbc.jar"
    configured_jar.write_bytes(b"jar")
    _patch_plm_settings(monkeypatch, _PlmSettings(ojdbc_jar=str(configured_jar)))
    monkeypatch.setattr(
        raw_oracle,
        "DEFAULT_OJDBC_JAR_CANDIDATES",
        (tmp_path / "missing-default.jar",),
    )

    assert raw_oracle.resolve_ojdbc_jar() == configured_jar


def test_resolve_ojdbc_jar_reports_configured_and_default_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configured_jar = tmp_path / "missing-configured.jar"
    default_jar = tmp_path / "missing-default.jar"
    _patch_plm_settings(monkeypatch, _PlmSettings(ojdbc_jar=str(configured_jar)))
    monkeypatch.setattr(raw_oracle, "DEFAULT_OJDBC_JAR_CANDIDATES", (default_jar,))

    with pytest.raises(PlmRawOracleError) as exc_info:
        raw_oracle.resolve_ojdbc_jar()

    assert exc_info.value.code == "plm.ojdbc_jar_not_found"
    assert str(configured_jar) in exc_info.value.params["path"]
    assert str(default_jar) in exc_info.value.params["path"]


def test_build_raw_query_sql_wraps_select_with_rownum_pagination() -> None:
    sql = build_raw_query_sql(
        "select 부품번호, 리비전 from infodba.viewpart",
        limit=50,
        offset=100,
    )

    assert "select 부품번호, 리비전 from infodba.viewpart" in sql
    assert "rownum OPEN_ALM_INTERNAL_RN" in sql
    assert "rownum <= 151" in sql
    assert "OPEN_ALM_INTERNAL_RN > 100" in sql


def test_strip_internal_rownum_column_removes_fetch_sentinel() -> None:
    result = PlmRawQueryResult(
        columns=(
            PlmRawColumn(name="부품번호", type="VARCHAR2"),
            PlmRawColumn(name=PLM_INTERNAL_ROWNUM_COLUMN, type="NUMBER"),
        ),
        rows=(("A-1", "1"), ("A-2", "2"), ("A-3", "3")),
    )

    stripped = strip_internal_rownum_column(result, limit=2)

    assert stripped.columns == (PlmRawColumn(name="부품번호", type="VARCHAR2"),)
    assert stripped.rows == (("A-1",), ("A-2",))
    assert stripped.has_more is True
