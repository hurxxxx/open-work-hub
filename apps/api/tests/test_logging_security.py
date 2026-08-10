from __future__ import annotations

import logging

import httpx

from ai_do_api.core.logging_security import install_sensitive_http_logging_guard


def test_http_client_request_urls_are_not_logged(caplog) -> None:
    api_key = "secret-kipris-key"
    query = "초전도체 검색어"
    applicant = "민감 출원인명"
    full_url = (
        "https://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/"
        f"wordSearchInfo?accessKey={api_key}&word={query}&applicant={applicant}"
    )

    install_sensitive_http_logging_guard()
    with caplog.at_level(logging.DEBUG):
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, request=request, text="<response />")
            )
        ) as client:
            response = client.get(full_url)
            response.raise_for_status()

    rendered_logs = caplog.text
    assert "HTTP Request:" not in rendered_logs
    assert full_url not in rendered_logs
    assert api_key not in rendered_logs
    assert query not in rendered_logs
    assert applicant not in rendered_logs
