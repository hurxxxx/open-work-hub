from open_work_hub_api.core.app_registry import app_registration

AGENT_TERMINAL_APP = app_registration(
    "agent-terminal",
    backend_domain="agent_terminal",
)
