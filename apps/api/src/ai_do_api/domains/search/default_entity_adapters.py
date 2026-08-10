from __future__ import annotations

from ai_do_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    register_search_entity_adapter,
)


def ensure_search_entity_adapters_registered() -> None:
    from ai_do_api.domains.docs.search_projection import (
        DOCS_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
    )
    from ai_do_api.domains.files.search_projection import (
        FILES_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
    )
    from ai_do_api.domains.meeting.search_projection import (
        MEETING_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
    )
    from ai_do_api.domains.pms.search_projection import (
        PMS_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
    )

    for adapter in (
        DOCS_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
        FILES_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
        MEETING_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
        PMS_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
    ):
        _register_default_search_entity_adapter(adapter)


def ensure_search_entity_descriptors_registered() -> None:
    ensure_search_entity_adapters_registered()


def _register_default_search_entity_adapter(adapter: SearchEntityAdapter) -> None:
    register_search_entity_adapter(adapter)


__all__ = [
    "ensure_search_entity_adapters_registered",
    "ensure_search_entity_descriptors_registered",
]
