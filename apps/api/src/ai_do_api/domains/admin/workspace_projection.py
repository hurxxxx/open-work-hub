from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import Workspace, WorkspaceUserBinding


@dataclass(frozen=True)
class WorkspaceContentCounts:
    space_count: int
    meeting_count: int
    doc_count: int

    @property
    def has_content(self) -> bool:
        return self.space_count > 0 or self.meeting_count > 0 or self.doc_count > 0


def visible_workspace_team_count(workspace: Workspace) -> int:
    return sum(1 for team in workspace.teams if team.trashed_at is None)


def workspace_member_count(db: Session, workspace_id: str) -> int:
    user_count = db.scalar(
        select(func.count())
        .select_from(WorkspaceUserBinding)
        .where(WorkspaceUserBinding.workspace_id == workspace_id)
    ) or 0
    return int(user_count)


def workspace_meeting_count(db: Session, workspace_id: str) -> int:
    from ai_do_api.domains.meeting.models import Meeting

    return int(
        db.scalar(
            select(func.count())
            .select_from(Meeting)
            .where(Meeting.workspace_id == workspace_id)
        )
        or 0
    )


def workspace_doc_count(db: Session, workspace_id: str) -> int:
    from ai_do_api.domains.docs.models import NativeDoc

    return int(
        db.scalar(
            select(func.count())
            .select_from(NativeDoc)
            .where(NativeDoc.workspace_id == workspace_id)
        )
        or 0
    )


def workspace_content_counts(db: Session, workspace: Workspace) -> WorkspaceContentCounts:
    return WorkspaceContentCounts(
        space_count=visible_workspace_team_count(workspace),
        meeting_count=workspace_meeting_count(db, workspace.id),
        doc_count=workspace_doc_count(db, workspace.id),
    )


def admin_workspace_item_projection(db: Session, workspace: Workspace) -> dict[str, Any]:
    content_counts = workspace_content_counts(db, workspace)
    return {
        "id": workspace.id,
        "key": workspace.key,
        "name": workspace.name,
        "description": workspace.description,
        "active": workspace.active,
        "team_count": content_counts.space_count,
        "member_count": workspace_member_count(db, workspace.id),
        "meeting_count": content_counts.meeting_count,
        "doc_count": content_counts.doc_count,
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
    }
