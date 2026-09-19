from sqlalchemy import delete, func, select, update

from .errors import ConsoleError
from .models import (
    Attachment,
    Event,
    Item,
    MessageAttachment,
    Operation,
    PendingRequest,
    Revision,
    Task,
    WorkspaceLease,
    now,
)

ACTIVE = ("starting", "running", "waiting")


def require_task(db, task_id: str, *, locked: bool = False) -> Task:
    query = select(Task).where(Task.id == task_id)
    if locked:
        query = query.with_for_update()
    task = db.scalar(query)
    if task is None:
        raise ConsoleError("task_not_found", 404)
    return task


def latest_revision(db, task_id, kind):
    return db.scalar(
        select(Revision)
        .where(Revision.task_id == task_id, Revision.kind == kind)
        .order_by(Revision.version.desc())
        .limit(1)
    )


def save_revision(db, task: Task, kind: str, body: str):
    previous = latest_revision(db, task.id, kind)
    if previous and previous.body == body:
        return previous
    row = Revision(
        task_id=task.id,
        kind=kind,
        version=previous.version + 1 if previous else 1,
        body=body[:100000],
    )
    task.approved_revision = None
    db.add(row)
    db.flush()
    changed(db, task, "document.updated")
    return row


def changed(db, task, kind):
    task.updated_at = now()
    db.add(Event(task_id=task.id, kind=kind))


def lease(db, task_id):
    row = db.scalar(select(WorkspaceLease).where(WorkspaceLease.id == 1).with_for_update())
    if row is None or row.task_id is not None:
        raise ConsoleError("workspace_busy")
    row.task_id = task_id


def release(db, task_id):
    db.execute(update(WorkspaceLease).where(WorkspaceLease.task_id == task_id).values(task_id=None))


def invalidate_pending(db, task_id):
    db.execute(
        update(PendingRequest)
        .where(PendingRequest.task_id == task_id, PendingRequest.state.in_(("pending", "sending")))
        .values(state="expired")
    )


def task_out(task):
    return {
        "id": task.id,
        "title": task.title,
        "stage": task.stage,
        "status": task.status,
        "thread_id": task.thread_id,
        "turn_id": task.turn_id,
        "root": task.root,
        "isolated": task.worktree_owned,
        "approved_revision": task.approved_revision,
        "error_code": task.error_code,
        "updated_at": task.updated_at.isoformat(),
    }


def attachment_out(row):
    return {"id": row.id, "name": row.name, "size": row.size, "deleted": row.deleted_at is not None}


def detail(factory, task_id, settings):
    from .attachments import limits

    with factory() as db:
        task = require_task(db, task_id)
        recent = list(
            db.scalars(
                select(Item).where(Item.task_id == task_id).order_by(Item.id.desc()).limit(2001)
            )
        )
        items = [dict(row.payload) for row in reversed(recent[:2000])]
        message_ids = [
            i["clientId"] for i in items if i.get("type") == "userMessage" and i.get("clientId")
        ]
        operations = {
            o.id: o
            for o in db.scalars(
                select(Operation).where(
                    Operation.task_id == task_id,
                    Operation.id.in_(message_ids),
                )
            )
        }
        references = {}
        for operation_id, row in db.execute(
            select(MessageAttachment.operation_id, Attachment)
            .join(Attachment, Attachment.id == MessageAttachment.attachment_id)
            .where(MessageAttachment.operation_id.in_(operations))
            .order_by(MessageAttachment.position)
        ):
            references.setdefault(operation_id, []).append(attachment_out(row))
        for item in items:
            if item.get("type") == "userMessage" and (
                operation := operations.get(item.get("clientId"))
            ):
                if operation.display_text is not None:
                    item["content"] = [{"type": "text", "text": operation.display_text}]
                item["attachments"] = references.get(operation.id, [])
        return {
            **task_out(task),
            "revisions": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "version": r.version,
                    "body": r.body,
                    "created_at": r.created_at.isoformat(),
                }
                for r in db.scalars(
                    select(Revision).where(Revision.task_id == task_id).order_by(Revision.id)
                )
            ],
            "items": items,
            "attachments": [
                attachment_out(row)
                for row in db.scalars(
                    select(Attachment)
                    .where(
                        Attachment.task_id == task_id,
                        Attachment.deleted_at.is_(None),
                    )
                    .order_by(Attachment.created_at, Attachment.id)
                )
            ],
            "attachment_limits": limits(settings),
            "history_truncated": len(recent) > 2000,
            "requests": [
                {"id": r.id, "method": r.method, "payload": r.payload}
                for r in db.scalars(
                    select(PendingRequest).where(
                        PendingRequest.task_id == task_id, PendingRequest.state == "pending"
                    )
                )
            ],
            "event_id": db.scalar(select(func.max(Event.id)).where(Event.task_id == task_id)) or 0,
        }


def upsert_item(db, task, turn_id, payload):
    item_id = payload.get("id")
    if not isinstance(item_id, str) or len(item_id) > 200:
        return
    # Reasoning internals and opaque tool arguments are not part of this UI's history projection.
    kind = payload.get("type")
    keys = {
        "userMessage": ("id", "clientId", "type", "content"),
        "agentMessage": ("id", "type", "text", "phase"),
        "plan": ("id", "type", "text"),
        "commandExecution": (
            "id",
            "type",
            "command",
            "cwd",
            "status",
            "aggregatedOutput",
            "exitCode",
            "durationMs",
        ),
        "fileChange": ("id", "type", "status", "changes"),
    }.get(kind)
    if not keys:
        return
    safe = {key: payload[key] for key in keys if key in payload}
    for key in ("text", "aggregatedOutput"):
        if isinstance(safe.get(key), str):
            safe[key] = safe[key][-100000:]
    row = db.scalar(select(Item).where(Item.task_id == task.id, Item.item_id == item_id))
    if row:
        row.payload = safe
    else:
        db.add(Item(task_id=task.id, item_id=item_id, turn_id=turn_id, payload=safe))


def reconcile_history(db, task, turns):
    # The official thread is canonical. The projection is replaceable, never fed back as history.
    db.execute(delete(Item).where(Item.task_id == task.id))
    for turn in turns[-100:]:
        for item in turn.get("items", []):
            upsert_item(db, task, turn["id"], item)
            if item.get("type") == "userMessage" and item.get("clientId"):
                db.execute(
                    update(Operation)
                    .where(
                        Operation.id == item["clientId"],
                        Operation.task_id == task.id,
                    )
                    .values(state="accepted")
                )


def recover_startup(factory):
    with factory.begin() as db:
        for task in db.scalars(select(Task).where(Task.status.in_(ACTIVE))):
            preparing = db.scalar(
                select(Operation.id)
                .where(
                    Operation.task_id == task.id,
                    Operation.state == "preparing",
                    Operation.kind != "steer",
                )
                .limit(1)
            )
            if task.status == "starting" and preparing:
                task.status, task.error_code = "failed", "execution_failed"
                release(db, task.id)
            else:
                task.status, task.error_code = "uncertain", "runtime_restarted"
            invalidate_pending(db, task.id)
            changed(db, task, "runtime.restarted")
        db.execute(update(Operation).where(Operation.state == "preparing").values(state="failed"))
        db.execute(
            update(Operation)
            .where(
                Operation.state.in_(("pending", "submitting")),
            )
            .values(state="uncertain")
        )
