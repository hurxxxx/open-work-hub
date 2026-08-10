from __future__ import annotations

import re


DM_ROUTE_ID_MAX_LENGTH = 36
DM_ROUTE_ID_ALLOWED_PATTERN = r"^[A-Za-z0-9_-]+$"
DM_ROUTE_ID_PATTERN = re.compile(DM_ROUTE_ID_ALLOWED_PATTERN)
DM_MESSAGE_BODY_MAX_LENGTH = 120000
DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH = 10
DM_PARTICIPANT_IDS_MAX_LENGTH = 50
DM_CONVERSATION_TITLE_MAX_LENGTH = 140


def normalize_optional_dm_route_id(value: object) -> str | None | object:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if not is_dm_route_id(normalized):
        raise ValueError("DM route ID is invalid")
    return normalized


def normalize_required_dm_route_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("DM route ID is invalid")
    normalized = value.strip()
    if not is_dm_route_id(normalized):
        raise ValueError("DM route ID is invalid")
    return normalized


def normalize_dm_route_id_list(value: object, *, allow_empty: bool) -> list[str] | object:
    if value is None:
        return [] if allow_empty else value
    if not isinstance(value, list):
        return value
    ids = [normalize_required_dm_route_id(item) for item in value]
    if not allow_empty and not ids:
        return ids
    if len(set(ids)) != len(ids):
        raise ValueError("DM route IDs must be unique")
    return ids


def normalize_optional_title(value: object) -> str | None | object:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return normalized or None


def normalize_message_body(value: object) -> str | object:
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else value


def is_dm_route_id(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= DM_ROUTE_ID_MAX_LENGTH
        and DM_ROUTE_ID_PATTERN.fullmatch(value) is not None
    )
