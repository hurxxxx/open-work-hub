from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


BENTO_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="bento",
    title="bento/slides",
    route_base="/bento",
    icon_key="presentation",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="bento-all",
            title="All Presentations",
            category="Library",
            icon_key="presentation",
        ),
        WorkspaceNavRegistration(
            id="bento-mine",
            title="My Presentations",
            category="Library",
            icon_key="user",
        ),
        WorkspaceNavRegistration(
            id="bento-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
