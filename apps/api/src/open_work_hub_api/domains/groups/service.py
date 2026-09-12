from __future__ import annotations

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.groups.schemas import GroupListResponse, GroupResponse
from open_work_hub_api.domains.groups.hr import (
    HrGroupError,
    ensure_unique_slug,
    ensure_valid_parent,
    ensure_valid_head,
    group_slug,
)


class GroupError(ValueError):
    def __init__(self, code: str, status_code: int = 400):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def active_group_predicate():
    return Group.active.is_(True)


def user_group_ids_query(user_id: str):
    """Read current direct HR membership and manual grants in one statement."""
    return select(Group.id).where(
        active_group_predicate(),
        exists().where(User.id == user_id, User.status == "active", User.login_blocked.is_(False)),
        or_(
            and_(
                Group.source == "local",
                exists().where(GroupMember.group_id == Group.id, GroupMember.user_id == user_id),
            ),
            and_(
                Group.source == "hr",
                exists().where(
                    User.id == user_id,
                    User.primary_organization_unit_id == Group.id,
                ),
            ),
        ),
    )


def current_group_ids(db: Session, user_id: str) -> frozenset[str]:
    return frozenset(db.scalars(user_group_ids_query(user_id)))


def group_members_query(group: Group):
    statement = select(User).where(User.status == "active", User.login_blocked.is_(False))
    if group.source == "hr":
        return statement.where(User.primary_organization_unit_id == group.id)
    return statement.where(
        exists().where(GroupMember.group_id == group.id, GroupMember.user_id == User.id)
    )


def managed_organization_ids(db: Session, user_id: str) -> list[str]:
    return list(
        db.scalars(
            select(Group.id)
            .where(
                Group.head_user_id == user_id,
                Group.source == "hr",
                Group.active.is_(True),
                exists().where(
                    User.id == user_id, User.status == "active", User.login_blocked.is_(False)
                ),
            )
            .order_by(Group.id)
        )
    )


def load_group(db: Session, group_id: str, *, for_update: bool = False) -> Group:
    statement = select(Group).where(Group.id == group_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    group = db.scalar(statement)
    if group is None:
        raise GroupError("group.not_found", 404)
    return group


def serialize_group(group: Group) -> GroupResponse:
    return GroupResponse.model_validate(group, from_attributes=True)


def list_groups(
    db: Session,
    *,
    query: str = "",
    page: int = 1,
    page_size: int = 50,
    include_inactive: bool = False,
    ids: list[str] | None = None,
    source: str | None = None,
    member_user_id: str | None = None,
) -> GroupListResponse:
    statement = select(Group)
    if member_user_id is not None:
        statement = statement.where(
            or_(
                and_(
                    Group.source == "local",
                    exists().where(
                        GroupMember.group_id == Group.id, GroupMember.user_id == member_user_id
                    ),
                ),
                and_(
                    Group.source == "hr",
                    exists().where(
                        User.id == member_user_id, User.primary_organization_unit_id == Group.id
                    ),
                ),
            )
        )
    if source is not None:
        statement = statement.where(Group.source == source)
    if ids is not None:
        statement = statement.where(Group.id.in_(ids))
    if not include_inactive:
        statement = statement.where(active_group_predicate())
    if query.strip():
        statement = statement.where(
            or_(
                Group.name.icontains(query.strip(), autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    groups = db.scalars(
        statement.order_by(Group.name, Group.id).offset((page - 1) * page_size).limit(page_size)
    )
    return GroupListResponse(
        items=[serialize_group(group) for group in groups],
        total=total,
        page=page,
        page_size=page_size,
    )


def require_manual_group(group: Group) -> None:
    if group.source != "local":
        raise GroupError("group.organization_managed", 409)


def replace_manual_members(db: Session, group: Group, user_ids: list[str]) -> None:
    require_manual_group(group)
    requested = set(user_ids)
    valid = set(
        db.scalars(
            select(User.id).where(
                User.id.in_(requested), User.status == "active", User.login_blocked.is_(False)
            )
        )
    )
    existing = set(db.scalars(select(GroupMember.user_id).where(GroupMember.group_id == group.id)))
    if not group.active and requested - existing:
        raise GroupError("group.inactive_assignment", 409)
    if not requested.issubset(valid | existing):
        raise GroupError("group.invalid_members")
    db.execute(delete(GroupMember).where(GroupMember.group_id == group.id))
    db.add_all(GroupMember(group_id=group.id, user_id=user_id) for user_id in sorted(requested))


def validate_metadata(db: Session, group: Group, changes: dict) -> dict:
    hr_fields = {"source_reference", "slug", "unit_type", "parent_id", "head_user_id"}
    if group.source == "local":
        if any(changes.get(field) is not None for field in hr_fields):
            raise GroupError("group.hr_metadata_only")
        return {key: value for key, value in changes.items() if key not in hr_fields}
    reference = changes.get("source_reference")
    if (
        reference
        and db.scalar(
            select(Group.id).where(
                Group.source == "hr", Group.source_reference == reference, Group.id != group.id
            )
        )
        is not None
    ):
        raise GroupError("group.source_reference_exists", 409)
    try:
        if "slug" in changes or not group.slug:
            slug = group_slug(changes.get("slug") or group.name)
            ensure_unique_slug(db, slug, exclude_id=group.id)
            changes["slug"] = slug
        if not group.unit_type and not changes.get("unit_type"):
            changes["unit_type"] = "department"
        if "head_user_id" in changes:
            ensure_valid_head(db, changes["head_user_id"])
        ensure_valid_parent(
            db, group_id=group.id, parent_id=changes.get("parent_id", group.parent_id)
        )
    except HrGroupError as error:
        code = 404 if error.code == "organization.unit_not_found" else 409
        raise GroupError(error.code, code) from error
    return changes
