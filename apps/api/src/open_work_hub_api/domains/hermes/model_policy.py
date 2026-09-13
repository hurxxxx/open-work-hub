"""Translate the administrator's immutable model selection to native Hermes config."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.llm import LlmPoolConfig
from open_work_hub_api.core.llm_errors import LlmProviderError
from open_work_hub_api.core.llm_provider_registry import llm_provider_descriptor
from open_work_hub_api.domains.hermes.client import HermesManagementClient


def resolve_model_policy(db: Session, *, workload_id: str = "chatbot") -> "HermesModelPolicy":
    from open_work_hub_api.domains.ai.model_settings_service import resolve_ai_model_workload_route
    from open_work_hub_api.domains.ai.runtime_status import build_resolved_llm_pool_config

    route = resolve_ai_model_workload_route(db, workload_id=workload_id)
    return HermesModelPolicy.from_pool(
        build_resolved_llm_pool_config(route),
        model=route.model_key,
        max_tokens=route.max_output_tokens,
    )


@dataclass(frozen=True)
class HermesModelPolicy:
    route: str
    provider: str
    model: str
    endpoint: str
    api_key: str = field(repr=False)
    max_tokens: int
    api_mode: str = "chat_completions"
    extra_headers: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def from_pool(cls, config: LlmPoolConfig, *, model: str, max_tokens: int):
        descriptor = llm_provider_descriptor(config.provider)
        if config.pool != "local" and not (
            descriptor
            and (descriptor.openai_compatible or config.provider in {"anthropic", "gemini"})
        ):
            raise LlmProviderError(
                "The selected provider has no supported Hermes transport.",
                pool=config.pool,
                provider=config.provider,
            )
        endpoint = config.base_url.rstrip("/")
        if config.provider == "gemini":
            # Google's documented OpenAI compatibility surface, same authority.
            if not endpoint.endswith("/v1beta/openai"):
                endpoint = endpoint.removesuffix("/v1beta") + "/v1beta/openai"
        return cls(
            route=config.pool,
            provider=config.provider,
            model=model,
            endpoint=endpoint,
            api_key=config.api_key,
            max_tokens=max_tokens,
            api_mode="anthropic_messages" if config.provider == "anthropic" else "chat_completions",
            extra_headers=dict(config.default_headers or {}),
        )

    @property
    def key(self) -> str:
        # Include credential rotation without persisting the secret in OWH run
        # projections. Each saved native provider entry is immutable.
        payload = [
            self.route,
            self.provider,
            self.model,
            self.endpoint,
            self.api_key,
            self.max_tokens,
            self.api_mode,
            sorted(self.extra_headers.items()),
        ]
        digest = hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:32]
        return f"owh-{digest}"

    def run_options(self, *, reasoning_effort: str | None = None) -> dict[str, Any]:
        return {
            "provider": f"custom:{self.key}",
            "model": self.model,
            "model_options": {"reasoning_effort": reasoning_effort} if reasoning_effort else {},
            "owh_policy": {
                "route": self.route,
                "provider": self.provider,
                "model": self.model,
                "max_output_tokens": self.max_tokens,
            },
        }


async def synchronize_model_policy(
    client: HermesManagementClient,
    *,
    profile_name: str,
    policy: HermesModelPolicy,
) -> None:
    env_key = f"OWH_MODEL_{policy.key[4:].upper()}"
    await client.update_profile_env(profile_name, env_key, policy.api_key or "no-key-required")
    await client.update_profile_config(
        profile_name,
        {
            "providers": {
                policy.key: {
                    "name": policy.key,
                    "base_url": policy.endpoint,
                    "key_env": env_key,
                    "default_model": policy.model,
                    "transport": policy.api_mode,
                    "max_output_tokens": policy.max_tokens,
                    "extra_headers": policy.extra_headers,
                }
            },
            "model": {
                "provider": f"custom:{policy.key}",
                "default": policy.model,
                "base_url": policy.endpoint,
                "key_env": env_key,
                "api_key": None,
                "max_tokens": None,
                "default_headers": {},
            },
            "fallback_providers": [],
            "fallback_model": None,
            "auxiliary": {
                task: {
                    "provider": "main",
                    "model": "",
                    "base_url": "",
                    "api_key": "",
                    "fallback_chain": [],
                }
                for task in (
                    "compression",
                    "vision",
                    "approval",
                    "title_generation",
                    "skills_hub",
                    "mcp",
                    "curator",
                    "background_review",
                    "memory_flush",
                )
            },
            "delegation": {"provider": "auto", "model": "", "base_url": "", "api_key": ""},
            "plugins": {"enabled": ["owh_runtime"], "disabled": []},
            "terminal": {
                "backend": "owh_sandbox",
                "container_persistent": False,
                "cwd": "/workspace",
            },
            "proxy": {"enabled": False},
            "platform_toolsets": {
                "api_server": [
                    "web",
                    "terminal",
                    "file",
                    "skills",
                    "todo",
                    "memory",
                    "session_search",
                    "code_execution",
                    "delegation",
                    "owh_runtime",
                ]
            },
        },
    )
