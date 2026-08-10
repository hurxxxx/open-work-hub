from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


IMAGE_MODEL_PROFILE_ID = "default"


class ImageModelProviderConfig(Base):
    __tablename__ = "image_model_provider_configs"

    provider_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        info={"secret": True},
    )
    supervisor_model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    generation_model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class ImageModelProfile(Base):
    __tablename__ = "image_model_profiles"
    __table_args__ = (
        CheckConstraint(
            "max_iterations BETWEEN 1 AND 20",
            name="ck_image_model_profiles_max_iterations",
        ),
    )

    profile_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    active_provider_id: Mapped[str | None] = mapped_column(
        ForeignKey("image_model_provider_configs.provider_id", ondelete="RESTRICT"),
        nullable=True,
    )
    brief_web_search_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    generation_web_search_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    max_iterations: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


__all__ = [
    "IMAGE_MODEL_PROFILE_ID",
    "ImageModelProfile",
    "ImageModelProviderConfig",
]
