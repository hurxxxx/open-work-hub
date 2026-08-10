from __future__ import annotations

import asyncio
import faulthandler
import logging
import signal
import sys

from open_work_hub_api.core.settings import Settings


logger = logging.getLogger(__name__)


def install_stack_dump_signal() -> None:
    try:
        if not faulthandler.is_enabled():
            faulthandler.enable(file=sys.stderr, all_threads=True)
        faulthandler.register(
            signal.SIGUSR1,
            file=sys.stderr,
            all_threads=True,
            chain=False,
        )
    except Exception as exc:
        logger.warning("Failed to install runtime stack dump signal handler: %s", exc)


def start_event_loop_lag_watchdog(settings: Settings) -> asyncio.Task[None]:
    return asyncio.create_task(
        _run_event_loop_lag_watchdog(
            interval_seconds=settings.event_loop_lag_interval_seconds,
            warn_ms=settings.event_loop_lag_warn_ms,
            instance_id=settings.instance_id,
        )
    )


async def _run_event_loop_lag_watchdog(
    *,
    interval_seconds: float,
    warn_ms: int,
    instance_id: str,
) -> None:
    loop = asyncio.get_running_loop()
    expected = loop.time() + interval_seconds
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            now = loop.time()
            lag_ms = max(0.0, (now - expected) * 1000)
            if lag_ms >= warn_ms:
                logger.warning(
                    "Event loop lag detected: instance_id=%s lag_ms=%.0f warn_ms=%s",
                    instance_id,
                    lag_ms,
                    warn_ms,
                )
            expected = now + interval_seconds
    except asyncio.CancelledError:
        raise
