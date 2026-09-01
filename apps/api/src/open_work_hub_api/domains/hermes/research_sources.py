from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias


ResearchSourceId: TypeAlias = Literal[
    "semantic_scholar",
    "arxiv",
    "openalex",
    "crossref",
]


@dataclass(frozen=True)
class ResearchSourceDefinition:
    id: ResearchSourceId
    display_name: str
    domains: tuple[str, ...]
    default_enabled: bool


RESEARCH_SOURCE_DEFINITIONS = (
    ResearchSourceDefinition(
        id="semantic_scholar",
        display_name="Semantic Scholar",
        domains=("semanticscholar.org", ".semanticscholar.org"),
        default_enabled=False,
    ),
    ResearchSourceDefinition(
        id="arxiv",
        display_name="arXiv",
        domains=("arxiv.org", ".arxiv.org"),
        default_enabled=True,
    ),
    ResearchSourceDefinition(
        id="openalex",
        display_name="OpenAlex",
        domains=("openalex.org", ".openalex.org"),
        default_enabled=True,
    ),
    ResearchSourceDefinition(
        id="crossref",
        display_name="Crossref",
        domains=("crossref.org", ".crossref.org"),
        default_enabled=True,
    ),
)
RESEARCH_SOURCE_IDS = tuple(source.id for source in RESEARCH_SOURCE_DEFINITIONS)
DEFAULT_RESEARCH_SOURCE_POLICY: dict[ResearchSourceId, bool] = {
    source.id: source.default_enabled for source in RESEARCH_SOURCE_DEFINITIONS
}


def normalize_research_source_policy(
    value: Mapping[str, object] | None,
) -> dict[ResearchSourceId, bool]:
    if value is None:
        return dict(DEFAULT_RESEARCH_SOURCE_POLICY)
    if set(value) != set(RESEARCH_SOURCE_IDS):
        raise ValueError("The research source policy must include every managed source.")
    if any(type(value[source_id]) is not bool for source_id in RESEARCH_SOURCE_IDS):
        raise ValueError("Every research source policy value must be a boolean.")
    return {
        source_id: value[source_id]  # type: ignore[return-value]
        for source_id in RESEARCH_SOURCE_IDS
    }


def academic_research_environment_hint(
    policy: Mapping[str, object] | None,
) -> str:
    normalized = normalize_research_source_policy(policy)
    enabled = [
        source.display_name
        for source in RESEARCH_SOURCE_DEFINITIONS
        if normalized[source.id]
    ]
    disabled = [
        source.display_name
        for source in RESEARCH_SOURCE_DEFINITIONS
        if not normalized[source.id]
    ]
    if not disabled:
        return ""
    disabled_text = ", ".join(disabled)
    if enabled:
        enabled_text = ", ".join(enabled)
        disabled_verb = "is" if len(disabled) == 1 else "are"
        return (
            f"Academic research source policy: {disabled_text} {disabled_verb} disabled. "
            "Do not access or cite disabled sources, including through generic "
            f"web search. Enabled sources: {enabled_text}."
        )
    return (
        "Academic research source policy: all managed academic sources are "
        f"disabled ({disabled_text}). Do not access or cite them, including "
        "through generic web search."
    )


def disabled_research_source_domains(
    policy: Mapping[str, object] | None,
) -> tuple[str, ...]:
    normalized = normalize_research_source_policy(policy)
    return tuple(
        domain
        for source in RESEARCH_SOURCE_DEFINITIONS
        if not normalized[source.id]
        for domain in source.domains
    )
