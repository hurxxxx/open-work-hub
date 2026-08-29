from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


GraphRunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
GraphRunVisibility = Literal["private", "workspace"]
GraphDispatchStatus = Literal[
    "pending",
    "claimed",
    "dispatched",
    "dead_letter",
    "cancelled",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class AiGraphNodeSpec(BaseModel):
    """One node in a reusable, app-owned graph definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")
    depends_on: tuple[str, ...] = ()
    purpose: str = Field(min_length=1, max_length=256)
    required: bool = True
    routes: dict[str, str | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dependencies(self) -> "AiGraphNodeSpec":
        if self.node_id in self.depends_on:
            raise ValueError(f"node {self.node_id} cannot depend on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError(f"node {self.node_id} has duplicate dependencies")
        for route, target in self.routes.items():
            if not route.strip():
                raise ValueError(f"node {self.node_id} has a blank route")
            if target == self.node_id:
                raise ValueError(f"node {self.node_id} cannot route to itself")
        return self


class AiGraphSpec(BaseModel):
    """Versioned DAG topology; prompts and provider/model choices do not belong here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")
    graph_version: str = Field(min_length=1, max_length=64)
    state_schema_version: int = Field(default=1, ge=1)
    nodes: tuple[AiGraphNodeSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dag(self) -> "AiGraphSpec":
        node_ids = [node.node_id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("graph node ids must be unique")
        known = set(node_ids)
        routed_sources: set[str] = set()
        for node in self.nodes:
            unknown = set(node.depends_on) - known
            if unknown:
                raise ValueError(
                    f"node {node.node_id} has unknown dependencies: {sorted(unknown)}"
                )
            unknown_targets = {
                target for target in node.routes.values() if target is not None and target not in known
            }
            if unknown_targets:
                raise ValueError(
                    f"node {node.node_id} has unknown route targets: {sorted(unknown_targets)}"
                )
            if node.routes:
                routed_sources.add(node.node_id)

        for node in self.nodes:
            overlap = set(node.depends_on) & routed_sources
            if overlap:
                raise ValueError(
                    f"node {node.node_id} must be reached either by routes or dependencies, "
                    f"not both: {sorted(overlap)}"
                )
            if node.depends_on and any(
                node.node_id in source.routes.values() for source in self.nodes
            ):
                raise ValueError(
                    f"routed node {node.node_id} cannot also declare static dependencies"
                )

        visiting: set[str] = set()
        visited: set[str] = set()
        dependencies = {
            node.node_id: tuple(
                dict.fromkeys(
                    (
                        *node.depends_on,
                        *(
                            source.node_id
                            for source in self.nodes
                            if node.node_id in source.routes.values()
                        ),
                    )
                )
            )
            for node in self.nodes
        }

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ValueError("graph dependencies must be acyclic")
            visiting.add(node_id)
            for dependency in dependencies[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)
        return self


class AiGraphRunRequest(BaseModel):
    """Server-authenticated input for one durable graph execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=36)
    requested_by_user_id: str = Field(min_length=1, max_length=36)
    app_id: str = Field(min_length=1, max_length=64)
    graph: AiGraphSpec
    inputs: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = Field(default=None, max_length=36)
    visibility: GraphRunVisibility = "private"
    checkpoint_ns: str = Field(default="", max_length=128)


class AiGraphNodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output: Any = None
    route: str | None = None


class AiGraphRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    status: Literal["completed", "failed", "skipped"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None


class AiGraphRunResponse(_CamelModel):
    id: str
    workspace_id: str
    requested_by_user_id: str
    conversation_id: str | None
    app_id: str
    graph_id: str
    graph_version: str
    checkpoint_thread_id: str
    checkpoint_ns: str
    artifact_id: str | None = None
    status: GraphRunStatus
    stage: str | None
    current_step: int
    total_steps: int
    progress_percent: int
    status_message_key: str | None
    error_code: str | None
    visibility: GraphRunVisibility
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class AiGraphRunListResponse(_CamelModel):
    items: list[AiGraphRunResponse]
    total: int


class AiGraphLlmRequest(BaseModel):
    """Provider-neutral request accepted by the graph-to-gateway adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workload_id: str = Field(min_length=1, max_length=128)
    app_id: str = Field(min_length=1, max_length=64)
    workspace_id: str = Field(min_length=1, max_length=36)
    source: str = Field(min_length=1, max_length=128)
    messages: list[dict[str, Any]] = Field(min_length=1)
    actor_user_id: str | None = Field(default=None, max_length=36)
    principal_kind: Literal["user", "service_account", "system"] = "user"
    principal_id: str | None = Field(default=None, max_length=128)
    graph_run_id: str | None = Field(default=None, max_length=36)
    conversation_id: str | None = Field(default=None, max_length=36)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    reasoning_effort: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    stream_reasoning: bool = True
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None


class AiGraphLlmResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    model: str | None = None
    usage: dict[str, int] | None = None
    finish_reason: str | None = None
    workload_id: str
    chosen_pool: str


class AiGraphDispatchCreate(BaseModel):
    """Retryable dispatch envelope containing a reference, never graph state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_run_id: str = Field(min_length=1, max_length=36)
    payload_ref: str = Field(min_length=1, max_length=512)
    queue_name: str = Field(default="ai-graph", min_length=1, max_length=128)
    task_name: str = Field(default="ai_graph.run", min_length=1, max_length=128)


def merge_graph_values(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer used by parallel LangGraph branches."""

    return {**left, **right}


class AiGraphState(dict):
    """Runtime type marker kept for backwards-compatible imports."""


GraphOutputMap = Annotated[dict[str, Any], merge_graph_values]
