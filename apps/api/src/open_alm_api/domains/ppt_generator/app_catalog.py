from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


PPT_ASSISTANT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="ppt-assistant",
    title="PPT 자동 생성",
    route_base="/ppt-assistant",
    icon_key="presentation",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="ppt-assistant",
            title="PPT 자동 생성",
            category="Assistants",
            icon_key="presentation",
        ),
    ),
)
