from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.domains.auth.models import Team, Workspace
from aidoo_api.domains.pms.models import Issue, IssueComment, IssueLabel, IssueUserAccess
from aidoo_api.domains.rag.contracts import RagProjection
from aidoo_api.domains.rag.projection import build_projection


PMS_ISSUE_RESOURCE_TYPE = "pms_issue"
PMS_ISSUE_SOURCE_KIND = "pms_issue"


def load_issue_projection(
    db: Session,
    *,
    issue_id: str,
) -> RagProjection | None:
    issue = db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.task_list),
            selectinload(Issue.milestone),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments).selectinload(IssueComment.author),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.user_access_grants).selectinload(IssueUserAccess.user),
        )
        .where(Issue.id == issue_id)
    )
    if issue is None:
        return None
    task_list = issue.task_list
    if task_list is None or task_list.team_id is None:
        return None
    team = db.scalar(
        select(Team).where(
            Team.id == task_list.team_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
        )
    )
    if team is None:
        return None
    return build_issue_projection(issue, team=team)


def build_issue_projection(issue: Issue, *, team: Team) -> RagProjection:
    comments_text = "\n\n".join(_comment_text(comment) for comment in issue.comments if _comment_text(comment))
    label_names = [link.label.name for link in issue.label_links if link.label is not None]
    text_sections = [
        issue.title.strip(),
        issue.description.strip(),
        _extract_blocks_text(issue.description_blocks),
        comments_text,
        " ".join(label_names),
    ]

    return build_projection(
        workspace_id=team.workspace_id,
        resource_type=PMS_ISSUE_RESOURCE_TYPE,
        resource_id=issue.id,
        source_kind=PMS_ISSUE_SOURCE_KIND,
        title=issue.title,
        summary=_build_summary(issue, label_names=label_names),
        text_content="\n\n".join(section for section in text_sections if section),
        owner_label=getattr(issue.reporter, "full_name", None),
        visibility_refs=_build_visibility_refs(issue, team=team),
        metadata={
            "team_id": team.id,
            "list_id": issue.list_id,
            "issue_number": issue.issue_number,
            "status": issue.status,
            "priority": issue.priority,
            "archived": issue.archived,
            "milestone_title": getattr(issue.milestone, "title", None),
            "assignee_id": issue.assignee_id,
            "assignee_name": getattr(issue.assignee, "full_name", None),
            "reporter_id": issue.reporter_id,
            "list_name": getattr(issue.task_list, "name", None),
            "list_key": getattr(issue.task_list, "key", None),
            "label_names": label_names,
        },
    )


def _build_summary(issue: Issue, *, label_names: list[str]) -> str | None:
    parts = [
        issue.description.strip(),
        f"status:{issue.status}",
        f"priority:{issue.priority}",
        getattr(issue.milestone, "title", None),
        ",".join(label_names) if label_names else None,
    ]
    summary = " | ".join(part for part in parts if part)
    return summary or issue.title.strip() or None


def _build_visibility_refs(issue: Issue, *, team: Team) -> list[str]:
    refs = {
        f"workspace:{team.workspace_id}",
        f"team:{team.id}",
        f"list:{issue.list_id}",
    }
    for grant in issue.user_access_grants:
        if grant.revoked_at is not None:
            continue
        refs.add(f"issue_grant:{grant.user_id}")
        if grant.granted_by_meeting_id:
            refs.add(f"meeting_source:{grant.granted_by_meeting_id}")
    return sorted(refs)


def _comment_text(comment: IssueComment) -> str:
    parts = [
        getattr(comment.author, "full_name", None),
        comment.body.strip(),
        _extract_blocks_text(comment.body_blocks),
    ]
    return " ".join(part for part in parts if part).strip()


def _extract_blocks_text(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""

    parts: list[str] = []
    for block in blocks:
        _collect_text_parts(block, parts)
    return " ".join(part for part in parts if part).strip()


def _collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if normalized:
            parts.append(normalized)
        return

    if isinstance(value, list):
        for item in value:
            _collect_text_parts(item, parts)
        return

    if not isinstance(value, dict):
        return

    if isinstance(value.get("text"), str):
        normalized = " ".join(value["text"].split()).strip()
        if normalized:
            parts.append(normalized)

    for key in ("content", "children"):
        nested = value.get(key)
        if nested is not None:
            _collect_text_parts(nested, parts)
