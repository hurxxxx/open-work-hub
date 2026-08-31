from open_work_hub_api.core.workspace_app_registry import workspace_app_registration


AGENT_TERMINAL_APP = workspace_app_registration(
    "agent-terminal",
    backend_domain="agent_terminal",
)
