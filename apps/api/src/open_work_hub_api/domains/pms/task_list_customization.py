from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.pms.access import (
    _ensure_list_editor,
    _ensure_list_member,
    _ensure_list_owner,
    _ensure_task_readable,
)
from open_work_hub_api.domains.pms.models import CustomField, CustomFieldValue, TaskTemplate


@dataclass(frozen=True)
class TaskTemplateDTO:
    id: str
    list_id: str
    name: str
    description: str
    default_status: str
    default_priority: str
    checklist_items: list[dict] | None
    created_at: datetime


@dataclass(frozen=True)
class CustomFieldDTO:
    id: str
    list_id: str
    name: str
    field_type: str
    options: list[str] | None
    sort_order: int


@dataclass(frozen=True)
class CustomFieldValueDTO:
    field_id: str
    value: str


def _template_dto(template: TaskTemplate) -> TaskTemplateDTO:
    return TaskTemplateDTO(
        id=template.id,
        list_id=template.list_id,
        name=template.name,
        description=template.description,
        default_status=template.default_status,
        default_priority=template.default_priority,
        checklist_items=template.checklist_items,
        created_at=template.created_at,
    )


def _custom_field_dto(field: CustomField) -> CustomFieldDTO:
    return CustomFieldDTO(
        id=field.id,
        list_id=field.list_id,
        name=field.name,
        field_type=field.field_type,
        options=field.options,
        sort_order=field.sort_order,
    )


def _custom_field_value_dto(value: CustomFieldValue) -> CustomFieldValueDTO:
    return CustomFieldValueDTO(field_id=value.field_id, value=value.value)


def list_task_templates(
    db: Session,
    *,
    user: User,
    list_id: str,
) -> list[TaskTemplateDTO]:
    _ensure_list_member(db, user, list_id)
    templates = list(
        db.scalars(
            select(TaskTemplate)
            .where(TaskTemplate.list_id == list_id)
            .order_by(TaskTemplate.created_at.desc())
        )
    )
    return [_template_dto(template) for template in templates]


def create_task_template(
    db: Session,
    *,
    user: User,
    list_id: str,
    name: str,
    description: str,
    default_status: str,
    default_priority: str,
    checklist_items: list[dict] | None,
) -> TaskTemplateDTO:
    _ensure_list_editor(db, user, list_id)
    template = TaskTemplate(
        id=new_id(),
        list_id=list_id,
        name=name.strip(),
        description=description.strip(),
        default_status=default_status,
        default_priority=default_priority,
        checklist_items=checklist_items,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _template_dto(template)


def update_task_template(
    db: Session,
    *,
    user: User,
    template_id: str,
    name: str | None = None,
    description: str | None = None,
    default_status: str | None = None,
    default_priority: str | None = None,
    checklist_items: list[dict] | None = None,
) -> TaskTemplateDTO:
    template = db.scalar(select(TaskTemplate).where(TaskTemplate.id == template_id))
    if template is None:
        raise localized_http_exception(status_code=404, code="pms.template_not_found")
    _ensure_list_editor(db, user, template.list_id)

    if name is not None:
        template.name = name.strip()
    if description is not None:
        template.description = description.strip()
    if default_status is not None:
        template.default_status = default_status
    if default_priority is not None:
        template.default_priority = default_priority
    if checklist_items is not None:
        template.checklist_items = checklist_items

    db.commit()
    db.refresh(template)
    return _template_dto(template)


def delete_task_template(
    db: Session,
    *,
    user: User,
    template_id: str,
) -> None:
    template = db.scalar(select(TaskTemplate).where(TaskTemplate.id == template_id))
    if template is None:
        raise localized_http_exception(status_code=404, code="pms.template_not_found")
    _ensure_list_editor(db, user, template.list_id)
    db.delete(template)
    db.commit()


def list_custom_fields(
    db: Session,
    *,
    user: User,
    list_id: str,
) -> list[CustomFieldDTO]:
    _ensure_list_member(db, user, list_id)
    fields = list(
        db.scalars(
            select(CustomField)
            .where(CustomField.list_id == list_id)
            .order_by(CustomField.sort_order)
        )
    )
    return [_custom_field_dto(field) for field in fields]


def create_custom_field(
    db: Session,
    *,
    user: User,
    list_id: str,
    name: str,
    field_type: str,
    options: list[str] | None,
    sort_order: int,
) -> CustomFieldDTO:
    _ensure_list_owner(db, user, list_id)
    field = CustomField(
        id=new_id(),
        list_id=list_id,
        name=name.strip(),
        field_type=field_type,
        options=options,
        sort_order=sort_order,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return _custom_field_dto(field)


def delete_custom_field(
    db: Session,
    *,
    user: User,
    field_id: str,
) -> None:
    field = db.scalar(select(CustomField).where(CustomField.id == field_id))
    if field is None:
        raise localized_http_exception(status_code=404, code="pms.custom_field_not_found")
    _ensure_list_owner(db, user, field.list_id)
    db.execute(delete(CustomFieldValue).where(CustomFieldValue.field_id == field_id))
    db.delete(field)
    db.commit()


def list_task_custom_field_values(
    db: Session,
    *,
    user: User,
    task_id: str,
) -> list[CustomFieldValueDTO]:
    task = _ensure_task_readable(db, user, task_id)
    values = list(db.scalars(select(CustomFieldValue).where(CustomFieldValue.task_id == task.id)))
    return [_custom_field_value_dto(value) for value in values]


def set_task_custom_field_value(
    db: Session,
    *,
    user: User,
    task_id: str,
    field_id: str,
    value: str,
) -> CustomFieldValueDTO:
    task = _ensure_task_readable(db, user, task_id)
    _ensure_list_editor(db, user, task.list_id)

    field = db.scalar(select(CustomField).where(CustomField.id == field_id))
    if field is None or field.list_id != task.list_id:
        raise localized_http_exception(status_code=400, code="pms.custom_field_wrong_list")

    existing = db.scalar(
        select(CustomFieldValue).where(
            CustomFieldValue.task_id == task.id,
            CustomFieldValue.field_id == field_id,
        )
    )
    if existing:
        existing.value = value
        result = existing
    else:
        result = CustomFieldValue(
            id=new_id(),
            task_id=task.id,
            field_id=field_id,
            value=value,
        )
        db.add(result)
    db.commit()
    return _custom_field_value_dto(result)
