from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


FILES_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="files",
    title="FILES",
    route_base="/files",
    icon_key="folder",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
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
