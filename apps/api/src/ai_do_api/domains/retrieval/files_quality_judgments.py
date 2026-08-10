from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.files.models import FileManagerFile
from ai_do_api.domains.retrieval.evaluation import RetrievalQualityCorpus
from ai_do_api.domains.source_access import SourceAclPolicy
from ai_do_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


_ACL_BATCH_SIZE = 500


class FilesQualityJudgmentError(RuntimeError):
    """Stable failure raised when a Files quality judgment no longer matches source ACLs."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class FilesQualityJudgmentSnapshot:
    """Secret-free digest of every Files resource visible to each judged principal."""

    acl_sha256: str
    context_count: int
    active_resource_count: int


SessionFactory = Callable[[], Session]
SourceAclPolicyFactory = Callable[[Session, Workspace, User], SourceAclPolicy]


def validate_files_quality_judgments(
    *,
    corpus: RetrievalQualityCorpus,
    session_factory: SessionFactory,
    source_acl_policy_factory: SourceAclPolicyFactory | None = None,
) -> FilesQualityJudgmentSnapshot:
    """Validate judged labels and fingerprint each principal's complete Files ACL view.

    The corpus bytes bind queries and labels.  This digest additionally binds the
    effective keyword and RAG candidate universe, so membership or scope changes
    cannot silently reuse stale evaluation evidence.
    """

    policy_factory = source_acl_policy_factory or _source_acl_policy
    cases_by_context: dict[tuple[str, str], list] = {}
    for case in corpus.cases:
        if not case.forbidden_resource_ids:
            raise FilesQualityJudgmentError("quality_judgment_forbidden_required")
        cases_by_context.setdefault((case.workspace_id, case.user_id), []).append(case)

    context_evidence: list[dict[str, object]] = []
    active_resource_count: int | None = None
    for (workspace_id, user_id), cases in sorted(cases_by_context.items()):
        try:
            with session_factory() as db:
                workspace = db.get(Workspace, workspace_id)
                user = db.get(User, user_id)
                if workspace is None or not workspace.active:
                    raise FilesQualityJudgmentError("evaluation_context_unavailable")
                if user is None or user.status != "active" or user.login_blocked:
                    raise FilesQualityJudgmentError("evaluation_context_unavailable")

                active_ids = tuple(
                    sorted(
                        str(resource_id)
                        for resource_id in db.scalars(
                            select(FileManagerFile.id).where(FileManagerFile.deleted_at.is_(None))
                        )
                    )
                )
                if active_resource_count is None:
                    active_resource_count = len(active_ids)
                elif active_resource_count != len(active_ids):
                    raise FilesQualityJudgmentError("quality_source_changed_during_validation")

                policy = policy_factory(db, workspace, user)
                workspace_role = getattr(policy, "workspace_role", None)
                if not isinstance(workspace_role, str) or not workspace_role.strip():
                    raise FilesQualityJudgmentError("evaluation_context_unavailable")
                keyword_allowed = _authorize_all(policy, active_ids, rag=False)
                rag_allowed = _authorize_all(policy, active_ids, rag=True)
                active_set = set(active_ids)
                for case in cases:
                    relevant = set(case.relevant_resource_ids)
                    forbidden = set(case.forbidden_resource_ids)
                    judged = relevant | forbidden
                    if not judged.issubset(active_set):
                        raise FilesQualityJudgmentError("quality_judgment_resource_missing")
                    if not relevant.issubset(keyword_allowed) or not relevant.issubset(rag_allowed):
                        raise FilesQualityJudgmentError("quality_judgment_relevant_not_authorized")
                    if forbidden & keyword_allowed or forbidden & rag_allowed:
                        raise FilesQualityJudgmentError("quality_judgment_forbidden_authorized")

                context_evidence.append(
                    {
                        "workspace_id": workspace_id,
                        "user_id": user_id,
                        "workspace_active": bool(workspace.active),
                        "user_status": str(user.status),
                        "user_login_blocked": bool(user.login_blocked),
                        "user_is_admin": bool(getattr(user, "is_admin", False)),
                        "workspace_role": workspace_role.strip().lower(),
                        "active_resource_count": len(active_ids),
                        "active_resource_sha256": _ids_sha256(active_ids),
                        "keyword_allowed_count": len(keyword_allowed),
                        "keyword_allowed_sha256": _ids_sha256(keyword_allowed),
                        "rag_allowed_count": len(rag_allowed),
                        "rag_allowed_sha256": _ids_sha256(rag_allowed),
                    }
                )
        except FilesQualityJudgmentError:
            raise
        except Exception as error:
            raise FilesQualityJudgmentError("quality_judgment_validation_failed") from error

    canonical = json.dumps(
        context_evidence,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return FilesQualityJudgmentSnapshot(
        acl_sha256=hashlib.sha256(canonical).hexdigest(),
        context_count=len(context_evidence),
        active_resource_count=active_resource_count or 0,
    )


def _authorize_all(
    policy: SourceAclPolicy,
    resource_ids: tuple[str, ...],
    *,
    rag: bool,
) -> set[str]:
    allowed: set[str] = set()
    for offset in range(0, len(resource_ids), _ACL_BATCH_SIZE):
        identities = tuple(
            (FILE_MANAGER_FILE_RESOURCE_TYPE, resource_id)
            for resource_id in resource_ids[offset : offset + _ACL_BATCH_SIZE]
        )
        allowed.update(
            resource_id
            for _resource_type, resource_id in policy.authorize_many_resources(
                identities,
                rag=rag,
            )
        )
    return allowed


def _ids_sha256(resource_ids) -> str:
    canonical = json.dumps(
        sorted(str(resource_id) for resource_id in resource_ids),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _source_acl_policy(
    db: Session,
    workspace: Workspace,
    user: User,
) -> SourceAclPolicy:
    return SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)


__all__ = [
    "FilesQualityJudgmentError",
    "FilesQualityJudgmentSnapshot",
    "validate_files_quality_judgments",
]
