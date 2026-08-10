from __future__ import annotations

from collections.abc import Callable
import math
import re
import time


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ProviderCircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_seconds: int,
        open_message: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._open_message = open_message
        self._clock = clock
        self._consecutive_failures = 0
        self._blocked_until_monotonic = 0.0

    @property
    def open_message(self) -> str:
        return self._open_message

    def record_failure(self, *, retry_after_seconds: int | None = None) -> None:
        if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
            self._open_for_seconds(retry_after_seconds)
            self._consecutive_failures = 0
            return

        self._consecutive_failures += 1
        if self._consecutive_failures < self._failure_threshold:
            return

        self._open_for_seconds(self._cooldown_seconds)
        self._consecutive_failures = 0

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def retry_after_seconds(self) -> int | None:
        remaining = self._blocked_until_monotonic - self._clock()
        if remaining <= 0:
            self._blocked_until_monotonic = 0.0
            return None
        return max(int(math.ceil(remaining)), 1)

    def raise_if_open(self, error_factory: Callable[[str, int], Exception]) -> None:
        retry_after_seconds = self.retry_after_seconds()
        if retry_after_seconds is None:
            return
        raise error_factory(self._open_message, retry_after_seconds)

    def _open_for_seconds(self, seconds: int) -> None:
        self._blocked_until_monotonic = max(
            self._blocked_until_monotonic,
            self._clock() + seconds,
        )


def ceil_positive_timeout_seconds(timeout_seconds: float | None) -> int | None:
    if timeout_seconds is None or timeout_seconds <= 0:
        return None
    return max(int(math.ceil(timeout_seconds)), 1)


def sanitize_untrusted_text(value: str, *, max_chars: int) -> str:
    normalized = _CONTROL_CHARS.sub(" ", value).replace("```", "` ` `")
    normalized = " ".join(normalized.split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
