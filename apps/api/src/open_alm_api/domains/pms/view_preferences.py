from __future__ import annotations

from typing import Literal, cast

from fastapi import status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import resolve_workspace_role
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.pms.models import PmsViewPreference, utcnow_naive


TaskListGroupBy = Literal["none", "status", "assignee"]
DEFAULT_TASK_LIST_GROUP_BY: TaskListGroupBy = "status"


def _ensure_workspace_member(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> None:
    if resolve_workspace_role(db, user, workspace.id) is not None:
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="workspace.membership_required",
        workspace=workspace.key,
    )


def get_task_list_group_by(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> TaskListGroupBy:
    _ensure_workspace_member(db, user=user, workspace=workspace)
    preference = db.scalar(
        select(PmsViewPreference).where(
            PmsViewPreference.workspace_id == workspace.id,
            PmsViewPreference.user_id == user.id,
        )
    )
    if preference is None:
        return DEFAULT_TASK_LIST_GROUP_BY
    return cast(TaskListGroupBy, preference.task_list_group_by)


def update_task_list_group_by(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    group_by: TaskListGroupBy,
) -> TaskListGroupBy:
    _ensure_workspace_member(db, user=user, workspace=workspace)
    timestamp = utcnow_naive()
    values = {
        "workspace_id": workspace.id,
        "user_id": user.id,
        "task_list_group_by": group_by,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = postgresql_insert(PmsViewPreference).values(**values)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["workspace_id", "user_id"],
                set_={
                    "task_list_group_by": group_by,
                    "updated_at": timestamp,
                },
            )
        )
    elif dialect_name == "sqlite":
        statement = sqlite_insert(PmsViewPreference).values(**values)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["workspace_id", "user_id"],
                set_={
                    "task_list_group_by": group_by,
                    "updated_at": timestamp,
                },
            )
        )
    else:
        preference = db.get(PmsViewPreference, (workspace.id, user.id))
        if preference is None:
            db.add(PmsViewPreference(**values))
        else:
            preference.task_list_group_by = group_by
            preference.updated_at = timestamp
    db.commit()
    return group_by


__all__ = [
    "DEFAULT_TASK_LIST_GROUP_BY",
    "TaskListGroupBy",
    "get_task_list_group_by",
    "update_task_list_group_by",
]
