from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


DOCUMENT_TRANSLATE_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="document-translate",
    title="문서 번역/요약",
    route_base="/document-translate",
    icon_key="languages",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="translate",
            title="문서 번역/요약",
            category="Core Tools",
            icon_key="languages",
        ),
    ),
)
