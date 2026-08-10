from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


LEARNING_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="learning",
    title="학습",
    route_base="/learning",
    icon_key="graduation-cap",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="learning-home",
            title="전체 코스",
            category="Courses",
            icon_key="graduation-cap",
        ),
    ),
)
