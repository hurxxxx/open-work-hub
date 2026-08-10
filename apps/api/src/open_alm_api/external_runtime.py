from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Protocol

from fastapi import FastAPI

from open_alm_api.core.realtime import AppRealtimeHub, InProcessAppRealtimeHub
from open_alm_api.core.settings import Settings, get_settings
from open_alm_api.core.storage import ensure_bucket
from open_alm_api.domains.collaboration.yjs_runtime import (
    InProcessCollabBus,
    UnavailableCollabBus,
)
from open_alm_api.domains.docs.collab import DocsCollabHub
from open_alm_api.domains.whiteboard.collab import WhiteboardCollabHub


class ApiExternalRuntime(Protocol):
    """External services required while an API application is running."""

    def prepare(self) -> None: ...

    def activate(self, app: FastAPI) -> AbstractAsyncContextManager[None]: ...


class _RuntimeService(Protocol):
    async def startup(self) -> None: ...

    async def shutdown(self) -> None: ...


ServiceFactory = Callable[[], _RuntimeService]


def _noop_prepare() -> None:
    return None


class _ComposedApiExternalRuntime:
    def __init__(
        self,
        *,
        app_realtime_factory: ServiceFactory,
        docs_collab_factory: ServiceFactory,
        whiteboard_collab_factory: ServiceFactory,
    ) -> None:
        self._service_factories = (
            ("app_realtime", app_realtime_factory),
            ("docs_collab", docs_collab_factory),
            ("whiteboard_collab", whiteboard_collab_factory),
        )

    @asynccontextmanager
    async def activate(self, app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for state_name, factory in self._service_factories:
                service = factory()
                setattr(app.state, state_name, service)
                stack.push_async_callback(
                    self._shutdown_service,
                    app,
                    state_name,
                    service,
                )
                await service.startup()
            yield

    @staticmethod
    async def _shutdown_service(
        app: FastAPI,
        state_name: str,
        service: _RuntimeService,
    ) -> None:
        try:
            await service.shutdown()
        finally:
            setattr(app.state, state_name, None)


class ProductionApiExternalRuntime(_ComposedApiExternalRuntime):
    """Redis- and object-storage-backed API runtime used in deployed processes."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        storage_prepare: Callable[[], None] = ensure_bucket,
    ) -> None:
        settings = settings or get_settings()
        self._storage_prepare = storage_prepare
        super().__init__(
            app_realtime_factory=lambda: AppRealtimeHub(
                settings.realtime_redis_url,
                instance_id=settings.instance_id,
            ),
            docs_collab_factory=DocsCollabHub,
            whiteboard_collab_factory=WhiteboardCollabHub,
        )

    def prepare(self) -> None:
        self._storage_prepare()


class InProcessApiExternalRuntime(_ComposedApiExternalRuntime):
    """Docker-free runtime for tests that do not exercise external relays or storage."""

    def __init__(
        self,
        *,
        instance_id: str | None = None,
        storage_prepare: Callable[[], None] = _noop_prepare,
    ) -> None:
        resolved_instance_id = instance_id or get_settings().instance_id
        self._storage_prepare = storage_prepare
        super().__init__(
            app_realtime_factory=lambda: InProcessAppRealtimeHub(
                instance_id=resolved_instance_id
            ),
            docs_collab_factory=lambda: DocsCollabHub(
                instance_id=resolved_instance_id,
                bus=InProcessCollabBus(instance_id=resolved_instance_id),
            ),
            whiteboard_collab_factory=lambda: WhiteboardCollabHub(
                instance_id=resolved_instance_id,
                bus=InProcessCollabBus(instance_id=resolved_instance_id),
            ),
        )

    def prepare(self) -> None:
        self._storage_prepare()


class UnavailableCollaborationApiExternalRuntime(_ComposedApiExternalRuntime):
    """Docker-free app runtime with collaboration explicitly degraded."""

    def __init__(
        self,
        *,
        instance_id: str | None = None,
        storage_prepare: Callable[[], None] = _noop_prepare,
    ) -> None:
        resolved_instance_id = instance_id or get_settings().instance_id
        self._storage_prepare = storage_prepare
        super().__init__(
            app_realtime_factory=lambda: InProcessAppRealtimeHub(
                instance_id=resolved_instance_id
            ),
            docs_collab_factory=lambda: DocsCollabHub(
                instance_id=resolved_instance_id,
                bus=UnavailableCollabBus(instance_id=resolved_instance_id),
            ),
            whiteboard_collab_factory=lambda: WhiteboardCollabHub(
                instance_id=resolved_instance_id,
                bus=UnavailableCollabBus(instance_id=resolved_instance_id),
            ),
        )

    def prepare(self) -> None:
        self._storage_prepare()
