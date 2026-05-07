from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.whiteboard.models import Whiteboard, WhiteboardContainer, empty_scene


def create_whiteboard_for_user(
    db: Session,
    *,
    workspace_id: str,
    owner_id: str,
    title: str,
    scene: dict[str, Any] | None = None,
    source_app: str = "whiteboard",
    source_kind: str = "manual",
    source_ref: str | None = None,
    generation_kind: str = "human",
    primary_container: tuple[str, str, str, int] | None = None,
) -> Whiteboard:
    whiteboard = Whiteboard(
        id=new_id(),
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=title.strip(),
        scene=scene or empty_scene(),
        source_app=source_app,
        source_kind=source_kind,
        source_ref=source_ref,
        generation_kind=generation_kind,
    )
    db.add(whiteboard)
    if primary_container is not None:
        container_app, container_type, container_id, sort_order = primary_container
        db.add(
            WhiteboardContainer(
                id=new_id(),
                whiteboard_id=whiteboard.id,
                container_app=container_app,
                container_type=container_type,
                container_id=container_id,
                is_primary=True,
                sort_order=sort_order,
                created_by_id=owner_id,
            )
        )
    db.flush()
    return whiteboard
