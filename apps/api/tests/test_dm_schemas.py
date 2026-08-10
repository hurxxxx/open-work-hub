from __future__ import annotations

import pytest
from pydantic import ValidationError

from open_work_hub_api.domains.dm.request_normalization import DM_MESSAGE_BODY_MAX_LENGTH
from open_work_hub_api.domains.dm.schemas import DmSendMessageRequest


def test_dm_send_message_request_accepts_maximum_body_length() -> None:
    body = "x" * DM_MESSAGE_BODY_MAX_LENGTH

    request = DmSendMessageRequest(body=body, reply_to_message_id=" reply-1 ")

    assert request.body == body
    assert request.reply_to_message_id == "reply-1"


def test_dm_send_message_request_rejects_body_over_maximum_length() -> None:
    with pytest.raises(ValidationError):
        DmSendMessageRequest(body="x" * (DM_MESSAGE_BODY_MAX_LENGTH + 1))


def test_dm_send_message_request_rejects_invalid_reply_target_id() -> None:
    with pytest.raises(ValidationError):
        DmSendMessageRequest(body="hello", reply_to_message_id="reply/1")
