from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import (
    AuthSession,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.hr.groupware_sync import GroupwareOrgRow, GroupwareUserRow
from ai_do_api.domains.hr.history import (
    begin_groupware_hr_sync_run,
    list_groupware_hr_sync_runs,
    load_latest_applied_groupware_hr_sync_run,
    prune_groupware_hr_history,
    run_groupware_hr_sync,
)
from ai_do_api.domains.hr.models import HrSyncRun, HrSyncUserSnapshotRow


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _department() -> GroupwareOrgRow:
    return GroupwareOrgRow(
        domain_num=1,
        depart_num=10,
        org_code="RND",
        org_depart="기술연구소",
    )


def _employee(
    *,
    user_num: int,
    login_id: str,
    employee_number: str,
) -> GroupwareUserRow:
    return GroupwareUserRow(
        domain_num=1,
        user_num=user_num,
        user_id=login_id,
        kor_name=login_id,
        com_state=1,
        email=f"{login_id}@example.test",
        com_num=employee_number,
        com_position="책임",
        org_code1="RND",
        org_level=1,
    )


def _stable_coworkers(count: int = 9) -> list[GroupwareUserRow]:
    return [
        _employee(
            user_num=200 + index,
            login_id=f"remaining{index}",
            employee_number=f"E{200 + index}",
        )
        for index in range(count)
    ]


def _run(
    db: Session,
    *,
    users: list[GroupwareUserRow],
    idempotency_key: str,
    synced_at: datetime,
    departments: list[GroupwareOrgRow] | None = None,
) -> HrSyncRun:
    run = run_groupware_hr_sync(
        db,
        departments=[_department()] if departments is None else departments,
        users=users,
        idempotency_key=idempotency_key,
        synced_at=synced_at,
    )
    db.commit()
    return run


def test_first_successful_run_becomes_the_comparison_baseline(db: Session) -> None:
    employee = _employee(user_num=100, login_id="baseline", employee_number="E100")

    run = _run(
        db,
        users=[employee],
        idempotency_key="baseline-2026-07-01",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )

    assert run.status == "succeeded"
    assert run.result_payload["users_seen"] == 1
    assert run.result_payload["users_created"] == 1
    assert run.result_payload["users_suspended"] == 0

    baseline = load_latest_applied_groupware_hr_sync_run(db)
    assert baseline is not None
    assert baseline.id == run.id
    assert baseline.idempotency_key == "baseline-2026-07-01"


def test_task_redelivery_is_idempotent_and_stale_live_runs_are_reclaimed(db: Session) -> None:
    employee = _employee(user_num=100, login_id="idempotent", employee_number="E100")
    original = _run(
        db,
        users=[employee],
        idempotency_key="same-task-id",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )
    redelivered = _run(
        db,
        users=[],
        departments=[],
        idempotency_key="same-task-id",
        synced_at=datetime(2026, 7, 1, 3, 11),
    )
    assert redelivered.id == original.id
    assert len(db.scalars(select(HrSyncRun)).all()) == 1

    stale = begin_groupware_hr_sync_run(
        db,
        idempotency_key="stale-task-id",
        synced_at=datetime(2026, 7, 2, 3, 10),
    )
    skipped = begin_groupware_hr_sync_run(
        db,
        idempotency_key="overlapping-task-id",
        synced_at=datetime(2026, 7, 2, 3, 11),
    )
    assert skipped.status == "skipped"
    assert skipped.blocked_by_run_id == stale.id

    replacement = begin_groupware_hr_sync_run(
        db,
        idempotency_key="replacement-task-id",
        synced_at=datetime(2026, 7, 2, 3, 31),
    )
    db.refresh(stale)
    assert stale.status == "abandoned"
    assert replacement.status == "pending"


def test_missing_employee_is_suspended_and_sessions_are_revoked_without_permission_loss(
    db: Session,
) -> None:
    departed = _employee(user_num=100, login_id="departed", employee_number="E100")
    remaining = _stable_coworkers()
    _run(
        db,
        users=[departed, *remaining],
        idempotency_key="employees-2026-07-01",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )

    user = db.scalar(select(User).where(User.employee_code == "E100"))
    assert user is not None
    workspace = Workspace(
        id=new_id(),
        key="hr-history-test",
        name="HR history test",
        description="",
        active=True,
    )
    role_id = new_id()
    binding_id = new_id()
    db.add_all(
        [
            workspace,
            UserSystemRole(id=role_id, user_id=user.id, role="platform_admin"),
            WorkspaceUserBinding(
                id=binding_id, workspace_id=workspace.id, user_id=user.id, role="owner"
            ),
            AuthSession(
                id=new_id(),
                user_id=user.id,
                token_hash="departed-session-token-hash",
                expires_at=datetime(2026, 7, 15, 3, 10),
            ),
        ]
    )
    db.commit()
    user_id = user.id

    run = _run(
        db,
        users=remaining,
        idempotency_key="employees-2026-07-02",
        synced_at=datetime(2026, 7, 2, 3, 10),
    )

    db.expire_all()
    suspended = db.get(User, user_id)
    assert suspended is not None
    assert suspended.status == "suspended"
    assert run.status == "succeeded"
    assert run.result_payload["users_suspended"] == 1

    session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
    assert session is not None
    assert session.revoked_at == datetime(2026, 7, 2, 3, 10)
    assert {
        role.id
        for role in db.scalars(
            select(UserSystemRole).where(UserSystemRole.user_id == user_id)
        ).all()
    } == {role_id}
    assert {
        binding.id
        for binding in db.scalars(
            select(WorkspaceUserBinding).where(WorkspaceUserBinding.user_id == user_id)
        ).all()
    } == {binding_id}


def test_same_employee_number_reactivates_the_existing_user_without_reviving_old_sessions(
    db: Session,
) -> None:
    departed = _employee(user_num=100, login_id="returnee", employee_number="E100")
    remaining = _stable_coworkers()
    _run(
        db,
        users=[departed, *remaining],
        idempotency_key="rehire-2026-07-01",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )

    original = db.scalar(select(User).where(User.employee_code == "E100"))
    assert original is not None
    original_id = original.id
    original.login_blocked = True
    old_session = AuthSession(
        id=new_id(),
        user_id=original_id,
        token_hash="returnee-old-session-token-hash",
        expires_at=datetime(2026, 7, 15, 3, 10),
    )
    db.add(old_session)
    db.commit()

    _run(
        db,
        users=remaining,
        idempotency_key="rehire-2026-07-02",
        synced_at=datetime(2026, 7, 2, 3, 10),
    )
    db.refresh(old_session)
    assert old_session.revoked_at == datetime(2026, 7, 2, 3, 10)

    reactivated_source = _employee(
        user_num=900,
        login_id="returnee-new",
        employee_number="E100",
    )
    rehire_run = _run(
        db,
        users=[*remaining, reactivated_source],
        idempotency_key="rehire-2026-07-03",
        synced_at=datetime(2026, 7, 3, 3, 10),
    )

    db.expire_all()
    matches = db.scalars(select(User).where(User.employee_code == "E100")).all()
    assert len(matches) == 1
    assert matches[0].id == original_id
    assert matches[0].status == "active"
    assert matches[0].hr_user_num == 900
    assert matches[0].login_blocked is True
    assert rehire_run.status == "succeeded"

    persisted_old_session = db.get(AuthSession, old_session.id)
    assert persisted_old_session is not None
    assert persisted_old_session.revoked_at == datetime(2026, 7, 2, 3, 10)


def test_new_employee_number_creates_a_new_account_without_merging_old_permissions(
    db: Session,
) -> None:
    departed = _employee(user_num=100, login_id="oldhire", employee_number="E100")
    remaining = _employee(user_num=101, login_id="remaining", employee_number="E101")
    _run(
        db,
        users=[departed, remaining],
        idempotency_key="new-number-2026-07-01",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )
    old_user = db.scalar(select(User).where(User.employee_code == "E100"))
    assert old_user is not None
    db.add(UserSystemRole(id=new_id(), user_id=old_user.id, role="platform_admin"))
    db.commit()

    _run(
        db,
        users=[remaining],
        idempotency_key="new-number-2026-07-02",
        synced_at=datetime(2026, 7, 2, 3, 10),
    )
    new_hire = _employee(user_num=900, login_id="newhire", employee_number="E200")
    run = _run(
        db,
        users=[remaining, new_hire],
        idempotency_key="new-number-2026-07-03",
        synced_at=datetime(2026, 7, 3, 3, 10),
    )

    db.expire_all()
    persisted_old = db.get(User, old_user.id)
    persisted_new = db.scalar(select(User).where(User.employee_code == "E200"))
    assert persisted_old is not None
    assert persisted_new is not None
    assert persisted_new.id != persisted_old.id
    assert persisted_old.status == "suspended"
    assert persisted_new.status == "active"
    assert db.scalars(
        select(UserSystemRole).where(UserSystemRole.user_id == persisted_old.id)
    ).all()
    assert not db.scalars(
        select(UserSystemRole).where(UserSystemRole.user_id == persisted_new.id)
    ).all()
    assert run.result_payload["users_created"] == 1


def test_rejected_empty_and_partial_snapshots_never_replace_the_applied_baseline(
    db: Session,
) -> None:
    employees = [
        _employee(user_num=100, login_id="membera", employee_number="E100"),
        _employee(user_num=101, login_id="memberb", employee_number="E101"),
    ]
    baseline = _run(
        db,
        users=employees,
        idempotency_key="validation-2026-07-01",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )

    empty = _run(
        db,
        departments=[],
        users=[],
        idempotency_key="validation-empty-2026-07-02",
        synced_at=datetime(2026, 7, 2, 3, 10),
    )
    partial = _run(
        db,
        departments=[],
        users=employees,
        idempotency_key="validation-partial-2026-07-03",
        synced_at=datetime(2026, 7, 3, 3, 10),
    )

    assert empty.status == "rejected"
    assert partial.status == "rejected"
    assert empty.result_payload["rejection_reason"] == "empty_snapshot"
    assert partial.result_payload["rejection_reason"] == "partial_snapshot"

    latest_baseline = load_latest_applied_groupware_hr_sync_run(db)
    assert latest_baseline is not None
    assert latest_baseline.id == baseline.id
    assert {user.status for user in db.scalars(select(User)).all()} == {"active"}

    recorded_runs = list_groupware_hr_sync_runs(db, limit=10)
    assert [run.id for run in recorded_runs] == [partial.id, empty.id, baseline.id]


def test_apply_failure_keeps_the_raw_snapshot_and_the_previous_baseline(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employee = _employee(user_num=100, login_id="stable", employee_number="E100")
    baseline = _run(
        db,
        users=[employee],
        idempotency_key="failure-2026-07-01",
        synced_at=datetime(2026, 7, 1, 3, 10),
    )

    def fail_apply(*_args, **_kwargs):
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr("ai_do_api.domains.hr.history.sync_groupware_hr", fail_apply)
    changed = _employee(user_num=100, login_id="stable", employee_number="E100")
    with pytest.raises(RuntimeError, match="simulated apply failure"):
        run_groupware_hr_sync(
            db,
            departments=[_department()],
            users=[changed],
            idempotency_key="failure-2026-07-02",
            synced_at=datetime(2026, 7, 2, 3, 10),
        )

    failed = list_groupware_hr_sync_runs(db, limit=1)[0]
    assert failed.status == "failed"
    assert failed.error_phase == "apply"
    assert db.scalars(
        select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == failed.id)
    ).all()
    latest_baseline = load_latest_applied_groupware_hr_sync_run(db)
    assert latest_baseline is not None
    assert latest_baseline.id == baseline.id


def test_retention_prunes_old_details_but_keeps_run_aggregates_and_latest_baseline(
    db: Session,
) -> None:
    employee = _employee(user_num=100, login_id="retained", employee_number="E100")
    older = _run(
        db,
        users=[employee],
        idempotency_key="retention-2025-06-01",
        synced_at=datetime(2025, 6, 1, 3, 10),
    )
    latest = _run(
        db,
        users=[employee],
        idempotency_key="retention-2025-06-15",
        synced_at=datetime(2025, 6, 15, 3, 10),
    )

    deleted = prune_groupware_hr_history(
        db,
        now=datetime(2026, 7, 21, 3, 10),
        retention_days=365,
    )
    db.commit()

    assert deleted["runs_deleted"] == 0
    assert deleted["user_snapshots_deleted"] == 1
    assert deleted["department_snapshots_deleted"] == 1

    runs = list_groupware_hr_sync_runs(db, limit=10)
    assert [run.id for run in runs] == [latest.id, older.id]
    assert [run.result_payload["users_seen"] for run in runs] == [1, 1]

    baseline = load_latest_applied_groupware_hr_sync_run(db)
    assert baseline is not None
    assert baseline.id == latest.id
