from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


class GroupwareAuthUnavailable(RuntimeError):
    pass


def _request_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in {"txtuserid", "txtpassword", "stype"}
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def verify_groupware_password(
    *,
    auth_url: str,
    login_id: str,
    password: str,
    timeout_seconds: float,
) -> bool:
    if not auth_url.strip():
        raise GroupwareAuthUnavailable("Groupware authentication URL is not configured.")

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            response = client.get(
                _request_url(auth_url),
                params={
                    "txtUserid": login_id,
                    "txtpassword": password,
                    "sType": "LOGIN",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GroupwareAuthUnavailable("Groupware authentication request failed.") from exc

    return response.text.strip().upper() == "Y"
