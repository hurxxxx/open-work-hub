from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidoo_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Folder(Base):
    """Intermediate grouping: Space > Folder > List (Project)."""

    __tablename__ = "pms_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(140))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    projects: Mapped[list["Project"]] = relationship(back_populates="folder")


class Project(Base):
    __tablename__ = "pms_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True, index=True
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_folders.id"), nullable=True, index=True
    )
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    labels: Mapped[list["Label"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    issues: Mapped[list["Issue"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    dependencies: Mapped[list["ScheduleDependency"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    statuses: Mapped[list["ProjectStatus"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectStatus.sort_order",
    )
    folder: Mapped[Folder | None] = relationship(back_populates="projects")


class ProjectStatus(Base):
    """Custom workflow statuses per project."""

    __tablename__ = "pms_project_statuses"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_pms_project_status_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    slug: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(24), default="#6b7280")
    category: Mapped[str] = mapped_column(
        String(24), default="active"
    )  # backlog | active | done | canceled
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    project: Mapped[Project] = relationship(back_populates="statuses")


class ProjectMember(Base):
    __tablename__ = "pms_project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_pms_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    project: Mapped[Project] = relationship(back_populates="members")
    user = relationship("User")


class Milestone(Base):
    __tablename__ = "pms_milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    project: Mapped[Project] = relationship(back_populates="milestones")
    issues: Mapped[list["Issue"]] = relationship(back_populates="milestone")


class Label(Base):
    __tablename__ = "pms_labels"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_pms_label_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(48))
    color: Mapped[str] = mapped_column(String(24), default="#1f2d38")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    project: Mapped[Project] = relationship(back_populates="labels")
    issue_links: Mapped[list["IssueLabel"]] = relationship(
        back_populates="label",
        cascade="all, delete-orphan",
    )


class Issue(Base):
    __tablename__ = "pms_issues"
    __table_args__ = (UniqueConstraint("project_id", "issue_number", name="uq_pms_issue_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="backlog", index=True)
    priority: Mapped[str] = mapped_column(String(24), default="medium", index=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_issues.id"),
        nullable=True,
        index=True,
    )
    milestone_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_milestones.id"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    board_position: Mapped[int] = mapped_column(Integer, default=0)
    estimate_hours: Mapped[float | None] = mapped_column(nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String(120), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    project: Mapped[Project] = relationship(back_populates="issues")
    parent: Mapped["Issue | None"] = relationship(
        back_populates="subtasks",
        remote_side="Issue.id",
    )
    subtasks: Mapped[list["Issue"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    milestone: Mapped[Milestone | None] = relationship(back_populates="issues")
    assignee = relationship("User", foreign_keys=[assignee_id])
    reporter = relationship("User", foreign_keys=[reporter_id])
    comments: Mapped[list["IssueComment"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    activity_logs: Mapped[list["IssueActivityLog"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    label_links: Mapped[list["IssueLabel"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    time_entries: Mapped[list["TimeEntry"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    assignee_links: Mapped[list["IssueAssignee"]] = relationship(
        cascade="all, delete-orphan",
    )


class IssueLabel(Base):
    __tablename__ = "pms_issue_labels"
    __table_args__ = (UniqueConstraint("issue_id", "label_id", name="uq_pms_issue_label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("pms_labels.id"), index=True)
    issue: Mapped[Issue] = relationship(back_populates="label_links")
    label: Mapped[Label] = relationship(back_populates="issue_links")


class IssueComment(Base):
    __tablename__ = "pms_issue_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    body_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    issue: Mapped[Issue] = relationship(back_populates="comments")
    author = relationship("User")


class IssueActivityLog(Base):
    __tablename__ = "pms_issue_activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    field_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    issue: Mapped[Issue] = relationship(back_populates="activity_logs")
    actor = relationship("User")


class ScheduleDependency(Base):
    __tablename__ = "pms_schedule_dependencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    predecessor_kind: Mapped[str] = mapped_column(String(24), default="issue")
    predecessor_id: Mapped[str] = mapped_column(String(36), index=True)
    successor_kind: Mapped[str] = mapped_column(String(24), default="issue")
    successor_id: Mapped[str] = mapped_column(String(36), index=True)
    relation_type: Mapped[str] = mapped_column(String(24), default="blocks")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    project: Mapped[Project] = relationship(back_populates="dependencies")


class Attachment(Base):
    __tablename__ = "pms_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    issue: Mapped[Issue] = relationship(back_populates="attachments")
    uploaded_by = relationship("User")


class ChecklistItem(Base):
    __tablename__ = "pms_checklist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    issue: Mapped[Issue] = relationship(back_populates="checklist_items")


class TimeEntry(Base):
    __tablename__ = "pms_time_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    entry_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    issue: Mapped[Issue] = relationship(back_populates="time_entries")
    user = relationship("User")


class Notification(Base):
    __tablename__ = "pms_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    reference_type: Mapped[str] = mapped_column(String(24), default="issue")
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class TaskTemplate(Base):
    """Reusable issue templates per project."""

    __tablename__ = "pms_task_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_status: Mapped[str] = mapped_column(String(40), default="backlog")
    default_priority: Mapped[str] = mapped_column(String(24), default="medium")
    checklist_items: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class CustomField(Base):
    """Custom fields per project (text, number, date, select)."""

    __tablename__ = "pms_custom_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    field_type: Mapped[str] = mapped_column(String(24))  # text | number | date | select
    options: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # for select type
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class CustomFieldValue(Base):
    """Custom field values per issue."""

    __tablename__ = "pms_custom_field_values"
    __table_args__ = (
        UniqueConstraint("issue_id", "field_id", name="uq_pms_cf_value"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    field_id: Mapped[str] = mapped_column(ForeignKey("pms_custom_fields.id"), index=True)
    value: Mapped[str] = mapped_column(Text, default="")


class IssueAssignee(Base):
    """Multiple assignees per issue (junction table)."""

    __tablename__ = "pms_issue_assignees"
    __table_args__ = (
        UniqueConstraint("issue_id", "user_id", name="uq_pms_issue_assignee"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user = relationship("User")


class Automation(Base):
    """Rule-based automation: When trigger → If condition → Then action."""

    __tablename__ = "pms_automations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger: Mapped[str] = mapped_column(String(40))  # status_changed | assignee_changed | created | ...
    condition: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # e.g. {"field":"status","value":"done"}
    action: Mapped[dict] = mapped_column(JSON)  # e.g. {"type":"notify","user_id":"..."}
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class Goal(Base):
    """OKR / Goal tracking linked to issues."""

    __tablename__ = "pms_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target: Mapped[float] = mapped_column(default=100.0)
    progress: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="active")  # active | completed | canceled
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class GoalLink(Base):
    """Links goals to issues for automatic progress tracking."""

    __tablename__ = "pms_goal_links"
    __table_args__ = (
        UniqueConstraint("goal_id", "issue_id", name="uq_pms_goal_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("pms_goals.id"), index=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("pms_issues.id"), index=True)


class Doc(Base):
    """Project-scoped documents (wiki pages)."""

    __tablename__ = "pms_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("pms_projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    created_by = relationship("User")
