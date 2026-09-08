from open_work_hub_api.core.app_registry import app_registration

HERMES_TERMINAL_APP = app_registration(
    "hermes-terminal",
    backend_domain="hermes_terminal",
)
