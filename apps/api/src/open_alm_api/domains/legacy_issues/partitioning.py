from __future__ import annotations

from sqlalchemy.orm import Session

from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAiChunk,
    LegacyIssueAttachment,
    LegacyIssueAttachmentIndexJob,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from open_alm_api.domains.retrieval.partitioning import assign_default_partition


class LegacyIssuePartitionMismatch(RuntimeError):
    pass


def ensure_revision_partition(
    db: Session,
    revision: LegacyIssueDataRevision,
) -> str:
    base_revision_id = getattr(revision, "base_revision_id", None)
    if base_revision_id:
        base_revision = db.get(LegacyIssueDataRevision, base_revision_id)
        if base_revision is None:
            raise LegacyIssuePartitionMismatch(
                f"legacy issue base revision is missing: {base_revision_id}"
            )
        partition_id = ensure_revision_partition(db, base_revision)
        _inherit_partition(revision, partition_id, parent="base revision")
        return partition_id
    return str(
        assign_default_partition(
            db,
            target=revision,
            source_namespace="legacy_issues",
            candidate_scope_kind="workspace",
            workspace_id=revision.workspace_id,
        )
    )


def ensure_record_partition(
    db: Session,
    record: LegacyIssueRecord,
    *,
    revision: LegacyIssueDataRevision | None = None,
) -> str:
    resolved_revision = revision
    if resolved_revision is None and record.revision_id:
        resolved_revision = db.get(LegacyIssueDataRevision, record.revision_id)
    if resolved_revision is None:
        raise LegacyIssuePartitionMismatch(
            f"legacy issue record requires a revision binding: {record.id}"
        )
    _require_same_workspace(record, resolved_revision, child="record")
    partition_id = ensure_revision_partition(db, resolved_revision)
    _inherit_partition(record, partition_id, parent="revision")
    return partition_id


def ensure_attachment_partition(
    db: Session,
    attachment: LegacyIssueAttachment,
    *,
    record: LegacyIssueRecord | None = None,
) -> str:
    resolved_record = record or db.get(LegacyIssueRecord, attachment.record_id)
    if resolved_record is None:
        raise LegacyIssuePartitionMismatch(
            f"legacy issue attachment record is missing: {attachment.record_id}"
        )
    _require_same_workspace(attachment, resolved_record, child="attachment")
    partition_id = ensure_record_partition(db, resolved_record)
    _inherit_partition(attachment, partition_id, parent="record")
    return partition_id


def ensure_chunk_partition(
    db: Session,
    chunk: LegacyIssueAiChunk,
    *,
    record: LegacyIssueRecord | None = None,
    attachment: LegacyIssueAttachment | None = None,
) -> str:
    if chunk.attachment_id:
        resolved_attachment = attachment or db.get(
            LegacyIssueAttachment,
            chunk.attachment_id,
        )
        if resolved_attachment is None:
            raise LegacyIssuePartitionMismatch(
                f"legacy issue chunk attachment is missing: {chunk.attachment_id}"
            )
        _require_same_workspace(chunk, resolved_attachment, child="chunk")
        partition_id = ensure_attachment_partition(db, resolved_attachment, record=record)
        _inherit_partition(chunk, partition_id, parent="attachment")
        return partition_id
    resolved_record = record or db.get(LegacyIssueRecord, chunk.record_id)
    if resolved_record is None:
        raise LegacyIssuePartitionMismatch(
            f"legacy issue chunk record is missing: {chunk.record_id}"
        )
    _require_same_workspace(chunk, resolved_record, child="chunk")
    partition_id = ensure_record_partition(db, resolved_record)
    _inherit_partition(chunk, partition_id, parent="record")
    return partition_id


def ensure_attachment_job_partition(
    db: Session,
    job: LegacyIssueAttachmentIndexJob,
    *,
    attachment: LegacyIssueAttachment,
) -> str:
    _require_same_workspace(job, attachment, child="attachment index job")
    partition_id = ensure_attachment_partition(db, attachment)
    _inherit_partition(job, partition_id, parent="attachment")
    return partition_id


def _inherit_partition(target: object, partition_id: str, *, parent: str) -> None:
    current = str(getattr(target, "retrieval_partition_id", None) or "").strip()
    if current and current != partition_id:
        raise LegacyIssuePartitionMismatch(
            f"legacy issue partition does not match {parent}: {current} != {partition_id}"
        )
    setattr(target, "retrieval_partition_id", partition_id)


def _require_same_workspace(child_row: object, parent_row: object, *, child: str) -> None:
    child_workspace_id = str(getattr(child_row, "workspace_id", "") or "")
    parent_workspace_id = str(getattr(parent_row, "workspace_id", "") or "")
    if child_workspace_id != parent_workspace_id:
        raise LegacyIssuePartitionMismatch(f"legacy issue {child} workspace does not match parent")


__all__ = [
    "LegacyIssuePartitionMismatch",
    "ensure_attachment_job_partition",
    "ensure_attachment_partition",
    "ensure_chunk_partition",
    "ensure_record_partition",
    "ensure_revision_partition",
]
