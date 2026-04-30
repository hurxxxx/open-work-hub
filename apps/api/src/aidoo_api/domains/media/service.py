from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.models import User
from aidoo_api.domains.media.models import MediaFile


MEDIA_ID_PATTERN = re.compile(r"media:([0-9a-f-]{36})")


def can_link_unlinked_media(user: User, media: MediaFile) -> bool:
    return media.uploaded_by_id == user.id


def sync_embedded_media(
    db: Session,
    blocks: object,
    resource_type: str,
    resource_id: str,
    current_user: User,
) -> None:
    """Full re-scan: link new media, unlink removed media for a resource."""
    raw = json.dumps(blocks) if not isinstance(blocks, str) else blocks
    current_ids = set(MEDIA_ID_PATTERN.findall(raw))

    if current_ids:
        media_files = db.scalars(
            select(MediaFile).where(
                MediaFile.id.in_(current_ids),
                MediaFile.resource_type.is_(None),
            )
        ).all()
        for media in media_files:
            if not can_link_unlinked_media(current_user, media):
                continue
            media.resource_type = resource_type
            media.resource_id = resource_id

    previously_linked = db.scalars(
        select(MediaFile).where(
            MediaFile.resource_type == resource_type,
            MediaFile.resource_id == resource_id,
        )
    ).all()

    for media in previously_linked:
        if media.id not in current_ids:
            media.resource_type = None
            media.resource_id = None


def cleanup_media_for_resource(db: Session, resource_type: str, resource_id: str) -> list[str]:
    """Mark media for deletion and return storage keys for post-commit MinIO cleanup."""
    media_files = db.scalars(
        select(MediaFile).where(
            MediaFile.resource_type == resource_type,
            MediaFile.resource_id == resource_id,
        )
    ).all()

    if not media_files:
        return []

    keys = [media.storage_key for media in media_files]
    for media in media_files:
        db.delete(media)
    return keys
