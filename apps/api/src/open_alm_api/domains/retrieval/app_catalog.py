from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


RETRIEVAL_SEARCH_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="retrieval-search",
    title="Retrieval 진단 검색",
    route_base="/retrieval-search",
    icon_key="search",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="retrieval-search",
            title="Retrieval 진단 검색",
            category="Business AI",
            icon_key="search",
        ),
    ),
)
