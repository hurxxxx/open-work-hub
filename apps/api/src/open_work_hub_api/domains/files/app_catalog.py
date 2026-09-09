from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

FILES_APP = app_registration(
    "files",
    backend_domain="files",
    nav_items=(
        AppNavRegistration(
            id="files-all",
            title="All Files",
            category="Drive",
            icon_key="folder-open",
        ),
        AppNavRegistration(
            id="files-search",
            title="Search",
            category="Drive",
            icon_key="search",
            path_suffix="?view=search",
        ),
    ),
)
