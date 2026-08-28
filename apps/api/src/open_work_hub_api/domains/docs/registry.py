from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from open_work_hub_api.core.app_routes import InternalAppLocation, build_app_href
from open_work_hub_api.domains.auth.models import Workspace
from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocTarget
from open_work_hub_api.domains.pms.links import pms_root_path, pms_space_docs_path


@dataclass(frozen=True)
class SourceDescriptor:
    label: str
    badge: str
    deep_link: str | None = None


class DocsSourceAdapter(Protocol):
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_target: NativeDocTarget | None,
    ) -> SourceDescriptor: ...


_source_adapters: dict[str, DocsSourceAdapter] = {}


def register_docs_source_adapter(app_id: str, adapter: DocsSourceAdapter) -> None:
    _source_adapters[app_id] = adapter


def get_docs_source_adapter(app_id: str) -> DocsSourceAdapter | None:
    return _source_adapters.get(app_id)


class _DocsSourceAdapter:
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_target: NativeDocTarget | None,
    ) -> SourceDescriptor:
        return SourceDescriptor(
            label="Docs",
            badge="Docs",
            deep_link=build_app_href(
                InternalAppLocation(
                    route_id="docs.document",
                    workspace_slug=workspace.key,
                    path_params={"docId": doc.id},
                )
            ),
        )


class _MeetingSourceAdapter:
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_target: NativeDocTarget | None,
    ) -> SourceDescriptor:
        return SourceDescriptor(
            label="Meeting",
            badge="Meeting",
            deep_link=build_app_href(
                InternalAppLocation(
                    route_id="meeting.root",
                    workspace_slug=workspace.key,
                )
            ),
        )


class _PmsSourceAdapter:
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_target: NativeDocTarget | None,
    ) -> SourceDescriptor:
        if primary_target is not None and primary_target.target_type == "space":
            deep_link = pms_space_docs_path(
                workspace,
                primary_target.target_id,
                doc_id=doc.id,
            )
        else:
            deep_link = pms_root_path(workspace)
        return SourceDescriptor(
            label="PMS",
            badge="PMS",
            deep_link=deep_link,
        )


class _GenericSourceAdapter:
    def __init__(self, app_id: str) -> None:
        self._app_id = app_id

    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_target: NativeDocTarget | None,
    ) -> SourceDescriptor:
        label = self._app_id.replace("_", " ").title()
        return SourceDescriptor(
            label=label,
            badge=label,
            deep_link=build_app_href(
                InternalAppLocation(
                    route_id="docs.document",
                    workspace_slug=workspace.key,
                    path_params={"docId": doc.id},
                )
            ),
        )


def describe_source(
    *,
    workspace: Workspace,
    doc: NativeDoc,
    primary_target: NativeDocTarget | None,
) -> SourceDescriptor:
    adapter = get_docs_source_adapter(doc.source_app)
    if adapter is None:
        adapter = _GenericSourceAdapter(doc.source_app)
    return adapter.describe(workspace=workspace, doc=doc, primary_target=primary_target)


register_docs_source_adapter("docs", _DocsSourceAdapter())
register_docs_source_adapter("meeting", _MeetingSourceAdapter())
register_docs_source_adapter("pms", _PmsSourceAdapter())
