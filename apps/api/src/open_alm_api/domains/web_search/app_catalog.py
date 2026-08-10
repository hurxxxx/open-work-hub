from open_alm_api.core.workspace_app_registry import WorkspaceAppRegistration


WEB_SEARCH_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="web-search",
    title="웹 검색 봇",
    route_base="/web-search",
    icon_key="globe-2",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
)

RESEARCH_TRENDS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="research-trends",
    title="논문·기술동향",
    route_base="/research-trends",
    icon_key="book-open",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
)

STANDARDS_MONITOR_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="standards-monitor",
    title="규격·법규 모니터링",
    route_base="/standards-monitor",
    icon_key="scale",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
)

WEB_SEARCH_WORKSPACE_APPS = (
    WEB_SEARCH_WORKSPACE_APP,
    RESEARCH_TRENDS_WORKSPACE_APP,
    STANDARDS_MONITOR_WORKSPACE_APP,
)
