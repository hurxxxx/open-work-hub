from __future__ import annotations

import base64
from collections.abc import Mapping
from urllib.parse import quote

import httpx

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.hermes_terminal.schemas import (
    BrokerFileListResponse,
    BrokerSessionCreateRequest,
    BrokerSessionResponse,
)
from open_work_hub_api.domains.hermes_terminal.security import broker_bearer_token


class HermesTerminalBrokerError(RuntimeError):
    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class HermesTerminalBrokerClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        token = broker_bearer_token(self.settings)
        return {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        timeout = kwargs.pop("timeout", 60.0)
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.hermes_terminal_broker_base_url,
                timeout=timeout,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    headers={**self._headers(), **kwargs.pop("headers", {})},
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise HermesTerminalBrokerError("hermes_terminal.broker_unavailable") from exc
        if response.is_error:
            code = "hermes_terminal.broker_request_failed"
            try:
                payload = response.json()
                detail = payload.get("detail") if isinstance(payload, dict) else None
                if isinstance(detail, dict) and isinstance(detail.get("code"), str):
                    code = detail["code"]
                elif isinstance(detail, str):
                    code = detail
            except ValueError:
                pass
            raise HermesTerminalBrokerError(code, status_code=response.status_code)
        return response

    async def health(self) -> dict:
        response = await self._request("GET", "/healthz", timeout=5.0)
        return response.json()

    async def create_session(
        self,
        *,
        session_id: str,
        profile_key: str,
        mode: str,
        cols: int,
        rows: int,
        mcp_url: str,
        mcp_token: str,
        research_sources: Mapping[str, bool],
        profile_archive: bytes | None,
    ) -> BrokerSessionResponse:
        payload = BrokerSessionCreateRequest(
            session_id=session_id,
            profile_key=profile_key,
            mode=mode,  # type: ignore[arg-type]
            cols=cols,
            rows=rows,
            mcp_url=mcp_url,
            mcp_token=mcp_token,
            research_sources=dict(research_sources),
            profile_archive_base64=(
                base64.b64encode(profile_archive).decode("ascii")
                if profile_archive is not None
                else None
            ),
        )
        response = await self._request(
            "POST",
            "/v1/sessions",
            json=payload.model_dump(mode="json"),
            timeout=120.0,
        )
        return BrokerSessionResponse.model_validate(response.json())

    async def get_session(self, session_id: str) -> BrokerSessionResponse:
        response = await self._request("GET", f"/v1/sessions/{quote(session_id)}")
        return BrokerSessionResponse.model_validate(response.json())

    async def stop_session(self, session_id: str) -> BrokerSessionResponse:
        response = await self._request(
            "POST",
            f"/v1/sessions/{quote(session_id)}/stop",
            timeout=45.0,
        )
        return BrokerSessionResponse.model_validate(response.json())

    async def forget_session(self, session_id: str) -> None:
        await self._request(
            "DELETE",
            f"/v1/sessions/{quote(session_id)}",
            timeout=45.0,
        )

    async def resize_session(self, session_id: str, *, cols: int, rows: int) -> None:
        await self._request(
            "POST",
            f"/v1/sessions/{quote(session_id)}/resize",
            json={"cols": cols, "rows": rows},
        )

    async def list_files(self, session_id: str, *, path: str) -> BrokerFileListResponse:
        response = await self._request(
            "GET",
            f"/v1/sessions/{quote(session_id)}/files",
            params={"path": path},
        )
        return BrokerFileListResponse.model_validate(response.json())

    async def read_file(self, session_id: str, *, path: str) -> bytes:
        response = await self._request(
            "GET",
            f"/v1/sessions/{quote(session_id)}/file",
            params={"path": path},
            timeout=120.0,
        )
        return response.content

    async def export_profile(self, session_id: str) -> bytes:
        response = await self._request(
            "POST",
            f"/v1/sessions/{quote(session_id)}/profile/export",
            timeout=180.0,
        )
        return response.content

    async def export_workspace(self, session_id: str) -> bytes:
        response = await self._request(
            "POST",
            f"/v1/sessions/{quote(session_id)}/workspace/export",
            timeout=180.0,
        )
        return response.content

    async def inventory_resources(self) -> dict:
        response = await self._request("GET", "/v1/resources", timeout=15.0)
        try:
            payload = response.json()
        except ValueError as exc:
            raise HermesTerminalBrokerError(
                "hermes_terminal.broker_response_invalid"
            ) from exc
        if not isinstance(payload, dict):
            raise HermesTerminalBrokerError(
                "hermes_terminal.broker_response_invalid"
            )
        return payload

    async def reconcile_resources(self, known_session_ids: set[str]) -> dict[str, int]:
        response = await self._request(
            "POST",
            "/v1/resources/reconcile",
            json={"known_session_ids": sorted(known_session_ids)},
            timeout=60.0,
        )
        try:
            payload = response.json()
            return {
                "removed_runners": int(payload.get("removed_runners") or 0),
                "removed_workspaces": int(payload.get("removed_workspaces") or 0),
                "removed_utilities": int(payload.get("removed_utilities") or 0),
            }
        except (AttributeError, TypeError, ValueError) as exc:
            raise HermesTerminalBrokerError(
                "hermes_terminal.broker_response_invalid"
            ) from exc

    def websocket_url(self, session_id: str) -> str:
        base = self.settings.hermes_terminal_broker_base_url
        if base.startswith("https://"):
            base = "wss://" + base.removeprefix("https://")
        elif base.startswith("http://"):
            base = "ws://" + base.removeprefix("http://")
        return f"{base}/v1/sessions/{quote(session_id)}/attach"
