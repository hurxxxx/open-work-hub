from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.params import Depends as DependsParam

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.admin.ai_model_settings_router import (
    router as admin_ai_model_settings_router,
)
from open_work_hub_api.domains.admin.app_access_router import router as admin_app_access_router
from open_work_hub_api.domains.admin.document_processing_router import (
    router as admin_document_processing_router,
)
from open_work_hub_api.domains.admin.model_runtime_status_router import (
    router as admin_model_runtime_status_router,
)
from open_work_hub_api.domains.admin.router import router as admin_router
from open_work_hub_api.domains.agent_terminal.router import (
    router as agent_terminal_router,
)
from open_work_hub_api.domains.agent_terminal.router import (
    ws_router as agent_terminal_ws_router,
)
from open_work_hub_api.domains.ai.router import router as ai_router
from open_work_hub_api.domains.ai_artifacts.router import router as ai_artifacts_router
from open_work_hub_api.domains.ai_graph.router import router as ai_graph_router
from open_work_hub_api.domains.announcements.router import router as announcements_router
from open_work_hub_api.domains.auth.apps_router import router as apps_router
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.router import router as auth_router
from open_work_hub_api.domains.bento.router import router as bento_router
from open_work_hub_api.domains.calendar.router import router as calendar_router
from open_work_hub_api.domains.community.router import router as community_router
from open_work_hub_api.domains.content_access.router import router as content_access_router
from open_work_hub_api.domains.diagrams.router import router as diagrams_router
from open_work_hub_api.domains.dm.router import router as dm_router
from open_work_hub_api.domains.docs.group_sharing import router as docs_group_sharing_router
from open_work_hub_api.domains.docs.router import router as docs_router
from open_work_hub_api.domains.docs.router import ws_router as docs_ws_router
from open_work_hub_api.domains.files.router import router as files_router
from open_work_hub_api.domains.groups.admin_router import router as admin_groups_router
from open_work_hub_api.domains.groups.directory_router import router as directory_router
from open_work_hub_api.domains.hermes.admin_router import router as admin_hermes_router
from open_work_hub_api.domains.hermes.mcp_router import router as hermes_mcp_router
from open_work_hub_api.domains.hermes.router import router as hermes_router
from open_work_hub_api.domains.hermes_terminal.router import (
    router as hermes_terminal_router,
)
from open_work_hub_api.domains.hermes_terminal.router import (
    ws_router as hermes_terminal_ws_router,
)
from open_work_hub_api.domains.integrations.admin_router import (
    router as admin_platform_api_keys_router,
)
from open_work_hub_api.domains.integrations.directory_router import (
    router as directory_integrations_router,
)
from open_work_hub_api.domains.mail.router import router as mail_router
from open_work_hub_api.domains.media.router import router as media_router
from open_work_hub_api.domains.meeting.router import router as meeting_router
from open_work_hub_api.domains.notifications.router import router as notifications_router
from open_work_hub_api.domains.ocr.router import router as ocr_router
from open_work_hub_api.domains.organization.admin_router import (
    router as admin_organization_router,
)
from open_work_hub_api.domains.personal_widgets.router import router as personal_widgets_router
from open_work_hub_api.domains.planner.router import router as planner_router
from open_work_hub_api.domains.pms.group_bindings import router as pms_group_bindings_router
from open_work_hub_api.domains.pms.router import router as pms_router
from open_work_hub_api.domains.rag.router import router as rag_router
from open_work_hub_api.domains.realtime.router import ws_router as realtime_ws_router
from open_work_hub_api.domains.recording.router import router as recording_router
from open_work_hub_api.domains.release_notes.router import router as release_notes_router
from open_work_hub_api.domains.retrieval.router import router as retrieval_router
from open_work_hub_api.domains.search.router import router as search_router
from open_work_hub_api.domains.usage.router import router as usage_router
from open_work_hub_api.domains.video_chat.router import router as video_chat_router
from open_work_hub_api.domains.web_search.router import router as web_search_router
from open_work_hub_api.domains.whiteboard.group_sharing import (
    router as whiteboard_group_sharing_router,
)
from open_work_hub_api.domains.whiteboard.router import router as whiteboard_router
from open_work_hub_api.domains.whiteboard.router import ws_router as whiteboard_ws_router
from open_work_hub_api.openapi_contract import PROTECTED_ERROR_RESPONSES

_RouterProtection = Literal["public", "protected"]


@dataclass(frozen=True)
class _RouterSpec:
    router: APIRouter
    protection: _RouterProtection = "public"


def _include_protected_router(
    app: FastAPI,
    router: APIRouter,
    *,
    prefix: str,
    dependencies: Sequence[DependsParam],
) -> None:
    app.include_router(
        router,
        prefix=prefix,
        dependencies=dependencies,
        responses=PROTECTED_ERROR_RESPONSES,
    )


def _include_router_spec(
    app: FastAPI,
    spec: _RouterSpec,
    *,
    api_prefix: str,
    protected_dependencies: Sequence[DependsParam],
) -> None:
    if spec.protection == "public":
        app.include_router(spec.router, prefix=api_prefix)
    else:
        _include_protected_router(
            app, spec.router, prefix=api_prefix, dependencies=protected_dependencies
        )


def _router_specs() -> list[_RouterSpec]:
    return [
        _RouterSpec(apps_router, "protected"),
        _RouterSpec(ai_router, "protected"),
        _RouterSpec(ai_graph_router, "protected"),
        _RouterSpec(ai_artifacts_router, "protected"),
        _RouterSpec(agent_terminal_router, "protected"),
        _RouterSpec(agent_terminal_ws_router),
        _RouterSpec(admin_router, "protected"),
        _RouterSpec(admin_ai_model_settings_router, "protected"),
        _RouterSpec(admin_document_processing_router, "protected"),
        _RouterSpec(admin_model_runtime_status_router, "protected"),
        _RouterSpec(admin_hermes_router, "protected"),
        _RouterSpec(admin_organization_router, "protected"),
        _RouterSpec(admin_groups_router, "protected"),
        _RouterSpec(directory_router, "protected"),
        _RouterSpec(admin_app_access_router, "protected"),
        _RouterSpec(admin_platform_api_keys_router, "protected"),
        _RouterSpec(directory_integrations_router),
        _RouterSpec(usage_router, "protected"),
        _RouterSpec(dm_router, "protected"),
        _RouterSpec(content_access_router),
        _RouterSpec(release_notes_router, "protected"),
        _RouterSpec(realtime_ws_router),
        _RouterSpec(notifications_router, "protected"),
        _RouterSpec(personal_widgets_router, "protected"),
        _RouterSpec(docs_router, "protected"),
        _RouterSpec(docs_group_sharing_router, "protected"),
        _RouterSpec(whiteboard_router, "protected"),
        _RouterSpec(whiteboard_group_sharing_router, "protected"),
        _RouterSpec(bento_router, "protected"),
        _RouterSpec(diagrams_router, "protected"),
        _RouterSpec(docs_ws_router),
        _RouterSpec(whiteboard_ws_router),
        _RouterSpec(files_router, "protected"),
        _RouterSpec(hermes_router, "protected"),
        _RouterSpec(hermes_mcp_router),
        _RouterSpec(hermes_terminal_router, "protected"),
        _RouterSpec(hermes_terminal_ws_router),
        _RouterSpec(ocr_router, "protected"),
        _RouterSpec(pms_router, "protected"),
        _RouterSpec(pms_group_bindings_router, "protected"),
        _RouterSpec(meeting_router, "protected"),
        _RouterSpec(video_chat_router, "protected"),
        _RouterSpec(recording_router, "protected"),
        _RouterSpec(calendar_router, "protected"),
        _RouterSpec(community_router, "protected"),
        _RouterSpec(planner_router, "protected"),
        _RouterSpec(announcements_router, "protected"),
        _RouterSpec(retrieval_router, "protected"),
        _RouterSpec(rag_router, "protected"),
        _RouterSpec(web_search_router, "protected"),
        _RouterSpec(mail_router, "protected"),
        _RouterSpec(search_router, "protected"),
        _RouterSpec(media_router, "protected"),
    ]


def register_api_routers(app: FastAPI, settings: Settings) -> None:
    app.include_router(auth_router, prefix=settings.api_prefix)
    for spec in _router_specs():
        _include_router_spec(
            app,
            spec,
            api_prefix=settings.api_prefix,
            protected_dependencies=[Depends(require_current_user)],
        )
