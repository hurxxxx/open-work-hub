from __future__ import annotations

import importlib
from pathlib import Path
import re
from types import ModuleType, SimpleNamespace
import sys

import pytest


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_alm_api.domains.hr.erp_snapshot import ERP_EMPLOYEE_COLUMNS  # noqa: E402


@pytest.fixture
def hr_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    original_worker_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "open_alm_worker" or name.startswith("open_alm_worker.")
    }
    for name in original_worker_modules:
        sys.modules.pop(name, None)

    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", "sqlite+pysqlite:///:memory:")
    module = importlib.import_module("open_alm_worker.tasks.hr")
    try:
        yield module
    finally:
        for name in list(sys.modules):
            if name == "open_alm_worker" or name.startswith("open_alm_worker."):
                sys.modules.pop(name, None)
        sys.modules.update(original_worker_modules)


class _FakeCursor:
    def __init__(self, result_sets: list[list[dict[str, object]]]) -> None:
        self._result_sets = result_sets
        self.queries: list[str] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str) -> None:
        self.queries.append(query)

    def fetchall(self) -> list[dict[str, object]]:
        return self._result_sets.pop(0)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


def _erp_settings(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        erp_db_ip="erp-db.internal",
        erp_db_port=1433,
        erp_db_name="ERP_HR",
        erp_db_id="readonly-user",
        erp_db_pw="synthetic-test-password",
        erp_db_timeout_seconds=15,
        erp_hr_snapshot_enabled=enabled,
    )


def test_fetch_erp_rows_uses_the_versioned_explicit_projection(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = dict.fromkeys(ERP_EMPLOYEE_COLUMNS)
    row["EMP_NO"] = "E001"
    row["INTERNAL_CD"] = "I001"
    group_row = {"DEPT_CD": "D001", "DEPT_NM": "Department"}
    cursor = _FakeCursor([[row], [group_row]])
    connect_kwargs: dict[str, object] = {}

    def connect(**kwargs: object) -> _FakeConnection:
        connect_kwargs.update(kwargs)
        return _FakeConnection(cursor)

    monkeypatch.setattr(hr_module.pytds, "connect", connect)

    employee_rows, group_rows = hr_module._fetch_erp_rows(_erp_settings())

    assert employee_rows == [row]
    assert group_rows == [group_row]
    assert tuple(employee_rows[0]) == ERP_EMPLOYEE_COLUMNS
    query = cursor.queries[0]
    assert "SELECT *" not in query.upper()
    assert "FROM [dbo].[UV_H_EMPLOYEE_LIST_DWC]" in query
    assert "ORDER BY [EMP_NO], [INTERNAL_CD]" in query
    aliases = tuple(re.findall(r"\[([A-Z0-9_]+)\]\s+AS\s+\[([A-Z0-9_]+)\]", query))
    assert aliases == tuple((column, column) for column in ERP_EMPLOYEE_COLUMNS)
    assert len(aliases) == 23
    group_query = cursor.queries[1]
    assert "FROM [dbo].[UV_H_EMPLOYEE_LIST_DWC]" in group_query
    assert "GROUP BY [DEPT_CD], [DEPT_NM]" in group_query
    assert "ORDER BY [DEPT_CD], [DEPT_NM]" in group_query
    assert "SELECT *" not in group_query.upper()
    group_aliases = tuple(re.findall(r"\[([A-Z0-9_]+)\]\s+AS\s+\[([A-Z0-9_]+)\]", group_query))
    assert group_aliases == (("DEPT_CD", "DEPT_CD"), ("DEPT_NM", "DEPT_NM"))
    assert connect_kwargs["server"] == "erp-db.internal"
    assert connect_kwargs["database"] == "ERP_HR"
    assert connect_kwargs["as_dict"] is True


def test_groupware_queries_have_deterministic_source_order(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    department = {
        "domain_num": 1,
        "org_code": "D1",
        "org_depart": "Department",
        "p_org_code": None,
        "org_order": 1,
        "org_level": None,
    }
    user = {
        "domain_num": 1,
        "user_num": 1,
        "user_id": "employee1",
        "kor_name": "Employee",
        "com_state": 1,
        "email": None,
        "com_num": "E001",
        "com_position": None,
        "org_code1": "D1",
        "org_code2": None,
        "org_code3": None,
        "org_code4": None,
        "org_code5": None,
        "org_code6": None,
        "org_level": 1,
        "user_order": None,
    }
    cursor = _FakeCursor([[department], [user]])
    monkeypatch.setattr(
        hr_module.pytds,
        "connect",
        lambda **_kwargs: _FakeConnection(cursor),
    )
    settings = SimpleNamespace(
        hr_groupware_db_host="groupware-db.internal",
        hr_groupware_db_port=1433,
        hr_groupware_db_name="Groupware",
        hr_groupware_db_username="readonly-user",
        hr_groupware_db_password="synthetic-test-password",
        hr_groupware_db_timeout_seconds=15,
    )

    departments, users = hr_module._fetch_groupware_rows(settings)

    assert len(departments) == 1
    assert len(users) == 1
    assert "ORDER BY [도메인번호], [부서코드]" in cursor.queries[0]
    assert "ORDER BY [user_num], [EMP_NO]" in cursor.queries[1]


def test_erp_task_is_disabled_without_opening_a_platform_session(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hr_module, "get_worker_settings", lambda: _erp_settings(enabled=False))
    monkeypatch.setattr(
        hr_module,
        "_session_factory",
        lambda: (_ for _ in ()).throw(AssertionError("disabled task opened a session")),
    )
    monkeypatch.setattr(
        hr_module,
        "_fetch_erp_rows",
        lambda _settings: (_ for _ in ()).throw(
            AssertionError("disabled task accessed the ERP source")
        ),
    )

    assert hr_module.capture_erp_hr_snapshot_task.run(force=False) == "disabled"


def test_erp_task_is_registered_with_the_contract_name(hr_module: ModuleType) -> None:
    assert "hr.capture_erp_snapshot" in hr_module.celery_app.tasks
    assert "hr.build_master" in hr_module.celery_app.tasks


def test_manual_erp_task_only_bypasses_the_enabled_flag(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        closed = False
        rolled_back = False

        def close(self) -> None:
            self.closed = True

        def rollback(self) -> None:
            self.rolled_back = True

    session = FakeSession()
    pending_run = SimpleNamespace(id="erp-run-1", status="pending", captured_at=None)
    completed_run = SimpleNamespace(
        id="erp-run-1",
        status="succeeded",
        user_row_count=1,
        org_row_count=1,
        result_payload={"distinct_employee_codes": 1},
    )
    observed: dict[str, object] = {}

    def begin(_session: object, **kwargs: object) -> SimpleNamespace:
        observed["begin"] = kwargs
        return pending_run

    def process(_session: object, **kwargs: object) -> SimpleNamespace:
        observed["process"] = kwargs
        return completed_run

    monkeypatch.setattr(hr_module, "get_worker_settings", lambda: _erp_settings(enabled=False))
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(hr_module, "begin_erp_hr_snapshot_run", begin)
    monkeypatch.setattr(
        hr_module,
        "_fetch_erp_rows",
        lambda _settings: (
            [{"EMP_NO": "E001"}],
            [{"DEPT_CD": "D001", "DEPT_NM": "Department"}],
        ),
    )
    monkeypatch.setattr(hr_module, "process_erp_hr_snapshot_run", process)
    monkeypatch.setattr(hr_module, "prune_hr_history", lambda _session: {})

    result = hr_module.capture_erp_hr_snapshot_task.run(force=True)

    assert result == "succeeded:run_id=erp-run-1,rows=1,distinct_employee_codes=1"
    assert observed["begin"]["trigger_kind"] == "manual"
    assert observed["process"]["allow_large_changes"] is False
    assert observed["process"]["group_rows"] == [{"DEPT_CD": "D001", "DEPT_NM": "Department"}]
    assert session.closed is True


def test_redelivered_erp_task_reuses_the_durable_snapshot_without_refetching(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

        def rollback(self) -> None:
            return None

    session = FakeSession()
    captured_run = SimpleNamespace(
        id="erp-run-captured",
        status="validating",
        captured_at=object(),
    )
    completed_run = SimpleNamespace(
        id=captured_run.id,
        status="succeeded",
        user_row_count=698,
        org_row_count=12,
        result_payload={"distinct_employee_codes": 698},
    )
    observed: dict[str, object] = {}

    monkeypatch.setattr(hr_module, "get_worker_settings", lambda: _erp_settings(enabled=True))
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        hr_module,
        "begin_erp_hr_snapshot_run",
        lambda _session, **_kwargs: captured_run,
    )
    monkeypatch.setattr(
        hr_module,
        "_fetch_erp_rows",
        lambda _settings: (_ for _ in ()).throw(
            AssertionError("durable ERP snapshot was fetched again")
        ),
    )

    def process(_session: object, **kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return completed_run

    monkeypatch.setattr(hr_module, "process_erp_hr_snapshot_run", process)
    monkeypatch.setattr(hr_module, "prune_hr_history", lambda _session: {})

    result = hr_module.capture_erp_hr_snapshot_task.run(force=False)

    assert result == ("succeeded:run_id=erp-run-captured,rows=698,distinct_employee_codes=698")
    assert observed["rows"] == []
    assert observed["group_rows"] == []
    assert observed["allow_large_changes"] is False
    assert session.closed is True


def test_erp_fetch_failure_persists_and_raises_only_a_safe_error(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    pending_run = SimpleNamespace(id="erp-run-2", status="pending", captured_at=None)
    observed: dict[str, object] = {}

    monkeypatch.setattr(hr_module, "get_worker_settings", lambda: _erp_settings(enabled=True))
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        hr_module,
        "begin_erp_hr_snapshot_run",
        lambda _session, **_kwargs: pending_run,
    )

    def fail_fetch(
        _settings: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        raise RuntimeError(
            "server=private-host;database=secret-db;password=secret-pw;EMP_NO=private-row"
        )

    def record_failure(_session: object, **kwargs: object) -> None:
        observed.update(kwargs)

    monkeypatch.setattr(hr_module, "_fetch_erp_rows", fail_fetch)
    monkeypatch.setattr(hr_module, "fail_erp_hr_snapshot_run", record_failure)

    with caplog.at_level("ERROR", logger=hr_module.__name__):
        with pytest.raises(
            RuntimeError,
            match=r"ERP HR source fetch failed \(RuntimeError\)",
        ) as error:
            hr_module.capture_erp_hr_snapshot_task.run(force=False)

    persisted_error = observed["error"]
    assert isinstance(persisted_error, RuntimeError)
    assert str(persisted_error) == "ERP HR source fetch failed (RuntimeError)"
    for sensitive_value in ("private-host", "secret-db", "secret-pw", "private-row"):
        assert sensitive_value not in str(persisted_error)
        assert sensitive_value not in str(error.value)
        assert sensitive_value not in caplog.text
    assert observed["phase"] == "fetch"
    assert session.closed is True


def test_missing_erp_settings_report_only_key_names(hr_module: ModuleType) -> None:
    settings = _erp_settings()
    settings.erp_db_ip = ""
    settings.erp_db_pw = ""

    with pytest.raises(RuntimeError) as error:
        hr_module._require_erp_db_settings(settings)

    message = str(error.value)
    assert "OPEN_ALM_ERP_DB_IP" in message
    assert "OPEN_ALM_ERP_DB_PW" in message
    assert "synthetic-test-password" not in message


def _master_settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        hr_master_sync_enabled=enabled,
        hr_groupware_sync_timezone="Asia/Seoul",
    )


def test_hr_master_task_is_disabled_without_opening_a_platform_session(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hr_module,
        "get_worker_settings",
        lambda: _master_settings(enabled=False),
    )
    monkeypatch.setattr(
        hr_module,
        "_session_factory",
        lambda: (_ for _ in ()).throw(AssertionError("disabled task opened a session")),
    )

    assert hr_module.build_hr_master_task.run(force=False) == "disabled"


def test_manual_hr_master_task_builds_latest_pair_with_task_idempotency(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    completed_run = SimpleNamespace(
        id="master-run-1",
        status="succeeded",
        person_row_count=3,
        group_row_count=2,
        conflict_row_count=1,
        result_payload={},
    )
    observed: dict[str, object] = {}
    retention_sessions: list[object] = []

    def build(_session: object, **kwargs: object) -> SimpleNamespace:
        observed["session"] = _session
        observed.update(kwargs)
        return completed_run

    monkeypatch.setattr(
        hr_module,
        "get_worker_settings",
        lambda: _master_settings(enabled=False),
    )
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(hr_module, "build_latest_hr_master_run", build)
    monkeypatch.setattr(
        hr_module,
        "prune_hr_master_history",
        lambda active_session: retention_sessions.append(active_session),
    )

    result = hr_module.build_hr_master_task.run(force=True)

    assert result == ("succeeded:run_id=master-run-1,people=3,groups=2,conflicts=1")
    assert observed["session"] is session
    assert observed["idempotency_key"] is None
    assert observed["now"].tzinfo.key == "Asia/Seoul"
    assert retention_sessions == [session]
    assert session.closed is True


def test_hr_master_task_reports_unavailable_source_pair_without_row_data(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(
        hr_module,
        "get_worker_settings",
        lambda: _master_settings(enabled=True),
    )
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        hr_module,
        "build_latest_hr_master_run",
        lambda *_args, **_kwargs: None,
    )

    with caplog.at_level("INFO", logger=hr_module.__name__):
        result = hr_module.build_hr_master_task.run(force=False)

    assert result == "skipped:source_pair_unavailable"
    assert "source_pair_unavailable" in caplog.text
    assert session.closed is True


@pytest.mark.parametrize("status", ["failed", "building"])
def test_hr_master_task_raises_when_master_run_did_not_succeed(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: str,
) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    incomplete_run = SimpleNamespace(
        id=f"master-{status}",
        status=status,
        error_code="source_validation_failed" if status == "failed" else None,
    )
    monkeypatch.setattr(
        hr_module,
        "get_worker_settings",
        lambda: _master_settings(enabled=True),
    )
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        hr_module,
        "build_latest_hr_master_run",
        lambda *_args, **_kwargs: incomplete_run,
    )
    monkeypatch.setattr(
        hr_module,
        "prune_hr_master_history",
        lambda _session: (_ for _ in ()).throw(
            AssertionError("non-succeeded master triggered retention")
        ),
    )

    with caplog.at_level("ERROR", logger=hr_module.__name__):
        with pytest.raises(
            RuntimeError,
            match=r"Integrated HR master build failed \(RuntimeError\)",
        ):
            hr_module.build_hr_master_task.run(force=False)

    assert f"run_id=master-{status}" in caplog.text
    assert f"status={status}" in caplog.text
    assert session.closed is True


def test_hr_master_task_failure_does_not_log_source_data(
    hr_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeSession:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(
        hr_module,
        "get_worker_settings",
        lambda: _master_settings(enabled=True),
    )
    monkeypatch.setattr(hr_module, "_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        hr_module,
        "build_latest_hr_master_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("EMP_NO=private-row;email=private@example.invalid")
        ),
    )

    with caplog.at_level("ERROR", logger=hr_module.__name__):
        with pytest.raises(
            RuntimeError,
            match=r"Integrated HR master build failed \(RuntimeError\)",
        ) as error:
            hr_module.build_hr_master_task.run(force=False)

    assert "private-row" not in caplog.text
    assert "private@example.invalid" not in caplog.text
    assert "private-row" not in str(error.value)
    assert session.closed is True
