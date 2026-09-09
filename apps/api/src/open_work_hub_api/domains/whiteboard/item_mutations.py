from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.whiteboard.models import Whiteboard, empty_scene
from open_work_hub_api.domains.whiteboard.scene_state import (
    apply_rest_scene_update,
    utcnow,
)


class WhiteboardItemAccess(Protocol):
    can_edit: bool
    can_manage: bool


@dataclass(frozen=True)
class WhiteboardItemUpdateCommand:
    whiteboard: Whiteboard
    access: WhiteboardItemAccess
    title: str | None = None
    scene: dict[str, Any] | None = None
    update_scene: bool = False


@dataclass(frozen=True)
class WhiteboardItemUpdateResult:
    whiteboard: Whiteboard
    changed: bool
    scene_changed: bool


def update_whiteboard_item(
    db: Session, command: WhiteboardItemUpdateCommand
) -> WhiteboardItemUpdateResult:
    if not command.access.can_edit:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.edit_access_required",
        )
    if command.title is not None and not command.access.can_manage:
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.manage_access_required",
        )

    whiteboard = command.whiteboard
    changed = False
    scene_changed = False

    if command.title is not None:
        title = command.title.strip()
        if title != whiteboard.title:
            whiteboard.title = title
            changed = True
    if command.update_scene:
        scene_state = apply_rest_scene_update(
            db,
            whiteboard=whiteboard,
            scene=command.scene or empty_scene(),
        )
        if scene_state.whiteboard_changed:
            changed = True
            scene_changed = True

    if changed and not scene_changed:
        whiteboard.updated_at = utcnow()
    if changed:
        db.add(whiteboard)
        db.commit()

    return WhiteboardItemUpdateResult(
        whiteboard=whiteboard,
        changed=changed,
        scene_changed=scene_changed,
    )
