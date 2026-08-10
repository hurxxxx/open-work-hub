from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


FMEA_COMPARE_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="fmea-compare",
    title="FMEA 비교",
    route_base="/fmea-compare",
    icon_key="alert-triangle",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="fmea-compare",
            title="FMEA 비교",
            category="Core Tools",
            icon_key="alert-triangle",
        ),
    ),
)
