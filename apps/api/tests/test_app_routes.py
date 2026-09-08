import pytest

from open_work_hub_api.core.app_routes import InternalAppLocation, app_route_pattern, build_app_href


def test_build_company_app_href() -> None:
    assert build_app_href(
        InternalAppLocation(
            route_id="docs.document",
            path_params={"docId": "doc/1"},
            query_params={"page": "page 1"},
        )
    ) == ("/apps/docs/documents/doc%2F1?page=page+1")


def test_build_global_app_href() -> None:
    assert app_route_pattern("docs.shared") == "/apps/docs/shared/:shareToken"
    assert (
        build_app_href(
            InternalAppLocation(route_id="docs.shared", path_params={"shareToken": "token"})
        )
        == "/apps/docs/shared/token"
    )


def test_build_app_href_rejects_unexpected_path_parameter() -> None:
    with pytest.raises(ValueError, match="Unexpected route parameter"):
        build_app_href(
            InternalAppLocation(
                route_id="docs.document",
                path_params={"docId": "doc-1", "unexpected": "value"},
            )
        )
