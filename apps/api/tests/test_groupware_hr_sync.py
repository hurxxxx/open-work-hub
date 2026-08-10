from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import AuditLog, AuthSession, OrgUnit, User, Workspace
from ai_do_api.domains.auth.security import hash_password, new_id
from ai_do_api.domains.hr.groupware_sync import (
    AUTH_PROVIDER_GROUPWARE,
    GROUPWARE_SOURCE_SYSTEM,
    GroupwareOrgRow,
    GroupwareUserRow,
    sync_groupware_hr,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Workspace.__table__,
            OrgUnit.__table__,
            User.__table__,
            AuditLog.__table__,
            AuthSession.__table__,
        ],
    )
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_groupware_sync_does_not_merge_an_existing_local_login_into_an_hr_identity(
    db: Session,
) -> None:
    existing = User(
        id=new_id(),
        login_id="shryu",
        email="old@example.com",
        full_name="Old Name",
        password_hash=hash_password("local-password"),
        status="active",
        auth_provider="local",
        must_change_password=False,
        theme_preference="system",
        locale="ko-KR",
        time_zone="Asia/Seoul",
        date_format="korean",
    )
    db.add(existing)
    db.commit()
    existing_id = existing.id

    result = sync_groupware_hr(
        db,
        synced_at=datetime(2026, 6, 1, 3, 10, 0),
        departments=[
            GroupwareOrgRow(
                domain_num=1,
                depart_num=10,
                org_code="RND",
                org_depart="기술연구소",
            ),
            GroupwareOrgRow(
                domain_num=1,
                depart_num=11,
                org_code="AI",
                org_depart="AI TFT",
                p_org_code="RND",
            ),
        ],
        users=[
            GroupwareUserRow(
                domain_num=1,
                user_num=100,
                user_id="shryu",
                kor_name="류승현",
                com_state=1,
                email="shared@example.com",
                com_num="E100",
                com_position="책임",
                org_code1="RND",
                org_code2="AI",
                org_level=2,
            )
        ],
    )
    db.commit()

    unchanged = db.scalar(select(User).where(User.login_id == "shryu"))
    assert unchanged is not None
    assert unchanged.id == existing_id
    assert unchanged.auth_provider == "local"
    assert unchanged.hr_source_system is None
    assert unchanged.email == "old@example.com"
    assert result.users_created == 0
    assert result.users_updated == 0
    assert result.skipped_conflict_users == 1


def test_groupware_sync_allows_duplicate_emails_for_hr_users(db: Session) -> None:
    departments = [
        GroupwareOrgRow(
            domain_num=1,
            depart_num=10,
            org_code="RND",
            org_depart="기술연구소",
        )
    ]
    users = [
        GroupwareUserRow(
            domain_num=1,
            user_num=100,
            user_id="membera",
            kor_name="사용자A",
            com_state=1,
            email="shared@example.com",
            com_num="E100",
            org_code1="RND",
            org_level=1,
        ),
        GroupwareUserRow(
            domain_num=1,
            user_num=101,
            user_id="memberb",
            kor_name="사용자B",
            com_state=1,
            email="shared@example.com",
            com_num="E101",
            org_code1="RND",
            org_level=1,
        ),
    ]

    result = sync_groupware_hr(db, departments=departments, users=users)
    db.commit()

    assert result.users_created == 2
    assert db.scalar(select(User).where(User.email == "shared@example.com").limit(1)) is not None
    assert len(db.scalars(select(User).where(User.email == "shared@example.com")).all()) == 2


def test_groupware_sync_uses_org_code_as_department_identity(db: Session) -> None:
    first_result = sync_groupware_hr(
        db,
        departments=[
            GroupwareOrgRow(
                domain_num=1,
                depart_num=10,
                org_code="RND",
                org_depart="기술연구소",
                org_order=8,
            )
        ],
        users=[],
    )
    db.commit()

    org = db.scalar(select(OrgUnit).where(OrgUnit.hr_org_code == "RND"))
    assert org is not None
    org_id = org.id
    assert org.hr_depart_num == 10
    assert org.hr_org_order == 8
    assert first_result.departments_created == 1

    second_result = sync_groupware_hr(
        db,
        departments=[
            GroupwareOrgRow(
                domain_num=1,
                org_code="RND",
                org_depart="기술연구소",
                org_order=9,
            )
        ],
        users=[],
    )
    db.commit()

    updated_org = db.scalar(select(OrgUnit).where(OrgUnit.hr_org_code == "RND"))
    assert updated_org is not None
    assert updated_org.id == org_id
    assert updated_org.hr_depart_num is None
    assert updated_org.hr_org_order == 9
    assert updated_org.active is True
    assert second_result.departments_created == 0
    assert second_result.departments_updated == 1
    assert second_result.departments_suspended == 0


def test_groupware_sync_skips_all_active_rows_with_duplicate_login_id(db: Session) -> None:
    result = sync_groupware_hr(
        db,
        departments=[],
        users=[
            GroupwareUserRow(
                domain_num=1,
                user_num=100,
                user_id="dupuser",
                kor_name="사용자A",
                com_state=1,
            ),
            GroupwareUserRow(
                domain_num=1,
                user_num=101,
                user_id="dupuser",
                kor_name="사용자B",
                com_state=1,
            ),
        ],
    )
    db.commit()

    assert result.skipped_duplicate_login_users == 2
    assert db.scalar(select(User).where(User.login_id == "dupuser")) is None


def test_groupware_sync_suspends_existing_hr_user_for_inactive_source_row(db: Session) -> None:
    user = User(
        id=new_id(),
        login_id="retired",
        email="retired@example.com",
        full_name="Retired",
        password_hash=hash_password("unused-password"),
        status="active",
        auth_provider=AUTH_PROVIDER_GROUPWARE,
        must_change_password=False,
        theme_preference="system",
        locale="ko-KR",
        time_zone="Asia/Seoul",
        date_format="korean",
        hr_source_system=GROUPWARE_SOURCE_SYSTEM,
        hr_domain_num=1,
        hr_user_num=100,
    )
    db.add(user)
    db.commit()

    result = sync_groupware_hr(
        db,
        departments=[],
        users=[
            GroupwareUserRow(
                domain_num=1,
                user_num=100,
                user_id="retired",
                kor_name="퇴직자",
                com_state=-1,
            ),
            GroupwareUserRow(
                domain_num=1,
                user_num=101,
                user_id="nevercreated",
                kor_name="퇴직자2",
                com_state=-1,
            ),
        ],
    )
    db.commit()

    db.refresh(user)
    assert user.status == "suspended"
    assert result.users_suspended == 1
    assert result.skipped_inactive_users == 1
    assert db.scalar(select(User).where(User.login_id == "nevercreated")) is None
