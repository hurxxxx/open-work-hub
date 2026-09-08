from __future__ import annotations

from types import SimpleNamespace

from open_work_hub_api.domains.notifications import visibility


def _notification(
    notification_id: str,
    *,
    source_id: str,
    source_type: str = "pms_task",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=notification_id,
        origin_app_id="pms",
        source_id=source_id,
        source_type=source_type,
        type="task_updated",
        user_id="user-1",
    )


def test_pms_notification_visibility_batches_app_and_source_acl(monkeypatch) -> None:
    admission_calls: list[str] = []
    authorized_resources: list[tuple[str, str]] = []

    def _allowed_apps(_db, *, user_id):
        admission_calls.append(user_id)
        return frozenset({"pms"})

    class Policy:
        def authorize_many_resources(self, resources):
            candidates = list(resources)
            authorized_resources.extend(candidates)
            return {resource for resource in candidates if resource[1] in {"task-1", "task-3"}}

    monkeypatch.setattr(
        visibility,
        "allowed_app_ids",
        _allowed_apps,
    )
    monkeypatch.setattr(
        visibility.SourceAclPolicy,
        "for_user",
        lambda *_args, **_kwargs: Policy(),
    )
    rows = [
        _notification("notification-1", source_id="task-1"),
        _notification("notification-2", source_id="task-2"),
        _notification("notification-3", source_id="task-3"),
        _notification(
            "notification-invalid-source",
            source_id="task-4",
            source_type="unknown",
        ),
    ]

    result = visibility.visible_notifications(
        object(),
        user=SimpleNamespace(id="user-1"),
        rows=rows,
    )

    assert [row.id for row in result] == ["notification-1", "notification-3"]
    assert admission_calls == ["user-1"]
    assert authorized_resources == [
        ("pms_task", "task-1"),
        ("pms_task", "task-2"),
        ("pms_task", "task-3"),
    ]
