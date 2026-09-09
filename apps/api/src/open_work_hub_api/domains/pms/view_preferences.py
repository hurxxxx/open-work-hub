from __future__ import annotations

from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.pms.models import PmsViewPreference, utcnow_naive

TaskListGroupBy = Literal["none", "status", "assignee"]
DEFAULT_TASK_LIST_GROUP_BY: TaskListGroupBy = "status"


def _ensure_app_access(db: Session, *, user: User) -> None:
    if not can_use_app(db, user_id=user.id, app_id="pms"):
        raise localized_http_exception(status_code=403, code="platform.app_disabled")


def get_task_list_group_by(
    db: Session,
    *,
    user: User,
) -> TaskListGroupBy:
    _ensure_app_access(
        db,
        user=user,
    )
    preference = db.scalar(
        select(PmsViewPreference).where(
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
    group_by: TaskListGroupBy,
) -> TaskListGroupBy:
    _ensure_app_access(
        db,
        user=user,
    )
    timestamp = utcnow_naive()
    values = {
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
                index_elements=["user_id"],
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
                index_elements=["user_id"],
                set_={
                    "task_list_group_by": group_by,
                    "updated_at": timestamp,
                },
            )
        )
    else:
        preference = db.get(PmsViewPreference, user.id)
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
