from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.object_storage import (
    DEFAULT_MEDIA_CONTENT_TYPE,
    MediaObjectRemovalResult,
    build_media_storage_key,
)


class MediaUploadRecordInput(TypedDict):
    media_id: str
    user_id: str
    filename: str | None
    content_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class OrphanMediaCleanupPlan:
    rows_to_delete: list[MediaFile]
    deleted_count: int
    failed_count: int


def build_media_upload_record(payload: MediaUploadRecordInput) -> MediaFile:
    filename = payload["filename"] or "unnamed"
    return MediaFile(
        id=payload["media_id"],
        storage_key=build_media_storage_key(
            user_id=payload["user_id"],
            media_id=payload["media_id"],
            filename=filename,
        ),
        filename=filename,
        content_type=payload["content_type"] or DEFAULT_MEDIA_CONTENT_TYPE,
        size_bytes=payload["size_bytes"],
        uploaded_by_id=payload["user_id"],
    )


def media_upload_response_payload(media_id: str) -> dict[str, str]:
    return {"id": media_id, "url": f"media:{media_id}"}


def apply_media_links(
    media_files: list[MediaFile],
    current_user: User,
    resource_type: str,
    resource_id: str,
) -> None:
    for media in media_files:
        if media.resource_type is not None:
            continue
        if media.uploaded_by_id != current_user.id:
            continue
        media.resource_type = resource_type
        media.resource_id = resource_id


def plan_orphan_media_cleanup(
    orphans: list[MediaFile],
    removal_result: MediaObjectRemovalResult,
) -> OrphanMediaCleanupPlan:
    deleted_keys = set(removal_result.removed_storage_keys)
    rows_to_delete = [orphan for orphan in orphans if orphan.storage_key in deleted_keys]
    return OrphanMediaCleanupPlan(
        rows_to_delete=rows_to_delete,
        deleted_count=len(rows_to_delete),
        failed_count=len(removal_result.failures),
    )
