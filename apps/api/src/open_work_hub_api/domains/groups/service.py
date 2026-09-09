from __future__ import annotations

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.groups.schemas import GroupListResponse, GroupResponse
from open_work_hub_api.domains.organization.models import OrganizationUnit


class GroupError(ValueError):
    def __init__(self, code: str, status_code: int = 400):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def active_group_predicate():
    return and_(
        Group.active.is_(True),
        or_(
            Group.kind == "manual",
            and_(
                Group.kind == "organization",
                exists()
                .where(
                    OrganizationUnit.id == Group.organization_unit_id,
                    OrganizationUnit.active.is_(True),
                )
                .correlate(Group),
            ),
        ),
    )


def user_group_ids_query(user_id: str):
    """Read current direct HR membership and manual grants in one statement."""
    return select(Group.id).where(
        active_group_predicate(),
        exists().where(User.id == user_id, User.status == "active", User.login_blocked.is_(False)),
        or_(
            and_(
                Group.kind == "manual",
                exists().where(GroupMember.group_id == Group.id, GroupMember.user_id == user_id),
            ),
            and_(
                Group.kind == "organization",
                exists().where(
                    User.id == user_id,
                    User.primary_organization_unit_id == Group.organization_unit_id,
                ),
            ),
        ),
    )


def current_group_ids(db: Session, user_id: str) -> frozenset[str]:
    return frozenset(db.scalars(user_group_ids_query(user_id)))


def group_members_query(group: Group):
    statement = select(User).where(User.status == "active", User.login_blocked.is_(False))
    if group.kind == "organization":
        return statement.where(User.primary_organization_unit_id == group.organization_unit_id)
    return statement.where(
        exists().where(GroupMember.group_id == group.id, GroupMember.user_id == User.id)
    )


def ensure_organization_group(db: Session, organization_unit_id: str) -> None:
    """Called in the organization's write transaction, including future HR ingestion."""
    db.flush()
    db.execute(
        insert(Group)
        .values(id=new_id(), kind="organization", organization_unit_id=organization_unit_id)
        .on_conflict_do_nothing(index_elements=[Group.organization_unit_id])
    )


def managed_organization_ids(db: Session, user_id: str) -> list[str]:
    return list(
        db.scalars(
            select(OrganizationUnit.id)
            .where(
                OrganizationUnit.head_user_id == user_id,
                OrganizationUnit.active.is_(True),
                exists().where(
                    User.id == user_id, User.status == "active", User.login_blocked.is_(False)
                ),
            )
            .order_by(OrganizationUnit.id)
        )
    )


def load_group(db: Session, group_id: str, *, for_update: bool = False) -> Group:
    statement = select(Group).where(Group.id == group_id)
    if for_update:
        statement = statement.with_for_update()
    group = db.scalar(statement)
    if group is None:
        raise GroupError("group.not_found", 404)
    return group


def serialize_group(db: Session, group: Group) -> GroupResponse:
    organization = (
        db.get(OrganizationUnit, group.organization_unit_id)
        if group.kind == "organization"
        else None
    )
    return GroupResponse(
        id=group.id,
        kind=group.kind,
        name=organization.name if organization else group.name,
        description=group.description,
        organization_unit_id=group.organization_unit_id,
        active=group.active
        and (bool(organization and organization.active) if group.kind == "organization" else True),
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def list_groups(
    db: Session,
    *,
    query: str = "",
    page: int = 1,
    page_size: int = 50,
    include_inactive: bool = False,
    ids: list[str] | None = None,
) -> GroupListResponse:
    statement = select(Group).outerjoin(
        OrganizationUnit, OrganizationUnit.id == Group.organization_unit_id
    )
    if ids is not None:
        statement = statement.where(Group.id.in_(ids))
    if not include_inactive:
        statement = statement.where(active_group_predicate())
    if query.strip():
        statement = statement.where(
            or_(
                Group.name.icontains(query.strip(), autoescape=True),
                OrganizationUnit.name.icontains(query.strip(), autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    groups = db.scalars(
        statement.order_by(Group.id).offset((page - 1) * page_size).limit(page_size)
    )
    return GroupListResponse(
        items=[serialize_group(db, group) for group in groups],
        total=total,
        page=page,
        page_size=page_size,
    )


def require_manual_group(group: Group) -> None:
    if group.kind != "manual":
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
    if not requested.issubset(valid | existing):
        raise GroupError("group.invalid_members")
    db.execute(delete(GroupMember).where(GroupMember.group_id == group.id))
    db.add_all(GroupMember(group_id=group.id, user_id=user_id) for user_id in sorted(requested))
