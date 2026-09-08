from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User, UserSystemRole
from open_work_hub_api.domains.auth.roles import SYSTEM_PLATFORM_ADMIN
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
)


def is_current_platform_admin(db: Session, user_id: str) -> bool:
    user = _load_current_active_user(db, user_id)
    return (
        user is not None
        and db.scalar(
            select(UserSystemRole.id).where(
                UserSystemRole.user_id == user_id, UserSystemRole.role == SYSTEM_PLATFORM_ADMIN
            )
        )
        is not None
    )


def authorize_explicit_file_ids(
    db: Session,
    *,
    file_ids: Iterable[str],
    user_id: str,
) -> set[str]:
    """Authorize explicit-grant files from current source-owned database state.

    Missing metadata, unresolved ACLs, and resolved-but-empty ACLs all fail closed.
    Platform admins may read existing company records; personal files have no override.
    """

    normalized_ids = tuple(dict.fromkeys(str(value) for value in file_ids if value))
    if not normalized_ids:
        return set()
    user = _load_current_active_user(db, user_id)
    if user is None or not can_use_app(db, user_id=user_id, app_id="files"):
        return set()
    if is_current_platform_admin(db, user_id):
        return set(
            db.scalars(
                select(FileManagerFile.id)
                .join(FileManagerCorpus, FileManagerCorpus.id == FileManagerFile.corpus_id)
                .where(
                    FileManagerFile.id.in_(normalized_ids),
                    FileManagerFile.deleted_at.is_(None),
                    FileManagerCorpus.access_scope_kind == "company",
                    FileManagerCorpus.authorization_mode == "explicit_grants",
                )
            )
        )

    grant_conditions = _current_grant_conditions(
        db,
        user=user,
    )
    if not grant_conditions:
        return set()
    return set(
        db.scalars(
            select(FileManagerFileAccessGrant.file_id)
            .join(
                FileManagerFileSourceMetadata,
                FileManagerFileSourceMetadata.file_id == FileManagerFileAccessGrant.file_id,
            )
            .where(
                FileManagerFileAccessGrant.file_id.in_(normalized_ids),
                FileManagerFileSourceMetadata.acl_resolved.is_(True),
                or_(*grant_conditions),
            )
            .distinct()
        ).all()
    )


def has_any_explicit_file_access(
    db: Session,
    *,
    user_id: str,
) -> bool:
    """Check whether at least one live, in-scope explicit-grant file is readable."""

    user = _load_current_active_user(db, user_id)
    if user is None or not can_use_app(db, user_id=user_id, app_id="files"):
        return False
    scope_condition = FileManagerCorpus.access_scope_kind == "company"
    base = (
        select(FileManagerFile.id)
        .join(FileManagerCorpus, FileManagerCorpus.id == FileManagerFile.corpus_id)
        .where(
            FileManagerCorpus.authorization_mode == "explicit_grants",
            scope_condition,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    explicit_candidate_exists = db.scalar(base.limit(1)) is not None
    if not explicit_candidate_exists:
        return False
    if is_current_platform_admin(db, user_id):
        return True

    grant_conditions = _current_grant_conditions(
        db,
        user=user,
    )
    if not grant_conditions:
        return False
    statement = (
        base.join(
            FileManagerFileSourceMetadata,
            FileManagerFileSourceMetadata.file_id == FileManagerFile.id,
        )
        .join(
            FileManagerFileAccessGrant,
            FileManagerFileAccessGrant.file_id == FileManagerFile.id,
        )
        .where(
            FileManagerFileSourceMetadata.acl_resolved.is_(True),
            or_(*grant_conditions),
        )
        .limit(1)
    )
    return db.scalar(statement) is not None


def _current_grant_conditions(db: Session, *, user: User) -> list[object]:
    from open_work_hub_api.domains.groups.service import user_group_ids_query
    from open_work_hub_api.domains.pms.access import accessible_space_ids_query

    return [
        and_(
            FileManagerFileAccessGrant.grant_type == "company",
            FileManagerFileAccessGrant.target_id.is_(None),
        ),
        and_(
            FileManagerFileAccessGrant.grant_type == "user",
            FileManagerFileAccessGrant.target_id == user.id,
        ),
        and_(
            FileManagerFileAccessGrant.grant_type == "group",
            FileManagerFileAccessGrant.target_id.in_(user_group_ids_query(user.id)),
        ),
        and_(
            FileManagerFileAccessGrant.grant_type == "team",
            FileManagerFileAccessGrant.target_id.in_(
                accessible_space_ids_query(db, user_id=user.id)
            ),
        ),
    ]


def _load_current_active_user(db: Session, user_id: str) -> User | None:
    return db.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.status == "active",
            User.login_blocked.is_(False),
        )
        .execution_options(populate_existing=True)
    )


__all__ = [
    "authorize_explicit_file_ids",
    "has_any_explicit_file_access",
    "is_current_platform_admin",
]
