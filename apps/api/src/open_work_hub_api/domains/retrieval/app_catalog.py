from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


RETRIEVAL_SEARCH_WORKSPACE_APP = workspace_app_registration(
    "retrieval-search",
    nav_items=(
        WorkspaceNavRegistration(
            id="retrieval-search",
            title="Retrieval 진단 검색",
            category="Business AI",
            icon_key="search",
        ),
    ),
)
