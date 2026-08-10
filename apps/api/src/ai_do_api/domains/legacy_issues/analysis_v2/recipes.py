from __future__ import annotations

import json
import re
from datetime import date
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from typing import Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    create_model,
    model_validator,
)

from ai_do_api.domains.legacy_issues.analysis_v2.contracts import RecipeReference
from ai_do_api.domains.legacy_issues.analysis_v2.sql_policy import (
    SafeSqlPolicy,
    ValidatedSql,
)
from ai_do_api.domains.legacy_issues.analysis_v2.views import ANALYSIS_VIEW_CONTRACTS


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_QUALIFIED_COLUMN = re.compile(r"^(?:[a-z][a-z0-9_]{0,79}\.)?[a-z][a-z0-9_]{0,79}$")
_TEMPLATE_TOKEN = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
_BIND_PARAMETER = re.compile(r"(?<!:):([a-z][a-z0-9_]*)")


class RecipeBootstrapError(ValueError):
    pass


class RecipeValueType(StrEnum):
    STRING = "string"
    STRING_LIST = "string_list"
    DATE = "date"
    INTEGER = "integer"
    BOOLEAN = "boolean"


class ParameterPlacement(StrEnum):
    IDENTIFIER = "identifier"
    LITERAL = "literal"
    BIND = "bind"
    FILTER = "filter"


class FilterOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class RecipeParameterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    value_type: RecipeValueType
    placement: ParameterPlacement
    description: str = Field(min_length=1, max_length=240)
    required: bool = False
    default: Any = None
    allowed_values: tuple[str, ...] = Field(default=(), max_length=64)
    minimum: int | None = None
    maximum: int | None = None
    column: str | None = Field(default=None, pattern=r"^(?:[a-z][a-z0-9_]*\.)?[a-z][a-z0-9_]*$")
    operator: FilterOperator | None = None

    @model_validator(mode="after")
    def _validate_placement(self) -> RecipeParameterSpec:
        if self.placement in {
            ParameterPlacement.IDENTIFIER,
            ParameterPlacement.LITERAL,
        }:
            if self.value_type != RecipeValueType.STRING or not self.allowed_values:
                raise ValueError(
                    "identifier/literal parameter requires string allowed_values"
                )
            if self.column is not None or self.operator is not None:
                raise ValueError(
                    "identifier/literal parameter cannot declare a filter"
                )
        elif self.placement == ParameterPlacement.FILTER:
            if self.column is None or self.operator is None:
                raise ValueError("filter parameter requires column and operator")
            if self.operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
                if self.value_type != RecipeValueType.STRING_LIST:
                    raise ValueError("IN filters require string_list parameters")
            elif self.operator in {
                FilterOperator.IS_NULL,
                FilterOperator.IS_NOT_NULL,
            }:
                if self.value_type != RecipeValueType.BOOLEAN:
                    raise ValueError("NULL filters require boolean parameters")
            elif self.value_type == RecipeValueType.STRING_LIST:
                raise ValueError("string_list parameters require IN or NOT IN")
        elif self.column is not None or self.operator is not None:
            raise ValueError("bind parameter cannot declare a filter")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum cannot exceed maximum")
        return self


class RecipeMetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    description: str = Field(min_length=1, max_length=300)
    numerator_column: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,79}$",
    )
    denominator_column: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,79}$",
    )


class AnalysisRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=800)
    result_shape: Literal["scalar", "table", "timeseries", "detail", "comparison"]
    counting_unit: Literal["issues", "checklists", "checklist_items", "mixed"]
    source_views: tuple[str, ...] = Field(min_length=1, max_length=3)
    sql_template: str = Field(min_length=1, max_length=20_000)
    parameters: tuple[RecipeParameterSpec, ...] = Field(default=(), max_length=32)
    metrics: tuple[RecipeMetricDefinition, ...] = Field(default=(), max_length=16)
    tags: tuple[str, ...] = Field(default=(), max_length=24)

    @model_validator(mode="after")
    def _validate_unique_parameters(self) -> AnalysisRecipe:
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("recipe parameter names must be unique")
        return self

    @property
    def reference(self) -> RecipeReference:
        return RecipeReference(recipe_id=self.recipe_id, version=self.version)


class RenderedRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    recipe: AnalysisRecipe
    sql: str
    arguments: dict[str, Any]
    bindings: dict[str, Any]
    validated_sql: ValidatedSql


class RecipeCatalog:
    def __init__(
        self,
        recipes: tuple[AnalysisRecipe, ...],
        *,
        sql_policy: SafeSqlPolicy | None = None,
        expected_count: int | None = None,
    ) -> None:
        self._policy = sql_policy or SafeSqlPolicy()
        self._recipes = {(item.recipe_id, item.version): item for item in recipes}
        if len(self._recipes) != len(recipes):
            raise RecipeBootstrapError("duplicate recipe id/version")
        if expected_count is not None and len(recipes) != expected_count:
            raise RecipeBootstrapError(
                f"expected {expected_count} recipes, loaded {len(recipes)}"
            )
        self._parameter_models: dict[tuple[str, int], type[BaseModel]] = {}
        self.bootstrap_validate()

    @classmethod
    def load_default(cls) -> RecipeCatalog:
        recipe_root = resources.files(__package__).joinpath("assets", "recipes")
        recipes: list[AnalysisRecipe] = []
        filenames: set[str] = set()
        for entry in sorted(recipe_root.iterdir(), key=lambda item: item.name):
            if not entry.name.endswith(".yaml"):
                continue
            if entry.name in filenames:
                raise RecipeBootstrapError(f"duplicate recipe asset: {entry.name}")
            filenames.add(entry.name)
            try:
                # JSON is a strict YAML 1.2 subset. Keeping recipe assets in this
                # subset avoids a second parser and makes bootstrap deterministic.
                payload = json.loads(entry.read_text(encoding="utf-8"))
                recipes.append(AnalysisRecipe.model_validate(payload))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise RecipeBootstrapError(f"invalid recipe asset: {entry.name}") from exc
        return cls(tuple(recipes))

    def bootstrap_validate(self) -> None:
        for recipe in self._recipes.values():
            self._validate_recipe_contract(recipe)
            model = self.parameter_model(recipe.recipe_id, recipe.version)
            bootstrap_values: dict[str, Any] = {}
            for parameter in recipe.parameters:
                if parameter.required and parameter.default is None:
                    if parameter.allowed_values:
                        bootstrap_values[parameter.name] = parameter.allowed_values[0]
                    elif parameter.value_type == RecipeValueType.DATE:
                        bootstrap_values[parameter.name] = date(2000, 1, 1)
                    elif parameter.value_type == RecipeValueType.INTEGER:
                        bootstrap_values[parameter.name] = parameter.minimum or 1
                    elif parameter.value_type == RecipeValueType.BOOLEAN:
                        bootstrap_values[parameter.name] = False
                    elif parameter.value_type == RecipeValueType.STRING_LIST:
                        bootstrap_values[parameter.name] = ["bootstrap"]
                    else:
                        bootstrap_values[parameter.name] = "bootstrap"
            validated = model.model_validate(bootstrap_values).model_dump(exclude_none=True)
            self._render_validated(recipe, validated)

    def all(self) -> tuple[AnalysisRecipe, ...]:
        return tuple(
            sorted(self._recipes.values(), key=lambda item: (item.recipe_id, item.version))
        )

    def get(self, recipe_id: str, version: int = 1) -> AnalysisRecipe:
        try:
            return self._recipes[(recipe_id, version)]
        except KeyError as exc:
            raise KeyError(f"unknown analysis recipe: {recipe_id}@{version}") from exc

    def parameter_model(self, recipe_id: str, version: int = 1) -> type[BaseModel]:
        key = (recipe_id, version)
        cached = self._parameter_models.get(key)
        if cached is not None:
            return cached
        recipe = self.get(recipe_id, version)
        fields: dict[str, tuple[Any, Any]] = {}
        for spec in recipe.parameters:
            annotation = _parameter_annotation(spec)
            default: Any
            if spec.required and spec.default is None:
                default = ...
            else:
                default = spec.default
            field = Field(
                default=default,
                description=spec.description,
                ge=spec.minimum,
                le=spec.maximum,
                min_length=(
                    1 if spec.value_type in {RecipeValueType.STRING, RecipeValueType.STRING_LIST}
                    else None
                ),
                max_length=(
                    50
                    if spec.value_type == RecipeValueType.STRING_LIST
                    else 240 if spec.value_type == RecipeValueType.STRING else None
                ),
            )
            fields[spec.name] = (annotation, field)
        model_name = "".join(part.title() for part in recipe.recipe_id.split("_"))
        model = create_model(
            f"{model_name}V{recipe.version}Parameters",
            __config__=ConfigDict(extra="forbid", frozen=True),
            **fields,
        )
        self._parameter_models[key] = model
        return model

    def parameter_json_schema(self, recipe_id: str, version: int = 1) -> dict[str, Any]:
        return self.parameter_model(recipe_id, version).model_json_schema()

    def render(
        self,
        recipe_id: str,
        version: int,
        parameters: Mapping[str, Any],
    ) -> RenderedRecipe:
        recipe = self.get(recipe_id, version)
        validated = self.parameter_model(recipe_id, version).model_validate(
            dict(parameters)
        )
        return self._render_validated(
            recipe,
            validated.model_dump(exclude_none=True),
        )

    def metadata_documents(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "id": f"recipe:{recipe.recipe_id}:v{recipe.version}",
                "text": (
                    f"{recipe.title}\n{recipe.description}\n"
                    f"shape={recipe.result_shape}; counting_unit={recipe.counting_unit}; "
                    f"tags={', '.join(recipe.tags)}"
                ),
                "metadata": {
                    "recipe_id": recipe.recipe_id,
                    "version": recipe.version,
                    "result_shape": recipe.result_shape,
                    "counting_unit": recipe.counting_unit,
                    "source_views": list(recipe.source_views),
                    "parameter_schema": self.parameter_json_schema(
                        recipe.recipe_id,
                        recipe.version,
                    ),
                },
            }
            for recipe in self.all()
        )

    def _validate_recipe_contract(self, recipe: AnalysisRecipe) -> None:
        unknown_views = set(recipe.source_views).difference(ANALYSIS_VIEW_CONTRACTS)
        if unknown_views:
            raise RecipeBootstrapError(
                f"{recipe.recipe_id} references unknown views: {sorted(unknown_views)}"
            )
        parameters = {parameter.name: parameter for parameter in recipe.parameters}
        tokens = set(_TEMPLATE_TOKEN.findall(recipe.sql_template))
        template_names = {
            parameter.name
            for parameter in recipe.parameters
            if parameter.placement
            in {ParameterPlacement.IDENTIFIER, ParameterPlacement.LITERAL}
        }
        if tokens != template_names.union({"filters"}):
            raise RecipeBootstrapError(
                f"{recipe.recipe_id} template tokens do not match identifier parameters"
            )
        bind_names = set(_BIND_PARAMETER.findall(recipe.sql_template))
        expected_binds = {
            parameter.name
            for parameter in recipe.parameters
            if parameter.placement == ParameterPlacement.BIND
        }
        if bind_names != expected_binds:
            raise RecipeBootstrapError(
                f"{recipe.recipe_id} bind placeholders do not match bind parameters"
            )
        all_columns = set().union(
            *(ANALYSIS_VIEW_CONTRACTS[name].columns for name in recipe.source_views)
        )
        for parameter in parameters.values():
            if parameter.placement == ParameterPlacement.IDENTIFIER:
                if not set(parameter.allowed_values).issubset(all_columns):
                    raise RecipeBootstrapError(
                        f"{recipe.recipe_id}.{parameter.name} allows unknown columns"
                    )
            if parameter.placement == ParameterPlacement.FILTER:
                column = str(parameter.column)
                if (
                    not _QUALIFIED_COLUMN.fullmatch(column)
                    or column.rsplit(".", 1)[-1] not in all_columns
                ):
                    raise RecipeBootstrapError(
                        f"{recipe.recipe_id}.{parameter.name} filters unknown column"
                    )
        if ";" in recipe.sql_template:
            raise RecipeBootstrapError(f"{recipe.recipe_id} template contains semicolon")

    def _render_validated(
        self,
        recipe: AnalysisRecipe,
        values: dict[str, Any],
    ) -> RenderedRecipe:
        sql = recipe.sql_template
        bindings: dict[str, Any] = {}
        filters: list[str] = []
        for parameter in recipe.parameters:
            value = values.get(parameter.name)
            if parameter.placement in {
                ParameterPlacement.IDENTIFIER,
                ParameterPlacement.LITERAL,
            }:
                if value not in parameter.allowed_values:
                    raise RecipeBootstrapError(
                        f"{recipe.recipe_id}.{parameter.name} is not allowlisted"
                    )
                sql = sql.replace(f"{{{{{parameter.name}}}}}", str(value))
            elif parameter.placement == ParameterPlacement.BIND:
                if value is None:
                    raise RecipeBootstrapError(
                        f"{recipe.recipe_id}.{parameter.name} requires a bind value"
                    )
                bindings[parameter.name] = value
            elif value is not None:
                predicate, filter_bindings = _render_filter(parameter, value)
                filters.append(predicate)
                bindings.update(filter_bindings)
        sql = sql.replace("{{filters}}", " AND ".join(filters) if filters else "TRUE")
        validated_sql = self._policy.validate(sql, parameters=bindings)
        return RenderedRecipe(
            recipe=recipe,
            sql=validated_sql.sql,
            arguments=dict(values),
            bindings=bindings,
            validated_sql=validated_sql,
        )


def _parameter_annotation(spec: RecipeParameterSpec) -> Any:
    if spec.allowed_values:
        literal = Literal.__getitem__(tuple(spec.allowed_values))
        if spec.required:
            return literal
        return literal | None
    types: dict[RecipeValueType, Any] = {
        RecipeValueType.STRING: str,
        RecipeValueType.STRING_LIST: list[str],
        RecipeValueType.DATE: date,
        RecipeValueType.INTEGER: int,
        RecipeValueType.BOOLEAN: bool,
    }
    annotation = types[spec.value_type]
    return annotation if spec.required else annotation | None


def _render_filter(
    spec: RecipeParameterSpec,
    value: Any,
) -> tuple[str, dict[str, Any]]:
    if spec.column is None or spec.operator is None:
        raise RecipeBootstrapError(f"{spec.name} is not a filter parameter")
    if spec.operator == FilterOperator.IN or spec.operator == FilterOperator.NOT_IN:
        values = TypeAdapter(list[str]).validate_python(value)
        if not values:
            raise RecipeBootstrapError(f"{spec.name} list cannot be empty")
        names = [f"{spec.name}_{index}" for index in range(len(values))]
        operator = "IN" if spec.operator == FilterOperator.IN else "NOT IN"
        return (
            f"{spec.column} {operator} ({', '.join(f':{name}' for name in names)})",
            dict(zip(names, values, strict=True)),
        )
    if spec.operator in {FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL}:
        is_null = bool(value)
        if spec.operator == FilterOperator.IS_NOT_NULL:
            is_null = not is_null
        return f"{spec.column} IS {'NULL' if is_null else 'NOT NULL'}", {}
    operator_map = {
        FilterOperator.EQ: "=",
        FilterOperator.NEQ: "<>",
        FilterOperator.GTE: ">=",
        FilterOperator.LTE: "<=",
    }
    if spec.operator == FilterOperator.CONTAINS:
        literal = (
            str(value)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        return (
            f"{spec.column} ILIKE :{spec.name} ESCAPE '\\'",
            {spec.name: f"%{literal}%"},
        )
    return (
        f"{spec.column} {operator_map[spec.operator]} :{spec.name}",
        {spec.name: value},
    )


@lru_cache(maxsize=1)
def default_recipe_catalog() -> RecipeCatalog:
    """Load and bootstrap-validate all packaged recipes once per process."""

    return RecipeCatalog.load_default()


__all__ = [
    "AnalysisRecipe",
    "FilterOperator",
    "ParameterPlacement",
    "RecipeBootstrapError",
    "RecipeCatalog",
    "RecipeMetricDefinition",
    "RecipeParameterSpec",
    "RecipeValueType",
    "RenderedRecipe",
    "default_recipe_catalog",
]
