from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import JsonValue

from open_alm_api.domains.mcloudoc.contracts import ResolvedGrant


@dataclass(frozen=True, slots=True)
class FilesUpsertCommand:
    source_id: str
    document_id: str
    existing_file_id: str | None
    scope_type: str
    scope_id: str
    corpus_id: str
    ingest_owner_id: str
    external_id: str
    opaque_revision: str | None
    checksum: str
    filename: str
    content_type: str
    content: bytes
    title: str | None
    author: str | None
    authored_at: datetime | None
    department: str | None
    document_type: str | None
    source_updated_at: datetime | None
    source_uri: str | None
    raw_metadata: dict[str, JsonValue]
    resolved_grants: tuple[ResolvedGrant, ...]


@dataclass(frozen=True, slots=True)
class FilesUpsertResult:
    file_id: str
    changed: bool
    acl_resolved: bool = True


class FilesIngressPort(Protocol):
    """Transactional port; implementations must join the caller's unit of work."""

    def upsert(self, command: FilesUpsertCommand) -> FilesUpsertResult: ...

    def delete(self, *, file_id: str, reason: str) -> bool: ...

    def quarantine(self, *, file_id: str, reason: str) -> bool: ...
