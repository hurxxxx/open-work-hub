from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import re
from time import monotonic
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.hermes.client import (
    HermesClientError,
    HermesManagementClient,
    HermesRuntimeClient,
)
from open_work_hub_api.domains.hermes.models import HermesProfileBinding
from open_work_hub_api.domains.hermes.research_settings import (
    get_research_settings,
)
from open_work_hub_api.domains.hermes.research_sources import ResearchSourceId
from open_work_hub_api.domains.hermes.repository import get_or_create_profile_binding


class HermesIntegrationDisabledError(RuntimeError):
    pass


_JOB_PROFILE_RECONCILE_TTL_SECONDS = 300.0
_PROFILE_RECONCILE_TTL_SECONDS = 300.0
_job_profile_reconciled_until: dict[str, float] = {}
_profile_reconciled_until: dict[str, float] = {}


def invalidate_profile_policy_cache() -> None:
    _job_profile_reconciled_until.clear()
    _profile_reconciled_until.clear()


def _reconcile_cache_hit(
    cache: dict[str, float],
    key: str,
    *,
    now: float,
) -> bool:
    if cache.get(key, 0.0) > now:
        return True
    if len(cache) >= 2048:
        expired = [name for name, deadline in cache.items() if deadline <= now]
        for name in expired:
            cache.pop(name, None)
        while len(cache) >= 2048:
            cache.pop(next(iter(cache)))
    return False


def runtime_client(settings: Settings | None = None) -> HermesRuntimeClient:
    resolved = settings or get_settings()
    return HermesRuntimeClient(
        base_url=resolved.hermes_runtime_base_url,
        api_key=resolved.hermes_api_key.get_secret_value(),
        timeout_seconds=resolved.hermes_request_timeout_seconds,
    )


def management_client(settings: Settings | None = None) -> HermesManagementClient:
    resolved = settings or get_settings()
    return HermesManagementClient(
        base_url=resolved.hermes_management_base_url,
        session_token=resolved.hermes_management_token.get_secret_value(),
        timeout_seconds=resolved.hermes_request_timeout_seconds,
    )


def require_hermes_enabled(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    if not resolved.hermes_enabled:
        raise HermesIntegrationDisabledError("Hermes integration is disabled.")
    return resolved


def _profile_names(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("profiles")
    if not isinstance(rows, list):
        return set()
    names: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            name = row.get("name")
        else:
            name = row
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _mcp_server_names(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("servers")
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("name")).strip()
        for row in rows
        if isinstance(row, dict) and row.get("name")
    }


def _mcp_server_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("servers")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("name")).strip(): row
        for row in rows
        if isinstance(row, dict) and row.get("name")
    }


def _internal_mcp_server_matches(
    current: dict[str, Any],
    desired: dict[str, Any],
) -> bool:
    """Compare fields Hermes returns for its official MCP server config."""
    return (
        current.get("url") == desired.get("url")
        and current.get("auth") == desired.get("auth")
        and current.get("enabled", True) is not False
        and current.get("tools") is None
    )


def _mcp_profile_servers(
    settings: Settings,
    binding: HermesProfileBinding,
) -> list[dict[str, Any]]:
    url = settings.hermes_mcp_server_url
    if not url:
        return []
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["profile"] = binding.profile_name
    profile_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )
    server: dict[str, Any] = {
        "name": internal_mcp_server_name(binding.profile_name),
        "url": profile_url,
        "auth": "header",
    }
    secret = mcp_profile_bearer_secret(settings, binding.profile_name)
    if secret:
        server["bearer_token"] = secret
    return [server]


def profile_mcp_namespace(profile_name: str) -> str:
    digest = hashlib.sha256(profile_name.encode()).hexdigest()[:20]
    return f"owh-mcp-{digest}"


def internal_mcp_server_name(profile_name: str) -> str:
    return f"{profile_mcp_namespace(profile_name)}-internal"


def scoped_mcp_server_name(profile_name: str, logical_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", logical_name.strip().lower())
    slug = normalized.strip("-_")[:16] or "server"
    digest = hashlib.sha256(logical_name.strip().encode()).hexdigest()[:10]
    return f"{profile_mcp_namespace(profile_name)}-{slug}-{digest}"


def is_profile_scoped_mcp_server(profile_name: str, server_name: str) -> bool:
    return server_name.startswith(f"{profile_mcp_namespace(profile_name)}-")


def mcp_profile_bearer_secret(settings: Settings, profile_name: str) -> str:
    root_secret = settings.hermes_mcp_shared_secret.get_secret_value()
    if not root_secret:
        return ""
    return hmac.new(
        root_secret.encode(),
        f"open-work-hub-hermes-mcp:{profile_name}".encode(),
        hashlib.sha256,
    ).hexdigest()


def job_profile_name(binding: HermesProfileBinding) -> str:
    return f"{binding.profile_name}-jobs"


async def ensure_job_profile(
    binding: HermesProfileBinding,
    *,
    settings: Settings | None = None,
    client: HermesManagementClient | None = None,
    research_sources: dict[ResearchSourceId, bool] | None = None,
    research_policy_revision: int = 0,
) -> str:
    """Provision the cron-only profile without any MCP servers.

    Hermes API runs and cron jobs can execute concurrently. Keeping cron in a
    separate profile prevents a scheduled run from borrowing the app scope of
    an unrelated interactive run through a process-global MCP connection.
    """
    resolved = require_hermes_enabled(settings)
    profile_name = job_profile_name(binding)
    reconcile_key = f"{profile_name}:research:{research_policy_revision}"
    now = monotonic()
    if _reconcile_cache_hit(
        _job_profile_reconciled_until,
        reconcile_key,
        now=now,
    ):
        return profile_name
    control = client or management_client(resolved)
    profiles = await control.list_profiles()
    if profile_name not in _profile_names(profiles):
        try:
            await control.create_profile(
                profile_name=profile_name,
                clone_from=binding.profile_name,
                description="Open Work Hub isolated scheduled-agent profile",
                mcp_servers=[],
            )
        except HermesClientError as error:
            if error.status_code not in {400, 409}:
                raise
            profiles = await control.list_profiles()
            if profile_name not in _profile_names(profiles):
                raise
    await control.set_profile_model(
        profile_name,
        research_sources=research_sources,
    )
    mcp_servers = await control.list_mcp_servers(profile_name)
    for server_name in sorted(_mcp_server_names(mcp_servers)):
        try:
            await control.remove_mcp_server(profile_name, server_name)
        except HermesClientError as error:
            if error.status_code != 404:
                raise
    remaining_servers = _mcp_server_names(await control.list_mcp_servers(profile_name))
    if remaining_servers:
        raise HermesClientError(
            operation="reconcile_job_profile",
            status_code=409,
            code="hermes.job_profile_mcp_not_empty",
            message="The isolated Hermes job profile still has MCP servers configured.",
        )
    _job_profile_reconciled_until[reconcile_key] = (
        monotonic() + _JOB_PROFILE_RECONCILE_TTL_SECONDS
    )
    return profile_name


async def ensure_profile_binding(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    settings: Settings | None = None,
    client: HermesManagementClient | None = None,
    research_sources: dict[ResearchSourceId, bool] | None = None,
    research_policy_revision: int | None = None,
) -> HermesProfileBinding:
    resolved = require_hermes_enabled(settings)
    binding = get_or_create_profile_binding(db, workspace=workspace, user=user)
    db.commit()
    db.refresh(binding)
    if research_sources is None or research_policy_revision is None:
        research_settings = get_research_settings(db)
        resolved_research_sources = research_settings.policy
        resolved_research_policy_revision = research_settings.revision
    else:
        resolved_research_sources = research_sources
        resolved_research_policy_revision = research_policy_revision
    reconcile_key = (
        f"{binding.profile_name}:research:{resolved_research_policy_revision}"
    )
    cache_now = monotonic()
    if binding.status == "active" and _reconcile_cache_hit(
        _profile_reconciled_until,
        reconcile_key,
        now=cache_now,
    ):
        return binding

    control = client or management_client(resolved)
    try:
        profiles = await control.list_profiles()
        if binding.profile_name not in _profile_names(profiles):
            try:
                await control.create_profile(
                    profile_name=binding.profile_name,
                    clone_from=resolved.hermes_profile_clone_source,
                    description="Open Work Hub isolated user workspace agent profile",
                    mcp_servers=_mcp_profile_servers(resolved, binding),
                )
            except HermesClientError as error:
                # Concurrent first requests may both observe an absent
                # profile. Treat the create conflict as success only after
                # reading the profile back from Hermes.
                if error.status_code not in {400, 409}:
                    raise
                profiles = await control.list_profiles()
                if binding.profile_name not in _profile_names(profiles):
                    raise
        await control.set_profile_model(
            binding.profile_name,
            research_sources=resolved_research_sources,
        )
        mcp_servers = await control.list_mcp_servers(binding.profile_name)
        server_rows = _mcp_server_rows(mcp_servers)
        server_names = set(server_rows)
        if resolved.hermes_mcp_server_url:
            internal_server_name = internal_mcp_server_name(binding.profile_name)
            internal_server = _mcp_profile_servers(resolved, binding)[0]
            current_internal_server = server_rows.get(internal_server_name)
            if current_internal_server is not None and not _internal_mcp_server_matches(
                current_internal_server,
                internal_server,
            ):
                try:
                    await control.remove_mcp_server(
                        binding.profile_name,
                        internal_server_name,
                    )
                except HermesClientError as error:
                    if error.status_code != 404:
                        raise
                server_names.discard(internal_server_name)
            if internal_server_name not in server_names:
                try:
                    await control.add_mcp_server(binding.profile_name, internal_server)
                except HermesClientError as error:
                    if error.status_code != 409:
                        raise
                    mcp_servers = await control.list_mcp_servers(binding.profile_name)
                    server_rows = _mcp_server_rows(mcp_servers)
                    server_names = set(server_rows)
                    current_internal_server = server_rows.get(internal_server_name)
                    if current_internal_server is None or not _internal_mcp_server_matches(
                        current_internal_server,
                        internal_server,
                    ):
                        raise
                server_names.add(internal_server_name)
            await control.set_profile_mcp_trust(
                binding.profile_name,
                internal_server_name,
            )
        # Hermes keeps MCP connections in one process-global registry, keyed
        # by server name. Drop inherited or legacy unscoped names so another
        # profile can never reuse this profile's connection.
        unsafe_server_names = sorted(
            name
            for name in server_names
            if not is_profile_scoped_mcp_server(binding.profile_name, name)
        )
        for server_name in unsafe_server_names:
            try:
                await control.remove_mcp_server(binding.profile_name, server_name)
            except HermesClientError as error:
                if error.status_code != 404:
                    raise
        reconciled_server_names = _mcp_server_names(
            await control.list_mcp_servers(binding.profile_name)
        )
        if any(
            not is_profile_scoped_mcp_server(binding.profile_name, name)
            for name in reconciled_server_names
        ):
            raise HermesClientError(
                operation="reconcile_profile_mcp",
                status_code=409,
                code="hermes.profile_mcp_not_isolated",
                message="The Hermes profile still has an unscoped MCP server configured.",
            )
        if (
            resolved.hermes_mcp_server_url
            and internal_mcp_server_name(binding.profile_name)
            not in reconciled_server_names
        ):
            raise HermesClientError(
                operation="reconcile_profile_mcp",
                status_code=409,
                code="hermes.internal_mcp_missing",
                message="The Hermes profile is missing its internal MCP server.",
            )
    except HermesClientError as error:
        binding.status = "error"
        binding.last_error_code = error.code[:160]
        binding.last_reconciled_at = datetime.now(UTC).replace(tzinfo=None)
        db.add(binding)
        db.commit()
        raise

    now = datetime.now(UTC).replace(tzinfo=None)
    binding.status = "active"
    binding.last_error_code = None
    binding.provisioned_at = binding.provisioned_at or now
    binding.last_reconciled_at = now
    db.add(binding)
    db.commit()
    db.refresh(binding)
    _profile_reconciled_until[reconcile_key] = (
        monotonic() + _PROFILE_RECONCILE_TTL_SECONDS
    )
    return binding
