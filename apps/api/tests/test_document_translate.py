from __future__ import annotations

import unicodedata
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.llm import LlmTaskContext
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from open_work_hub_api.domains.document_translate import prompts, router as dt_router, service
from open_work_hub_api.domains.document_translate.service import DocumentTranslateError


def _context() -> LlmTaskContext:
    return LlmTaskContext(
        source="test.document_translate",
        workspace_id="ws-1",
        task_kind=service.TASK_KIND,
        app_id="document-translate",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id="user-1",
    )


def _fake_completion(text: str):
    message = SimpleNamespace(content=text)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    return response, None, None


def _fake_gateway_response(text: str):
    return SimpleNamespace(completion=SimpleNamespace(text=text))


# --- prompts -----------------------------------------------------------------


def _all_mode_prompts(target_lang: str) -> tuple[str, ...]:
    return (
        prompts.build_translate_prompt("본문", target_lang),
        prompts.build_summarize_prompt("본문", "brief", target_lang),
        prompts.build_summarize_prompt("본문", "detailed", target_lang),
        prompts.build_extract_prompt("본문", target_lang),
    )


def _contains_han(text: str) -> bool:
    return any(
        unicodedata.name(character, "").startswith(
            ("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH")
        )
        for character in text
    )


@pytest.mark.parametrize(("target_lang", "lang_name"), list(prompts.LANG_NAMES.items()))
def test_all_prompts_declare_target_language_once(
    target_lang: str,
    lang_name: str,
) -> None:
    for prompt in _all_mode_prompts(target_lang):
        assert prompt.count("출력 언어:") == 1
        assert f"출력 언어: {lang_name}" in prompt


def test_prompts_use_minimal_grounded_contract_without_personas_or_han_examples() -> None:
    for prompt in _all_mode_prompts("ko"):
        assert "원문에 없는 내용을 추가하거나 추측하지 마세요." in prompt
        assert "수치와 고유명사는 원문을 정확히 반영하세요." in prompt
        assert "당신은" not in prompt
        assert "Open Work Hub" not in prompt
        assert "한자" not in prompt
        assert not _contains_han(prompt)


def test_translate_prompt_preserves_translation_only_contract() -> None:
    prompt = prompts.build_translate_prompt("hello world", "en")
    assert "hello world" in prompt
    assert "기술 용어" in prompt
    assert "번역 결과만 출력" in prompt


def test_brief_summary_preserves_prose_length_contract() -> None:
    prompt = prompts.build_summarize_prompt("본문", "brief", "ko")
    assert "3~5줄의 줄글" in prompt
    assert "문장으로 핵심 메시지를 설명" in prompt


def test_detailed_summary_uses_section_structure() -> None:
    prompt = prompts.build_summarize_prompt("본문", "detailed", "ko")
    assert "## 개요" in prompt
    assert "## 결론 및 시사점" in prompt
    assert "원문에 명시된 목적·배경·범위만" in prompt
    assert prompt.count("해당 내용이 없으면 이 섹션을 생략") == 2
    assert "원문에 명시된 결론·판단·시사점만" in prompt
    # 요약은 줄글 중심 — 수치 표/항목 추출은 핵심추출의 몫이므로 표 지시가 없어야 한다.
    assert "마크다운 표" not in prompt


def test_extract_prompt_lists_structured_categories() -> None:
    prompt = prompts.build_extract_prompt("본문", "ko")
    assert "[핵심 키워드]" in prompt
    assert "[주요 수치·스펙]" in prompt
    assert "[결정사항·조치(액션 아이템)]" in prompt
    assert "마크다운 기호" in prompt
    assert "해당 내용이 없는 분류는 생략" in prompt


# --- extract_text ------------------------------------------------------------


def test_extract_text_decodes_txt() -> None:
    text = service.extract_text(
        content="안녕하세요 본문입니다".encode("utf-8"),
        filename="note.txt",
        mime_type="text/plain",
    )
    assert text == "안녕하세요 본문입니다"


def test_extract_text_empty_raises() -> None:
    with pytest.raises(DocumentTranslateError):
        service.extract_text(content=b"   ", filename="empty.txt", mime_type="text/plain")


# --- process -----------------------------------------------------------------


def test_process_translate_dispatches_translate_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_prompt: dict[str, str] = {}
    captured_kwargs: dict[str, object] = {}

    def _fake_execute_llm(workload_id, context, db, **kwargs):
        del workload_id, context
        del db
        messages = kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        captured_prompt["value"] = messages[0]["content"]
        if kwargs.get("max_tokens") is not None:
            captured_kwargs["max_tokens"] = kwargs["max_tokens"]
        return _fake_gateway_response("translated text")

    monkeypatch.setattr(service, "execute_llm", _fake_execute_llm)

    result = service.process(
        db=None,
        context=_context(),
        text="원문 텍스트",
        mode="translate",
        target_lang="en",
        summary_level="detailed",
    )
    assert result.result == "translated text"
    assert result.mode == "translate"
    assert result.char_count == len("원문 텍스트")
    assert "영어(English)" in captured_prompt["value"]
    assert "max_tokens" not in captured_kwargs


def test_process_truncates_long_input(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _fake_execute_llm(workload_id, context, db, **kwargs):
        del workload_id, context
        del db
        captured["prompt"] = kwargs["messages"][0]["content"]
        return _fake_gateway_response("ok")

    monkeypatch.setattr(service, "execute_llm", _fake_execute_llm)

    long_text = "가" * 40_000
    result = service.process(
        db=None,
        context=_context(),
        text=long_text,
        mode="summarize",
        target_lang="ko",
        summary_level="brief",
    )
    # char_count 는 원본 길이를 반영하되, 프롬프트에는 절단 안내가 포함된다.
    assert result.char_count == 40_000
    assert "[이하 내용 생략" in captured["prompt"]


def test_process_empty_text_raises() -> None:
    with pytest.raises(DocumentTranslateError):
        service.process(
            db=None,
            context=_context(),
            text="   ",
            mode="summarize",
            target_lang="ko",
            summary_level="detailed",
        )


# --- router integration --------------------------------------------------------
# A minimal FastAPI app with the router mounted under the workspace prefix, with
# auth/db dependencies overridden and the LLM stubbed. Exercises auth/workspace
# scoping and request validation without external infra (Postgres/Redis/MinIO).

_WS_PREFIX = "/api/v1/workspaces/acme/document-translate"


def _make_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def _fake_execute_llm(workload_id, context, db, **kwargs):
        del workload_id, context, db
        return _fake_gateway_response("OK:" + kwargs["messages"][0]["content"][:8])

    monkeypatch.setattr(service, "execute_llm", _fake_execute_llm)

    from starlette.exceptions import HTTPException as StarletteHTTPException

    from open_work_hub_api.app import localized_http_exception_handler

    app = FastAPI()
    app.include_router(dt_router.router, prefix="/api/v1/workspaces/{workspace_slug}")
    # The router raises localized_http_exception (detail=LocalizedApiMessage); register
    # the same handler create_app() uses so the bare test app serializes it correctly.
    app.add_exception_handler(StarletteHTTPException, localized_http_exception_handler)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(id="user-1")
    app.dependency_overrides[require_current_workspace] = lambda: SimpleNamespace(id="ws-1")
    app.dependency_overrides[dt_router.require_document_translate_app_enabled] = lambda: None
    return TestClient(app)


def test_process_text_endpoint_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process-text",
        json={"text": "안녕하세요", "mode": "translate", "target_lang": "en"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "translate"
    assert body["result"].startswith("OK:")
    assert body["char_count"] == len("안녕하세요")


def test_process_text_rejects_invalid_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(f"{_WS_PREFIX}/process-text", json={"text": "x", "mode": "bogus"})
    assert response.status_code == 422  # pydantic Literal


def test_process_text_rejects_invalid_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process-text",
        json={"text": "x", "mode": "translate", "target_lang": "fr"},
    )
    assert response.status_code == 422


def test_process_text_requires_nonempty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(f"{_WS_PREFIX}/process-text", json={"text": "", "mode": "summarize"})
    assert response.status_code == 422  # min_length=1


def test_process_file_txt_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process",
        data={"mode": "summarize", "target_lang": "ko", "summary_level": "brief"},
        files={"file": ("note.txt", "회의 내용".encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "summarize"


def test_process_file_rejects_unsupported_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process",
        data={"mode": "summarize"},
        files={"file": ("malware.exe", b"x", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_process_file_rejects_invalid_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process",
        data={"mode": "bogus"},
        files={"file": ("note.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400


def test_process_file_rejects_invalid_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    # /process Form validation must match /process-text JSON validation.
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process",
        data={"mode": "translate", "target_lang": "fr"},
        files={"file": ("note.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400


def test_process_file_rejects_invalid_summary_level(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch)
    response = client.post(
        f"{_WS_PREFIX}/process",
        data={"mode": "summarize", "summary_level": "epic"},
        files={"file": ("note.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400
