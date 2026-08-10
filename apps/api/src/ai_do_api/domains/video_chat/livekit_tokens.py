from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _base64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def create_livekit_join_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    display_name: str,
    room_name: str,
    ttl_seconds: int,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims: dict[str, Any] = {
        "iss": api_key,
        "sub": identity,
        "name": display_name,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "video": {
            "roomJoin": True,
            "room": room_name,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_claims = _base64url_encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(
        api_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_claims}.{_base64url_encode(signature)}"
