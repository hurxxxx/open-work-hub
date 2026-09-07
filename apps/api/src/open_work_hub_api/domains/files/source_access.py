from __future__ import annotations

from sqlalchemy import select

from open_work_hub_api.domains.auth.access import workspace_role_allows
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.external_access import (
    authorize_explicit_file_ids,
    has_any_explicit_file_access,
)
from open_work_hub_api.domains.files.models import FileManagerCorpus, FileManagerFile
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    FILES_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.retrieval.partition_adapter_registry import bind_model_partition
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


def can_read_file(policy, file_id: str) -> bool:
    file = policy.db.scalar(
        select(FileManagerFile).where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    if file is None:
        return False
    if file.corpus_id is not None:
        corpus = policy.db.get(FileManagerCorpus, file.corpus_id)
        if corpus is None:
            return False
        if not _corpus_scope_allows(policy, corpus):
            return False
        if corpus.authorization_mode == "explicit_grants":
            return file.id in authorize_explicit_file_ids(
                policy.db,
                file_ids=(file.id,),
                user_id=policy.user.id,
                workspace_id=policy.workspace.id if policy.workspace is not None else None,
            )
        # A corpus is one security cohort. Its source-owned ACL intentionally
        # overrides legacy child visibility and folder ACL fields.
        return True
    elif policy.workspace is None or file.workspace_id != policy.workspace.id:
        return False
    if workspace_role_allows(policy.workspace_role, "admin"):
        return True
    if file.owner_id != policy.user.id and file.visibility != "workspace":
        return False
    if file.folder_id is None:
        return True
    accessible_folder_ids = {
        folder.id
        for folder in files_service.list_accessible_folders(
            policy.db,
            workspace=policy.workspace,
            user=policy.user,
        )
    }
    return file.folder_id in accessible_folder_ids


def has_accessible_file(policy) -> bool:
    corpus_scope_clause = FileManagerCorpus.access_scope_kind == "company"
    if policy.workspace is not None:
        corpus_scope_clause = corpus_scope_clause | (
            (FileManagerCorpus.access_scope_kind == "workspace")
            & (FileManagerCorpus.managed_workspace_id == policy.workspace.id)
        )
    corpus_file_id = policy.db.scalar(
        select(FileManagerFile.id)
        .join(FileManagerCorpus, FileManagerCorpus.id == FileManagerFile.corpus_id)
        .where(
            FileManagerCorpus.authorization_mode == "cohort",
            corpus_scope_clause,
            FileManagerFile.deleted_at.is_(None),
        )
        .limit(1)
    )
    if corpus_file_id is not None:
        return True
    if has_any_explicit_file_access(
        policy.db,
        user_id=policy.user.id,
        workspace_id=policy.workspace.id if policy.workspace is not None else None,
    ):
        return True
    if policy.workspace is None:
        return False
    accessible_folder_ids = {
        folder.id
        for folder in files_service.list_accessible_folders(
            policy.db,
            workspace=policy.workspace,
            user=policy.user,
        )
    }
    return bool(
        files_service.list_accessible_files(
            policy.db,
            workspace=policy.workspace,
            user=policy.user,
            accessible_folder_ids=accessible_folder_ids,
        )
    )


def authorize_many_files(policy, file_ids) -> set[str]:
    """Authorize a candidate page with a bounded number of source queries."""

    normalized_ids = tuple(dict.fromkeys(str(file_id) for file_id in file_ids if file_id))
    if not normalized_ids:
        return set()
    files = list(
        policy.db.scalars(
            select(FileManagerFile).where(
                FileManagerFile.id.in_(normalized_ids),
                FileManagerFile.deleted_at.is_(None),
            )
        )
    )
    corpus_ids = {file.corpus_id for file in files if file.corpus_id is not None}
    corpora = (
        {
            corpus.id: corpus
            for corpus in policy.db.scalars(
                select(FileManagerCorpus).where(FileManagerCorpus.id.in_(corpus_ids))
            )
        }
        if corpus_ids
        else {}
    )
    accessible_folder_ids: set[str] | None = None
    is_admin = bool(
        policy.workspace is not None and workspace_role_allows(policy.workspace_role, "admin")
    )
    allowed: set[str] = set()
    explicit_file_ids: list[str] = []
    for file in files:
        if file.corpus_id is not None:
            corpus = corpora.get(file.corpus_id)
            if corpus is None:
                continue
            if not _corpus_scope_allows(policy, corpus):
                continue
            if corpus.authorization_mode == "explicit_grants":
                explicit_file_ids.append(file.id)
            else:
                allowed.add(file.id)
            continue
        if policy.workspace is None or file.workspace_id != policy.workspace.id:
            continue
        if not is_admin and file.owner_id != policy.user.id and file.visibility != "workspace":
            continue
        if file.folder_id is not None:
            if accessible_folder_ids is None:
                accessible_folder_ids = {
                    folder.id
                    for folder in files_service.list_accessible_folders(
                        policy.db,
                        workspace=policy.workspace,
                        user=policy.user,
                    )
                }
            if file.folder_id not in accessible_folder_ids:
                continue
        allowed.add(file.id)
    allowed.update(
        authorize_explicit_file_ids(
            policy.db,
            file_ids=explicit_file_ids,
            user_id=policy.user.id,
            workspace_id=policy.workspace.id if policy.workspace is not None else None,
        )
    )
    return allowed


def _corpus_scope_allows(policy, corpus: FileManagerCorpus) -> bool:
    if corpus.access_scope_kind == "company":
        return True
    return bool(
        policy.workspace is not None
        and corpus.access_scope_kind == "workspace"
        and corpus.managed_workspace_id == policy.workspace.id
    )


class FileManagerSourceAccessAdapter:
    app_id = "files"
    adapter_id = FILES_RETRIEVAL_PARTITION_ADAPTER_ID
    partition_adapter_id = FILES_RETRIEVAL_PARTITION_ADAPTER_ID
    source_namespace = "files"
    resource_types = (FILE_MANAGER_FILE_RESOURCE_TYPE,)
    allowed_candidate_scopes = ("workspace", "company")
    allowed_transitions = ("corpus_scope_change", "corpus_workspace_transfer")
    transition_mode = "source_owned"
    keyword_acl_entity_types = ("file",)

    def bind_resource_partition(
        self,
        db,
        *,
        resource_type: str,
        resource_id: str,
    ):
        return bind_model_partition(
            db,
            model=FileManagerFile,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def can_read_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_file(policy, resource_id)

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del resource_type
        return can_read_file(policy, resource_id)

    def authorize_many_resources(
        self,
        policy,
        *,
        resource_type: str,
        resource_ids,
    ) -> set[str]:
        del resource_type
        return authorize_many_files(policy, resource_ids)

    def authorize_many_rag_resources(
        self,
        policy,
        *,
        resource_type: str,
        resource_ids,
    ) -> set[str]:
        del resource_type
        return authorize_many_files(policy, resource_ids)

    def has_accessible_source(
        self,
        policy,
        *,
        resource_type: str,
    ) -> bool:
        del resource_type
        return has_accessible_file(policy)

    def keyword_acl_branches(self, policy):
        clauses = [policy._keyword_acl_clause("owner_user_id", policy.user.id)]
        if workspace_role_allows(policy.workspace_role, "admin"):
            clauses.append(policy._keyword_acl_clause("visibility", ["private", "workspace"]))
        elif policy.workspace_role is not None:
            clauses.append(policy._keyword_acl_clause("visibility", "workspace"))
        return [policy._keyword_entity_branch("file", clauses)]


__all__ = [
    "FILES_RETRIEVAL_PARTITION_ADAPTER_ID",
    "FileManagerSourceAccessAdapter",
    "authorize_many_files",
    "can_read_file",
    "has_accessible_file",
]
