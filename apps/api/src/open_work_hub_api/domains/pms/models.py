from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from open_work_hub_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _native_doc_model() -> type[object]:
    from open_work_hub_api.domains.docs.models import NativeDoc

    return NativeDoc


class Folder(Base):
    """Intermediate grouping: Space > Folder > List."""

    __tablename__ = "pms_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_spaces.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(140))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task_lists: Mapped[list["TaskList"]] = relationship(back_populates="folder")


class PmsViewPreference(Base):
    """Personal PMS presentation preferences for one user."""

    __tablename__ = "pms_view_preferences"
    __table_args__ = (
        CheckConstraint(
            "task_list_group_by IN ('none', 'status', 'assignee')",
            name="ck_pms_view_preferences_task_list_group_by",
        ),
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_list_group_by: Mapped[str] = mapped_column(
        String(16),
        default="status",
        server_default=text("'status'"),
        nullable=False,
    )
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


class SpaceStatus(Base):
    """Default workflow statuses for a PMS Space."""

    __tablename__ = "pms_space_statuses"
    __table_args__ = (UniqueConstraint("team_id", "slug", name="uq_pms_space_status_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("pms_spaces.id"), index=True)
    slug: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(24), default="#6b7280")
    category: Mapped[str] = mapped_column(
        String(24), default="active"
    )  # not_started | active | done | closed
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class TaskList(Base):
    __tablename__ = "pms_task_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    status_mode: Mapped[str] = mapped_column(String(16), default="custom", nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_spaces.id"), nullable=True, index=True
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_folders.id"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="task_list",
        cascade="all, delete-orphan",
    )
    labels: Mapped[list["Label"]] = relationship(
        back_populates="task_list",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="task_list",
        cascade="all, delete-orphan",
    )
    statuses: Mapped[list["TaskListStatus"]] = relationship(
        back_populates="task_list",
        cascade="all, delete-orphan",
        order_by="TaskListStatus.sort_order",
    )
    space_statuses: Mapped[list[SpaceStatus]] = relationship(
        primaryjoin=lambda: TaskList.team_id == foreign(SpaceStatus.team_id),
        viewonly=True,
        order_by="SpaceStatus.sort_order",
    )
    folder: Mapped[Folder | None] = relationship(back_populates="task_lists")
    task_templates: Mapped[list["TaskTemplate"]] = relationship(
        back_populates="task_list",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["CustomField"]] = relationship(
        back_populates="task_list",
        cascade="all, delete-orphan",
    )


class TaskListStatus(Base):
    """Custom workflow statuses per task list."""

    __tablename__ = "pms_task_list_statuses"
    __table_args__ = (UniqueConstraint("list_id", "slug", name="uq_pms_task_list_status_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("pms_task_lists.id"), index=True)
    slug: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(24), default="#6b7280")
    category: Mapped[str] = mapped_column(
        String(24), default="active"
    )  # not_started | active | done | closed
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task_list: Mapped[TaskList] = relationship(back_populates="statuses")


class Milestone(Base):
    __tablename__ = "pms_milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("pms_task_lists.id"), index=True)
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
    task_list: Mapped[TaskList] = relationship(back_populates="milestones")
    tasks: Mapped[list["Task"]] = relationship(back_populates="milestone")


class Label(Base):
    __tablename__ = "pms_labels"
    __table_args__ = (UniqueConstraint("list_id", "name", name="uq_pms_label_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("pms_task_lists.id"), index=True)
    name: Mapped[str] = mapped_column(String(48))
    color: Mapped[str] = mapped_column(String(24), default="#1f2d38")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task_list: Mapped[TaskList] = relationship(back_populates="labels")
    task_links: Mapped[list["TaskLabel"]] = relationship(
        back_populates="label",
        cascade="all, delete-orphan",
    )


class Task(Base):
    __tablename__ = "pms_tasks"
    __table_args__ = (
        UniqueConstraint("list_id", "task_number", name="uq_pms_task_number"),
        Index("ix_pms_tasks_due_date", "due_date"),
        Index("ix_pms_tasks_start_date", "start_date"),
        Index(
            "ix_pms_tasks_list_archived_board",
            "list_id",
            "archived",
            "board_position",
            "task_number",
        ),
        Index("ix_pms_tasks_list_archived_updated", "list_id", "archived", "updated_at"),
        Index("ix_pms_tasks_reporter_archived_created", "reporter_id", "archived", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("pms_task_lists.id"), index=True)
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    task_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="todo", index=True)
    priority: Mapped[str] = mapped_column(String(24), default="medium", index=True)
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("pms_tasks.id"),
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
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    board_position: Mapped[int] = mapped_column(Integer, default=0)
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
    task_list: Mapped[TaskList] = relationship(back_populates="tasks")
    parent: Mapped["Task | None"] = relationship(
        back_populates="subtasks",
        remote_side="Task.id",
    )
    subtasks: Mapped[list["Task"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    milestone: Mapped[Milestone | None] = relationship(back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id])
    reporter = relationship("User", foreign_keys=[reporter_id])
    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    activity_logs: Mapped[list["TaskActivityLog"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    label_links: Mapped[list["TaskLabel"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    assignee_links: Mapped[list["TaskAssignee"]] = relationship(
        cascade="all, delete-orphan",
    )
    follower_links: Mapped[list["TaskFollower"]] = relationship(
        cascade="all, delete-orphan",
    )
    user_access_grants: Mapped[list["TaskUserAccess"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    doc_links: Mapped[list["TaskDocLink"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class TaskLabel(Base):
    __tablename__ = "pms_task_labels"
    __table_args__ = (
        UniqueConstraint("task_id", "label_id", name="uq_pms_task_label"),
        Index("ix_pms_task_labels_label_task", "label_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("pms_labels.id"), index=True)
    task: Mapped[Task] = relationship(back_populates="label_links")
    label: Mapped[Label] = relationship(back_populates="task_links")


class TaskComment(Base):
    __tablename__ = "pms_task_comments"
    __table_args__ = (Index("ix_pms_task_comments_author_created", "author_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    body_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task: Mapped[Task] = relationship(back_populates="comments")
    author = relationship("User")


class TaskActivityLog(Base):
    __tablename__ = "pms_task_activity_logs"
    __table_args__ = (Index("ix_pms_task_activity_logs_actor_created", "actor_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    field_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task: Mapped[Task] = relationship(back_populates="activity_logs")
    actor = relationship("User")


class Attachment(Base):
    __tablename__ = "pms_attachments"
    __table_args__ = (Index("ix_pms_attachments_uploaded_created", "uploaded_by_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
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
    task: Mapped[Task] = relationship(back_populates="attachments")
    uploaded_by = relationship("User")


class ChecklistItem(Base):
    __tablename__ = "pms_checklist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task: Mapped[Task] = relationship(back_populates="checklist_items")


class Notification(Base):
    __tablename__ = "pms_notifications"
    __table_args__ = (
        Index(
            "ix_pms_notifications_user_created_global",
            "user_id",
            "created_at",
            postgresql_where=text("type <> 'dm_message'"),
        ),
        Index(
            "ix_pms_notifications_user_unread_global",
            "user_id",
            postgresql_where=text("is_read = false AND type <> 'dm_message'"),
        ),
        Index(
            "ix_pms_notifications_user_source_unread",
            "user_id",
            "origin_app_id",
            "source_type",
            "source_id",
            postgresql_where=text("is_read = false"),
        ),
        CheckConstraint(
            "origin_app_id IS NOT NULL AND source_id IS NOT NULL",
            name="ck_pms_notifications_global_origin",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(40), default="task")
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    origin_app_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class TaskTemplate(Base):
    """Reusable task templates per task list."""

    __tablename__ = "pms_task_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("pms_task_lists.id"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_status: Mapped[str] = mapped_column(String(40), default="todo")
    default_priority: Mapped[str] = mapped_column(String(24), default="medium")
    checklist_items: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task_list: Mapped[TaskList] = relationship(back_populates="task_templates")


class CustomField(Base):
    """Custom fields per task list (text, number, date, select)."""

    __tablename__ = "pms_custom_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey("pms_task_lists.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    field_type: Mapped[str] = mapped_column(String(24))  # text | number | date | select
    options: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # for select type
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    task_list: Mapped[TaskList] = relationship(back_populates="custom_fields")


class CustomFieldValue(Base):
    """Custom field values per task."""

    __tablename__ = "pms_custom_field_values"
    __table_args__ = (UniqueConstraint("task_id", "field_id", name="uq_pms_cf_value"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    field_id: Mapped[str] = mapped_column(ForeignKey("pms_custom_fields.id"), index=True)
    value: Mapped[str] = mapped_column(Text, default="")


class TaskAssignee(Base):
    """Multiple assignees per task (junction table)."""

    __tablename__ = "pms_task_assignees"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_pms_task_assignee"),
        Index("ix_pms_task_assignees_user_task", "user_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user = relationship("User")


class TaskFollower(Base):
    """Users following an task for updates."""

    __tablename__ = "pms_task_followers"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_pms_task_follower"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user = relationship("User")


class TaskUserAccess(Base):
    __tablename__ = "pms_task_user_access"
    __table_args__ = (
        Index("ix_pms_task_user_access_user_revoked", "user_id", "revoked_at"),
        Index(
            "ix_pms_task_user_access_meeting_revoked",
            "granted_by_meeting_id",
            "revoked_at",
        ),
        Index(
            "ix_pms_task_user_access_expires_active",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_pms_task_user_access_active",
            "task_id",
            "user_id",
            "granted_by_meeting_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    access_level: Mapped[str] = mapped_column(String(16), default="read")
    granted_by_meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id"),
        nullable=True,
        index=True,
    )
    granted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(String(24), default="meeting_attendee")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
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

    task: Mapped[Task] = relationship(back_populates="user_access_grants")
    user = relationship("User", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by_user_id])
    revoked_by_user = relationship("User", foreign_keys=[revoked_by_user_id])


class TaskDocLink(Base):
    __tablename__ = "pms_task_doc_links"
    __table_args__ = (
        UniqueConstraint("task_id", "doc_id", name="uq_pms_task_doc_link"),
        Index("ix_pms_task_doc_links_task_created", "task_id", "created_at"),
        Index("ix_pms_task_doc_links_doc_created", "doc_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("pms_tasks.id"), index=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("docs_native_docs.id"), index=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )

    task: Mapped[Task] = relationship(back_populates="doc_links")
    doc = relationship(_native_doc_model)
    created_by = relationship("User")
