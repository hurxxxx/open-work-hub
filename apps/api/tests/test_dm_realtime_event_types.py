from __future__ import annotations

from open_alm_api.domains.dm import realtime_event_types


def test_dm_realtime_event_type_constants_match_client_contract() -> None:
    assert realtime_event_types.DM_MESSAGE_CREATED == "dm.message.created"
    assert realtime_event_types.DM_CONVERSATION_CREATED == "dm.conversation.created"
    assert realtime_event_types.DM_CONVERSATION_UPDATED == "dm.conversation.updated"
    assert realtime_event_types.DM_CONVERSATION_READ == "dm.conversation.read"
    assert realtime_event_types.DM_CONVERSATION_REMOVED == "dm.conversation.removed"
