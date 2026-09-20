import json
from uuid import UUID

import httpx

EXCHANGE_PATH = "/api/v1/auth/codex-console-session-links/exchange"
MAX_RESPONSE_BYTES = 4096


def exchange_code(*, issuer: str, code: str) -> str | None:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", issuer + EXCHANGE_PATH, json={"code": code}) as response:
                if response.status_code != 200:
                    return None
                length = response.headers.get("content-length")
                if length and int(length) > MAX_RESPONSE_BYTES:
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return None
        payload = json.loads(body)
    except (httpx.HTTPError, UnicodeDecodeError, ValueError, TypeError):
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"authenticated", "subject"}
        or payload.get("authenticated") is not True
        or not isinstance(payload.get("subject"), str)
    ):
        return None
    try:
        return str(UUID(payload["subject"]))
    except ValueError:
        return None
