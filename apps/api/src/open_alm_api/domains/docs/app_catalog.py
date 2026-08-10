from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


DOCS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="docs",
    title="DOCS",
    route_base="/docs",
    icon_key="files",
    backend_domain="docs",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    launcher_pinned_by_default=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="docs-all",
            title="All Docs",
            category="Library",
            icon_key="files",
        ),
        WorkspaceNavRegistration(
            id="docs-my",
            title="My Docs",
            category="Library",
            icon_key="user",
        ),
        WorkspaceNavRegistration(
            id="docs-shared",
            title="Shared with me",
            category="Library",
            icon_key="share-2",
        ),
        WorkspaceNavRegistration(
            id="docs-private",
            title="Private",
            category="Library",
            icon_key="lock",
        ),
        WorkspaceNavRegistration(
            id="docs-notes",
            title="Meeting Notes",
            category="Library",
            icon_key="mic",
        ),
        WorkspaceNavRegistration(
            id="docs-recent",
            title="Recent Pages",
            category="Library",
            icon_key="history",
        ),
        WorkspaceNavRegistration(
            id="docs-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
