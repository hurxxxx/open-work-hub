from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


PATENT_COMPOSE_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="patent-compose",
    title="AI 특허 작성",
    route_base="/patent-compose",
    icon_key="gavel",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="patent-interpret",
            title="AI 특허 작성",
            category="Patent",
            icon_key="gavel",
        ),
    ),
)

PATENT_ANALYSIS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="patent-analysis",
    title="AI 특허 분석",
    route_base="/patent-analysis",
    icon_key="scan-search",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="patent-apply",
            title="AI 특허 분석",
            category="Patent",
            icon_key="scan-search",
        ),
    ),
)

PATENT_REPORT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="patent-report",
    title="AI 특허 보고서",
    route_base="/patent-report",
    icon_key="file-bar-chart",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="patent-report",
            title="AI 특허 보고서",
            category="Patent",
            icon_key="file-bar-chart",
            coming_soon=True,
        ),
    ),
    coming_soon=True,
)

PATENT_WORKSPACE_APPS = (
    PATENT_COMPOSE_WORKSPACE_APP,
    PATENT_ANALYSIS_WORKSPACE_APP,
    PATENT_REPORT_WORKSPACE_APP,
)
