from open_work_hub_api.core.workspace_app_registry import workspace_app_registration


# Home is the platform landing surface, so its registration is owned by auth/shell.
HOME_WORKSPACE_APP = workspace_app_registration("home")
