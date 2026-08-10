from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


class NotificationDmDelivery(Base):
    __tablename__ = "notification_dm_deliveries"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_notification_dm_deliveries_message"),
        Index("ix_notification_dm_deliveries_user", "user_id", "created_at"),
        Index("ix_notification_dm_deliveries_conversation", "conversation_id", "created_at"),
        Index(
            "ix_notification_dm_deliveries_user_conversation",
            "user_id",
            "conversation_id",
            "notification_id",
        ),
    )

    notification_id: Mapped[str] = mapped_column(
        ForeignKey("pms_notifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("dm_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("dm_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    notification = relationship("Notification")
    user = relationship("User")
    conversation = relationship("DmConversation")
    message = relationship("DmMessage")
