"""Pure policy helpers for image generation reference images."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


VALID_REFERENCE_ROLES: tuple[str, ...] = ("style", "composition", "content")
ALLOWED_REFERENCE_CONTENT_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/webp",
)
REFERENCE_ORIGINAL_NAME_MAX_LENGTH = 200


def detect_reference_content_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_declared_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def is_allowed_declared_reference_content_type(content_type: str | None) -> bool:
    declared = normalize_declared_content_type(content_type)
    return (
        not declared
        or declared == "application/octet-stream"
        or declared in ALLOWED_REFERENCE_CONTENT_TYPES
    )


def build_reference_storage_key(generation_id: str, *, token: str | None = None) -> str:
    return f"images/refs/{generation_id}/{token or uuid4().hex}"


def build_reference_entry(
    *,
    storage_key: str,
    role: str,
    content_type: str,
    size_bytes: int,
    original_name: str,
) -> dict[str, Any]:
    return {
        "storage_key": storage_key,
        "role": role,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "original_name": original_name[:REFERENCE_ORIGINAL_NAME_MAX_LENGTH],
    }


@dataclass(frozen=True)
class ReferenceImagePolicy:
    generation_id: str
    workspace_id: str

    def reference_storage_key(self) -> str:
        return build_reference_storage_key(self.generation_id)

    def reference_entry(
        self,
        *,
        storage_key: str,
        role: str,
        content_type: str,
        size_bytes: int,
        original_name: str,
    ) -> dict[str, Any]:
        return build_reference_entry(
            storage_key=storage_key,
            role=role,
            content_type=content_type,
            size_bytes=size_bytes,
            original_name=original_name,
        )

    def is_owned_reference_key(self, key: str) -> bool:
        return key.startswith(f"images/refs/{self.generation_id}/")

    def is_owned_result_key(self, key: str) -> bool:
        return key == f"images/results/{self.workspace_id}/{self.generation_id}.png"

    def owned_reference_entries(self, refs: list[Any] | None) -> list[dict[str, Any]]:
        return [
            ref
            for ref in refs or []
            if isinstance(ref, dict)
            and isinstance(ref.get("storage_key"), str)
            and self.is_owned_reference_key(ref["storage_key"])
        ]

    def owned_reference_count(self, refs: list[Any] | None) -> int:
        return len(self.owned_reference_entries(refs))

    def owned_object_keys(
        self,
        refs: list[Any] | None,
        image_storage_key: str | None,
    ) -> list[str]:
        keys = [ref["storage_key"] for ref in self.owned_reference_entries(refs)]
        if image_storage_key and self.is_owned_result_key(image_storage_key):
            keys.append(image_storage_key)
        return keys
