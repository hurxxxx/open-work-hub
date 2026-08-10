from __future__ import annotations

import pytest

from open_work_hub_api.domains.retrieval.projection_identity import (
    RetrievalProjectionIdentityError,
    canonical_resource_key,
    canonical_search_document_id,
    canonical_vector_point_id,
)


def test_canonical_projection_identity_has_fixed_v1_vectors() -> None:
    assert canonical_resource_key(
        resource_type="file_manager_file",
        resource_id="file-123",
    ) == ("18:open-work-hub-retrieval-v1|8:resource|17:file_manager_file|8:file-123")
    assert (
        canonical_search_document_id(
            resource_type="file_manager_file",
            resource_id="file-123",
        )
        == "3992a36d-1222-56f3-9e9e-43a4237fbb6b"
    )
    assert (
        canonical_vector_point_id(
            resource_type="file_manager_file",
            resource_id="file-123",
            chunk_id="chunk-0",
        )
        == "87bd7107-a900-5c27-93ed-0acb1850b4cb"
    )


def test_projection_identity_is_scope_neutral_and_collision_safe() -> None:
    first = canonical_vector_point_id(
        resource_type="a:b",
        resource_id="c",
        chunk_id="d",
    )
    second = canonical_vector_point_id(
        resource_type="a",
        resource_id="b:c",
        chunk_id="d",
    )

    assert first != second
    assert "workspace" not in canonical_resource_key(
        resource_type="native_doc",
        resource_id="doc-1",
    )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_projection_identity_rejects_blank_components(value: object) -> None:
    with pytest.raises(RetrievalProjectionIdentityError):
        canonical_search_document_id(resource_type=value, resource_id="resource-1")
