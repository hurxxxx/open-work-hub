from open_work_hub_api.core.request_validation_errors import build_request_validation_error_body


def test_request_validation_body_prefers_first_domain_error() -> None:
    body, error_code = build_request_validation_error_body(
        [
            {
                "type": "int_type",
                "loc": ("body", "limit"),
            },
            {
                "type": "conversations.unsupported_scope",
                "loc": ("body", "scope_ref"),
                "ctx": {"scope_ref": "legacy", "extra": "kept"},
            },
        ],
        "en-US",
    )

    assert error_code == "conversations.unsupported_scope"
    assert body == {
        "detail": "Unsupported conversation scope: legacy",
        "code": "conversations.unsupported_scope",
        "params": {"scope_ref": "legacy", "extra": "kept"},
        "validation": [
            {
                "loc": ["body", "limit"],
                "type": "int_type",
                "message": "Value must be an integer.",
            },
            {
                "loc": ["body", "scope_ref"],
                "type": "conversations.unsupported_scope",
                "message": "Unsupported conversation scope: legacy",
            },
        ],
    }


def test_request_validation_body_localizes_generic_error_params() -> None:
    body, error_code = build_request_validation_error_body(
        [
            {
                "type": "greater_than_equal",
                "loc": ("body", "count"),
                "ctx": {"ge": 2, "ignored": "not exposed"},
            }
        ],
        "ko-KR",
    )

    assert error_code == "validation.request_invalid"
    assert body == {
        "detail": "요청 값이 올바르지 않습니다.",
        "code": "validation.request_invalid",
        "validation": [
            {
                "loc": ["body", "count"],
                "type": "greater_than_equal",
                "message": "값은 2 이상이어야 합니다.",
            }
        ],
    }


def test_request_validation_body_handles_unknown_error_shape() -> None:
    body, error_code = build_request_validation_error_body(
        [{"loc": ("query", "cursor"), "ctx": {"unexpected": object()}}],
        "en-US",
    )

    assert error_code == "validation.request_invalid"
    assert body == {
        "detail": "Request validation failed.",
        "code": "validation.request_invalid",
        "validation": [
            {
                "loc": ["query", "cursor"],
                "type": "unknown",
                "message": "Value is invalid.",
            }
        ],
    }
