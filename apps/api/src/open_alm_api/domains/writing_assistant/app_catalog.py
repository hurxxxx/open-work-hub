from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


DRAFTING_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="drafting",
    title="기안작성 도우미",
    route_base="/drafting",
    icon_key="file-text",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="drafting",
            title="기안작성 도우미",
            category="Core Tools",
            icon_key="file-text",
        ),
    ),
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
