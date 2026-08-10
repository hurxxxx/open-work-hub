from open_work_hub_api.core.workspace_app_registry import WorkspaceAppRegistration


CHATBOT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="chatbot",
    title="AI 어시스턴트",
    route_base="/chatbot",
    icon_key="message-square",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    coming_soon=True,
)
