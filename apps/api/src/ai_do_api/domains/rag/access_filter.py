from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import User
from ai_do_api.domains.docs.service import can_read_native_doc_for_rag
from ai_do_api.domains.meeting.service import can_read_meeting_for_rag
from ai_do_api.domains.planner.service import can_read_planner_event_for_rag
from ai_do_api.domains.pms.access import can_read_issue_for_rag
from ai_do_api.domains.rag.contracts import RagVectorSearchHit
from ai_do_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from ai_do_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE
from ai_do_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE
from ai_do_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE


def build_user_rag_post_filter(
    db: Session,
    *,
    user: User,
) -> Callable[[RagVectorSearchHit], bool]:
    def _filter(hit: RagVectorSearchHit) -> bool:
        return can_user_access_hit(db, user=user, hit=hit)

    return _filter


def can_user_access_hit(
    db: Session,
    *,
    user: User,
    hit: RagVectorSearchHit,
) -> bool:
    return can_user_access_resource(
        db,
        user=user,
        workspace_id=hit.projection.workspace_id,
        resource_type=hit.projection.resource_type,
        resource_id=hit.projection.resource_id,
    )


def can_user_access_resource(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
) -> bool:
    if resource_type == NATIVE_DOC_RESOURCE_TYPE:
        return can_read_native_doc_for_rag(db, user=user, doc_id=resource_id)
    if resource_type == PMS_ISSUE_RESOURCE_TYPE:
        return can_read_issue_for_rag(db, user=user, issue_id=resource_id)
    if resource_type == MEETING_RESOURCE_TYPE:
        return can_read_meeting_for_rag(
            db,
            user=user,
            workspace_id=workspace_id,
            meeting_id=resource_id,
        )
    if resource_type == PLANNER_EVENT_RESOURCE_TYPE:
        return can_read_planner_event_for_rag(
            db,
            user=user,
            workspace_id=workspace_id,
            event_id=resource_id,
        )
    return False
