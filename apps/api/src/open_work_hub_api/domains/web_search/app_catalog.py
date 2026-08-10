from open_work_hub_api.core.workspace_app_registry import WorkspaceAppRegistration


WEB_SEARCH_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="web-search",
    title="웹 검색 봇",
    route_base="/web-search",
    icon_key="globe-2",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
)

WEB_SEARCH_WORKSPACE_APPS = (WEB_SEARCH_WORKSPACE_APP,)
