from __future__ import annotations

from types import SimpleNamespace

from open_alm_api.domains.media.lifecycle import (
    apply_media_links,
    build_media_upload_record,
    media_upload_response_payload,
    plan_orphan_media_cleanup,
)
from open_alm_api.domains.media.models import MediaFile
from open_alm_api.domains.media.object_storage import (
    MediaObjectRemovalFailure,
    MediaObjectRemovalResult,
)


def _media(**overrides: object) -> MediaFile:
    defaults = {
        "id": "media-1",
        "storage_key": "media/uploader/media-1/fixture.png",
        "filename": "fixture.png",
        "content_type": "image/png",
        "size_bytes": 128,
        "uploaded_by_id": "uploader",
        "resource_type": None,
        "resource_id": None,
    }
    defaults.update(overrides)
    return MediaFile(**defaults)


def test_build_media_upload_record_uses_unnamed_fallback_and_storage_key_layout() -> None:
    media = build_media_upload_record(
        {
            "media_id": "media-1",
            "user_id": "user-1",
            "filename": None,
            "content_type": None,
            "size_bytes": 42,
        }
    )

    assert media.id == "media-1"
    assert media.filename == "unnamed"
    assert media.storage_key == "media/user-1/media-1/unnamed"
    assert media.content_type == "application/octet-stream"
    assert media.size_bytes == 42
    assert media.uploaded_by_id == "user-1"


def test_media_upload_response_payload_uses_media_url_scheme() -> None:
    assert media_upload_response_payload("media-1") == {
        "id": "media-1",
        "url": "media:media-1",
    }


def test_apply_media_links_mutates_only_upload_owner_unlinked_files() -> None:
    owner_unlinked = _media(id="owner-unlinked", uploaded_by_id="user-1")
    other_owner = _media(id="other-owner", uploaded_by_id="user-2")
    already_linked = _media(
        id="already-linked",
        uploaded_by_id="user-1",
        resource_type="docs_native_page",
        resource_id="existing-resource",
    )

    apply_media_links(
        [owner_unlinked, other_owner, already_linked],
        SimpleNamespace(id="user-1"),
        "task",
        "task-1",
    )

    assert owner_unlinked.resource_type == "task"
    assert owner_unlinked.resource_id == "task-1"
    assert other_owner.resource_type is None
    assert other_owner.resource_id is None
    assert already_linked.resource_type == "docs_native_page"
    assert already_linked.resource_id == "existing-resource"


def test_plan_orphan_media_cleanup_deletes_only_successful_storage_removals() -> None:
    removed = _media(id="removed", storage_key="media/user-1/removed/file.png")
    failed = _media(id="failed", storage_key="media/user-1/failed/file.png")
    skipped = _media(id="skipped", storage_key="media/user-1/skipped/file.png")

    cleanup_plan = plan_orphan_media_cleanup(
        [removed, failed, skipped],
        MediaObjectRemovalResult(
            removed_storage_keys=[removed.storage_key],
            failures=[
                MediaObjectRemovalFailure(
                    storage_key=failed.storage_key,
                    exc=RuntimeError("remove failed"),
                )
            ],
        ),
    )

    assert cleanup_plan.rows_to_delete == [removed]
    assert cleanup_plan.deleted_count == 1
    assert cleanup_plan.failed_count == 1
