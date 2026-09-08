from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ModelRuntimeTargetStatus = Literal[
    "online",
    "degraded",
    "offline",
    "not_configured",
]


class ModelRuntimeModelResponse(BaseModel):
    name: str
    task: str | None = None
    loaded: bool = True


class ModelRuntimeTargetResponse(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    display_name: str = Field(min_length=1, max_length=120)
    kind: Literal["inference_gateway", "llm"]
    role: Literal["serving", "redundancy", "diagnostic"]
    provider_id: str | None = None
    status: ModelRuntimeTargetStatus
    models: list[ModelRuntimeModelResponse] = Field(default_factory=list)
    error_code: (
        Literal[
            "connection_failed",
            "http_error",
            "invalid_response",
            "model_missing",
            "configuration_invalid",
            "timeout",
        ]
        | None
    ) = None


class AdminModelRuntimeStatusResponse(BaseModel):
    checked_at: datetime
    status: Literal["online", "degraded", "offline"]
    targets: list[ModelRuntimeTargetResponse] = Field(default_factory=list)


__all__ = [
    "AdminModelRuntimeStatusResponse",
    "ModelRuntimeModelResponse",
    "ModelRuntimeTargetResponse",
]
