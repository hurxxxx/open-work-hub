from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


FILES_WORKSPACE_APP = workspace_app_registration(
    "files",
    backend_domain="files",
    nav_items=(
        WorkspaceNavRegistration(
            id="files-all",
            title="All Files",
            category="Drive",
            icon_key="folder-open",
        ),
        WorkspaceNavRegistration(
            id="files-search",
            title="Search",
            category="Drive",
            icon_key="search",
            path_suffix="?view=search",
        ),
    ),
)
