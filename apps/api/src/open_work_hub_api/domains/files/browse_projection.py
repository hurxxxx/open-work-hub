from __future__ import annotations

from datetime import datetime
from typing import Mapping

from pydantic import BaseModel

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.files.models import FileManagerFile, FileManagerFolder
from open_work_hub_api.domains.files.rag_status import FileRagState, FileRagStatus


class FileFolderItem(BaseModel):
    id: str
    corpus_id: str | None
    parent_id: str | None
    name: str
    visibility: str
    owner_id: str
    owner_name: str
    can_manage: bool
    created_at: datetime
    updated_at: datetime


class FileItem(BaseModel):
    id: str
    corpus_id: str | None
    folder_id: str | None
    filename: str
    content_type: str
    size_bytes: int
    visibility: str
    owner_id: str
    owner_name: str
    can_delete: bool
    rag_status: FileRagStatus
    rag_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FileBrowseResponse(BaseModel):
    current_folder: FileFolderItem | None
    breadcrumbs: list[FileFolderItem]
    folders: list[FileFolderItem]
    files: list[FileItem]
    all_folders: list[FileFolderItem]


def build_file_browse_response(
    *,
    folders: list[FileManagerFolder],
    files: list[FileManagerFile],
    folder_id: str | None,
    user: User,
    is_admin: bool,
    rag_states: Mapping[str, FileRagState],
) -> FileBrowseResponse:
    folder_items = [
        serialize_folder_item(folder, user=user, is_admin=is_admin) for folder in folders
    ]
    folder_item_by_id = {folder.id: folder for folder in folder_items}
    return FileBrowseResponse(
        current_folder=folder_item_by_id.get(folder_id) if folder_id else None,
        breadcrumbs=[
            serialize_folder_item(folder, user=user, is_admin=is_admin)
            for folder in folder_breadcrumbs(folders, folder_id)
        ],
        folders=[
            serialize_folder_item(folder, user=user, is_admin=is_admin)
            for folder in folders
            if folder.parent_id == folder_id
        ],
        files=[
            serialize_file_item(
                file,
                user=user,
                is_admin=is_admin,
                rag_state=rag_states[file.id],
            )
            for file in files
            if file.folder_id == folder_id
        ],
        all_folders=folder_items,
    )


def serialize_folder_item(
    folder: FileManagerFolder,
    *,
    user: User,
    is_admin: bool,
) -> FileFolderItem:
    return FileFolderItem(
        id=folder.id,
        corpus_id=folder.corpus_id,
        parent_id=folder.parent_id,
        name=folder.name,
        visibility=folder.visibility,
        owner_id=folder.owner_id,
        owner_name=_owner_name(folder),
        can_manage=folder.owner_id == user.id,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def serialize_file_item(
    file: FileManagerFile,
    *,
    user: User,
    is_admin: bool,
    rag_state: FileRagState,
) -> FileItem:
    return FileItem(
        id=file.id,
        corpus_id=file.corpus_id,
        folder_id=file.folder_id,
        filename=file.filename,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        visibility=file.visibility,
        owner_id=file.owner_id,
        owner_name=_owner_name(file),
        can_delete=file.owner_id == user.id,
        rag_status=rag_state.status,
        rag_updated_at=rag_state.updated_at,
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


def folder_breadcrumbs(
    folders: list[FileManagerFolder],
    current_folder_id: str | None,
) -> list[FileManagerFolder]:
    if current_folder_id is None:
        return []
    by_id = {folder.id: folder for folder in folders}
    chain: list[FileManagerFolder] = []
    cursor = by_id.get(current_folder_id)
    seen: set[str] = set()
    while cursor is not None and cursor.id not in seen:
        seen.add(cursor.id)
        chain.append(cursor)
        cursor = by_id.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def _owner_name(row: FileManagerFile | FileManagerFolder) -> str:
    if row.owner is None:
        return ""
    return row.owner.display_name or row.owner.full_name
