from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from ai_do_api.core.realtime import AppRealtimeHub, realtime_user_topic


async def _wait_for_redis_available(*hubs: AppRealtimeHub) -> None:
    deadline = asyncio.get_running_loop().time() + 8
    while True:
        if all(hub.redis_available for hub in hubs):
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("Timed out waiting for realtime Redis relay availability.")
        await asyncio.sleep(0.1)


@pytest.mark.external_integration("redis")
def test_app_realtime_hub_relays_between_publishers_with_same_instance_id(redis_url: str) -> None:
    async def exercise_hubs() -> None:
        channel_prefix = f"ai-do:test-realtime:{uuid4().hex}"
        first_hub = AppRealtimeHub(redis_url, instance_id="api", channel_prefix=channel_prefix)
        second_hub = AppRealtimeHub(redis_url, instance_id="api", channel_prefix=channel_prefix)
        await first_hub.startup()
        await second_hub.startup()
        queue = second_hub.subscribe(realtime_user_topic("user-1"))
        try:
            await _wait_for_redis_available(first_hub, second_hub)

            first_hub.publish_user("user-1", {"type": "probe.event", "data": {"value": 1}})
            event = await asyncio.wait_for(queue.get(), timeout=5)

            assert event["type"] == "probe.event"
            assert event["data"] == {"value": 1}
            assert event["topic"] == realtime_user_topic("user-1")
        finally:
            second_hub.unsubscribe(realtime_user_topic("user-1"), queue)
            await second_hub.shutdown()
            await first_hub.shutdown()

    asyncio.run(exercise_hubs())
