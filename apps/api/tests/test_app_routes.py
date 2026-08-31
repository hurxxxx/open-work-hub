import pytest

from open_work_hub_api.core.app_routes import (
    InternalAppLocation,
    app_route_pattern,
    build_app_href,
)


def test_build_workspace_app_href() -> None:
    assert build_app_href(
        InternalAppLocation(
            route_id="docs.document",
            workspace_slug="제품 연구",
            path_params={"docId": "doc/1"},
            query_params={"page": "page 1"},
        )
    ) == (
        "/apps/docs/workspaces/%EC%A0%9C%ED%92%88%20%EC%97%B0%EA%B5%AC/"
        "documents/doc%2F1?page=page+1"
    )


def test_build_global_app_href() -> None:
    assert app_route_pattern("docs.shared") == "/apps/docs/shared/:shareToken"
    assert build_app_href(
        InternalAppLocation(route_id="docs.shared", path_params={"shareToken": "token"})
    ) == "/apps/docs/shared/token"


def test_build_app_href_rejects_unexpected_path_parameter() -> None:
    with pytest.raises(ValueError, match="Unexpected route parameter"):
        build_app_href(
            InternalAppLocation(
                route_id="docs.document",
                workspace_slug="hq",
                path_params={"docId": "doc-1", "unexpected": "value"},
            )
        )
