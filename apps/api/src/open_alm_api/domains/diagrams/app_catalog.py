from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


DIAGRAMS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="diagrams",
    title="Diagrams",
    route_base="/diagrams",
    icon_key="workflow",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="diagrams-all",
            title="All Diagrams",
            category="Library",
            icon_key="workflow",
        ),
        WorkspaceNavRegistration(
            id="diagrams-mine",
            title="My Diagrams",
            category="Library",
            icon_key="user",
            path_suffix="?view=mine",
        ),
        WorkspaceNavRegistration(
            id="diagrams-archived",
            title="Archived",
            category="Library",
            icon_key="archive",
            path_suffix="?view=archived",
        ),
    ),
)
