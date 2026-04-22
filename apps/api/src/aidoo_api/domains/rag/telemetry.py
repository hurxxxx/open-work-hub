from __future__ import annotations

from collections.abc import Mapping


def rag_span_attributes(
    *,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    source_kind: str | None = None,
    operation: str | None = None,
    provider_name: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    job_id: str | None = None,
    job_lane: str | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, str | int | float | bool]:
    attributes: dict[str, str | int | float | bool] = {}

    for key, value in (
        ("workspace_id", workspace_id),
        ("resource_type", resource_type),
        ("resource_id", resource_id),
        ("source_kind", source_kind),
        ("operation", operation),
        ("provider_name", provider_name),
        ("scope_type", scope_type),
        ("scope_id", scope_id),
        ("rag.job.id", job_id),
        ("rag.job.lane", job_lane),
    ):
        if isinstance(value, str) and value:
            attributes[key] = value

    if extra:
        for key, value in extra.items():
            if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
                attributes[key] = value

    return attributes
