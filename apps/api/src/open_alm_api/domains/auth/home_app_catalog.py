from open_alm_api.core.workspace_app_registry import WorkspaceAppRegistration


# Home is the platform landing surface, so its registration is owned by auth/shell.
HOME_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="home",
    title="HOME",
    route_base="/home",
    icon_key="home",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=False,
    launcher_fixed=True,
)
