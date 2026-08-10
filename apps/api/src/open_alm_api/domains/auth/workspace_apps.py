from __future__ import annotations

from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppCatalogItem,
    WorkspaceAppRegistration,
    WorkspaceNavCatalogItem,
    compile_workspace_app_registry,
)
from open_alm_api.domains.community.app_catalog import COMMUNITY_WORKSPACE_APP
from open_alm_api.domains.commute.app_catalog import PERSONAL_ATTENDANCE_WORKSPACE_APP
from open_alm_api.domains.conversations.app_catalog import CHATBOT_WORKSPACE_APP
from open_alm_api.domains.dataviz.app_catalog import DATA_VIZ_WORKSPACE_APP
from open_alm_api.domains.diagrams.app_catalog import DIAGRAMS_WORKSPACE_APP
from open_alm_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP
from open_alm_api.domains.document_translate.app_catalog import (
    DOCUMENT_TRANSLATE_WORKSPACE_APP,
)
from open_alm_api.domains.files.app_catalog import FILES_WORKSPACE_APP
from open_alm_api.domains.fmea_compare.app_catalog import FMEA_COMPARE_WORKSPACE_APP
from open_alm_api.domains.images.app_catalog import IMAGE_WIZARD_WORKSPACE_APP
from open_alm_api.domains.imds_minerals.app_catalog import IMDS_MINERALS_WORKSPACE_APP
from open_alm_api.domains.lawsearch.app_catalog import LAW_SEARCH_WORKSPACE_APP
from open_alm_api.domains.learning_notes.app_catalog import LEARNING_WORKSPACE_APP
from open_alm_api.domains.legacy_issues.app_catalog import LEGACY_ISSUES_WORKSPACE_APP
from open_alm_api.domains.mail.app_catalog import MAIL_WORKSPACE_APP
from open_alm_api.domains.management_tasks.app_catalog import (
    MANAGEMENT_TASKS_WORKSPACE_APP,
)
from open_alm_api.domains.meal_invoice_ocr.app_catalog import (
    MEAL_INVOICE_OCR_WORKSPACE_APP,
)
from open_alm_api.domains.meeting.app_catalog import MEETING_WORKSPACE_APP
from open_alm_api.domains.news.app_catalog import NEWS_WORKSPACE_APP
from open_alm_api.domains.patent.app_catalog import PATENT_WORKSPACE_APPS
from open_alm_api.domains.patent_automation.app_catalog import (
    PATENT_AUTOMATION_WORKSPACE_APP,
)
from open_alm_api.domains.patent_prior_art.app_catalog import (
    PATENT_PRIOR_ART_WORKSPACE_APP,
)
from open_alm_api.domains.planner.app_catalog import PLANNER_WORKSPACE_APP
from open_alm_api.domains.plm.app_catalog import PLM_WORKSPACE_APP
from open_alm_api.domains.pms.app_catalog import PMS_WORKSPACE_APP
from open_alm_api.domains.ppt_generator.app_catalog import PPT_ASSISTANT_WORKSPACE_APP
from open_alm_api.domains.qna.app_catalog import QA_ASSISTANT_WORKSPACE_APP
from open_alm_api.domains.recording.app_catalog import RECORDING_WORKSPACE_APP
from open_alm_api.domains.retrieval.app_catalog import RETRIEVAL_SEARCH_WORKSPACE_APP
from open_alm_api.domains.spec_compare.app_catalog import SPEC_COMPARE_WORKSPACE_APP
from open_alm_api.domains.video_chat.app_catalog import VIDEO_CHAT_WORKSPACE_APP
from open_alm_api.domains.web_search.app_catalog import WEB_SEARCH_WORKSPACE_APPS
from open_alm_api.domains.whiteboard.app_catalog import WHITEBOARD_WORKSPACE_APP
from open_alm_api.domains.writing_assistant.app_catalog import (
    DRAFTING_WORKSPACE_APP,
    EMAIL_ASSISTANT_WORKSPACE_APP,
)

from .home_app_catalog import HOME_WORKSPACE_APP


_WORKSPACE_APP_REGISTRATIONS = (
    HOME_WORKSPACE_APP,
    CHATBOT_WORKSPACE_APP,
    *WEB_SEARCH_WORKSPACE_APPS,
    PMS_WORKSPACE_APP,
    DOCS_WORKSPACE_APP,
    FILES_WORKSPACE_APP,
    MAIL_WORKSPACE_APP,
    MANAGEMENT_TASKS_WORKSPACE_APP,
    COMMUNITY_WORKSPACE_APP,
    PLM_WORKSPACE_APP,
    WHITEBOARD_WORKSPACE_APP,
    DIAGRAMS_WORKSPACE_APP,
    PLANNER_WORKSPACE_APP,
    PERSONAL_ATTENDANCE_WORKSPACE_APP,
    MEETING_WORKSPACE_APP,
    VIDEO_CHAT_WORKSPACE_APP,
    RECORDING_WORKSPACE_APP,
    LEARNING_WORKSPACE_APP,
    NEWS_WORKSPACE_APP,
    DRAFTING_WORKSPACE_APP,
    DOCUMENT_TRANSLATE_WORKSPACE_APP,
    SPEC_COMPARE_WORKSPACE_APP,
    FMEA_COMPARE_WORKSPACE_APP,
    IMDS_MINERALS_WORKSPACE_APP,
    IMAGE_WIZARD_WORKSPACE_APP,
    EMAIL_ASSISTANT_WORKSPACE_APP,
    PPT_ASSISTANT_WORKSPACE_APP,
    RETRIEVAL_SEARCH_WORKSPACE_APP,
    LAW_SEARCH_WORKSPACE_APP,
    *PATENT_WORKSPACE_APPS,
    PATENT_PRIOR_ART_WORKSPACE_APP,
    PATENT_AUTOMATION_WORKSPACE_APP,
    MEAL_INVOICE_OCR_WORKSPACE_APP,
    DATA_VIZ_WORKSPACE_APP,
    LEGACY_ISSUES_WORKSPACE_APP,
    QA_ASSISTANT_WORKSPACE_APP,
)
_WORKSPACE_APP_REGISTRY = compile_workspace_app_registry(_WORKSPACE_APP_REGISTRATIONS)
_WORKSPACE_APP_REGISTRATIONS_BY_ID = {
    registration.app_id: registration for registration in _WORKSPACE_APP_REGISTRATIONS
}

WORKSPACE_APP_CATALOG = _WORKSPACE_APP_REGISTRY.catalog
WORKSPACE_APP_IDS = _WORKSPACE_APP_REGISTRY.app_ids
WORKSPACE_APP_BAR_FIXED_APP_IDS = _WORKSPACE_APP_REGISTRY.launcher_fixed_app_ids
WORKSPACE_APP_BAR_PINNED_BY_DEFAULT_APP_IDS = (
    _WORKSPACE_APP_REGISTRY.launcher_pinned_by_default_app_ids
)
WORKSPACE_APP_BAR_PERSONAL_TOOLS_APP_IDS = _WORKSPACE_APP_REGISTRY.launcher_personal_tools_app_ids


def iter_workspace_app_catalog() -> tuple[WorkspaceAppCatalogItem, ...]:
    return WORKSPACE_APP_CATALOG


def get_workspace_app_catalog_item(app_id: str) -> WorkspaceAppCatalogItem | None:
    return _WORKSPACE_APP_REGISTRY.by_app_id.get(app_id)


def get_workspace_app_registration(app_id: str) -> WorkspaceAppRegistration | None:
    return _WORKSPACE_APP_REGISTRATIONS_BY_ID.get(app_id)


__all__ = [
    "WORKSPACE_APP_CATALOG",
    "WORKSPACE_APP_BAR_FIXED_APP_IDS",
    "WORKSPACE_APP_BAR_PINNED_BY_DEFAULT_APP_IDS",
    "WORKSPACE_APP_BAR_PERSONAL_TOOLS_APP_IDS",
    "WORKSPACE_APP_IDS",
    "WorkspaceAppCatalogItem",
    "WorkspaceAppRegistration",
    "WorkspaceNavCatalogItem",
    "get_workspace_app_catalog_item",
    "get_workspace_app_registration",
    "iter_workspace_app_catalog",
]
