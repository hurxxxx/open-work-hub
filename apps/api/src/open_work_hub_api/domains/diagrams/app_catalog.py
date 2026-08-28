from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


DIAGRAMS_WORKSPACE_APP = workspace_app_registration(
    "diagrams",
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
