from open_work_hub_api.core.app_registry import app_registration

# Home is the platform landing surface, so its registration is owned by auth/shell.
HOME_APP = app_registration("home")
