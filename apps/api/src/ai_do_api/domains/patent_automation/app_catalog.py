from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


PATENT_AUTOMATION_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="patent-automation",
    title="특허업무 자동화",
    route_base="/patent-automation",
    icon_key="clipboard-check",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="patent-automation",
            title="특허업무 자동화",
            category="Patent",
            icon_key="clipboard-check",
        ),
    ),
)
