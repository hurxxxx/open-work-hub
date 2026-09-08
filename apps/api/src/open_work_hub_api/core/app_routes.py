from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import quote, urlencode

from open_work_hub_api.core.app_contracts_generated import (
    APP_CONTRACT_BY_ID,
    APP_ROUTE_BY_ID,
)


@dataclass(frozen=True)
class InternalAppLocation:
    route_id: str
    path_params: Mapping[str, str] = field(default_factory=dict)
    query_params: Mapping[str, str | tuple[str, ...] | None] = field(default_factory=dict)
    fragment: str | None = None


def app_route_pattern(route_id: str) -> str:
    route = APP_ROUTE_BY_ID.get(route_id)
    if route is None:
        raise ValueError(f"Unknown app route: {route_id}")
    return f"{route['route_base']}{route['suffix']}"


def build_app_href(location: InternalAppLocation) -> str:
    route = APP_ROUTE_BY_ID.get(location.route_id)
    if route is None:
        raise ValueError(f"Unknown app route: {location.route_id}")
    params = dict(location.path_params)
    pathname = app_route_pattern(location.route_id)
    for key, value in params.items():
        placeholder = f":{key}"
        if placeholder not in pathname:
            raise ValueError(f"Unexpected route parameter for {location.route_id}: {key}")
        pathname = pathname.replace(placeholder, quote(value, safe=""))
    if ":" in pathname:
        missing = pathname.split(":", 1)[1].split("/", 1)[0]
        raise ValueError(f"Missing route parameter for {location.route_id}: {missing}")

    pairs: list[tuple[str, str]] = []
    for key in sorted(location.query_params):
        raw_value = location.query_params[key]
        if raw_value is None:
            continue
        values = raw_value if isinstance(raw_value, tuple) else (raw_value,)
        pairs.extend((key, value) for value in values)
    search = f"?{urlencode(pairs)}" if pairs else ""
    fragment = f"#{quote(location.fragment.lstrip('#'), safe='')}" if location.fragment else ""
    return f"{pathname}{search}{fragment}"


def app_entry_href(app_id: str) -> str:
    app = APP_CONTRACT_BY_ID.get(app_id)
    if app is None:
        raise ValueError(f"Unknown app: {app_id}")
    return str(app["route_base"])


__all__ = ["InternalAppLocation", "app_entry_href", "app_route_pattern", "build_app_href"]
