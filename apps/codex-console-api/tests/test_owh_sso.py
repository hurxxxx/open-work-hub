import httpx

from codex_console import owh_sso


def test_exchange_code_accepts_only_exact_bounded_success(monkeypatch):
    real_client = httpx.Client

    def client(**kwargs):
        return real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"authenticated": True})
            ),
            **kwargs,
        )

    monkeypatch.setattr(owh_sso.httpx, "Client", client)
    assert owh_sso.exchange_code(
        issuer="https://dev.example.test",
        code="cc1_code",
        allowed_origins=["https://dev.example.test"],
    )
    assert not owh_sso.exchange_code(
        issuer="https://evil.example.test",
        code="cc1_code",
        allowed_origins=["https://dev.example.test"],
    )


def test_exchange_code_rejects_redirects_and_large_responses(monkeypatch):
    real_client = httpx.Client
    responses = iter(
        (
            httpx.Response(302, headers={"location": "http://127.0.0.1/private"}),
            httpx.Response(200, content=b"x" * (owh_sso.MAX_RESPONSE_BYTES + 1)),
        )
    )

    def client(**kwargs):
        return real_client(
            transport=httpx.MockTransport(lambda request: next(responses)),
            **kwargs,
        )

    monkeypatch.setattr(owh_sso.httpx, "Client", client)
    for _ in range(2):
        assert not owh_sso.exchange_code(
            issuer="https://dev.example.test",
            code="cc1_code",
            allowed_origins=["https://dev.example.test"],
        )
