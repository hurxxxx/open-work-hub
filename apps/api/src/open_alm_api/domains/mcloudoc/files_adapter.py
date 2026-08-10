from __future__ import annotations

from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import User
from open_alm_api.domains.files.external_lifecycle import (
    ExternalFileGrant,
    delete_external_file,
    quarantine_external_file,
    upsert_external_file,
)
from open_alm_api.domains.files.models import FileManagerCorpus
from open_alm_api.domains.mcloudoc.models import McloudocDocument, McloudocSource
from open_alm_api.domains.mcloudoc.ports import FilesUpsertCommand, FilesUpsertResult


class McloudocFilesAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SqlAlchemyMcloudocFilesIngress:
    """Source-bound transactional adapter into the canonical Files lifecycle."""

    def __init__(self, db: Session, *, source_id: str) -> None:
        self.db = db
        self.source_id = source_id

    def upsert(self, command: FilesUpsertCommand) -> FilesUpsertResult:
        source, corpus, actor = self._binding()
        self._require_command_binding(command, source=source)
        result = upsert_external_file(
            self.db,
            actor=actor,
            corpus_id=corpus.id,
            external_id=command.external_id,
            source_kind="mcloudoc",
            # This is the stable source-document identity. The connector source
            # itself is represented by McloudocSource and may own many documents.
            source_id=command.document_id,
            expected_file_id=command.existing_file_id,
            filename=command.filename,
            content_type=command.content_type,
            content=BytesIO(command.content),
            size_bytes=len(command.content),
            grants=tuple(
                ExternalFileGrant(
                    grant_type=grant.principal_type,
                    target_id=grant.principal_id,
                )
                for grant in command.resolved_grants
            ),
            acl_resolved=True,
            source_version=command.opaque_revision,
            source_uri=command.source_uri,
            source_updated_at=command.source_updated_at,
            title=command.title,
            author=command.author,
            authored_at=command.authored_at,
            department=command.department,
            document_type=command.document_type,
            raw_metadata=command.raw_metadata,
        )
        return FilesUpsertResult(
            file_id=result.file.id,
            changed=result.changed,
            acl_resolved=result.acl_resolved,
        )

    def delete(self, *, file_id: str, reason: str) -> bool:
        del reason  # The canonical Files lifecycle owns durable deletion diagnostics.
        source, corpus, actor = self._binding()
        self._require_owned_file(source=source, file_id=file_id)
        return delete_external_file(
            self.db,
            actor=actor,
            corpus_id=corpus.id,
            file_id=file_id,
        ).changed

    def quarantine(self, *, file_id: str, reason: str) -> bool:
        del reason  # The mcloudoc document ledger retains the quarantine reason.
        source, corpus, actor = self._binding()
        self._require_owned_file(source=source, file_id=file_id)
        return quarantine_external_file(
            self.db,
            actor=actor,
            corpus_id=corpus.id,
            file_id=file_id,
        )

    def _binding(self) -> tuple[McloudocSource, FileManagerCorpus, User]:
        source = self.db.get(McloudocSource, self.source_id)
        if source is None:
            raise McloudocFilesAdapterError("source_not_found")
        if not source.enabled:
            raise McloudocFilesAdapterError("source_inactive")
        corpus = self.db.get(FileManagerCorpus, source.corpus_id)
        if (
            corpus is None
            or not corpus.source_managed
            or corpus.authorization_mode != "explicit_grants"
            or corpus.access_scope_kind != source.scope_type
        ):
            raise McloudocFilesAdapterError("source_corpus_binding_invalid")
        if source.scope_type == "workspace" and corpus.managed_workspace_id != source.scope_id:
            raise McloudocFilesAdapterError("source_workspace_binding_invalid")
        actor = self.db.get(User, source.ingest_owner_id)
        if actor is None:
            raise McloudocFilesAdapterError("source_ingest_owner_missing")
        return source, corpus, actor

    def _require_command_binding(
        self,
        command: FilesUpsertCommand,
        *,
        source: McloudocSource,
    ) -> None:
        if (
            command.source_id != source.id
            or command.scope_type != source.scope_type
            or command.scope_id != source.scope_id
            or command.corpus_id != source.corpus_id
            or command.ingest_owner_id != source.ingest_owner_id
        ):
            raise McloudocFilesAdapterError("source_command_binding_mismatch")
        document = self.db.get(McloudocDocument, command.document_id)
        if (
            document is None
            or document.source_id != source.id
            or document.external_id != command.external_id
            or document.file_id != command.existing_file_id
        ):
            raise McloudocFilesAdapterError("source_document_binding_mismatch")

    def _require_owned_file(self, *, source: McloudocSource, file_id: str) -> None:
        document_id = self.db.scalar(
            select(McloudocDocument.id).where(
                McloudocDocument.source_id == source.id,
                McloudocDocument.file_id == file_id,
            )
        )
        if document_id is None:
            raise McloudocFilesAdapterError("source_file_binding_mismatch")


__all__ = [
    "McloudocFilesAdapterError",
    "SqlAlchemyMcloudocFilesIngress",
]
