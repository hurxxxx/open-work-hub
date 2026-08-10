from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"|?*/\\]+')
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:+")


@dataclass(frozen=True)
class ArchivePlanFolder:
    id: str
    parent_id: str | None
    name: str


@dataclass(frozen=True)
class ArchivePlanFile:
    id: str
    folder_id: str | None
    filename: str


@dataclass(frozen=True)
class PlannedArchiveEntry:
    archive_path: str
    file_id: str | None


def safe_filename(value: str | None) -> str:
    raw = str(value or "unnamed").strip()
    raw = raw.replace("\\", "/")
    filename = raw.rsplit("/", 1)[-1].strip()
    filename = _WINDOWS_DRIVE_PREFIX.sub("", filename).strip()
    filename = _UNSAFE_FILENAME_CHARS.sub("_", filename).strip(" .")
    if not filename:
        return "unnamed"
    if filename in {".", ".."}:
        return "unnamed"
    return filename[:512]


def plan_archive_entries(
    *,
    selected_folder_ids: set[str],
    folders: Sequence[ArchivePlanFolder],
    folder_files: Sequence[ArchivePlanFile],
    selected_files: Sequence[ArchivePlanFile],
    sanitize_name: Callable[[str | None], str] = safe_filename,
) -> list[PlannedArchiveEntry]:
    entries: list[PlannedArchiveEntry] = []
    used_paths: set[str] = set()
    included_file_ids: set[str] = set()
    folder_by_id = {folder.id: folder for folder in folders}

    if selected_folder_ids:
        files_by_folder: dict[str | None, list[ArchivePlanFile]] = defaultdict(list)
        for file in folder_files:
            files_by_folder[file.folder_id].append(file)

        for folder_id in sorted(
            selected_folder_ids,
            key=lambda value: _folder_archive_path(folder_by_id, value, sanitize_name).lower(),
        ):
            root_path = _folder_archive_path(folder_by_id, folder_id, sanitize_name)
            entries.append(
                PlannedArchiveEntry(
                    _unique_archive_path(used_paths, root_path, is_dir=True),
                    None,
                )
            )
            for child_folder in _archive_folder_descendants(folders, folder_id, sanitize_name):
                folder_path = _folder_archive_path(folder_by_id, child_folder.id, sanitize_name)
                entries.append(
                    PlannedArchiveEntry(
                        _unique_archive_path(used_paths, folder_path, is_dir=True),
                        None,
                    )
                )
            folder_ids_in_tree = _archive_folder_ids(folders, folder_id)
            for file in sorted(
                [
                    file
                    for tree_folder_id in folder_ids_in_tree
                    for file in files_by_folder.get(tree_folder_id, [])
                ],
                key=lambda item: (
                    _folder_archive_path(folder_by_id, item.folder_id, sanitize_name).lower(),
                    item.filename.lower(),
                ),
            ):
                folder_path = _folder_archive_path(folder_by_id, file.folder_id, sanitize_name)
                path = f"{folder_path}/{sanitize_name(file.filename)}"
                entries.append(
                    PlannedArchiveEntry(_unique_archive_path(used_paths, path), file.id)
                )
                included_file_ids.add(file.id)

    for file in selected_files:
        if file.id in included_file_ids:
            continue
        entries.append(
            PlannedArchiveEntry(
                _unique_archive_path(used_paths, sanitize_name(file.filename)),
                file.id,
            )
        )
        included_file_ids.add(file.id)

    return entries


def _archive_folder_ids(folders: Sequence[ArchivePlanFolder], root_id: str) -> set[str]:
    children_by_parent: dict[str | None, list[ArchivePlanFolder]] = defaultdict(list)
    for folder in folders:
        children_by_parent[folder.parent_id].append(folder)
    ids: set[str] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in ids:
            continue
        ids.add(current)
        stack.extend(child.id for child in children_by_parent.get(current, []))
    return ids


def _archive_folder_descendants(
    folders: Sequence[ArchivePlanFolder],
    root_id: str,
    sanitize_name: Callable[[str | None], str],
) -> list[ArchivePlanFolder]:
    folder_by_id = {folder.id: folder for folder in folders}
    descendant_ids = _archive_folder_ids(folders, root_id) - {root_id}
    return sorted(
        [folder_by_id[folder_id] for folder_id in descendant_ids if folder_id in folder_by_id],
        key=lambda folder: _folder_archive_path(folder_by_id, folder.id, sanitize_name).lower(),
    )


def _folder_archive_path(
    folder_by_id: dict[str, ArchivePlanFolder],
    folder_id: str | None,
    sanitize_name: Callable[[str | None], str],
) -> str:
    if folder_id is None:
        return ""
    segments: list[str] = []
    seen: set[str] = set()
    cursor = folder_by_id.get(folder_id)
    while cursor is not None and cursor.id not in seen:
        seen.add(cursor.id)
        segments.append(sanitize_name(cursor.name))
        cursor = folder_by_id.get(cursor.parent_id) if cursor.parent_id else None
    return "/".join(reversed(segments))


def ensure_directory_path(path: str) -> str:
    return path.rstrip("/") + "/"


def _unique_archive_path(
    used_paths: set[str],
    path: str,
    *,
    is_dir: bool = False,
) -> str:
    normalized = ensure_directory_path(path) if is_dir else path
    if normalized not in used_paths:
        used_paths.add(normalized)
        return normalized

    suffix = 2
    base_path = normalized.rstrip("/") if is_dir else normalized
    stem = Path(base_path).stem
    extension = Path(base_path).suffix
    parent = str(Path(base_path).parent)
    parent_prefix = "" if parent == "." else f"{parent}/"
    while True:
        candidate = f"{parent_prefix}{stem} ({suffix}){extension}"
        normalized_candidate = ensure_directory_path(candidate) if is_dir else candidate
        if normalized_candidate not in used_paths:
            used_paths.add(normalized_candidate)
            return normalized_candidate
        suffix += 1
