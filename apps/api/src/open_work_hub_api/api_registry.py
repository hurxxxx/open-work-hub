from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.params import Depends as DependsParam

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.ai.router import router as ai_router
from open_work_hub_api.domains.ai_artifacts.router import router as ai_artifacts_router
from open_work_hub_api.domains.ai_graph.router import router as ai_graph_router
from open_work_hub_api.domains.admin.router import router as admin_router
from open_work_hub_api.domains.admin.ai_model_settings_router import (
    router as admin_ai_model_settings_router,
)
from open_work_hub_api.domains.admin.document_processing_router import (
    router as admin_document_processing_router,
)
from open_work_hub_api.domains.admin.image_model_settings_router import (
    router as admin_image_model_settings_router,
)
from open_work_hub_api.domains.admin.model_runtime_status_router import (
    router as admin_model_runtime_status_router,
)
from open_work_hub_api.domains.announcements.router import router as announcements_router
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    require_workspace_membership,
)
from open_work_hub_api.domains.auth.router import router as auth_router
from open_work_hub_api.domains.auth.apps_router import router as apps_router
from open_work_hub_api.domains.auth.workspace_router import router as workspace_router
from open_work_hub_api.domains.calendar.router import router as calendar_router
from open_work_hub_api.domains.community.router import router as community_router
from open_work_hub_api.domains.docs.router import public_router as docs_public_router
from open_work_hub_api.domains.docs.router import router as docs_router
from open_work_hub_api.domains.docs.router import ws_router as docs_ws_router
from open_work_hub_api.domains.documents.router import router as documents_router
from open_work_hub_api.domains.diagrams.router import router as diagrams_router
from open_work_hub_api.domains.dm.router import public_router as dm_public_router
from open_work_hub_api.domains.dm.router import router as dm_router
from open_work_hub_api.domains.files.router import public_router as files_public_router
from open_work_hub_api.domains.files.router import router as files_router
from open_work_hub_api.domains.images.router import router as images_router
from open_work_hub_api.domains.mail.router import router as mail_router
from open_work_hub_api.domains.media.router import public_router as media_public_router
from open_work_hub_api.domains.media.router import router as media_router
from open_work_hub_api.domains.meeting.router import public_router as meeting_public_router
from open_work_hub_api.domains.meeting.router import router as meeting_router
from open_work_hub_api.domains.notifications.router import router as notifications_router
from open_work_hub_api.domains.ocr.router import router as ocr_router
from open_work_hub_api.domains.personal_widgets.router import router as personal_widgets_router
from open_work_hub_api.domains.planner.router import router as planner_router
from open_work_hub_api.domains.pms.router import public_router as pms_public_router
from open_work_hub_api.domains.pms.router import router as pms_router
from open_work_hub_api.domains.rag.router import router as rag_router
from open_work_hub_api.domains.release_notes.router import router as release_notes_router
from open_work_hub_api.domains.recording.router import router as recording_router
from open_work_hub_api.domains.realtime.router import ws_router as realtime_ws_router
from open_work_hub_api.domains.retrieval.router import router as retrieval_router
from open_work_hub_api.domains.search.router import router as search_router
from open_work_hub_api.domains.usage.router import router as usage_router
from open_work_hub_api.domains.video_chat.router import router as video_chat_router
from open_work_hub_api.domains.web_search.router import router as web_search_router
from open_work_hub_api.domains.writing_assistant.router import router as writing_assistant_router
from open_work_hub_api.domains.whiteboard.router import public_router as whiteboard_public_router
from open_work_hub_api.domains.whiteboard.router import router as whiteboard_router
from open_work_hub_api.domains.whiteboard.router import ws_router as whiteboard_ws_router
from open_work_hub_api.domains.wiki_pms.router import router as wiki_pms_router
from open_work_hub_api.openapi_contract import PROTECTED_ERROR_RESPONSES

_RouterPrefix = Literal["api", "workspace"]
_RouterProtection = Literal["public", "protected", "workspace"]


@dataclass(frozen=True)
class _RouterSpec:
    router: APIRouter
    prefix: _RouterPrefix
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
    workspace_prefix: str,
    protected_dependencies: Sequence[DependsParam],
    workspace_dependencies: Sequence[DependsParam],
) -> None:
    prefix = workspace_prefix if spec.prefix == "workspace" else api_prefix
    if spec.protection == "public":
        app.include_router(spec.router, prefix=prefix)
        return
    dependencies = (
        workspace_dependencies if spec.protection == "workspace" else protected_dependencies
    )
    _include_protected_router(
        app,
        spec.router,
        prefix=prefix,
        dependencies=dependencies,
    )


def _router_specs() -> list[_RouterSpec]:
    return [
        _RouterSpec(apps_router, "api", "protected"),
        _RouterSpec(workspace_router, "api", "workspace"),
        _RouterSpec(ai_router, "workspace", "workspace"),
        _RouterSpec(ai_graph_router, "workspace", "workspace"),
        _RouterSpec(ai_artifacts_router, "workspace", "workspace"),
        _RouterSpec(admin_router, "api", "protected"),
        _RouterSpec(admin_ai_model_settings_router, "api", "protected"),
        _RouterSpec(admin_image_model_settings_router, "api", "protected"),
        _RouterSpec(admin_document_processing_router, "api", "protected"),
        _RouterSpec(admin_model_runtime_status_router, "api", "protected"),
        _RouterSpec(usage_router, "api", "protected"),
        _RouterSpec(dm_router, "api", "protected"),
        _RouterSpec(dm_public_router, "api"),
        _RouterSpec(release_notes_router, "api", "protected"),
        _RouterSpec(realtime_ws_router, "api"),
        _RouterSpec(notifications_router, "api", "protected"),
        _RouterSpec(personal_widgets_router, "api", "protected"),
        _RouterSpec(documents_router, "workspace", "workspace"),
        _RouterSpec(docs_public_router, "api", "protected"),
        _RouterSpec(docs_router, "workspace", "workspace"),
        _RouterSpec(whiteboard_public_router, "api", "protected"),
        _RouterSpec(whiteboard_router, "workspace", "workspace"),
        _RouterSpec(diagrams_router, "workspace", "workspace"),
        _RouterSpec(docs_ws_router, "workspace"),
        _RouterSpec(whiteboard_ws_router, "workspace"),
        _RouterSpec(files_router, "workspace", "workspace"),
        _RouterSpec(files_public_router, "api"),
        _RouterSpec(ocr_router, "workspace", "workspace"),
        _RouterSpec(wiki_pms_router, "workspace", "workspace"),
        _RouterSpec(pms_public_router, "api"),
        _RouterSpec(pms_router, "workspace", "workspace"),
        _RouterSpec(meeting_public_router, "api"),
        _RouterSpec(meeting_router, "workspace", "workspace"),
        _RouterSpec(video_chat_router, "workspace", "workspace"),
        _RouterSpec(recording_router, "workspace", "workspace"),
        _RouterSpec(images_router, "workspace", "workspace"),
        _RouterSpec(calendar_router, "api", "protected"),
        _RouterSpec(community_router, "api", "protected"),
        _RouterSpec(planner_router, "api", "protected"),
        _RouterSpec(announcements_router, "workspace", "workspace"),
        _RouterSpec(retrieval_router, "workspace", "workspace"),
        _RouterSpec(rag_router, "workspace", "workspace"),
        _RouterSpec(web_search_router, "workspace", "workspace"),
        _RouterSpec(mail_router, "api", "protected"),
        _RouterSpec(search_router, "workspace", "workspace"),
        _RouterSpec(writing_assistant_router, "workspace", "workspace"),
        _RouterSpec(media_router, "api", "protected"),
        _RouterSpec(media_public_router, "api"),
    ]


def register_api_routers(app: FastAPI, settings: Settings) -> None:
    app.include_router(auth_router, prefix=settings.api_prefix)
    protected_dependencies = [Depends(require_current_user)]
    workspace_dependencies = [
        *protected_dependencies,
        Depends(require_workspace_membership()),
    ]
    workspace_prefix = f"{settings.api_prefix}/workspaces/{{workspace_slug}}"
    for spec in _router_specs():
        _include_router_spec(
            app,
            spec,
            api_prefix=settings.api_prefix,
            workspace_prefix=workspace_prefix,
            protected_dependencies=protected_dependencies,
            workspace_dependencies=workspace_dependencies,
        )
