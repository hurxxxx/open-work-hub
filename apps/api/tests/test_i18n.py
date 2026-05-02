from aidoo_api.core.i18n import LocalizedApiMessage, select_locale, translate_message


def test_select_locale_prefers_explicit_app_locale() -> None:
    assert (
        select_locale(explicit_locale="ko-KR", accept_language="en-US,en;q=0.9")
        == "ko-KR"
    )


def test_select_locale_uses_accept_language_quality() -> None:
    assert select_locale(accept_language="en-US;q=0.6, ko-KR;q=0.9") == "ko-KR"
    assert select_locale(accept_language="en;q=0.9, ko;q=0.4") == "en-US"


def test_translate_message_interpolates_params() -> None:
    message = LocalizedApiMessage(
        code="workspace.membership_required",
        params={"workspace": "hq"},
    )

    assert translate_message(message, "en-US") == "Workspace membership required: hq"
    assert translate_message(message, "ko-KR") == "워크스페이스 멤버십이 필요합니다: hq"


def test_translate_domain_message_interpolates_dynamic_values() -> None:
    message = LocalizedApiMessage(
        code="pms.status_in_use",
        params={"count": 3},
    )

    assert translate_message(message, "en-US") == "Cannot delete status: 3 issue(s) are using it."
    assert translate_message(message, "ko-KR") == "상태를 삭제할 수 없습니다. 3개의 이슈가 사용 중입니다."


def test_translate_search_backend_message_preserves_dynamic_reason() -> None:
    message = LocalizedApiMessage(
        code="search.keyword_backend_unavailable",
        params={"reason": "index missing"},
    )

    assert (
        translate_message(message, "en-US")
        == "Keyword search is unavailable: index missing"
    )
    assert translate_message(message, "ko-KR") == "키워드 검색을 사용할 수 없습니다: index missing"


def test_translate_conversation_cursor_message_preserves_dynamic_error() -> None:
    message = LocalizedApiMessage(
        code="conversations.cursor_invalid_timestamp",
        params={"error": "bad month"},
    )

    assert translate_message(message, "en-US") == "Invalid cursor timestamp: bad month"
    assert translate_message(message, "ko-KR") == "cursor timestamp가 올바르지 않습니다: bad month"


def test_translate_rag_unavailable_message_preserves_dynamic_reason() -> None:
    message = LocalizedApiMessage(
        code="rag.unavailable",
        params={"reason": "provider timeout"},
    )

    assert translate_message(message, "en-US") == "RAG is unavailable: provider timeout"
    assert translate_message(message, "ko-KR") == "RAG를 사용할 수 없습니다: provider timeout"


def test_translate_whiteboard_access_message() -> None:
    message = LocalizedApiMessage(code="whiteboard.edit_access_required")

    assert translate_message(message, "en-US") == "Whiteboard edit access required."
    assert translate_message(message, "ko-KR") == "화이트보드 편집 권한이 필요합니다."
