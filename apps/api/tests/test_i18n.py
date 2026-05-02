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
