from ai_do_api.core.workspace_app_registry import WorkspaceAppRegistration


COMMUNITY_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="community",
    title="커뮤니티",
    route_base="/community",
    icon_key="message-square",
    enabled_by_default=True,
    visible_by_default=True,
    availability_scope="platform",
    launcher_category=True,
)
