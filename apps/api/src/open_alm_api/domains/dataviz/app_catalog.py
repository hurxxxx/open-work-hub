from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


DATA_VIZ_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="data-viz",
    title="데이터 시각화",
    route_base="/data-viz",
    icon_key="bar-chart-3",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="data-viz",
            title="데이터 시각화",
            category="business-apps",
            icon_key="bar-chart-3",
        ),
    ),
)
