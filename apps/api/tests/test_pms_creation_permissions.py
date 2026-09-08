from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from company_admission_fixture import company_authority_tables, seed_company_app_access
from open_work_hub_api.core import settings
from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.pms.space_models import SpaceGroupBinding, Team, TeamMember


@pytest.fixture
def pms_creation_db(monkeypatch: pytest.MonkeyPatch):
    # Import the real handlers with isolated settings, without reading deployment env files.
    monkeypatch.setattr(settings, "ENV_FILE", Path("/dev/null"))
    monkeypatch.setitem(settings.Settings.model_config, "env_file", None)
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", "sqlite://")
    settings.get_settings.cache_clear()
    from open_work_hub_api.domains.pms import router

    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                *company_authority_tables(),
                *(
                    table
                    for table in Base.metadata.tables.values()
                    if table.name.startswith("pms_")
                ),
            ],
        )
        with Session(engine) as db:
            seed_company_app_access(db, app_ids=["pms"])
            yield db, router
    finally:
        engine.dispose()
        settings.get_settings.cache_clear()


@pytest.mark.parametrize("resource_kind", ["folder", "list"])
@pytest.mark.parametrize("group_role", ["member", "admin"])
@pytest.mark.parametrize("revoke", ["membership", "binding"])
def test_group_creation_never_grants_direct_space_ownership(
    pms_creation_db, resource_kind: str, group_role: str, revoke: str
) -> None:
    db, router = pms_creation_db
    owner = User(
        id="space-owner",
        login_id="space-owner",
        email="space-owner@example.test",
        full_name="Space Owner",
        password_hash="fixture",
    )
    contributor = User(
        id="group-contributor",
        login_id="group-contributor",
        email="group-contributor@example.test",
        full_name="Group Contributor",
        password_hash="fixture",
    )
    db.add_all([owner, contributor])
    db.commit()
    space = router.create_space(
        router.SpaceCreateRequest(name="Group project"), db=db, current_user=owner
    )
    group = Group(id="working-group", kind="manual", name="Working group")
    membership = GroupMember(group_id=group.id, user_id=contributor.id)
    binding = SpaceGroupBinding(team_id=space.id, group_id=group.id, role=group_role)
    db.add_all([group, membership, binding])
    db.commit()

    if resource_kind == "folder":
        folder = router.create_folder(
            router.FolderCreateRequest(team_id=space.id, name="Group folder"),
            db=db,
            current_user=contributor,
        )
        from open_work_hub_api.domains.pms.models import TaskList

        list_id = db.scalar(select(TaskList.id).where(TaskList.folder_id == folder.id))
    else:
        created = router.create_task_list(
            router.TaskListCreateRequest(team_id=space.id, name="Group list"),
            db=db,
            current_user=contributor,
        )
        list_id = created.id

    assert list_id is not None
    direct_role = db.scalar(
        select(TeamMember.role).where(
            TeamMember.team_id == space.id, TeamMember.user_id == contributor.id
        )
    )
    assert (
        db.scalar(
            select(TeamMember.role).where(
                TeamMember.team_id == space.id, TeamMember.user_id == owner.id
            )
        )
        == "owner"
    )
    effective_role = router.get_task_list(list_id, db=db, current_user=contributor).role

    db.delete(membership if revoke == "membership" else binding)
    db.commit()
    with pytest.raises(HTTPException) as denied:
        router.get_task_list(list_id, db=db, current_user=contributor)
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as denied_write:
        router.create_folder(
            router.FolderCreateRequest(team_id=space.id, name="After revocation"),
            db=db,
            current_user=contributor,
        )
    assert denied_write.value.status_code == 403
    assert direct_role is None
    assert effective_role == group_role
    if resource_kind == "list":
        assert created.role == group_role
    assert router.get_task_list(list_id, db=db, current_user=owner).role == "owner"
    assert db.get(Team, space.id) is not None
