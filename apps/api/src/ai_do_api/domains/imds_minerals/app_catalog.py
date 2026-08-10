from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


IMDS_MINERALS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="imds-minerals",
    title="IMDS 책임광물 조사표",
    route_base="/imds-minerals",
    icon_key="gem",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="imds-minerals",
            title="IMDS 책임광물 조사표",
            category="Core Tools",
            icon_key="gem",
        ),
    ),
)
