from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.pms import service as pms_service
from open_work_hub_api.domains.pms.models import Task, TaskDocLink
from open_work_hub_api.domains.source_access import can_read_native_doc, can_read_pms_task


def _task_reference(task: Task) -> str:
    task_list = task.task_list
    return (
        f"{task_list.key}-{task.task_number}"
        if task_list is not None
        else f"PMS-{task.task_number}"
    )


def serialize_task_doc_link(link: TaskDocLink) -> dict[str, Any]:
    doc = link.doc
    return {
        "id": link.id,
        "task_id": link.task_id,
        "doc_id": link.doc_id,
        "doc_title": doc.title if doc is not None else "",
        "doc_type": doc.doc_type if doc is not None else "general",
        "source_app": doc.source_app if doc is not None else "docs",
        "source_kind": doc.source_kind if doc is not None else "manual",
        "updated_at": doc.updated_at if doc is not None else link.created_at,
        "created_by_id": link.created_by_id,
        "created_at": link.created_at,
    }


def serialize_related_pms_task_link(link: TaskDocLink) -> dict[str, Any]:
    task = link.task
    task_list = task.task_list if task is not None else None
    return {
        "id": link.id,
        "doc_id": link.doc_id,
        "task_id": link.task_id,
        "task_reference": _task_reference(task) if task is not None else "",
        "task_title": task.title if task is not None else "",
        "task_status": task.status if task is not None else "todo",
        "task_status_label": task.status.replace("_", " ").title() if task is not None else "Todo",
        "task_priority": task.priority if task is not None else "medium",
        "task_list_id": task_list.id if task_list is not None else "",
        "task_list_name": task_list.name if task_list is not None else "",
        "created_by_id": link.created_by_id,
        "created_at": link.created_at,
    }


def load_task_doc_links(db: Session, *, task_id: str) -> list[TaskDocLink]:
    return list(
        db.scalars(
            select(TaskDocLink)
            .options(joinedload(TaskDocLink.doc))
            .where(TaskDocLink.task_id == task_id)
            .order_by(TaskDocLink.created_at.asc())
        )
    )


def load_related_pms_task_links(db: Session, *, doc_id: str) -> list[TaskDocLink]:
    return list(
        db.scalars(
            select(TaskDocLink)
            .options(joinedload(TaskDocLink.task).joinedload(Task.task_list))
            .where(TaskDocLink.doc_id == doc_id)
            .order_by(TaskDocLink.created_at.asc())
        )
    )


def visible_task_doc_links(
    db: Session,
    *,
    user: User,
    links: list[TaskDocLink],
) -> list[TaskDocLink]:
    visible: list[TaskDocLink] = []
    for link in links:
        if link.doc is None or link.doc.trashed_at is not None:
            continue
        if can_read_native_doc(db, user=user, doc_id=link.doc_id):
            visible.append(link)
    return visible


def visible_related_pms_task_links(
    db: Session,
    *,
    user: User,
    links: list[TaskDocLink],
) -> list[TaskDocLink]:
    visible: list[TaskDocLink] = []
    for link in links:
        if link.task is None or link.task.archived:
            continue
        if can_read_pms_task(db, user=user, task_id=link.task_id):
            visible.append(link)
    return visible


def visible_task_doc_link_items(
    db: Session,
    *,
    user: User,
    task_id: str,
) -> list[dict[str, Any]]:
    links = visible_task_doc_links(
        db,
        user=user,
        links=load_task_doc_links(db, task_id=task_id),
    )
    return [serialize_task_doc_link(link) for link in links]


def visible_related_pms_task_items(
    db: Session,
    *,
    user: User,
    doc_id: str,
) -> list[dict[str, Any]]:
    links = visible_related_pms_task_links(
        db,
        user=user,
        links=load_related_pms_task_links(db, doc_id=doc_id),
    )
    return [serialize_related_pms_task_link(link) for link in links]


def load_readable_doc_for_task_link(db: Session, *, user: User, doc_id: str) -> NativeDoc:
    doc = db.scalar(select(NativeDoc).where(NativeDoc.id == doc_id, NativeDoc.trashed_at.is_(None)))
    if doc is None:
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    if not can_read_native_doc(db, user=user, doc_id=doc.id):
        raise localized_http_exception(status_code=403, code="docs.doc_access_required")
    return doc


def ensure_task_linkable_from_doc(db: Session, *, user: User, task_id: str) -> None:
    if not can_read_pms_task(db, user=user, task_id=task_id):
        raise localized_http_exception(status_code=403, code="pms.task_access_required")


def attach_doc_to_task(
    db: Session,
    *,
    user: User,
    task: Task,
    doc_id: str,
) -> None:
    doc = load_readable_doc_for_task_link(db, user=user, doc_id=doc_id)
    existing = db.scalar(
        select(TaskDocLink).where(TaskDocLink.task_id == task.id, TaskDocLink.doc_id == doc.id)
    )
    if existing is not None:
        return
    db.add(
        TaskDocLink(
            id=new_id(),
            task_id=task.id,
            doc_id=doc.id,
            created_by_id=user.id,
        )
    )
    pms_service._log_task_activity(
        db,
        task.id,
        user.id,
        "doc_linked",
        f"{user.full_name} linked doc {doc.title} to {_task_reference(task)}.",
    )
    db.commit()


def detach_doc_from_task(
    db: Session,
    *,
    user: User,
    task: Task,
    doc_id: str,
) -> None:
    link = db.scalar(
        select(TaskDocLink).where(TaskDocLink.task_id == task.id, TaskDocLink.doc_id == doc_id)
    )
    if link is None:
        return
    db.delete(link)
    pms_service._log_task_activity(
        db,
        task.id,
        user.id,
        "doc_unlinked",
        f"{user.full_name} removed a linked doc from {_task_reference(task)}.",
    )
    db.commit()


def attach_task_to_doc(
    db: Session,
    *,
    user: User,
    doc: NativeDoc,
    task_id: str,
) -> None:
    ensure_task_linkable_from_doc(
        db,
        user=user,
        task_id=task_id,
    )
    existing = db.scalar(
        select(TaskDocLink).where(TaskDocLink.doc_id == doc.id, TaskDocLink.task_id == task_id)
    )
    if existing is not None:
        return
    db.add(
        TaskDocLink(
            id=new_id(),
            doc_id=doc.id,
            task_id=task_id,
            created_by_id=user.id,
        )
    )
    db.commit()


def detach_task_from_doc(
    db: Session,
    *,
    user: User,
    doc: NativeDoc,
    task_id: str,
) -> None:
    link = db.scalar(
        select(TaskDocLink).where(TaskDocLink.doc_id == doc.id, TaskDocLink.task_id == task_id)
    )
    if link is None:
        return
    ensure_task_linkable_from_doc(
        db,
        user=user,
        task_id=task_id,
    )
    db.delete(link)
    db.commit()
