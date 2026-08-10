from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)
from open_alm_api.domains.patent_prior_art import PATENT_PRIOR_ART_APP_ID


PATENT_PRIOR_ART_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id=PATENT_PRIOR_ART_APP_ID,
    title="AI 특허 선행기술 조사",
    route_base="/patent-prior-art",
    icon_key="file-search",
    backend_domain="patent_prior_art",
    enabled_by_default=False,
    visible_by_default=False,
    launcher_category=True,
    coming_soon=False,
    nav_items=(
        WorkspaceNavRegistration(
            id=PATENT_PRIOR_ART_APP_ID,
            title="AI 특허 선행기술 조사",
            category="Patent",
            icon_key="file-search",
            coming_soon=False,
        ),
    ),
)


__all__ = ["PATENT_PRIOR_ART_WORKSPACE_APP"]
