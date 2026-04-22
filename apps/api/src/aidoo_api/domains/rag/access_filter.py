from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from aidoo_api.domains.auth.models import User
from aidoo_api.domains.docs.service import can_read_native_doc_for_rag
from aidoo_api.domains.meeting.service import can_read_meeting_for_rag
from aidoo_api.domains.planner.service import can_read_planner_event_for_rag
from aidoo_api.domains.pms.access import can_read_issue_for_rag
from aidoo_api.domains.rag.contracts import RagVectorSearchHit
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from aidoo_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE
from aidoo_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE
from aidoo_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE


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
    projection = hit.projection
    if projection.resource_type == NATIVE_DOC_RESOURCE_TYPE:
        return can_read_native_doc_for_rag(db, user=user, doc_id=projection.resource_id)
    if projection.resource_type == PMS_ISSUE_RESOURCE_TYPE:
        return can_read_issue_for_rag(db, user=user, issue_id=projection.resource_id)
    if projection.resource_type == MEETING_RESOURCE_TYPE:
        return can_read_meeting_for_rag(
            db,
            user=user,
            workspace_id=projection.workspace_id,
            meeting_id=projection.resource_id,
        )
    if projection.resource_type == PLANNER_EVENT_RESOURCE_TYPE:
        return can_read_planner_event_for_rag(
            db,
            user=user,
            workspace_id=projection.workspace_id,
            event_id=projection.resource_id,
        )
    return False
