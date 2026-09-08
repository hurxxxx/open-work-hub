from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.organization.models import OrganizationUnit


class OrganizationDirectoryError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def lock_organization_hierarchy(db: Session) -> None:
    # Acquire before any unit row locks so concurrent subtree moves cannot form a cycle.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext("organization_hierarchy"))))


def organization_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-_")
    slug = slug.replace("_", "-")[:80].rstrip("-")
    return slug or f"unit-{new_id()[:8]}"


def load_organization_unit(
    db: Session,
    organization_unit_id: str,
    *,
    for_update: bool = False,
) -> OrganizationUnit:
    statement = select(OrganizationUnit).where(OrganizationUnit.id == organization_unit_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(statement)
    if item is None:
        raise OrganizationDirectoryError("organization.unit_not_found")
    return item


def ensure_active_organization_unit(
    db: Session,
    organization_unit_id: str | None,
) -> OrganizationUnit | None:
    if organization_unit_id is None:
        return None
    item = load_organization_unit(db, organization_unit_id)
    if not item.active:
        raise OrganizationDirectoryError("organization.unit_inactive")
    return item


def ensure_unique_slug(
    db: Session,
    slug: str,
    *,
    exclude_id: str | None = None,
) -> None:
    statement = select(OrganizationUnit.id).where(OrganizationUnit.slug == slug)
    if exclude_id is not None:
        statement = statement.where(OrganizationUnit.id != exclude_id)
    if db.scalar(statement) is not None:
        raise OrganizationDirectoryError("organization.slug_exists")


def ensure_valid_parent(
    db: Session,
    *,
    organization_unit_id: str | None,
    parent_id: str | None,
) -> None:
    if parent_id is None:
        return
    if organization_unit_id == parent_id:
        raise OrganizationDirectoryError("organization.cycle_detected")

    current_id = parent_id
    visited: set[str] = set()
    while current_id is not None:
        if current_id in visited or current_id == organization_unit_id:
            raise OrganizationDirectoryError("organization.cycle_detected")
        visited.add(current_id)
        # An ORM identity map may predate the hierarchy lock; read current scalar edges.
        row = db.execute(
            select(OrganizationUnit.parent_id).where(OrganizationUnit.id == current_id)
        ).one_or_none()
        if row is None:
            raise OrganizationDirectoryError("organization.unit_not_found")
        current_id = row[0]


def descendant_organization_unit_ids(
    db: Session,
    organization_unit_id: str,
) -> set[str]:
    load_organization_unit(db, organization_unit_id)
    children_by_parent: dict[str, list[str]] = {}
    for item_id, parent_id in db.execute(
        select(OrganizationUnit.id, OrganizationUnit.parent_id)
    ).all():
        if parent_id is not None:
            children_by_parent.setdefault(parent_id, []).append(item_id)

    descendants: set[str] = set()
    pending = [organization_unit_id]
    while pending:
        current_id = pending.pop()
        if current_id in descendants:
            continue
        descendants.add(current_id)
        pending.extend(children_by_parent.get(current_id, ()))
    return descendants


def serialize_organization_unit(item: OrganizationUnit) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "slug": item.slug,
        "unit_type": item.unit_type,
        "parent_id": item.parent_id,
        "active": item.active,
        "head_user_id": item.head_user_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def ensure_valid_head(db: Session, user_id: str | None) -> None:
    if (
        user_id is not None
        and db.scalar(
            select(User.id).where(
                User.id == user_id, User.status == "active", User.login_blocked.is_(False)
            )
        )
        is None
    ):
        raise OrganizationDirectoryError("organization.head_inactive")
