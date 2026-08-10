from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, Response, UploadFile
from pydantic import ValidationError

from ai_do_api.domains.ai.registry import (
    get_ai_capability_registry,
    reset_ai_capability_registry,
)
from ai_do_api.domains.ai.gateway import AiGatewayPolicyViolation
from ai_do_api.domains.patent_prior_art import (
    PATENT_PRIOR_ART_APP_ID,
    PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND,
    PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID,
    PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND,
    PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID,
)
from ai_do_api.domains.patent_prior_art import service
from ai_do_api.domains.patent_prior_art.app_catalog import (
    PATENT_PRIOR_ART_WORKSPACE_APP,
)
from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtJobCreateRequest,
    PatentPriorArtQueryPreviewRequest,
    PatentPriorArtSearchValues,
)


def test_app_is_hidden_disabled_and_vehicle_category_is_explicit_input() -> None:
    registration = PATENT_PRIOR_ART_WORKSPACE_APP
    assert registration.app_id == PATENT_PRIOR_ART_APP_ID
    assert registration.enabled_by_default is False
    assert registration.visible_by_default is False
    assert registration.coming_soon is False

    config = service.config()
    assert [item.id for item in config.categories] == ["vehicle"]
    assert config.max_plan_values_per_field == 30
    assert config.max_plan_value_chars == 256
    assert config.max_upload_bytes == 30 * 1024 * 1024
    assert config.allowed_upload_extensions == [".pdf", ".docx", ".xlsx", ".pptx"]
    assert config.categories[0].selected_by_default is True
    assert config.categories[0].label_key == "ai.patentPriorArt.categories.vehicle.label"
    assert [item.id for item in config.jurisdictions if item.selected_by_default] == ["KR"]
    assert all(
        item.label_key.startswith("ai.patentPriorArt.jurisdictions.")
        for item in config.jurisdictions
    )
    assert config.report_formats == [
        "html",
        "pdf",
        "docx",
        "summary_pdf",
        "summary_docx",
    ]


def test_job_create_requires_idempotency_key() -> None:
    assert PatentPriorArtJobCreateRequest.model_fields["idempotency_key"].is_required()


def test_scaffold_rejects_oversized_or_unverifiable_body_before_parsing() -> None:
    from ai_do_api.domains.patent_prior_art.router import (
        _BODY_LIMIT_BY_ENDPOINT,
        parse_file,
        router,
    )

    route = next(route for route in router.routes if getattr(route, "endpoint", None) is parse_file)
    limit = _BODY_LIMIT_BY_ENDPOINT[parse_file]

    for headers in (
        [(b"content-length", str(limit + 1).encode())],
        [(b"content-length", b"not-a-number")],
        [(b"content-length", b"\xb2")],
        [(b"content-length", b"9" * 5000)],
    ):
        messages: list[dict] = []
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/patent-prior-art/files/parse",
            "raw_path": b"/patent-prior-art/files/parse",
            "query_string": b"",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        async def receive() -> dict:
            raise AssertionError("oversized request body must not be read")

        async def send(message: dict) -> None:
            messages.append(message)

        try:
            asyncio.run(route.handle(scope, receive, send))
        except HTTPException as exc:
            assert exc.status_code == 413
        else:
            assert any(
                message.get("type") == "http.response.start" and message.get("status") == 413
                for message in messages
            )


def test_scaffold_body_limit_preserves_method_not_allowed() -> None:
    from ai_do_api.domains.patent_prior_art.router import (
        _BODY_LIMIT_BY_ENDPOINT,
        parse_file,
        router,
    )

    route = next(route for route in router.routes if getattr(route, "endpoint", None) is parse_file)
    limit = _BODY_LIMIT_BY_ENDPOINT[parse_file]
    messages: list[dict] = []
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/patent-prior-art/files/parse",
        "raw_path": b"/patent-prior-art/files/parse",
        "query_string": b"",
        "headers": [(b"content-length", str(limit + 1).encode())],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict:
        raise AssertionError("405 responses must not read the request body")

    async def send(message: dict) -> None:
        messages.append(message)

    asyncio.run(route.handle(scope, receive, send))

    assert any(
        message.get("type") == "http.response.start" and message.get("status") == 405
        for message in messages
    )


def test_scaffold_counts_actual_body_for_chunked_and_understated_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_do_api.domains.patent_prior_art.router import (
        _BODY_LIMIT_BY_ENDPOINT,
        _BodySizeLimitRoute,
    )
    from ai_do_api.app import localized_http_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException

    limited_router = APIRouter(route_class=_BodySizeLimitRoute)

    @limited_router.post("/consume")
    async def consume(request: Request) -> Response:
        await request.body()
        return Response(status_code=204)

    body_limit = 8
    monkeypatch.setitem(_BODY_LIMIT_BY_ENDPOINT, consume, body_limit)
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, localized_http_exception_handler)
    app.include_router(limited_router)

    def run_request(*, chunks: tuple[bytes, ...], headers: list[tuple[bytes, bytes]]) -> int:
        receive_calls = 0
        messages: list[dict] = []
        request_chunks = iter(chunks)
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/consume",
            "raw_path": b"/consume",
            "query_string": b"",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        async def receive() -> dict:
            nonlocal receive_calls
            chunk = next(request_chunks)
            receive_calls += 1
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": receive_calls < len(chunks),
            }

        async def send(message: dict) -> None:
            messages.append(message)

        asyncio.run(app(scope, receive, send))
        return next(
            message["status"]
            for message in messages
            if message.get("type") == "http.response.start"
        )

    assert run_request(chunks=(b"1234", b"5678"), headers=[]) == 204
    assert (
        run_request(
            chunks=(b"1234", b"5678"),
            headers=[(b"content-length", str(body_limit).encode())],
        )
        == 204
    )
    assert run_request(chunks=(b"1234", b"56789"), headers=[]) == 413
    assert (
        run_request(
            chunks=(b"1234", b"56789"),
            headers=[(b"content-length", b"1")],
        )
        == 413
    )


def test_scaffold_closes_partial_multipart_spool_on_body_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import starlette.formparsers as formparsers
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from ai_do_api.app import localized_http_exception_handler
    from ai_do_api.domains.patent_prior_art.router import (
        _BODY_LIMIT_BY_ENDPOINT,
        _BodySizeLimitRoute,
    )

    created_files = []
    original_spooled_file = formparsers.SpooledTemporaryFile

    def tracked_spooled_file(*args, **kwargs):
        spooled_file = original_spooled_file(*args, **kwargs)
        created_files.append(spooled_file)
        return spooled_file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_spooled_file)

    endpoint_calls = 0
    limited_router = APIRouter(route_class=_BodySizeLimitRoute)

    @limited_router.post("/upload")
    async def upload(file: UploadFile = File(...)) -> Response:
        nonlocal endpoint_calls
        endpoint_calls += 1
        return Response(status_code=204)

    first_chunk = (
        b"--x\r\n"
        b'Content-Disposition: form-data; name="file"; filename="a.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"partial"
    )
    second_chunk = b"-overflow\r\n--x--\r\n"
    monkeypatch.setitem(_BODY_LIMIT_BY_ENDPOINT, upload, len(first_chunk))

    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, localized_http_exception_handler)
    app.include_router(limited_router)
    chunks = iter((first_chunk, second_chunk))
    receive_calls = 0
    messages: list[dict] = []
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"transfer-encoding", b"chunked"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict:
        nonlocal receive_calls
        chunk = next(chunks)
        receive_calls += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": receive_calls == 1,
        }

    async def send(message: dict) -> None:
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    assert receive_calls == 2
    assert endpoint_calls == 0
    assert created_files
    assert all(spooled_file.closed for spooled_file in created_files)
    assert [
        message["status"] for message in messages if message.get("type") == "http.response.start"
    ] == [413]


def test_preview_maps_core_external_transfer_block_to_localized_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_do_api.domains.patent_prior_art.router import preview_query

    def blocked_preview(*_args: Any, **_kwargs: Any) -> None:
        raise AiGatewayPolicyViolation(
            reason_code="external_transfer_blocked",
            task_kind=PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND,
        )

    monkeypatch.setattr(service, "preview_query", blocked_preview)

    with pytest.raises(HTTPException) as exc_info:
        preview_query(
            PatentPriorArtQueryPreviewRequest(
                invention_text="센서 입력에 따라 열교환기와 송풍기를 제어하는 차량 열관리 기술입니다.",
                category_ids=["vehicle"],
                jurisdictions=["KR"],
            ),
            db=cast(Any, None),
            current_user=cast(Any, None),
            workspace=cast(Any, None),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail.code == "ai.external_transfer_blocked"


def test_search_plan_values_have_per_item_length_limits() -> None:
    with pytest.raises(ValidationError):
        PatentPriorArtSearchValues(values=["x" * 257], source="user")


def test_prior_art_workloads_are_app_specific_and_budgeted() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()
    expected = {
        PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID: PATENT_PRIOR_ART_SEARCH_PLAN_TASK_KIND,
        PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID: (
            PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_TASK_KIND
        ),
    }

    for workload_id, task_kind in expected.items():
        workload = registry.resolve_llm_workload(workload_id)
        assert workload.task_kind == task_kind
        assert workload.app_ids == (PATENT_PRIOR_ART_APP_ID,)
        assert workload.external_data is True
        assert workload.local_max_output_tokens == 8_192
        assert workload.external_max_output_tokens == 8_192
