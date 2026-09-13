from __future__ import annotations

from open_work_hub_api.core.app_contracts_generated import APP_CONTRACT_BY_ID
from open_work_hub_api.core.app_registry import (
    AppCatalogItem,
    AppNavCatalogItem,
    AppRegistration,
    compile_app_registry,
)
from open_work_hub_api.domains.agent_terminal.app_catalog import AGENT_TERMINAL_APP
from open_work_hub_api.domains.bento.app_catalog import BENTO_APP
from open_work_hub_api.domains.community.app_catalog import COMMUNITY_APP
from open_work_hub_api.domains.conversations.app_catalog import CHATBOT_APP
from open_work_hub_api.domains.diagrams.app_catalog import DIAGRAMS_APP
from open_work_hub_api.domains.docs.app_catalog import DOCS_APP
from open_work_hub_api.domains.files.app_catalog import FILES_APP
from open_work_hub_api.domains.mail.app_catalog import MAIL_APP
from open_work_hub_api.domains.meeting.app_catalog import MEETING_APP
from open_work_hub_api.domains.planner.app_catalog import PLANNER_APP
from open_work_hub_api.domains.pms.app_catalog import PMS_APP
from open_work_hub_api.domains.recording.app_catalog import RECORDING_APP
from open_work_hub_api.domains.retrieval.app_catalog import RETRIEVAL_SEARCH_APP
from open_work_hub_api.domains.video_chat.app_catalog import VIDEO_CHAT_APP
from open_work_hub_api.domains.web_search.app_catalog import WEB_SEARCH_APPS
from open_work_hub_api.domains.whiteboard.app_catalog import WHITEBOARD_APP

from .home_app_catalog import HOME_APP

_APP_REGISTRATIONS = (
    HOME_APP,
    AGENT_TERMINAL_APP,
    CHATBOT_APP,
    *WEB_SEARCH_APPS,
    PMS_APP,
    DOCS_APP,
    FILES_APP,
    MAIL_APP,
    COMMUNITY_APP,
    WHITEBOARD_APP,
    DIAGRAMS_APP,
    BENTO_APP,
    PLANNER_APP,
    MEETING_APP,
    VIDEO_CHAT_APP,
    RECORDING_APP,
    RETRIEVAL_SEARCH_APP,
)
_APP_REGISTRY = compile_app_registry(
    _APP_REGISTRATIONS,
    require_generated_contract=True,
)
if set(_APP_REGISTRY.app_ids) != set(APP_CONTRACT_BY_ID):
    raise RuntimeError(
        "Backend app registrations must exactly match the generated app contract: "
        f"registered={sorted(_APP_REGISTRY.app_ids)!r}, "
        f"contract={sorted(APP_CONTRACT_BY_ID)!r}"
    )
_APP_REGISTRATIONS_BY_ID = {
    registration.app_id: registration for registration in _APP_REGISTRATIONS
}

APP_CATALOG = _APP_REGISTRY.catalog
APP_IDS = _APP_REGISTRY.app_ids
APP_BAR_FIXED_APP_IDS = _APP_REGISTRY.launcher_fixed_app_ids
APP_BAR_PINNED_BY_DEFAULT_APP_IDS = _APP_REGISTRY.launcher_pinned_by_default_app_ids
APP_BAR_PERSONAL_TOOLS_APP_IDS = _APP_REGISTRY.launcher_personal_tools_app_ids


def iter_app_catalog() -> tuple[AppCatalogItem, ...]:
    return APP_CATALOG


def get_app_catalog_item(app_id: str) -> AppCatalogItem | None:
    return _APP_REGISTRY.by_app_id.get(app_id)


def get_app_registration(app_id: str) -> AppRegistration | None:
    return _APP_REGISTRATIONS_BY_ID.get(app_id)


__all__ = [
    "APP_CATALOG",
    "APP_BAR_FIXED_APP_IDS",
    "APP_BAR_PINNED_BY_DEFAULT_APP_IDS",
    "APP_BAR_PERSONAL_TOOLS_APP_IDS",
    "APP_IDS",
    "AppCatalogItem",
    "AppRegistration",
    "AppNavCatalogItem",
    "get_app_catalog_item",
    "get_app_registration",
    "iter_app_catalog",
]
