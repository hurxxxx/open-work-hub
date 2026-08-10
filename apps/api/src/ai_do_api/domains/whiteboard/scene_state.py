from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardCollabDocument,
    empty_scene,
)


PERSISTED_SCENE_APP_STATE_KEYS = frozenset(
    {
        "gridModeEnabled",
        "gridSize",
        "viewBackgroundColor",
    }
)


@dataclass(frozen=True)
class WhiteboardSceneStateResult:
    whiteboard_changed: bool
    collab_changed: bool
    collab: WhiteboardCollabDocument | None


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def make_whiteboard_room_key(whiteboard_id: str) -> str:
    return f"whiteboard:{whiteboard_id}"


def make_fresh_whiteboard_room_key(whiteboard_id: str) -> str:
    return f"whiteboard:{whiteboard_id}:{new_id()}"


def scene_for_compare(scene: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(scene, dict):
        scene = empty_scene()
    elements = scene.get("elements")
    app_state = scene.get("appState")
    files = scene.get("files")
    comparable_app_state = (
        {key: app_state[key] for key in PERSISTED_SCENE_APP_STATE_KEYS if key in app_state}
        if isinstance(app_state, dict)
        else {}
    )
    return {
        "elements": elements if isinstance(elements, list) else [],
        "appState": comparable_app_state,
        "files": files if isinstance(files, dict) else {},
    }


def scene_matches(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    return json.dumps(
        scene_for_compare(left), sort_keys=True, separators=(",", ":")
    ) == json.dumps(
        scene_for_compare(right),
        sort_keys=True,
        separators=(",", ":"),
    )


def get_collab_document(
    db: Session,
    *,
    whiteboard_id: str,
) -> WhiteboardCollabDocument | None:
    return db.scalar(
        select(WhiteboardCollabDocument).where(
            WhiteboardCollabDocument.whiteboard_id == whiteboard_id,
        )
    )


def ensure_collab_session_state(
    db: Session,
    *,
    whiteboard: Whiteboard,
    reset_stale_yjs_state: bool = True,
) -> WhiteboardSceneStateResult:
    room_key = make_whiteboard_room_key(whiteboard.id)
    collab = get_collab_document(db, whiteboard_id=whiteboard.id)
    snapshot_scene = whiteboard.scene or empty_scene()
    if collab is None:
        collab = WhiteboardCollabDocument(
            id=new_id(),
            room_key=room_key,
            whiteboard_id=whiteboard.id,
            snapshot_scene=snapshot_scene,
            last_snapshot_at=whiteboard.updated_at,
        )
        db.add(collab)
        db.flush()
        return WhiteboardSceneStateResult(
            whiteboard_changed=False,
            collab_changed=True,
            collab=collab,
        )

    if collab.snapshot_scene is None:
        collab.snapshot_scene = snapshot_scene
        collab.last_snapshot_at = whiteboard.updated_at
        db.add(collab)
        db.flush()
        return WhiteboardSceneStateResult(
            whiteboard_changed=False,
            collab_changed=True,
            collab=collab,
        )

    if reset_stale_yjs_state and collab.updated_at < whiteboard.updated_at:
        collab.room_key = make_fresh_whiteboard_room_key(whiteboard.id)
        collab.yjs_state = None
        collab.snapshot_scene = snapshot_scene
        collab.last_snapshot_at = whiteboard.updated_at
        db.add(collab)
        db.flush()
        return WhiteboardSceneStateResult(
            whiteboard_changed=False,
            collab_changed=True,
            collab=collab,
        )

    return WhiteboardSceneStateResult(
        whiteboard_changed=False,
        collab_changed=False,
        collab=collab,
    )


def apply_rest_scene_update(
    db: Session,
    *,
    whiteboard: Whiteboard,
    scene: dict[str, Any] | None,
) -> WhiteboardSceneStateResult:
    next_scene = scene or empty_scene()
    if scene_matches(whiteboard.scene or empty_scene(), next_scene):
        return WhiteboardSceneStateResult(
            whiteboard_changed=False,
            collab_changed=False,
            collab=get_collab_document(db, whiteboard_id=whiteboard.id),
        )

    whiteboard.scene = next_scene
    whiteboard.updated_at = utcnow()
    db.add(whiteboard)

    collab = get_collab_document(db, whiteboard_id=whiteboard.id)
    if collab is None:
        return WhiteboardSceneStateResult(
            whiteboard_changed=True,
            collab_changed=False,
            collab=None,
        )

    collab.room_key = make_fresh_whiteboard_room_key(whiteboard.id)
    collab.yjs_state = None
    collab.snapshot_scene = next_scene
    collab.last_snapshot_at = utcnow()
    db.add(collab)
    db.flush()
    return WhiteboardSceneStateResult(
        whiteboard_changed=True,
        collab_changed=True,
        collab=collab,
    )


def apply_collab_snapshot(
    db: Session,
    *,
    whiteboard: Whiteboard,
    scene: dict[str, Any] | None,
    yjs_state: bytes | None,
) -> WhiteboardSceneStateResult:
    next_scene = scene or empty_scene()
    state = ensure_collab_session_state(
        db,
        whiteboard=whiteboard,
        reset_stale_yjs_state=False,
    )
    assert state.collab is not None
    collab = state.collab
    whiteboard_changed = not scene_matches(whiteboard.scene or empty_scene(), next_scene)
    collab_changed = (
        not scene_matches(collab.snapshot_scene or empty_scene(), next_scene)
        or collab.yjs_state != yjs_state
    )

    if whiteboard_changed:
        whiteboard.scene = next_scene
        whiteboard.updated_at = utcnow()
        db.add(whiteboard)
    if whiteboard_changed or collab_changed:
        collab.snapshot_scene = next_scene
        collab.yjs_state = yjs_state
        collab.last_snapshot_at = utcnow()
        db.add(collab)
        db.flush()
        collab_changed = True

    return WhiteboardSceneStateResult(
        whiteboard_changed=whiteboard_changed,
        collab_changed=collab_changed,
        collab=collab,
    )


def persist_runtime_yjs_state(
    session_factory: Any,
    *,
    whiteboard_id: str,
    yjs_state: bytes,
) -> None:
    db = session_factory()
    try:
        whiteboard = db.scalar(select(Whiteboard).where(Whiteboard.id == whiteboard_id))
        if whiteboard is None:
            return
        state = ensure_collab_session_state(
            db,
            whiteboard=whiteboard,
            reset_stale_yjs_state=False,
        )
        assert state.collab is not None
        state.collab.yjs_state = yjs_state
        db.add(state.collab)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
