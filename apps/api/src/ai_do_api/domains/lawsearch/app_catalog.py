from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


LAW_SEARCH_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="law-search",
    title="법규/규제 찾기",
    route_base="/law-search",
    icon_key="scale",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="law-search",
            title="법규/규제 찾기",
            category="제품분석",
            icon_key="scale",
        ),
    ),
)
