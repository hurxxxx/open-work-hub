from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.content_access.ownership import record_ownership_transition
from open_work_hub_api.domains.whiteboard.models import Whiteboard, WhiteboardTarget, empty_scene


@dataclass(frozen=True)
class WhiteboardPrimaryTargetInput:
    app: str
    type: str
    id: str
    sort_order: int


PrimaryTargetInput = WhiteboardPrimaryTargetInput | tuple[str, str, str, int]


def normalize_primary_target_input(
    value: PrimaryTargetInput,
) -> WhiteboardPrimaryTargetInput:
    if isinstance(value, WhiteboardPrimaryTargetInput):
        return value
    target_app, target_type, target_id, sort_order = value
    return WhiteboardPrimaryTargetInput(
        app=target_app,
        type=target_type,
        id=target_id,
        sort_order=sort_order,
    )


def create_whiteboard_for_user(
    db: Session,
    *,
    owner_id: str,
    title: str,
    scene: dict[str, Any] | None = None,
    source_app: str = "whiteboard",
    source_kind: str = "manual",
    source_ref: str | None = None,
    generation_kind: str = "human",
    primary_target: PrimaryTargetInput | None = None,
    company_admin_read_acknowledged: bool = False,
) -> Whiteboard:
    whiteboard = Whiteboard(
        id=new_id(),
        owner_id=owner_id,
        title=title.strip(),
        scene=scene or empty_scene(),
        source_app=source_app,
        source_kind=source_kind,
        source_ref=source_ref,
        generation_kind=generation_kind,
    )
    db.add(whiteboard)
    if primary_target is not None:
        record_ownership_transition(
            db,
            actor_user_id=owner_id,
            resource_kind="whiteboard",
            resource_id=whiteboard.id,
            current_kind="personal",
            next_kind="company",
            company_admin_read_acknowledged=company_admin_read_acknowledged,
        )
        whiteboard.ownership_kind = "company"
        target = normalize_primary_target_input(primary_target)
        db.add(
            WhiteboardTarget(
                id=new_id(),
                whiteboard_id=whiteboard.id,
                target_app=target.app,
                target_type=target.type,
                target_id=target.id,
                is_primary=True,
                sort_order=target.sort_order,
                created_by_id=owner_id,
            )
        )
    db.flush()
    return whiteboard
