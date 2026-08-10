from __future__ import annotations

from types import SimpleNamespace

from open_alm_api.domains.images import generation_jobs


def test_dispatch_image_generation_uses_configured_task_and_queue(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def send_task(self, name, *, args, queue):
            captured["name"] = name
            captured["args"] = args
            captured["queue"] = queue
            return SimpleNamespace(id="task-1")

    monkeypatch.setattr(generation_jobs, "get_celery_client", lambda: FakeClient())

    assert generation_jobs.dispatch_image_generation("generation-1") == "task-1"
    assert captured == {
        "name": "images.generate_image",
        "args": ["generation-1"],
        "queue": "image_generation",
    }


def test_revoke_image_generation_preserves_non_terminating_cancel(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeControl:
        def revoke(self, task_id, *, terminate):
            captured["task_id"] = task_id
            captured["terminate"] = terminate

    class FakeClient:
        control = FakeControl()

    monkeypatch.setattr(generation_jobs, "get_celery_client", lambda: FakeClient())

    generation_jobs.revoke_image_generation("task-1")

    assert captured == {"task_id": "task-1", "terminate": False}
