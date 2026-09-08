from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Any

TASK_UPDATE_NULLABLE_FIELDS = frozenset(
    {
        "assignee_id",
        "milestone_id",
        "start_date",
        "due_date",
        "completed_date",
        "recurrence_rule",
    }
)


@dataclass(frozen=True)
class TaskScalarFieldSpec:
    field_name: str
    activity_message: str

    @property
    def nullable(self) -> bool:
        return self.field_name in TASK_UPDATE_NULLABLE_FIELDS


@dataclass(frozen=True)
class TaskScalarUpdate:
    field_name: str
    activity_message: str
    previous_value: Any
    next_value: Any


TASK_UPDATE_SCALAR_FIELD_SPECS = (
    TaskScalarFieldSpec("title", "updated title"),
    TaskScalarFieldSpec("description", "updated description"),
    TaskScalarFieldSpec("status", "changed status"),
    TaskScalarFieldSpec("priority", "changed priority"),
    TaskScalarFieldSpec("assignee_id", "changed assignee"),
    TaskScalarFieldSpec("milestone_id", "changed milestone"),
    TaskScalarFieldSpec("start_date", "updated start date"),
    TaskScalarFieldSpec("due_date", "updated due date"),
    TaskScalarFieldSpec("completed_date", "updated completion date"),
    TaskScalarFieldSpec("board_position", "reordered board position"),
    TaskScalarFieldSpec("archived", "changed archive state"),
    TaskScalarFieldSpec("recurrence_rule", "updated recurrence"),
)


def effective_task_update_fields(provided_fields: Set[str]) -> set[str]:
    effective_fields = set(provided_fields)
    if "assignee_ids" in effective_fields:
        effective_fields.add("assignee_id")
    return effective_fields


def plan_task_scalar_updates(
    *,
    current_values: Mapping[str, Any],
    provided_fields: Set[str],
    proposed_values: Mapping[str, Any],
) -> list[TaskScalarUpdate]:
    updates: list[TaskScalarUpdate] = []
    for spec in TASK_UPDATE_SCALAR_FIELD_SPECS:
        if spec.field_name not in provided_fields:
            continue
        value = proposed_values.get(spec.field_name)
        if value is None and not spec.nullable:
            continue
        previous = current_values.get(spec.field_name)
        normalized_value = value.strip() if isinstance(value, str) else value
        if previous == normalized_value:
            continue
        updates.append(
            TaskScalarUpdate(
                field_name=spec.field_name,
                activity_message=spec.activity_message,
                previous_value=previous,
                next_value=normalized_value,
            )
        )
    return updates
