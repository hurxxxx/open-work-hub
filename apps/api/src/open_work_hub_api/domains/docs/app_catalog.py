from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

DOCS_APP = app_registration(
    "docs",
    backend_domain="docs",
    nav_items=(
        AppNavRegistration(
            id="docs-all",
            title="All Docs",
            category="Library",
            icon_key="files",
        ),
        AppNavRegistration(
            id="docs-my",
            title="My Docs",
            category="Library",
            icon_key="user",
        ),
        AppNavRegistration(
            id="docs-shared",
            title="Shared with me",
            category="Library",
            icon_key="share-2",
        ),
        AppNavRegistration(
            id="docs-private",
            title="Private",
            category="Library",
            icon_key="lock",
        ),
        AppNavRegistration(
            id="docs-notes",
            title="Meeting Notes",
            category="Library",
            icon_key="mic",
        ),
        AppNavRegistration(
            id="docs-recent",
            title="Recent Pages",
            category="Library",
            icon_key="history",
        ),
        AppNavRegistration(
            id="docs-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
