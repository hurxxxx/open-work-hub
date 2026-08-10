from __future__ import annotations

from ai_do_api.domains.auth import groupware_http


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __enter__(self) -> "_Client":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, url: str, *, params: dict[str, str]) -> _Response:
        self.requests.append((url, params))
        return _Response(self.response_text)


def test_groupware_auth_rewrites_supplied_query_credentials(monkeypatch) -> None:
    client = _Client("Y")
    monkeypatch.setattr(groupware_http.httpx, "Client", lambda **kwargs: client)

    authenticated = groupware_http.verify_groupware_password(
        auth_url=(
            "http://gw.example/checker9_new.aspx"
            "?txtUserid=id&txtpassword=pass&sType=LOGIN&keep=1"
        ),
        login_id="shryu",
        password="secret",
        timeout_seconds=5,
    )

    assert authenticated is True
    assert client.requests == [
        (
            "http://gw.example/checker9_new.aspx?keep=1",
            {"txtUserid": "shryu", "txtpassword": "secret", "sType": "LOGIN"},
        )
    ]


def test_groupware_auth_only_accepts_y_response(monkeypatch) -> None:
    client = _Client("N")
    monkeypatch.setattr(groupware_http.httpx, "Client", lambda **kwargs: client)

    authenticated = groupware_http.verify_groupware_password(
        auth_url="http://gw.example/checker9_new.aspx",
        login_id="shryu",
        password="secret",
        timeout_seconds=5,
    )

    assert authenticated is False
