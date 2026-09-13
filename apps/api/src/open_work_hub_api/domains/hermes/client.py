from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import quote

import httpx

from open_work_hub_api.core.settings import (
    HERMES_FALLBACK_MODEL,
    HERMES_MODEL,
    HERMES_PROVIDER,
)
from open_work_hub_api.domains.hermes.research_sources import (
    academic_research_environment_hint,
)

_OPENROUTER_METADATA_HEADERS = {"X-OpenRouter-Metadata": "enabled"}


def fixed_model_runtime_policy(
    research_sources: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Return the managed Hermes model and resilience settings."""

    return {
        "model": {
            "default_headers": dict(_OPENROUTER_METADATA_HEADERS),
        },
        "fallback_providers": [{"provider": HERMES_PROVIDER, "model": HERMES_FALLBACK_MODEL}],
        "agent": {
            "api_max_retries": 1,
            "environment_hint": academic_research_environment_hint(research_sources),
        },
        "compression": {
            "enabled": True,
            "threshold": 0.50,
            "threshold_tokens": 100_000,
            "target_ratio": 0.20,
            "protect_last_n": 20,
            "proactive_prune_tokens": 48_000,
            "proactive_prune_min_result_chars": 8_000,
            "proactive_prune_min_reclaim_tokens": 4_096,
        },
        "provider_routing": {
            "sort": "throughput",
            "require_parameters": True,
        },
        "auxiliary": {
            "free_only": False,
            "openrouter_model": HERMES_MODEL,
        },
    }


class HermesClientError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        status_code: int | None,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.code = code


def _safe_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Hermes returned HTTP {response.status_code}."
    if not isinstance(payload, dict):
        return f"Hermes returned HTTP {response.status_code}."
    error = payload.get("error")
    if isinstance(error, dict):
        value = error.get("message") or error.get("code")
    else:
        value = error
    detail = payload.get("detail")
    message = value or detail
    if isinstance(message, str) and message.strip():
        return message.strip()[:1000]
    return f"Hermes returned HTTP {response.status_code}."


class HermesRuntimeClient:
    """Typed client for Hermes' official headless API server surface."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0))
        self._transport = transport

    def _profile_path(self, profile_name: str, path: str) -> str:
        profile = quote(profile_name, safe="")
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"/p/{profile}{normalized_path}"

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if extra:
            headers.update(extra)
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        )

    async def _request(
        self,
        method: str,
        *,
        profile_name: str,
        path: str,
        operation: str,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        expected: frozenset[int] = frozenset({200}),
    ) -> Any:
        try:
            async with self._client() as client:
                response = await client.request(
                    method,
                    self._profile_path(profile_name, path),
                    json=dict(json_body) if json_body is not None else None,
                    params=params,
                    headers=self._headers(headers),
                )
        except httpx.TimeoutException as error:
            raise HermesClientError(
                operation=operation,
                status_code=None,
                code="hermes.timeout",
                message="Hermes request timed out.",
            ) from error
        except httpx.HTTPError as error:
            raise HermesClientError(
                operation=operation,
                status_code=None,
                code="hermes.unavailable",
                message="Hermes runtime is unavailable.",
            ) from error
        if response.status_code not in expected:
            raise HermesClientError(
                operation=operation,
                status_code=response.status_code,
                code=f"hermes.http_{response.status_code}",
                message=_safe_error_message(response),
            )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as error:
            raise HermesClientError(
                operation=operation,
                status_code=response.status_code,
                code="hermes.invalid_json",
                message="Hermes returned an invalid JSON response.",
            ) from error
        if not isinstance(payload, dict):
            raise HermesClientError(
                operation=operation,
                status_code=response.status_code,
                code="hermes.invalid_response",
                message="Hermes returned an unexpected response.",
            )
        return payload

    async def health(self, profile_name: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path="/health/detailed",
            operation="health",
        )

    async def capabilities(self, profile_name: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path="/v1/capabilities",
            operation="capabilities",
        )

    async def toolsets(self, profile_name: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path="/v1/toolsets",
            operation="toolsets",
        )

    async def list_sessions(
        self,
        profile_name: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path="/api/sessions",
            operation="list_sessions",
            params={"limit": limit, "offset": offset},
        )

    async def create_session(
        self,
        profile_name: str,
        *,
        session_id: str,
        title: str | None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": session_id,
            "source": "open-work-hub",
        }
        if title:
            body["title"] = title
        if system_prompt:
            body["system_prompt"] = system_prompt
        return await self._request(
            "POST",
            profile_name=profile_name,
            path="/api/sessions",
            operation="create_session",
            json_body=body,
            expected=frozenset({201}),
        )

    async def get_session(self, profile_name: str, session_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path=f"/api/sessions/{quote(session_id, safe='')}",
            operation="get_session",
        )

    async def update_session(
        self,
        profile_name: str,
        session_id: str,
        changes: Mapping[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            profile_name=profile_name,
            path=f"/api/sessions/{quote(session_id, safe='')}",
            operation="update_session",
            json_body=changes,
        )

    async def delete_session(self, profile_name: str, session_id: str) -> None:
        await self._request(
            "DELETE",
            profile_name=profile_name,
            path=f"/api/sessions/{quote(session_id, safe='')}",
            operation="delete_session",
            expected=frozenset({200, 204}),
        )

    async def session_messages(
        self,
        profile_name: str,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path=f"/api/sessions/{quote(session_id, safe='')}/messages",
            operation="session_messages",
            params={"limit": limit, "offset": offset, "order": "oldest"},
        )

    async def fork_session(
        self,
        profile_name: str,
        session_id: str,
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            profile_name=profile_name,
            path=f"/api/sessions/{quote(session_id, safe='')}/fork",
            operation="fork_session",
            json_body={"title": title} if title else {},
            expected=frozenset({200, 201}),
        )

    async def create_run(
        self,
        profile_name: str,
        *,
        input_text: str,
        session_id: str,
        idempotency_key: str,
        instructions: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        runtime_options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            **{
                key: value
                for key, value in (runtime_options or {}).items()
                if key in {"provider", "model", "model_options"}
            },
            "input": input_text,
            "session_id": session_id,
        }
        if instructions:
            body["instructions"] = instructions
        if conversation_history:
            body["conversation_history"] = conversation_history
        return await self._request(
            "POST",
            profile_name=profile_name,
            path="/v1/runs",
            operation="create_run",
            json_body=body,
            headers={
                "Idempotency-Key": idempotency_key,
                "X-Hermes-Session-Id": session_id,
                "X-Hermes-Session-Key": f"open-work-hub:{profile_name}:{session_id}",
            },
            expected=frozenset({202}),
        )

    async def get_run(self, profile_name: str, run_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path=f"/v1/runs/{quote(run_id, safe='')}",
            operation="get_run",
        )

    async def iter_run_events(
        self,
        profile_name: str,
        run_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        path = self._profile_path(
            profile_name,
            f"/v1/runs/{quote(run_id, safe='')}/events",
        )
        try:
            stream_timeout = httpx.Timeout(
                connect=min(self._timeout.connect or 10.0, 10.0),
                read=None,
                write=self._timeout.write,
                pool=self._timeout.pool,
            )
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=stream_timeout,
                transport=self._transport,
            ) as client:
                async with client.stream("GET", path, headers=self._headers()) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise HermesClientError(
                            operation="run_events",
                            status_code=response.status_code,
                            code=f"hermes.http_{response.status_code}",
                            message=_safe_error_message(response),
                        )
                    data_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if not line:
                            if not data_lines:
                                continue
                            raw = "\n".join(data_lines)
                            data_lines.clear()
                            try:
                                event = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(event, dict):
                                yield event
                            continue
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
        except HermesClientError:
            raise
        except httpx.TimeoutException as error:
            raise HermesClientError(
                operation="run_events",
                status_code=None,
                code="hermes.events_timeout",
                message="Hermes event stream timed out.",
            ) from error
        except httpx.HTTPError as error:
            raise HermesClientError(
                operation="run_events",
                status_code=None,
                code="hermes.events_unavailable",
                message="Hermes event stream is unavailable.",
            ) from error

    async def stop_run(self, profile_name: str, run_id: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            profile_name=profile_name,
            path=f"/v1/runs/{quote(run_id, safe='')}/stop",
            operation="stop_run",
            json_body={},
        )

    async def steer_run(
        self,
        profile_name: str,
        run_id: str,
        input_text: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            profile_name=profile_name,
            path=f"/v1/runs/{quote(run_id, safe='')}/steer",
            operation="steer_run",
            json_body={"input": input_text},
        )

    async def resolve_approval(
        self,
        profile_name: str,
        run_id: str,
        *,
        request_id: str,
        choice: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            profile_name=profile_name,
            path=f"/v1/runs/{quote(run_id, safe='')}/approval",
            operation="resolve_approval",
            json_body={"request_id": request_id, "choice": choice},
        )

    async def list_jobs(self, profile_name: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            profile_name=profile_name,
            path="/api/jobs",
            operation="list_jobs",
            params={"include_disabled": "true"},
        )

    async def create_job(
        self,
        profile_name: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            profile_name=profile_name,
            path="/api/jobs",
            operation="create_job",
            json_body=payload,
        )

    async def job_action(
        self,
        profile_name: str,
        job_id: str,
        action: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if action not in {"pause", "resume", "run"}:
            raise ValueError(f"Unsupported Hermes job action: {action}")
        return await self._request(
            "POST",
            profile_name=profile_name,
            path=f"/api/jobs/{quote(job_id, safe='')}/{action}",
            operation=f"job_{action}",
            json_body=payload or {},
        )

    async def delete_job(self, profile_name: str, job_id: str) -> None:
        await self._request(
            "DELETE",
            profile_name=profile_name,
            path=f"/api/jobs/{quote(job_id, safe='')}",
            operation="delete_job",
        )


class HermesManagementClient:
    """Client for the local Hermes dashboard control plane."""

    def __init__(
        self,
        *,
        base_url: str,
        session_token: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session_token = session_token
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0))
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._session_token:
            headers["X-Hermes-Session-Token"] = self._session_token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        expected: frozenset[int] = frozenset({200}),
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=dict(body) if body is not None else None,
                    params=params,
                    headers=self._headers(),
                )
        except httpx.HTTPError as error:
            raise HermesClientError(
                operation=operation,
                status_code=None,
                code="hermes.management_unavailable",
                message="Hermes management service is unavailable.",
            ) from error
        if response.status_code not in expected:
            raise HermesClientError(
                operation=operation,
                status_code=response.status_code,
                code=f"hermes.management_http_{response.status_code}",
                message=_safe_error_message(response),
            )
        if not response.content:
            return {}
        return response.json()

    async def list_profiles(self) -> dict[str, Any]:
        return await self._request("GET", "/api/profiles", operation="list_profiles")

    async def list_mcp_servers(self, profile_name: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/mcp/servers",
            operation="list_mcp_servers",
            params={"profile": profile_name},
        )

    async def add_mcp_server(
        self,
        profile_name: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/mcp/servers",
            operation="add_mcp_server",
            params={"profile": profile_name},
            body={**payload, "profile": profile_name},
        )

    async def remove_mcp_server(self, profile_name: str, server_name: str) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/api/mcp/servers/{quote(server_name, safe='')}",
            operation="remove_mcp_server",
            params={"profile": profile_name},
        )

    async def set_mcp_server_enabled(
        self,
        profile_name: str,
        server_name: str,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/api/mcp/servers/{quote(server_name, safe='')}/enabled",
            operation="set_mcp_server_enabled",
            params={"profile": profile_name},
            body={"enabled": enabled, "profile": profile_name},
        )

    async def list_skills(self, profile_name: str) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            "/api/skills",
            operation="list_skills",
            params={"profile": profile_name},
        )
        if isinstance(payload, list):
            return {"skills": payload}
        return payload if isinstance(payload, dict) else {"skills": []}

    async def set_skill_enabled(
        self,
        profile_name: str,
        skill_name: str,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            "/api/skills/toggle",
            operation="set_skill_enabled",
            params={"profile": profile_name},
            body={"name": skill_name, "enabled": enabled, "profile": profile_name},
        )

    async def create_profile(
        self,
        *,
        profile_name: str,
        clone_from: str | None,
        description: str,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/profiles",
            operation="create_profile",
            body={
                "name": profile_name,
                "clone_from": clone_from,
                "description": description,
                "mcp_servers": mcp_servers or [],
            },
            expected=frozenset({200, 201}),
        )

    async def set_profile_model(
        self,
        profile_name: str,
        *,
        research_sources: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        result = await self._request(
            "PUT",
            f"/api/profiles/{quote(profile_name, safe='')}/model",
            operation="set_profile_model",
            body={"provider": HERMES_PROVIDER, "model": HERMES_MODEL},
        )
        await self._request(
            "PUT",
            "/api/config",
            operation="set_profile_model_policy",
            body={
                "profile": profile_name,
                "config": fixed_model_runtime_policy(research_sources),
            },
        )
        return result

    async def update_profile_config(
        self, profile_name: str, config: Mapping[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            "/api/config",
            operation="update_profile_config",
            body={"profile": profile_name, "config": dict(config)},
        )

    async def update_profile_env(self, profile_name: str, key: str, value: str) -> dict[str, Any]:
        return await self._request(
            "PUT",
            "/api/env",
            operation="update_profile_env",
            body={"profile": profile_name, "key": key, "value": value},
        )

    async def set_profile_mcp_trust(self, profile_name: str, server_name: str) -> dict[str, Any]:
        return await self._request(
            "PUT",
            "/api/config",
            operation="set_profile_mcp_trust",
            body={
                "profile": profile_name,
                "config": {
                    "mcp_servers": {
                        server_name: {
                            "trust": "untrusted",
                        }
                    }
                },
            },
        )
