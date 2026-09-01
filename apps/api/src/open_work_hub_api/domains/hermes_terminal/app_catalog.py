from open_work_hub_api.core.workspace_app_registry import workspace_app_registration


HERMES_TERMINAL_APP = workspace_app_registration(
    "hermes-terminal",
    backend_domain="hermes_terminal",
)
