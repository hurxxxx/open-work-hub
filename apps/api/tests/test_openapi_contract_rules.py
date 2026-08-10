from __future__ import annotations

from ai_do_api.openapi_contract_rules import validate_openapi_contract_rules


def messages(schema: dict) -> list[str]:
    return [finding.message for finding in validate_openapi_contract_rules(schema)]


def test_openapi_contract_rules_accept_valid_minimal_schema() -> None:
    assert messages(
        {
            "paths": {
                "/healthz": {
                    "get": {
                        "operationId": "system_healthz_get",
                    }
                }
            },
            "components": {"schemas": {"ErrorResponse": {}}},
        }
    ) == []


def test_openapi_contract_rules_report_operation_id_shape_problems() -> None:
    assert messages(
        {
            "paths": {
                "/missing": {"get": {}},
                "/camel": {"post": {"operationId": "CamelCase"}},
                "/derived": {"patch": {"operationId": "post_api_v1_workspace_slug_patch"}},
            }
        }
    ) == [
        "GET /missing is missing operationId.",
        "POST /camel has non-snake operationId 'CamelCase'.",
        "PATCH /derived has path-derived operationId 'post_api_v1_workspace_slug_patch'.",
    ]


def test_openapi_contract_rules_report_duplicate_operation_ids() -> None:
    assert messages(
        {
            "paths": {
                "/one": {"get": {"operationId": "shared_get"}},
                "/two": {"post": {"operationId": "shared_get"}},
            }
        }
    ) == ["operationId 'shared_get' is duplicated 2 times."]


def test_openapi_contract_rules_report_path_derived_component_names() -> None:
    assert messages(
        {
            "paths": {},
            "components": {
                "schemas": {
                    "ApiV1WorkspaceSlugResponse": {},
                    "Pms__Task": {},
                    "CleanResponse": {},
                }
            },
        }
    ) == ["component schema 'Pms__Task' includes path-derived text."]
