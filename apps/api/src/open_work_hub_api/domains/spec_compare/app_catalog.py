from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


SPEC_COMPARE_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="spec-compare",
    title="규격서 비교",
    route_base="/spec-compare",
    icon_key="file-search",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="spec-compare",
            title="규격서 비교",
            category="Core Tools",
            icon_key="file-search",
        ),
    ),
)
