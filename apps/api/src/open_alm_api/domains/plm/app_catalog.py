from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


PLM_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="plm",
    title="PLM",
    route_base="/plm",
    icon_key="database",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="plm-raw-tables",
            title="Raw Tables",
            category="PLM",
            icon_key="table-2",
        ),
        WorkspaceNavRegistration(
            id="plm-raw-sql",
            title="SQL",
            category="PLM",
            icon_key="terminal-square",
            path_suffix="?tab=sql",
        ),
    ),
)
