from open_alm_api.core.workspace_app_registry import WorkspaceAppRegistration


QA_ASSISTANT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="qa-assistant",
    title="사내 관리팀 Q&A",
    route_base="/qa-assistant",
    icon_key="message-circle-question",
    availability_scope="platform",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    launcher_pinned_by_default=True,
)
