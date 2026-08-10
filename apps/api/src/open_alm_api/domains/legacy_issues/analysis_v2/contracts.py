from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisRoute(StrEnum):
    RECIPE = "recipe"
    SAFE_SQL = "safe_sql"
    CLARIFY = "clarify"


class FallbackReason(StrEnum):
    NO_RECIPE_MATCH = "no_recipe_match"
    UNSUPPORTED_METRIC = "unsupported_metric"
    UNSUPPORTED_JOIN = "unsupported_join"
    UNSUPPORTED_SHAPE = "unsupported_shape"


class RecipeReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    version: int = Field(ge=1)


class AnalysisRouteDecision(BaseModel):
    """Machine-checkable recipe-first routing decision emitted by the planner.

    The safe-SQL route is valid only when the planner explicitly states why the
    versioned recipe catalog cannot express the request.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: AnalysisRoute
    recipe: RecipeReference | None = None
    fallback_reason: FallbackReason | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=500)
    missing_parameters: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def _enforce_recipe_first(self) -> AnalysisRouteDecision:
        if self.route == AnalysisRoute.RECIPE:
            if self.recipe is None:
                raise ValueError("recipe route requires recipe reference")
            if self.fallback_reason is not None or self.missing_parameters:
                raise ValueError("recipe route cannot declare fallback or missing parameters")
        elif self.route == AnalysisRoute.SAFE_SQL:
            if self.recipe is not None:
                raise ValueError("safe_sql route cannot select a recipe")
            if self.fallback_reason is None:
                raise ValueError("safe_sql route requires an explicit fallback reason")
            if self.missing_parameters:
                raise ValueError("safe_sql route cannot hide missing parameters")
        else:
            if self.recipe is not None or self.fallback_reason is not None:
                raise ValueError("clarify route cannot select an execution strategy")
            if not self.missing_parameters:
                raise ValueError("clarify route requires missing_parameters")
        return self


class RecipeInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    version: int = Field(default=1, ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class QueryColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    value_type: Literal["null", "boolean", "integer", "number", "date", "datetime", "text"]


PublicCell = str | int | float | bool | date | datetime | None
SqlParameterValue = str | int | float | bool | date | datetime | None


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(min_length=12, max_length=64)
    source: Literal["recipe", "safe_sql"]
    recipe: RecipeReference | None = None
    parameterized_sql: str = Field(min_length=1, max_length=20_000)
    parameters: dict[str, SqlParameterValue] = Field(default_factory=dict)
    recipe_arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["succeeded", "failed"]
    error_code: str | None = Field(default=None, pattern=r"^[a-z0-9_.-]{1,120}$")
    columns: tuple[QueryColumn, ...]
    rows: tuple[dict[str, PublicCell], ...]
    row_count: int = Field(ge=0, le=1000)
    truncated: bool
    payload_bytes: int = Field(ge=0, le=250 * 1024)
    elapsed_ms: int = Field(ge=0)
    referenced_views: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_execution_status(self) -> QueryResult:
        if self.status == "succeeded" and self.error_code is not None:
            raise ValueError("successful query cannot declare error_code")
        if self.status == "failed":
            if self.error_code is None:
                raise ValueError("failed query requires error_code")
            if self.columns or self.rows or self.row_count or self.payload_bytes:
                raise ValueError("failed query cannot expose partial result data")
        return self


class RetrievalHit(BaseModel):
    """A candidate that has already passed final source ACL authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=20_000)
    score: float = Field(ge=0)
    resource_type: str = Field(min_length=1, max_length=120)
    resource_id: str = Field(min_length=1, max_length=160)
    partition_id: str | None = Field(default=None, min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    hits: tuple[RetrievalHit, ...]
    backend_id: str = Field(min_length=1, max_length=120)


__all__ = [
    "AnalysisRoute",
    "AnalysisRouteDecision",
    "FallbackReason",
    "PublicCell",
    "SqlParameterValue",
    "QueryColumn",
    "QueryResult",
    "RecipeInvocation",
    "RecipeReference",
    "RetrievalHit",
    "RetrievalResult",
]
