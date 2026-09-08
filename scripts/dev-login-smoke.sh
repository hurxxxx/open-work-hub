#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/dev-env.sh"

API_BASE_URL="${OPEN_WORK_HUB_DEV_SMOKE_API_URL:-http://127.0.0.1:${OPEN_WORK_HUB_API_DEV_PORT:-8001}}"
LOGIN_ID="administrator"
LOGIN_PASSWORD="${OPEN_WORK_HUB_API_DEV_LOGIN_PASSWORD:-open-work-hub-dev-only}"

SMOKE_API_BASE_URL="$API_BASE_URL" \
SMOKE_LOGIN_ID="$LOGIN_ID" \
SMOKE_LOGIN_PASSWORD="$LOGIN_PASSWORD" \
python3 - <<'PY'
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


base_url = os.environ["SMOKE_API_BASE_URL"].rstrip("/")
login_id = os.environ["SMOKE_LOGIN_ID"]
password = os.environ["SMOKE_LOGIN_PASSWORD"]


def request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, str] | None = None,
    token: str | None = None,
) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"{method} {path} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


try:
    health = request_json("/healthz")
    if health.get("status") != "ok":
        raise RuntimeError("API health response is not ok")

    session = request_json(
        "/api/v1/auth/login",
        method="POST",
        payload={"login_id": login_id, "password": password},
    )
    token = session.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Login response did not include a session token")

    user = request_json("/api/v1/auth/me", token=token)
    if user.get("login_id") != login_id:
        raise RuntimeError("Authenticated user does not match the seeded login ID")
    if "platform_admin" not in user.get("system_roles", []):
        raise RuntimeError("Seeded user does not have the platform-admin role")
    bootstrap = request_json("/api/v1/apps/bootstrap", token=token)
    if not isinstance(bootstrap.get("apps"), list):
        raise RuntimeError("Company app bootstrap is missing its app list")
    if any(key in user for key in ("workspaces", "default_workspace_id")):
        raise RuntimeError("Authenticated company user exposes obsolete workspace state")

except HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"Login smoke failed: HTTP {exc.code}: {detail}") from exc
except URLError as exc:
    raise SystemExit(f"Login smoke failed: API is unavailable at {base_url}: {exc.reason}") from exc

print(f"Login smoke passed: {user['login_id']} ({user['email']})")
PY
