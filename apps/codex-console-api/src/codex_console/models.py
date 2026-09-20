from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Owner(Base):
    __tablename__ = "console_owner"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    password_hash: Mapped[str] = mapped_column(Text)
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebSession(Base):
    __tablename__ = "console_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Task(Base):
    __tablename__ = "console_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(200))
    thread_id: Mapped[str | None] = mapped_column(String(160), unique=True)
    stage: Mapped[str] = mapped_column(String(24), default="plan")
    status: Mapped[str] = mapped_column(String(24), default="idle")
    root: Mapped[str] = mapped_column(Text)
    last_execution_root: Mapped[str | None] = mapped_column(Text)
    previous_execution_root: Mapped[str | None] = mapped_column(Text)
    previous_permissions: Mapped[str | None] = mapped_column(String(24))
    worktree_owned: Mapped[bool] = mapped_column(default=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(200))
    effort: Mapped[str | None] = mapped_column(String(40))
    permissions: Mapped[str] = mapped_column(String(24), default="read-only")
    progress: Mapped[dict | None] = mapped_column(JSON)
    runtime_generation: Mapped[str | None] = mapped_column(String(36))
    turn_id: Mapped[str | None] = mapped_column(String(160))
    current_operation_id: Mapped[str | None] = mapped_column(String(36))
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Revision(Base):
    __tablename__ = "console_revisions"
    __table_args__ = (
        UniqueConstraint("task_id", "kind", "version"),
        UniqueConstraint("task_id", "kind", "source_turn_id", name="uq_console_revision_kind_turn"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("console_tasks.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    source_turn_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Item(Base):
    __tablename__ = "console_items"
    __table_args__ = (UniqueConstraint("task_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("console_tasks.id", ondelete="CASCADE"))
    item_id: Mapped[str] = mapped_column(String(200))
    turn_id: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON)


class PendingRequest(Base):
    __tablename__ = "console_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("console_tasks.id", ondelete="CASCADE"))
    turn_id: Mapped[str] = mapped_column(String(160))
    rpc_id: Mapped[str] = mapped_column(Text)
    generation: Mapped[str] = mapped_column(String(36))
    method: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    answer: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Operation(Base):
    __tablename__ = "console_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("console_tasks.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(24), default="pending")
    digest: Mapped[str] = mapped_column(String(64))
    display_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Attachment(Base):
    __tablename__ = "console_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("console_tasks.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageAttachment(Base):
    __tablename__ = "console_message_attachments"
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("console_operations.id", ondelete="CASCADE"), primary_key=True
    )
    attachment_id: Mapped[str] = mapped_column(
        ForeignKey("console_attachments.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)


class WorkspaceLease(Base):
    __tablename__ = "console_workspace_lease"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("console_tasks.id"))
    __table_args__ = (CheckConstraint("id = 1"),)


class Event(Base):
    __tablename__ = "console_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("console_tasks.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_console_events_task_id_id", "task_id", "id"),)


def database(url: str):
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    return engine, sessionmaker(engine, expire_on_commit=False)
