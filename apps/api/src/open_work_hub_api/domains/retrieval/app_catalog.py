from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

RETRIEVAL_SEARCH_APP = app_registration(
    "retrieval-search",
    nav_items=(
        AppNavRegistration(
            id="retrieval-search",
            title="Retrieval 진단 검색",
            category="Business AI",
            icon_key="search",
        ),
    ),
)
