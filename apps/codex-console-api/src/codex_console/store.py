from sqlalchemy import delete, func, select, update

from . import planning
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
from .rpc import MAX_MESSAGE_BYTES

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


def save_revision(db, task: Task, kind: str, body: str, *, source_turn_id=None):
    if source_turn_id:
        projected = db.scalar(
            select(Revision).where(
                Revision.task_id == task.id,
                Revision.kind == kind,
                Revision.source_turn_id == source_turn_id,
            )
        )
        if projected:
            return projected
    previous = latest_revision(db, task.id, kind)
    if previous and previous.body == body and not source_turn_id:
        requirements = latest_revision(db, task.id, "requirements") if kind == "plan" else None
        if requirements is None or requirements.created_at <= previous.created_at:
            return previous
    row = Revision(
        task_id=task.id,
        kind=kind,
        version=previous.version + 1 if previous else 1,
        body=body[:100000],
        source_turn_id=source_turn_id,
    )
    task.approved_revision = None
    db.add(row)
    db.flush()
    changed(db, task, "document.updated")
    return row


def project_document(db, task, turn_id, items):
    if task.stage != "plan":
        return
    final = [
        i for i in items if i.get("type") == "agentMessage" and i.get("phase") == "final_answer"
    ]
    final = final or [i for i in items if i.get("type") == "plan"]
    result = planning.parse(final[-1].get("text", "")) if final else None
    if result is None:
        task.error_code = "planning_output_invalid"
        changed(db, task, "document.rejected")
        return
    kinds = [update.kind for update in result.documents]
    if len(kinds) != len(set(kinds)):
        task.error_code = "planning_output_invalid"
        changed(db, task, "document.rejected")
        return
    pending = []
    for document in result.documents:
        if db.scalar(
            select(Revision.id).where(
                Revision.task_id == task.id,
                Revision.kind == document.kind,
                Revision.source_turn_id == turn_id,
            )
        ):
            continue
        latest = latest_revision(db, task.id, document.kind)
        if (latest.version if latest else 0) != document.base_version:
            task.error_code = "document_conflict"
            changed(db, task, "document.rejected")
            return
        pending.append(document)
    # A plan based on this same confirmed change must be newer than its requirements.
    for document in sorted(pending, key=lambda document: document.kind == "plan"):
        save_revision(db, task, document.kind, document.body, source_turn_id=turn_id)


def recover_document(db, task, turns):
    if task.stage != "plan":
        return
    operation = db.get(Operation, task.current_operation_id) if task.current_operation_id else None
    if not operation or operation.task_id != task.id or operation.kind != task.stage:
        return
    submitted_at = (
        db.scalar(
            select(Event.created_at)
            .where(Event.task_id == task.id, Event.kind == "turn.submitting")
            .order_by(Event.id.desc())
            .limit(1)
        )
        or operation.created_at
    )
    # Preserve later user edits, including records created before turn provenance
    # was introduced. Recovery never reinterprets an older turn as a new plan.
    if db.scalar(
        select(Revision.id)
        .where(Revision.task_id == task.id, Revision.created_at >= submitted_at)
        .limit(1)
    ):
        return
    for turn in reversed(turns):
        if turn.get("status") != "completed":
            continue
        items = turn.get("items", [])
        if (task.turn_id and turn.get("id") == task.turn_id) or any(
            item.get("type") == "userMessage" and item.get("clientId") == operation.id
            for item in items
        ):
            project_document(db, task, turn["id"], items)
            return


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


def implementation_authorized(db, task):
    if task.stage != "implement":
        return False
    if task.approved_revision:
        return True
    operation = db.get(Operation, task.current_operation_id) if task.current_operation_id else None
    return bool(
        operation
        and operation.task_id == task.id
        and operation.kind == "execute"
        and operation.state == "accepted"
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
        "model": task.model,
        "effort": task.effort,
        "permissions": task.permissions,
        "progress": task.progress,
    }


def attachment_out(row):
    return {"id": row.id, "name": row.name, "size": row.size, "deleted": row.deleted_at is not None}


def detail(factory, task_id, settings):
    from .attachments import limits

    with factory() as db:
        # The event cursor must describe the same snapshot as every projected row.
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        task = require_task(db, task_id)
        recent = list(
            db.scalars(
                select(Item).where(Item.task_id == task_id).order_by(Item.id.desc()).limit(2001)
            )
        )
        items = [{**row.payload, "turn_id": row.turn_id} for row in reversed(recent[:2000])]
        for item in items:
            if item.get("type") in ("agentMessage", "plan"):
                result = planning.parse(item.get("text", ""))
                if result:
                    item["text"] = result.answer
                    item["document_updates"] = [
                        {"kind": document.kind, "summary": document.summary}
                        for document in result.documents
                    ]
                elif (
                    task.stage == "plan"
                    and task.status in ACTIVE
                    and item["turn_id"] == task.turn_id
                    and item.get("phase") == "final_answer"
                ):
                    item["text"] = ""
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
        failed = db.get(Operation, task.current_operation_id) if task.current_operation_id else None
        return {
            **task_out(task),
            "failed_request_text": failed.display_text
            if failed and failed.state == "failed" and task.status == "failed"
            else None,
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


def bounded_item_text(task, payload, key, value):
    # Structured planning finals contain an answer and up to two full documents.
    # Keep the transport byte bound without applying the command-output tail limit.
    if (
        key == "text"
        and (
            payload.get("type") == "plan"
            or (
                payload.get("type") == "agentMessage"
                and payload.get("phase") in (None, "final_answer")
            )
        )
    ):
        bounded = value.encode("utf-8")[:MAX_MESSAGE_BYTES].decode("utf-8", errors="ignore")
        if task.stage == "plan" or planning.parse(bounded) is not None:
            return bounded
    return value[-100000:]


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
            safe[key] = bounded_item_text(task, safe, key, safe[key])
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
