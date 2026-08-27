from open_work_hub_api.core.workspace_app_registry import WorkspaceAppRegistration


AGENT_TERMINAL_APP = WorkspaceAppRegistration(
    app_id="agent-terminal",
    title="Codex Terminal",
    route_base="/agent-terminal",
    icon_key="square-terminal",
    availability_scope="platform",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_personal_tools=True,
    feature_flag="agent_terminal_enabled",
    required_system_roles=("platform_admin",),
    backend_domain="agent_terminal",
)
