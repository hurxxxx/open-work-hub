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


def test_translate_auth_and_admin_validation_messages() -> None:
    email_message = LocalizedApiMessage(code="auth.valid_email_required")
    role_message = LocalizedApiMessage(code="admin.invalid_workspace_role")

    assert translate_message(email_message, "en-US") == "A valid email address is required."
    assert translate_message(email_message, "ko-KR") == "올바른 이메일 주소가 필요합니다."
    assert translate_message(role_message, "en-US") == "Invalid workspace role."
    assert translate_message(role_message, "ko-KR") == "워크스페이스 역할이 올바르지 않습니다."


def test_translate_llm_health_messages() -> None:
    disabled = LocalizedApiMessage(code="llm.pool_disabled", params={"pool": "local"})
    missing = LocalizedApiMessage(
        code="llm.missing_settings",
        params={"pool": "external", "settings": "api_key, default_model"},
    )

    assert translate_message(disabled, "en-US") == "local LLM pool is disabled."
    assert translate_message(disabled, "ko-KR") == "local LLM pool이 비활성화되어 있습니다."
    assert translate_message(missing, "en-US") == (
        "Missing LLM external setting(s): api_key, default_model"
    )
    assert translate_message(missing, "ko-KR") == (
        "external LLM 설정이 누락되었습니다: api_key, default_model"
    )


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
    query_message = LocalizedApiMessage(
        code="rag.query_unavailable",
        params={"reason": "provider timeout"},
    )

    assert translate_message(message, "en-US") == "RAG is unavailable: provider timeout"
    assert translate_message(message, "ko-KR") == "RAG를 사용할 수 없습니다: provider timeout"
    assert translate_message(query_message, "en-US") == (
        "RAG query is unavailable: provider timeout"
    )
    assert translate_message(query_message, "ko-KR") == (
        "RAG 조회를 사용할 수 없습니다: provider timeout"
    )


def test_translate_rag_filter_validation_messages() -> None:
    reserved = LocalizedApiMessage(
        code="rag.metadata_filter_key_reserved",
        params={"key": "workspace_id"},
    )
    invalid = LocalizedApiMessage(
        code="rag.metadata_filter_key_invalid",
        params={"key": "metadata.owner"},
    )

    assert translate_message(reserved, "en-US") == (
        "Metadata filter key is reserved: workspace_id"
    )
    assert translate_message(reserved, "ko-KR") == (
        "예약된 메타데이터 필터 key입니다: workspace_id"
    )
    assert translate_message(invalid, "en-US") == (
        "Invalid metadata filter key: metadata.owner"
    )
    assert translate_message(invalid, "ko-KR") == (
        "메타데이터 필터 key가 올바르지 않습니다: metadata.owner"
    )


def test_translate_whiteboard_access_message() -> None:
    message = LocalizedApiMessage(code="whiteboard.edit_access_required")

    assert translate_message(message, "en-US") == "Whiteboard edit access required."
    assert translate_message(message, "ko-KR") == "화이트보드 편집 권한이 필요합니다."


def test_translate_meeting_recording_in_progress_message() -> None:
    message = LocalizedApiMessage(
        code="meeting.recording_in_progress",
        params={"recorder_name": "Admin User"},
    )

    assert translate_message(message, "en-US") == (
        "A recording is already in progress by Admin User."
    )
    assert translate_message(message, "ko-KR") == "이미 Admin User 님이 녹음 중입니다."


def test_translate_admin_workspace_delete_blockers_preserves_counts() -> None:
    message = LocalizedApiMessage(
        code="admin.workspace_contains_content",
        params={"space_count": 2, "meeting_count": 1, "doc_count": 3},
    )

    assert "2 space(s), 1 meeting(s), 3 document(s)" in translate_message(message, "en-US")
    assert "스페이스 2개, 회의 1개, 문서 3개" in translate_message(message, "ko-KR")


def test_translate_ai_dynamic_tool_and_status_messages() -> None:
    tool_message = LocalizedApiMessage(
        code="ai.unknown_tool",
        params={"tool_name": "missing.tool"},
    )
    status_message = LocalizedApiMessage(
        code="ai.approval_already_status",
        params={"status": "approved"},
    )

    assert translate_message(tool_message, "en-US") == "Unknown AI tool: missing.tool"
    assert translate_message(tool_message, "ko-KR") == "알 수 없는 AI 도구입니다: missing.tool"
    assert translate_message(status_message, "en-US") == "Approval is already approved."
    assert translate_message(status_message, "ko-KR") == "승인이 이미 승인됨 상태입니다."


def test_translate_ai_router_dynamic_messages() -> None:
    workspace_app_message = LocalizedApiMessage(
        code="ai.unknown_workspace_app",
        params={"app_id": "shadow-app"},
    )
    json_message = LocalizedApiMessage(
        code="ai.invalid_tool_argument_json",
        params={"error": "Expecting value"},
    )
    model_message = LocalizedApiMessage(
        code="ai.configured_llm_model_required",
        params={"canonical_model": "local/model"},
    )

    assert translate_message(workspace_app_message, "en-US") == (
        "Unknown workspace app: shadow-app"
    )
    assert translate_message(workspace_app_message, "ko-KR") == (
        "알 수 없는 워크스페이스 앱입니다: shadow-app"
    )
    assert translate_message(json_message, "en-US") == (
        "Invalid tool argument JSON: Expecting value"
    )
    assert translate_message(json_message, "ko-KR") == (
        "AI 도구 인자 JSON이 올바르지 않습니다: Expecting value"
    )
    assert "local/model" in translate_message(model_message, "en-US")
    assert "local/model" in translate_message(model_message, "ko-KR")
    assert '{"arg":"value"}' in translate_message(
        LocalizedApiMessage(code="ai.tool_command_syntax"),
        "en-US",
    )
