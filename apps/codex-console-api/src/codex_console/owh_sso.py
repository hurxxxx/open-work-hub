import json

import httpx

EXCHANGE_PATH = "/api/v1/auth/codex-console-session-links/exchange"
MAX_RESPONSE_BYTES = 4096


def exchange_code(*, issuer: str, code: str, allowed_origins: list[str]) -> bool:
    if issuer not in allowed_origins:
        return False
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", issuer + EXCHANGE_PATH, json={"code": code}) as response:
                if response.status_code != 200:
                    return False
                length = response.headers.get("content-length")
                if length and int(length) > MAX_RESPONSE_BYTES:
                    return False
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return False
        payload = json.loads(body)
    except (httpx.HTTPError, UnicodeDecodeError, ValueError, TypeError):
        return False
    return payload == {"authenticated": True}
