from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm import serialization
from open_work_hub_api.domains.dm.schemas import DmUserItem

USER_DIRECTORY_SEARCH_COLUMNS = (
    User.full_name,
    User.display_name,
    User.email,
)


def build_user_directory_query(
    *,
    current_user_id: str,
    include_current: bool = False,
    search: str,
    limit: int,
) -> Select[tuple[User]]:
    query = select(User).where(User.status == "active", User.login_blocked.is_(False))
    if not include_current:
        query = query.where(User.id != current_user_id)
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
) -> list[DmUserItem]:
    query = build_user_directory_query(
        current_user_id=current_user.id,
        include_current=include_current,
        search=q,
        limit=limit,
    )
    return [serialization.serialize_user(user) for user in db.scalars(query)]
