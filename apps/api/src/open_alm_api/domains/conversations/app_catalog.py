from open_alm_api.core.workspace_app_registry import WorkspaceAppRegistration


CHATBOT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="chatbot",
    title="아이두 챗봇",
    route_base="/chatbot",
    icon_key="message-square",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    coming_soon=True,
)
