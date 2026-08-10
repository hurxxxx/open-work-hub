from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, contains_eager
from sqlalchemy.sql import Select

from ai_do_api.domains.auth.models import OrgUnit, User, WorkspaceUserBinding
from ai_do_api.domains.dm import serialization
from ai_do_api.domains.dm.schemas import DmUserItem


USER_DIRECTORY_SEARCH_COLUMNS = (
    User.full_name,
    User.display_name,
    User.email,
    User.job_title,
    OrgUnit.name,
)


def build_user_directory_query(
    *,
    current_user_id: str,
    include_current: bool = False,
    search: str,
    limit: int,
    workspace_id: str | None = None,
) -> Select[tuple[User]]:
    query = (
        select(User)
        .outerjoin(OrgUnit, User.primary_org_unit_id == OrgUnit.id)
        .options(contains_eager(User.primary_org_unit))
        .where(User.status == "active")
    )
    if not include_current:
        query = query.where(User.id != current_user_id)
    if workspace_id is not None:
        query = query.join(
            WorkspaceUserBinding,
            WorkspaceUserBinding.user_id == User.id,
        ).where(WorkspaceUserBinding.workspace_id == workspace_id)
    normalized_search = search.strip()
    if normalized_search:
        like = f"%{normalized_search}%"
        query = query.where(or_(*(column.ilike(like) for column in USER_DIRECTORY_SEARCH_COLUMNS)))
    return query.order_by(User.full_name.asc(), User.email.asc()).limit(limit)


def search_users(
    db: Session,
    *,
    current_user: User,
    include_current: bool = False,
    q: str,
    limit: int,
    workspace_id: str | None = None,
) -> list[DmUserItem]:
    query = build_user_directory_query(
        current_user_id=current_user.id,
        include_current=include_current,
        search=q,
        limit=limit,
        workspace_id=workspace_id,
    )
    return [serialization.serialize_user(user) for user in db.scalars(query)]
