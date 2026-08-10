from __future__ import annotations

import pytest

from open_work_hub_api.domains.rag.providers.operation import (
    ProviderCircuitBreaker,
)


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_provider_circuit_breaker_opens_after_threshold_and_expires() -> None:
    clock = _Clock(100.0)
    circuit = ProviderCircuitBreaker(
        failure_threshold=2,
        cooldown_seconds=5,
        open_message="temporarily blocked",
        clock=clock,
    )

    circuit.record_failure()
    assert circuit.retry_after_seconds() is None

    circuit.record_failure()
    assert circuit.retry_after_seconds() == 5
    with pytest.raises(RuntimeError, match="temporarily blocked:5"):
        circuit.raise_if_open(lambda message, retry_after: RuntimeError(f"{message}:{retry_after}"))

    clock.now = 105.1
    assert circuit.retry_after_seconds() is None


def test_provider_circuit_breaker_honors_retry_after_without_accumulating_failures() -> None:
    clock = _Clock(200.0)
    circuit = ProviderCircuitBreaker(
        failure_threshold=2,
        cooldown_seconds=5,
        open_message="retry later",
        clock=clock,
    )

    circuit.record_failure(retry_after_seconds=9)
    assert circuit.retry_after_seconds() == 9

    clock.now = 209.1
    assert circuit.retry_after_seconds() is None
    circuit.record_failure()
    assert circuit.retry_after_seconds() is None
