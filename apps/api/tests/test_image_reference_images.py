from __future__ import annotations

from open_work_hub_api.domains.images.reference_images import (
    REFERENCE_ORIGINAL_NAME_MAX_LENGTH,
    ReferenceImagePolicy,
    build_reference_entry,
    build_reference_storage_key,
    detect_reference_content_type,
    is_allowed_declared_reference_content_type,
    normalize_declared_content_type,
)


def test_detect_reference_content_type_from_magic_bytes() -> None:
    assert detect_reference_content_type(b"\x89PNG\r\n\x1a\npayload") == "image/png"
    assert detect_reference_content_type(b"\xff\xd8\xffpayload") == "image/jpeg"
    assert detect_reference_content_type(b"RIFF1234WEBPpayload") == "image/webp"
    assert detect_reference_content_type(b"not an image") is None


def test_declared_reference_content_type_policy_preserves_upload_contract() -> None:
    assert normalize_declared_content_type(" Image/PNG ; charset=utf-8") == "image/png"

    assert is_allowed_declared_reference_content_type(None)
    assert is_allowed_declared_reference_content_type("")
    assert is_allowed_declared_reference_content_type("application/octet-stream")
    assert is_allowed_declared_reference_content_type("image/jpeg; charset=binary")
    assert not is_allowed_declared_reference_content_type("text/plain")
    assert not is_allowed_declared_reference_content_type("application/pdf")


def test_reference_image_policy_identifies_owned_reference_and_result_keys() -> None:
    policy = ReferenceImagePolicy(generation_id="generation-1", workspace_id="workspace-1")

    assert policy.is_owned_reference_key("images/refs/generation-1/ref-a")
    assert not policy.is_owned_reference_key("images/refs/generation-2/ref-a")
    assert policy.is_owned_result_key("images/results/workspace-1/generation-1.png")
    assert not policy.is_owned_result_key("images/results/workspace-2/generation-1.png")


def test_reference_image_policy_collects_only_owned_reference_entries_and_objects() -> None:
    policy = ReferenceImagePolicy(generation_id="generation-1", workspace_id="workspace-1")
    owned_ref = {"storage_key": "images/refs/generation-1/ref-a", "role": "style"}
    external_ref = {"storage_key": "images/refs/generation-2/ref-b", "role": "style"}
    malformed_ref = {"storage_key": 123, "role": "style"}
    refs = [owned_ref, external_ref, malformed_ref, "ignored"]

    assert policy.owned_reference_entries(refs) == [owned_ref]
    assert policy.owned_reference_count(refs) == 1
    assert policy.owned_object_keys(
        refs,
        "images/results/workspace-1/generation-1.png",
    ) == [
        "images/refs/generation-1/ref-a",
        "images/results/workspace-1/generation-1.png",
    ]
    assert policy.owned_object_keys(
        refs,
        "images/results/workspace-2/generation-1.png",
    ) == ["images/refs/generation-1/ref-a"]


def test_reference_storage_key_and_entry_builders_preserve_shape() -> None:
    storage_key = build_reference_storage_key("generation-1", token="fixed-token")
    long_name = "a" * (REFERENCE_ORIGINAL_NAME_MAX_LENGTH + 1)

    assert storage_key == "images/refs/generation-1/fixed-token"
    assert build_reference_entry(
        storage_key=storage_key,
        role="composition",
        content_type="image/webp",
        size_bytes=123,
        original_name=long_name,
    ) == {
        "storage_key": storage_key,
        "role": "composition",
        "content_type": "image/webp",
        "size_bytes": 123,
        "original_name": "a" * REFERENCE_ORIGINAL_NAME_MAX_LENGTH,
    }
