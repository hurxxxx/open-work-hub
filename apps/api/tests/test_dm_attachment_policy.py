from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_alm_api.domains.dm.attachment_policy import (
    DEFAULT_ATTACHMENT_CONTENT_TYPE,
    DM_MAX_ATTACHMENT_SIZE,
    DmAttachmentPolicy,
    decide_dm_attachment_request_size,
    decide_dm_attachment_size,
    decide_dm_attachment_upload,
    dm_attachment_size_limit_mb,
    is_dm_attachment_request_size_allowed,
    is_dm_attachment_size_allowed,
    is_previewable_image_content_type,
    normalize_attachment_content_type,
    prepare_attachment_upload,
    safe_attachment_filename,
    sniff_attachment_content_type,
)


@pytest.mark.slow
def test_attachment_size_limit_matches_shared_dm_contract() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "open-alm-desktop"
        / "desktop-dm-api.manifest.json"
    )
    if not manifest_path.exists():
        pytest.skip("Open ALM desktop DM manifest is not present in this checkout.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert DM_MAX_ATTACHMENT_SIZE == manifest["maxAttachmentBytes"]
    assert dm_attachment_size_limit_mb() == 50


def test_attachment_size_policy_checks_payload_and_request_sizes() -> None:
    assert is_dm_attachment_size_allowed(1) is True
    assert is_dm_attachment_size_allowed(DM_MAX_ATTACHMENT_SIZE) is True
    assert is_dm_attachment_size_allowed(0) is False
    assert is_dm_attachment_size_allowed(DM_MAX_ATTACHMENT_SIZE + 1) is False
    assert is_dm_attachment_request_size_allowed(
        DM_MAX_ATTACHMENT_SIZE + 1024,
        overhead_bytes=1024,
    ) is True
    assert is_dm_attachment_request_size_allowed(
        DM_MAX_ATTACHMENT_SIZE + 1025,
        overhead_bytes=1024,
    ) is False


def test_attachment_size_decisions_expose_policy_limits() -> None:
    payload_decision = decide_dm_attachment_size(DM_MAX_ATTACHMENT_SIZE + 1)
    request_decision = decide_dm_attachment_request_size(
        DM_MAX_ATTACHMENT_SIZE + 1025,
        overhead_bytes=1024,
    )

    assert payload_decision.allowed is False
    assert payload_decision.max_size_bytes == DM_MAX_ATTACHMENT_SIZE
    assert request_decision.allowed is False
    assert request_decision.request_limit_bytes == DM_MAX_ATTACHMENT_SIZE + 1024


def test_safe_attachment_filename_strips_paths_and_unsafe_characters() -> None:
    assert safe_attachment_filename(r"C:\tmp\..\report?.png") == "report_.png"
    assert safe_attachment_filename("../../..") == "unnamed"
    assert safe_attachment_filename(None) == "unnamed"


def test_normalize_attachment_content_type_removes_parameters_and_rejects_invalid_values() -> None:
    assert normalize_attachment_content_type("Image/PNG; charset=binary") == "image/png"
    assert normalize_attachment_content_type("text/plain") == "text/plain"
    assert normalize_attachment_content_type("image/png\r\nx-evil: yes") == DEFAULT_ATTACHMENT_CONTENT_TYPE


def test_sniff_attachment_content_type_recognizes_previewable_images() -> None:
    assert sniff_attachment_content_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_attachment_content_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_attachment_content_type(b"GIF89arest") == "image/gif"
    assert sniff_attachment_content_type(b"RIFF\x00\x00\x00\x00WEBPrest") == "image/webp"
    assert sniff_attachment_content_type(b"<svg></svg>") is None


def test_prepare_attachment_upload_uses_sniffed_image_type() -> None:
    prepared = prepare_attachment_upload(
        filename="clipboard.bin",
        content_type="application/octet-stream",
        sniff_bytes=b"\x89PNG\r\n\x1a\nrest",
    )

    assert prepared.filename == "clipboard.bin"
    assert prepared.content_type == "image/png"
    assert prepared.is_previewable_image is True


def test_attachment_upload_decision_tracks_normalization_and_sniffing() -> None:
    decision = decide_dm_attachment_upload(
        filename=r"C:\tmp\spoof?.png",
        content_type="Image/PNG; charset=binary",
        sniff_bytes=b"not really an image",
    )

    assert decision.filename == "spoof_.png"
    assert decision.declared_content_type == "image/png"
    assert decision.sniffed_content_type is None
    assert decision.content_type == DEFAULT_ATTACHMENT_CONTENT_TYPE
    assert decision.is_previewable_image is False
    assert decision.downgraded_untrusted_declared_image is True


def test_attachment_policy_model_can_be_constructed_with_explicit_limits() -> None:
    policy = DmAttachmentPolicy(
        max_size_bytes=10,
        sniff_bytes=8,
        default_content_type=DEFAULT_ATTACHMENT_CONTENT_TYPE,
        previewable_image_content_types=frozenset({"image/png"}),
    )

    assert policy.size_limit_mb == 0
    assert policy.decide_payload_size(10).allowed is True
    assert policy.decide_payload_size(11).allowed is False
    assert policy.decide_request_size(11, overhead_bytes=1).allowed is True
    assert policy.prepare_upload_decision(
        filename=None,
        content_type="application/octet-stream",
        sniff_bytes=b"\x89PNG\r\n\x1a\nrest",
    ).content_type == "image/png"


def test_prepare_attachment_upload_downgrades_untrusted_image_headers() -> None:
    prepared = prepare_attachment_upload(
        filename="spoof.png",
        content_type="image/png",
        sniff_bytes=b"not really an image",
    )

    assert prepared.content_type == DEFAULT_ATTACHMENT_CONTENT_TYPE
    assert prepared.is_previewable_image is False
    assert is_previewable_image_content_type(prepared.content_type) is False
