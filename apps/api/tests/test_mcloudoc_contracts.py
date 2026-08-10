from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_do_api.domains.mcloudoc.contracts import (
    MAX_RAW_JSON_BYTES,
    MAX_RESOLVED_GRANTS,
    MAX_SEARCHABLE_CONTENT_BYTES,
    McloudocChange,
    ResolvedGrant,
)


def test_upsert_contract_accepts_typed_metadata_and_opaque_revision() -> None:
    change = McloudocChange(
        operation="upsert",
        external_id="문서/안전규정/1",
        delivery_id="delivery-1",
        opaque_revision="not-an-ordered-version:zz-001",
        checksum="upstream:opaque:checksum",
        filename="안전규정.pdf",
        content_type="application/pdf",
        size_bytes=3,
        searchable_content=b"pdf",
        title="안전 규정",
        author="홍길동",
        authored_at=datetime(2026, 8, 4, tzinfo=UTC),
        department="안전환경팀",
        document_type="규정",
        source_updated_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        source_uri="opaque internal locator without URL validation",
        raw_metadata={"upstream-field": {"value": 1}},
        raw_acl={"entries": ["group-a"]},
        resolved_grants=(
            ResolvedGrant(principal_type="org_unit", principal_id="safety"),
            ResolvedGrant(principal_type="team", principal_id="safety-audit"),
        ),
        acl_resolution_complete=True,
    )

    assert change.opaque_revision == "not-an-ordered-version:zz-001"
    assert change.resolved_grants[0].permission == "read"
    assert change.resolved_grants[1].principal_type == "team"
    assert change.source_uri == "opaque internal locator without URL validation"


def test_source_uri_is_optional_and_limited_to_2048_characters() -> None:
    kwargs = _upsert_kwargs()
    kwargs["source_uri"] = "x" * 2048
    assert len(McloudocChange(**kwargs).source_uri or "") == 2048

    kwargs["source_uri"] = "x" * 2049
    with pytest.raises(ValidationError):
        McloudocChange(**kwargs)


@pytest.mark.parametrize("field_name", ["raw_metadata", "raw_acl"])
def test_raw_json_payloads_are_limited_to_64_kib(field_name: str) -> None:
    payload = {"value": "x" * MAX_RAW_JSON_BYTES}
    kwargs = _upsert_kwargs()
    kwargs[field_name] = payload

    with pytest.raises(ValidationError, match="raw JSON exceeds"):
        McloudocChange(**kwargs)


def test_resolved_grants_are_limited_to_500() -> None:
    kwargs = _upsert_kwargs()
    kwargs["resolved_grants"] = [
        {"principal_type": "user", "principal_id": f"user-{index}"}
        for index in range(MAX_RESOLVED_GRANTS + 1)
    ]

    with pytest.raises(ValidationError):
        McloudocChange(**kwargs)


def test_company_is_the_only_singleton_grant_without_principal_id() -> None:
    company = ResolvedGrant(principal_type="company")
    assert company.principal_id is None

    with pytest.raises(ValidationError, match="must not have principal_id"):
        ResolvedGrant(principal_type="company", principal_id="company-a")

    for principal_type in ("workspace", "user", "org_unit", "team"):
        with pytest.raises(ValidationError, match="requires principal_id"):
            ResolvedGrant(principal_type=principal_type)

    with pytest.raises(ValidationError):
        ResolvedGrant(principal_type="user", principal_id="x" * 37)


def test_searchable_content_contract_exposes_120_mib_limit_without_allocating_it() -> None:
    schema = McloudocChange.model_json_schema()
    content_schema = schema["properties"]["searchable_content"]
    binary_variant = next(
        variant for variant in content_schema["anyOf"] if variant.get("format") == "binary"
    )

    assert binary_variant["maxLength"] == MAX_SEARCHABLE_CONTENT_BYTES


def test_upsert_requires_content_fields_and_exact_size() -> None:
    with pytest.raises(ValidationError, match="missing required fields"):
        McloudocChange(
            operation="upsert",
            external_id="doc-1",
            delivery_id="delivery-1",
            searchable_content=b"body",
        )

    kwargs = _upsert_kwargs()
    kwargs["size_bytes"] = 999
    with pytest.raises(ValidationError, match="does not match"):
        McloudocChange(**kwargs)


def test_delete_forbids_searchable_content() -> None:
    with pytest.raises(ValidationError, match="must not include"):
        McloudocChange(
            operation="delete",
            external_id="doc-1",
            delivery_id="delivery-1",
            searchable_content=b"must-not-be-here",
        )


def _upsert_kwargs() -> dict[str, object]:
    return {
        "operation": "upsert",
        "external_id": "doc-1",
        "delivery_id": "delivery-1",
        "opaque_revision": "opaque-revision",
        "checksum": "opaque-checksum",
        "filename": "document.txt",
        "content_type": "text/plain",
        "size_bytes": 4,
        "searchable_content": b"body",
        "raw_metadata": {},
        "raw_acl": {"entries": []},
        "resolved_grants": [],
        "acl_resolution_complete": True,
    }
