from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecordingTargetRef:
    target_app: str
    target_type: str
    target_id: str


@dataclass(frozen=True)
class RecordingTargetPlan:
    ref: RecordingTargetRef
    is_primary: bool
    sort_order: int | None = None


def recording_target_ref(
    target_app: str | None,
    target_type: str | None,
    target_id: str | None,
) -> RecordingTargetRef | None:
    if target_app and target_type and target_id:
        return RecordingTargetRef(
            target_app=target_app,
            target_type=target_type,
            target_id=target_id,
        )
    return None


def plan_recording_ingest_targets(
    *,
    initial_target: RecordingTargetRef | None,
    linked_task_id: str | None,
) -> list[RecordingTargetPlan]:
    if initial_target is None:
        return []

    plans = [
        RecordingTargetPlan(
            ref=initial_target,
            is_primary=True,
        )
    ]
    if (
        linked_task_id
        and initial_target.target_app == "meeting"
        and initial_target.target_type == "meeting"
    ):
        plans.append(
            RecordingTargetPlan(
                ref=RecordingTargetRef(
                    target_app="pms",
                    target_type="task",
                    target_id=linked_task_id,
                ),
                is_primary=False,
                sort_order=0,
            )
        )
    return plans
