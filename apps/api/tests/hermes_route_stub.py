"""Feed existing route contract fixtures through the common Hermes executor seam.

These tests exercise route/audit/artifact behavior. Native dispatch, run identity,
schema correction and concurrent execution are covered by test_hermes_runtime.
The legacy fixture format is decoded here only; production has no SDK fallback.
"""

import pytest

from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core.llm_execution_adapters import select_llm_execution_adapter
from open_work_hub_api.domains.hermes import workloads


@pytest.fixture
def hermes_route_stub(monkeypatch):
    def complete(context, execution, payload, *, timeout_seconds, output_schema=None):
        adapter = select_llm_execution_adapter(execution.config.pool, execution.config.provider)
        return adapter.complete(
            execution.config,
            payload,
            timeout_seconds=timeout_seconds,
            sync_client_factory=lambda *_: llm_core._new_pool_client(execution.config),
        )

    async def stream(context, execution, payload, *, timeout_seconds, output_schema=None):
        adapter = select_llm_execution_adapter(execution.config.pool, execution.config.provider)
        async for chunk in adapter.stream(
            execution.config,
            payload,
            timeout_seconds=timeout_seconds,
            sync_client_factory=lambda *_: llm_core._new_pool_client(execution.config),
            async_client_factory=lambda *_: llm_core._new_async_pool_client(execution.config),
        ):
            yield chunk

    monkeypatch.setattr(workloads, "complete_workload", complete)
    monkeypatch.setattr(workloads, "stream_workload", stream)
