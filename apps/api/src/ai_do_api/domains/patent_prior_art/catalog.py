"""Data-only category anchors for the patent prior-art app.

Categories describe an optional caller-selected search scope.  Search and
ranking code consumes this catalog generically; adding a category must not add
conditionals to the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True, slots=True)
class PatentPriorArtCategoryDefinition:
    id: str
    fallback_label: str
    query_terms_ko: tuple[str, ...]
    query_terms_en: tuple[str, ...]
    classification_anchors: tuple[str, ...]

    @property
    def query_terms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.query_terms_ko, *self.query_terms_en)))


_CATEGORY_DEFINITIONS: Final = (
    PatentPriorArtCategoryDefinition(
        id="vehicle",
        fallback_label="차량 관련 기술",
        query_terms_ko=("차량", "자동차", "차량 시스템"),
        query_terms_en=("vehicle", "automotive", "vehicle system"),
        classification_anchors=("B60",),
    ),
)

PATENT_PRIOR_ART_CATEGORY_CATALOG: Final = MappingProxyType(
    {definition.id: definition for definition in _CATEGORY_DEFINITIONS}
)


def get_category_definitions(
    category_ids: tuple[str, ...] | list[str],
) -> tuple[PatentPriorArtCategoryDefinition, ...]:
    """Resolve ordered, unique category IDs or reject unsupported input."""

    resolved: list[PatentPriorArtCategoryDefinition] = []
    seen: set[str] = set()
    for raw_category_id in category_ids:
        category_id = raw_category_id.strip().lower()
        if not category_id or category_id in seen:
            continue
        try:
            definition = PATENT_PRIOR_ART_CATEGORY_CATALOG[category_id]
        except KeyError as error:
            raise ValueError(f"Unsupported patent prior-art category: {category_id}") from error
        resolved.append(definition)
        seen.add(category_id)
    return tuple(resolved)


__all__ = [
    "PATENT_PRIOR_ART_CATEGORY_CATALOG",
    "PatentPriorArtCategoryDefinition",
    "get_category_definitions",
]
