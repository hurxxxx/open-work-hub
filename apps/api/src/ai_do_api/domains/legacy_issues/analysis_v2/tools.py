from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_do_api.domains.legacy_issues.analysis_v2.contracts import (
    AnalysisRoute,
    AnalysisRouteDecision,
    FallbackReason,
)
from ai_do_api.domains.legacy_issues.analysis_v2.execution import SafeAnalysisQueryService
from ai_do_api.domains.legacy_issues.analysis_v2.recipes import RecipeCatalog
from ai_do_api.domains.legacy_issues.analysis_v2.retrieval import (
    LlamaIndexRetrieverAdapter,
)


class RunRecipeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    version: int = Field(default=1, ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RunSafeSqlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1, max_length=20_000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    fallback_reason: FallbackReason
    rationale: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.7, ge=0, le=1)


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=8, ge=1, le=50)


class AnalysisToolset:
    """Bound tool implementation; no method accepts auth or model-routing input."""

    def __init__(
        self,
        *,
        catalog: RecipeCatalog,
        query_service: SafeAnalysisQueryService,
        metadata_retriever: LlamaIndexRetrieverAdapter,
        evidence_retriever: LlamaIndexRetrieverAdapter,
    ) -> None:
        if metadata_retriever.kind != "analysis_metadata":
            raise ValueError("metadata_retriever must be analysis_metadata")
        if evidence_retriever.kind != "legacy_evidence":
            raise ValueError("evidence_retriever must be legacy_evidence")
        self.catalog = catalog
        self._queries = query_service
        self._metadata = metadata_retriever
        self._evidence = evidence_retriever

    @property
    def allowed_module_keys(self) -> tuple[str, ...]:
        return self._queries.allowed_module_keys

    @property
    def authorized_revision_ids(self) -> tuple[str, ...]:
        return self._queries.authorized_revision_ids

    def run_recipe(
        self,
        recipe_id: str,
        version: int = 1,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rendered = self.catalog.render(recipe_id, version, parameters or {})
        decision = AnalysisRouteDecision(
            route=AnalysisRoute.RECIPE,
            recipe=rendered.recipe.reference,
            confidence=1,
            rationale="versioned recipe selected",
        )
        result = self._queries.run_recipe(rendered)
        return {
            "decision": decision.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }

    def run_safe_sql(
        self,
        sql: str,
        parameters: dict[str, Any] | None,
        fallback_reason: FallbackReason | str,
        rationale: str,
        confidence: float = 0.7,
    ) -> dict[str, Any]:
        decision = AnalysisRouteDecision(
            route=AnalysisRoute.SAFE_SQL,
            fallback_reason=FallbackReason(fallback_reason),
            confidence=confidence,
            rationale=rationale,
        )
        result = self._queries.run_safe_sql(sql, parameters=parameters)
        return {
            "decision": decision.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }

    def search_analysis_context(self, query: str, limit: int = 8) -> dict[str, Any]:
        return self._metadata.search(query, limit=limit).model_dump(mode="json")

    def search_legacy_evidence(self, query: str, limit: int = 8) -> dict[str, Any]:
        return self._evidence.search(query, limit=limit).model_dump(mode="json")

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        dispatch = {
            "run_recipe": (RunRecipeInput, self.run_recipe),
            "run_safe_sql": (RunSafeSqlInput, self.run_safe_sql),
            "search_analysis_context": (SearchInput, self.search_analysis_context),
            "search_legacy_evidence": (SearchInput, self.search_legacy_evidence),
        }
        try:
            schema, function = dispatch[tool_name]
        except KeyError as exc:
            raise ValueError(f"unknown analysis tool: {tool_name}") from exc
        validated = schema.model_validate(arguments)
        return function(**validated.model_dump())

    def action_schemas(self) -> tuple[dict[str, Any], ...]:
        definitions = (
            (
                "run_recipe",
                "Execute one validated versioned analysis recipe. Module filters accept "
                "only server-declared module keys, never component or symptom names.",
                RunRecipeInput,
            ),
            (
                "run_safe_sql",
                "Execute allowlisted SELECT SQL only when no recipe can express the request.",
                RunSafeSqlInput,
            ),
            (
                "search_analysis_context",
                "Search recipe, view, column, and metric metadata before choosing an action.",
                SearchInput,
            ),
            (
                "search_legacy_evidence",
                "Search authorized semantic evidence for qualitative support and examples.",
                SearchInput,
            ),
        )
        return tuple(
            {
                "name": name,
                "description": description,
                "input_schema": schema.model_json_schema(),
            }
            for name, description, schema in definitions
        )


def build_langchain_tools(toolset: AnalysisToolset) -> tuple[Any, ...]:
    """Build native StructuredTools without making LangChain a base dependency."""

    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError("langchain-core is required for analysis_v2 tools") from exc
    return (
        StructuredTool.from_function(
            func=toolset.run_recipe,
            name="run_recipe",
            description=(
                "Execute a validated versioned analysis recipe. "
                "Use this before considering generated SQL. Module filters accept only "
                "server-declared module keys, never component or symptom names."
            ),
            args_schema=RunRecipeInput,
        ),
        StructuredTool.from_function(
            func=toolset.run_safe_sql,
            name="run_safe_sql",
            description=(
                "Execute SQLGlot-validated SELECT SQL on v1 security views only. "
                "Requires an explicit reason no recipe matches."
            ),
            args_schema=RunSafeSqlInput,
        ),
        StructuredTool.from_function(
            func=toolset.search_analysis_context,
            name="search_analysis_context",
            description="Search recipe and analysis schema metadata.",
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            func=toolset.search_legacy_evidence,
            name="search_legacy_evidence",
            description="Search final-ACL-authorized legacy issue evidence.",
            args_schema=SearchInput,
        ),
    )


__all__ = [
    "AnalysisToolset",
    "RunRecipeInput",
    "RunSafeSqlInput",
    "SearchInput",
    "build_langchain_tools",
]
