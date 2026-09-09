from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.access import project_platform_app_bar_categories
from open_work_hub_api.domains.auth.app_access import allowed_app_ids
from open_work_hub_api.domains.auth.app_catalog import iter_app_catalog
from open_work_hub_api.domains.auth.bootstrap_projection import project_bootstrap_apps
from open_work_hub_api.domains.auth.models import User


def build_launch_catalog(
    db: Session, *, user: User, source: str, session_id: str | None = None
) -> dict[str, Any]:
    from open_work_hub_api.domains.ai.chat_context_policy import (
        filter_business_chat_context_app_ids,
    )
    from open_work_hub_api.domains.ai.registry import get_chatbot_capable_app_ids
    from open_work_hub_api.domains.search.entity_adapter_registry import (
        resolve_keyword_search_scope,
    )

    catalog = iter_app_catalog()
    enabled = allowed_app_ids(db, user_id=user.id)
    settings = get_settings()
    projection = project_bootstrap_apps(catalog, enabled_app_ids=enabled, settings=settings)
    app_by_id = {app.app_id: app for app in catalog}
    for app in projection.apps:
        contract = app_by_id[app["app_id"]]
        app.update(
            entry_route_id=contract.entry_route_id,
            execution_context_kind=contract.execution_context_kind,
            resource_scope=contract.resource_scope,
        )
    keyword_search = resolve_keyword_search_scope(enabled)
    return {
        "apps": projection.apps,
        "nav": projection.nav,
        "app_bar_categories": project_platform_app_bar_categories(
            db, enabled_app_ids=set(enabled), settings=settings
        ),
        "personal_tool_app_ids": [
            app.app_id for app in catalog if app.app_id in enabled and app.launcher_personal_tools
        ],
        "chatbot_app_ids": filter_business_chat_context_app_ids(
            app_id for app_id in get_chatbot_capable_app_ids() if app_id in enabled
        ),
        "keyword_search": {
            "entity_types": [
                {"value": item.entity_type, "label": item.label, "label_key": item.label_key}
                for item in keyword_search.descriptors
            ]
        },
        "principal": {
            "kind": "user",
            "user_id": user.id,
            "source": source,
            "session_id": session_id,
        },
    }
