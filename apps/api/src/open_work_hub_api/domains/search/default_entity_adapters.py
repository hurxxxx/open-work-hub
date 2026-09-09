from __future__ import annotations

from open_work_hub_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    register_search_entity_adapter,
)


def ensure_search_entity_adapters_registered() -> None:
    from open_work_hub_api.domains.docs.search_projection import (
        DOCS_KEYWORD_SEARCH_ADAPTER,
    )
    from open_work_hub_api.domains.files.search_projection import (
        FILES_KEYWORD_SEARCH_ADAPTER,
    )
    from open_work_hub_api.domains.meeting.search_projection import (
        MEETING_KEYWORD_SEARCH_ADAPTER,
    )
    from open_work_hub_api.domains.pms.search_projection import (
        PMS_KEYWORD_SEARCH_ADAPTER,
    )

    for adapter in (
        DOCS_KEYWORD_SEARCH_ADAPTER,
        FILES_KEYWORD_SEARCH_ADAPTER,
        MEETING_KEYWORD_SEARCH_ADAPTER,
        PMS_KEYWORD_SEARCH_ADAPTER,
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
