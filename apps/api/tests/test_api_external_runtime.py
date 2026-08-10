from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
import pytest

from open_work_hub_api import external_runtime as runtime_module


class _ProbeService:
    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        startup_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._events = events
        self._startup_error = startup_error

    async def startup(self) -> None:
        self._events.append(f"start:{self._name}")
        if self._startup_error is not None:
            raise self._startup_error

    async def shutdown(self) -> None:
        self._events.append(f"stop:{self._name}")


def _runtime_settings() -> SimpleNamespace:
    return SimpleNamespace(
        realtime_redis_url="redis://unused.invalid/0",
        instance_id="runtime-test",
    )


def test_production_external_runtime_starts_and_stops_services_in_contract_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    services = {
        "app": _ProbeService("app", events),
        "docs": _ProbeService("docs", events),
        "whiteboard": _ProbeService("whiteboard", events),
    }
    monkeypatch.setattr(runtime_module, "AppRealtimeHub", lambda *_args, **_kwargs: services["app"])
    monkeypatch.setattr(runtime_module, "DocsCollabHub", lambda: services["docs"])
    monkeypatch.setattr(runtime_module, "WhiteboardCollabHub", lambda: services["whiteboard"])
    runtime = runtime_module.ProductionApiExternalRuntime(_runtime_settings())  # type: ignore[arg-type]
    app = FastAPI()

    async def exercise() -> None:
        async with runtime.activate(app):
            assert app.state.app_realtime is services["app"]
            assert app.state.docs_collab is services["docs"]
            assert app.state.whiteboard_collab is services["whiteboard"]
            events.append("active")

    asyncio.run(exercise())

    assert events == [
        "start:app",
        "start:docs",
        "start:whiteboard",
        "active",
        "stop:whiteboard",
        "stop:docs",
        "stop:app",
    ]
    assert app.state.app_realtime is None
    assert app.state.docs_collab is None
    assert app.state.whiteboard_collab is None


def test_production_external_runtime_rolls_back_started_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    services = {
        "app": _ProbeService("app", events),
        "docs": _ProbeService("docs", events, startup_error=RuntimeError("failed")),
    }
    monkeypatch.setattr(runtime_module, "AppRealtimeHub", lambda *_args, **_kwargs: services["app"])
    monkeypatch.setattr(runtime_module, "DocsCollabHub", lambda: services["docs"])
    monkeypatch.setattr(
        runtime_module,
        "WhiteboardCollabHub",
        lambda: _ProbeService("whiteboard", events),
    )
    runtime = runtime_module.ProductionApiExternalRuntime(_runtime_settings())  # type: ignore[arg-type]
    app = FastAPI()

    async def exercise() -> None:
        with pytest.raises(RuntimeError, match="failed"):
            async with runtime.activate(app):
                raise AssertionError("unreachable")

    asyncio.run(exercise())

    assert events == ["start:app", "start:docs", "stop:docs", "stop:app"]
    assert app.state.app_realtime is None
    assert app.state.docs_collab is None
