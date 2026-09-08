from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

from open_work_hub_api.open_work_hub_desktop_update_manifest import (
    DesktopUpdateManifestProjection,
    open_work_hub_desktop_update_manifest_projection,
)


@dataclass(frozen=True)
class DesktopUpdateAttachmentHeaders:
    content_disposition: str
    content_type: str


@dataclass(frozen=True)
class DesktopUpdateServingPolicy:
    platforms: tuple[str, ...]
    feed_path_prefix: str
    metadata_files: Mapping[str, str]
    artifact_suffixes: Mapping[str, frozenset[str]]
    attachment_suffixes: Mapping[str, frozenset[str]]
    content_types: Mapping[str, str]

    @classmethod
    def from_manifest(
        cls,
        manifest: DesktopUpdateManifestProjection | None = None,
    ) -> "DesktopUpdateServingPolicy":
        resolved_manifest = manifest or open_work_hub_desktop_update_manifest_projection()
        return cls(
            platforms=resolved_manifest.platforms,
            feed_path_prefix=resolved_manifest.feed_path_prefix,
            metadata_files=resolved_manifest.metadata_files,
            artifact_suffixes=resolved_manifest.artifact_suffixes,
            attachment_suffixes=resolved_manifest.attachment_suffixes,
            content_types=resolved_manifest.served_artifact_content_types,
        )

    def update_dirs(self, configured_dirs: Mapping[str, str]) -> dict[str, Path]:
        return {
            platform: Path(configured_dirs[platform]).expanduser() for platform in self.platforms
        }

    def is_allowed_file_path(self, platform: str, path: str) -> bool:
        if not path or "/" in path or "\\" in path:
            return False
        metadata_file = self.metadata_files.get(platform)
        if metadata_file is None:
            return False

        file_name = Path(path).name
        if not _is_safe_public_file_name(file_name):
            return False
        suffix = Path(file_name).suffix.lower()
        if suffix == ".yml":
            return file_name == metadata_file
        return suffix in self.artifact_suffixes.get(platform, frozenset())

    def attachment_headers(
        self,
        platform: str,
        path: str,
    ) -> DesktopUpdateAttachmentHeaders | None:
        if not self.is_allowed_file_path(platform, path):
            return None

        file_name = Path(path).name
        suffix = Path(file_name).suffix.lower()
        if suffix not in self.attachment_suffixes.get(platform, frozenset()):
            return None

        content_type = self.content_types.get(suffix)
        if content_type is None:
            return None

        safe_file_name = safe_header_file_name(file_name)
        encoded_file_name = quote(file_name, safe="")
        return DesktopUpdateAttachmentHeaders(
            content_disposition=(
                f"attachment; filename=\"{safe_file_name}\"; filename*=UTF-8''{encoded_file_name}"
            ),
            content_type=content_type,
        )


def open_work_hub_desktop_update_serving_policy() -> DesktopUpdateServingPolicy:
    return DesktopUpdateServingPolicy.from_manifest()


def _is_safe_public_file_name(file_name: str) -> bool:
    return (
        file_name not in {"", ".", ".."}
        and not file_name.startswith(".")
        and not any(ord(character) < 32 or ord(character) == 127 for character in file_name)
    )


def safe_header_file_name(file_name: str) -> str:
    return "".join(
        "_"
        if character in {'"', "\\"} or ord(character) < 32 or ord(character) == 127
        else character
        for character in file_name
    )
