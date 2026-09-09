from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol

from open_work_hub_api.domains.auth.realtime_contract_generated import (
    AUTH_ACCESS_CHANGED,
    AUTH_ACCESS_CHANGED_REASON_APP_AVAILABILITY,
    AUTH_ACCESS_CHANGED_REASON_PRINCIPAL,
)
from open_work_hub_api.domains.realtime.realtime_event_types import build_realtime_event

logger = logging.getLogger(__name__)


def _build_access_changed_event(reason: str) -> dict[str, object]:
    return build_realtime_event(
        AUTH_ACCESS_CHANGED,
        {"reason": reason},
    )


def build_principal_access_changed_event() -> dict[str, object]:
    return _build_access_changed_event(AUTH_ACCESS_CHANGED_REASON_PRINCIPAL)


def build_app_availability_access_changed_event() -> dict[str, object]:
    return _build_access_changed_event(AUTH_ACCESS_CHANGED_REASON_APP_AVAILABILITY)


class UserRealtimePublisher(Protocol):
    def publish_user(self, user_id: str, event: dict[str, object]) -> None: ...


def _publish_access_changed(
    realtime: UserRealtimePublisher | None,
    user_ids: Iterable[str],
    *,
    event: dict[str, object],
) -> None:
    """Publish an at-most-once invalidation after its owning transaction commits."""

    if realtime is None:
        return
    for user_id in sorted(set(user_ids)):
        if not user_id:
            continue
        try:
            realtime.publish_user(user_id, event)
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception(
                "Could not publish access invalidation for user %s",
                user_id,
            )


def publish_principal_access_changed(
    realtime: UserRealtimePublisher | None,
    user_ids: Iterable[str],
) -> None:
    _publish_access_changed(
        realtime,
        user_ids,
        event=build_principal_access_changed_event(),
    )


def publish_app_availability_access_changed(
    realtime: UserRealtimePublisher | None,
    user_ids: Iterable[str],
) -> None:
    _publish_access_changed(
        realtime,
        user_ids,
        event=build_app_availability_access_changed_event(),
    )
