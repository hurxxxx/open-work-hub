from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


DOCS_WORKSPACE_APP = workspace_app_registration(
    "docs",
    backend_domain="docs",
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
