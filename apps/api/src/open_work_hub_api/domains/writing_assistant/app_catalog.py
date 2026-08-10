from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


EMAIL_ASSISTANT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="email-assistant",
    title="메일 작성 도우미",
    route_base="/email-assistant",
    icon_key="mail",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="email-assistant",
            title="메일 작성 도우미",
            category="Assistants",
            icon_key="mail",
        ),
    ),
)
