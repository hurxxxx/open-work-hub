from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


IMAGE_WIZARD_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="image-wizard",
    title="이미지 위저드",
    route_base="/image-wizard",
    icon_key="image",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="image-wizard",
            title="이미지 위저드",
            category="Assistants",
            icon_key="image",
            feature_flag="image_enabled",
        ),
    ),
    feature_flag="image_enabled",
)
