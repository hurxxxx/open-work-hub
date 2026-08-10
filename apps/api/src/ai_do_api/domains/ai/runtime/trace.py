from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeTraceSequencer:
    run_seq: int = 0
    _next_event_seq: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.run_seq < 0:
            raise ValueError("run_seq must be non-negative")

    def next_event(self, *, invocation_seq: int = 0) -> tuple[int, int, int]:
        if self.run_seq < 0:
            raise ValueError("run_seq must be non-negative")
        if invocation_seq < 0:
            raise ValueError("invocation_seq must be non-negative")
        if self._next_event_seq < 0:
            raise ValueError("event_seq must be non-negative")
        event_seq = self._next_event_seq
        self._next_event_seq += 1
        return self.run_seq, invocation_seq, event_seq
