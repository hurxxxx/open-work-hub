from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.groups.models import Group


class HrGroupError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def lock_group_hierarchy(db: Session) -> None:
    # Acquire before any group row locks so concurrent subtree moves cannot form a cycle.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext("organization_hierarchy"))))


def group_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-_")
    slug = slug.replace("_", "-")[:80].rstrip("-")
    return slug or f"unit-{new_id()[:8]}"


def load_hr_group(
    db: Session,
    group_id: str,
) -> Group:
    statement = select(Group).where(Group.id == group_id, Group.source == "hr")
    item = db.scalar(statement)
    if item is None:
        raise HrGroupError("organization.unit_not_found")
    return item


def ensure_active_hr_group(
    db: Session,
    group_id: str | None,
) -> Group | None:
    if group_id is None:
        return None
    item = load_hr_group(db, group_id)
    if not item.active:
        raise HrGroupError("organization.unit_inactive")
    return item


def ensure_unique_slug(
    db: Session,
    slug: str,
    *,
    exclude_id: str | None = None,
) -> None:
    statement = select(Group.id).where(Group.slug == slug)
    if exclude_id is not None:
        statement = statement.where(Group.id != exclude_id)
    if db.scalar(statement) is not None:
        raise HrGroupError("organization.slug_exists")


def ensure_valid_parent(
    db: Session,
    *,
    group_id: str | None,
    parent_id: str | None,
) -> None:
    if parent_id is None:
        return
    if group_id == parent_id:
        raise HrGroupError("organization.cycle_detected")

    current_id = parent_id
    visited: set[str] = set()
    while current_id is not None:
        if current_id in visited or current_id == group_id:
            raise HrGroupError("organization.cycle_detected")
        visited.add(current_id)
        # An ORM identity map may predate the hierarchy lock; read current scalar edges.
        row = db.execute(
            select(Group.parent_id).where(Group.id == current_id, Group.source == "hr")
        ).one_or_none()
        if row is None:
            raise HrGroupError("organization.unit_not_found")
        current_id = row[0]


def descendant_hr_group_ids(
    db: Session,
    group_id: str,
) -> set[str]:
    load_hr_group(db, group_id)
    children_by_parent: dict[str, list[str]] = {}
    for item_id, parent_id in db.execute(
        select(Group.id, Group.parent_id).where(Group.source == "hr")
    ).all():
        if parent_id is not None:
            children_by_parent.setdefault(parent_id, []).append(item_id)

    descendants: set[str] = set()
    pending = [group_id]
    while pending:
        current_id = pending.pop()
        if current_id in descendants:
            continue
        descendants.add(current_id)
        pending.extend(children_by_parent.get(current_id, ()))
    return descendants


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
        raise HrGroupError("organization.head_inactive")
