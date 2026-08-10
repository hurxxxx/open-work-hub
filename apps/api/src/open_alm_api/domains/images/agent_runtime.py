from __future__ import annotations

import base64
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from open_alm_api.domains.ai.external_gateway import (
    AiExternalCapabilityPolicyViolation,
    AiExternalCapabilityRequest,
    execute_external_capability,
    execute_external_capability_async,
)
from open_alm_api.domains.images.prompt import (
    BRIEF_SYSTEM_PROMPT,
    ILLUSTRATOR_SYSTEM_PROMPT,
    build_agent_prompt,
)
from open_alm_api.domains.images.provider_registry import (
    ensure_builtin_image_providers_registered,
    normalize_image_adapter_id,
    normalize_image_provider_id,
)


logger = logging.getLogger(__name__)


_VALID_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
_VALID_BACKGROUNDS = {"transparent", "opaque", "auto"}
_VALID_QUALITIES = {"low", "medium", "high", "auto"}


@dataclass(frozen=True)
class ImageBriefRuntimeResult:
    text: str
    raw_result: Any | None = None


@dataclass(frozen=True)
class ImageGenerationRuntimeResult:
    image_bytes: bytes | None
    agent_trace_id: str | None = None
    raw_result: Any | None = None


class ImageRuntimeConfigurationError(RuntimeError):
    pass


class ImageRuntimeProviderError(RuntimeError):
    pass


class ImageAgentRuntimeAdapter(Protocol):
    provider_id: str

    def run_brief(
        self,
        *,
        input_text: str,
        model: str,
        api_key: str,
        base_url: str,
        workspace_id: str,
        user_id: str,
        generation_id: str,
        enable_web_search: bool,
        execution_profile: Mapping[str, Any] | None = None,
        db: Session | None = None,
    ) -> ImageBriefRuntimeResult: ...

    async def generate_image(
        self,
        *,
        brief_text: str,
        style: dict[str, Any],
        layout: dict[str, Any],
        reference_images: list[tuple[str, str, bytes]],
        max_turns: int,
        supervisor_model: str,
        image_model: str,
        api_key: str,
        base_url: str,
        enable_web_search: bool,
        workspace_id: str = "unknown",
        user_id: str | None = None,
        generation_id: str | None = None,
        execution_profile: Mapping[str, Any] | None = None,
        db: Session | None = None,
    ) -> ImageGenerationRuntimeResult: ...


_adapters_by_provider: dict[str, ImageAgentRuntimeAdapter] = {}
_adapters_by_id: dict[str, ImageAgentRuntimeAdapter] = {}


def image_agent_runtime_adapter_id(adapter: ImageAgentRuntimeAdapter) -> str:
    return normalize_image_adapter_id(
        getattr(adapter, "adapter_id", "") or normalize_image_provider_id(adapter.provider_id)
    )


def register_image_agent_runtime_adapter(adapter: ImageAgentRuntimeAdapter) -> None:
    provider_id = normalize_image_provider_id(adapter.provider_id)
    adapter_id = image_agent_runtime_adapter_id(adapter)
    if not provider_id:
        raise ValueError("Image agent runtime adapter provider id is required")
    if not adapter_id:
        raise ValueError(f"Image agent runtime adapter id is required for {provider_id}")
    if adapter_id in _adapters_by_id:
        raise ValueError(f"Image agent runtime adapter already registered: {adapter_id}")
    if provider_id not in _adapters_by_provider:
        _adapters_by_provider[provider_id] = adapter
    _adapters_by_id[adapter_id] = adapter


def get_image_agent_runtime_adapter(provider_id: str) -> ImageAgentRuntimeAdapter | None:
    return _adapters_by_provider.get(normalize_image_provider_id(provider_id))


def get_image_agent_runtime_adapter_by_id(adapter_id: str) -> ImageAgentRuntimeAdapter | None:
    return _adapters_by_id.get(normalize_image_adapter_id(adapter_id))


def has_image_agent_runtime_adapter(provider_id: str) -> bool:
    return normalize_image_provider_id(provider_id) in _adapters_by_provider


def image_agent_runtime_provider_ids() -> tuple[str, ...]:
    return tuple(sorted(_adapters_by_provider))


def image_agent_runtime_adapter_ids() -> tuple[str, ...]:
    return tuple(sorted(_adapters_by_id))


def reset_image_agent_runtime_adapters() -> None:
    _adapters_by_provider.clear()
    _adapters_by_id.clear()


def ensure_builtin_image_agent_runtime_adapters_registered() -> None:
    ensure_builtin_image_providers_registered()
    if not has_image_agent_runtime_adapter(OpenAIImageAgentRuntimeAdapter.provider_id):
        register_image_agent_runtime_adapter(OpenAIImageAgentRuntimeAdapter())


def select_image_agent_runtime_adapter(
    provider_id: str,
    *,
    adapter_id: str | None = None,
) -> ImageAgentRuntimeAdapter:
    ensure_builtin_image_agent_runtime_adapters_registered()
    if adapter_id is not None:
        normalized_adapter_id = normalize_image_adapter_id(adapter_id)
        adapter = get_image_agent_runtime_adapter_by_id(normalized_adapter_id)
        if adapter is not None:
            normalized_provider_id = normalize_image_provider_id(provider_id)
            adapter_provider_id = normalize_image_provider_id(adapter.provider_id)
            if adapter_provider_id != normalized_provider_id:
                raise ValueError(
                    "Image agent runtime adapter provider mismatch: "
                    f"{normalized_adapter_id} is registered for {adapter_provider_id}, "
                    f"not {normalized_provider_id}"
                )
            return adapter
        raise ValueError(f"Image agent runtime adapter is not registered: {normalized_adapter_id}")
    adapter = get_image_agent_runtime_adapter(provider_id)
    if adapter is None:
        normalized = normalize_image_provider_id(provider_id)
        raise ValueError(f"Image agent runtime adapter is not registered for {normalized}")
    return adapter


def extract_agent_text(result: Any) -> str:
    final_output = getattr(result, "final_output", None)
    if isinstance(final_output, str):
        return final_output.strip()
    if final_output is not None:
        return str(final_output).strip()
    return ""


def _normalize_size(value: str) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned in _VALID_SIZES else "1024x1024"


def _normalize_background(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned == "white" or cleaned == "dark":
        # Treat preset palette backgrounds as opaque so the prompt language
        # carries the exact requested look.
        return "opaque"
    return cleaned if cleaned in _VALID_BACKGROUNDS else "auto"


def _normalize_quality(value: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in _VALID_QUALITIES else "high"


def _build_agent_input_items(
    *,
    brief_text: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    reference_images: list[tuple[str, str, bytes]],
) -> list[dict[str, Any]]:
    text = build_agent_prompt(
        brief_text=brief_text,
        style=style,
        layout=layout,
        reference_roles=[role for role, _, _ in reference_images],
    )
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for _role, content_type, data in reference_images:
        b64 = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{content_type};base64,{b64}",
                "detail": "high",
            }
        )
    return [{"role": "user", "content": content}]


def _require_api_key(api_key: str) -> str:
    cleaned = (api_key or "").strip()
    if not cleaned:
        raise ImageRuntimeConfigurationError("OpenAI image runtime requires an API key")
    return cleaned


def _extract_image_result(result: Any) -> ImageGenerationRuntimeResult:
    image_bytes: bytes | None = None
    new_items = getattr(result, "new_items", None) or []
    for item in new_items:
        raw = getattr(item, "raw_item", None)
        item_type = getattr(raw, "type", None) if raw is not None else None
        if item_type == "image_generation_call":
            status = getattr(raw, "status", None)
            data = getattr(raw, "result", None)
            if status == "completed" and isinstance(data, str) and data:
                try:
                    image_bytes = base64.b64decode(data)
                except Exception:
                    image_bytes = None
    trace_id = (
        getattr(result, "_trace_id", None)
        or getattr(result, "trace_id", None)
        or getattr(getattr(result, "context", None), "trace_id", None)
    )
    if not isinstance(trace_id, str):
        trace_id = None
    return ImageGenerationRuntimeResult(
        image_bytes=image_bytes,
        agent_trace_id=trace_id,
        raw_result=result,
    )


class OpenAIImageAgentRuntimeAdapter:
    adapter_id = "openai"
    provider_id = "openai"

    @staticmethod
    def _normalize_background_for_model(value: str, *, image_model: str) -> str:
        background = _normalize_background(value)
        if background == "transparent" and image_model.startswith("gpt-image-2"):
            logger.info(
                "images.generate: coercing transparent background to auto for %s",
                image_model,
            )
            return "auto"
        return background

    def run_brief(
        self,
        *,
        input_text: str,
        model: str,
        api_key: str,
        base_url: str,
        workspace_id: str,
        user_id: str,
        generation_id: str,
        enable_web_search: bool,
        execution_profile: Mapping[str, Any] | None = None,
        db: Session | None = None,
    ) -> ImageBriefRuntimeResult:
        del execution_profile
        # Local import so DB-only tests can import the service without initializing
        # the SDK until the image feature is actually used.
        from agents import (
            Agent,
            ModelSettings,
            OpenAIProvider,
            RunConfig,
            Runner,
            WebSearchTool,
        )

        agent = Agent(
            name="image-brief-designer",
            instructions=BRIEF_SYSTEM_PROMPT,
            model=model,
            model_settings=ModelSettings(max_tokens=2600, tool_choice="auto"),
            tools=[WebSearchTool(search_context_size="high")] if enable_web_search else [],
        )
        run_config = RunConfig(
            model_provider=OpenAIProvider(api_key=_require_api_key(api_key), base_url=base_url),
            workflow_name="Open ALM Image Plan",
            trace_metadata={
                "source": "images.brief",
                "workspace_id": workspace_id,
                "actor_user_id": user_id,
                "generation_id": generation_id,
            },
        )

        gateway_request = AiExternalCapabilityRequest(
            source="images.brief",
            workspace_id=workspace_id,
            actor_user_id=user_id,
            principal_id=user_id,
            task_kind="image_brief",
            capability="image_brief",
            provider=self.provider_id,
            input_texts=[input_text],
            entity_id=generation_id,
            metadata={
                "adapter_id": self.adapter_id,
                "model": model,
                "web_search_enabled": enable_web_search,
            },
        )

        def _run_sdk(execution):
            return Runner.run_sync(
                agent,
                input=execution.sanitized_text(fallback=input_text),
                max_turns=10,
                run_config=run_config,
            )

        try:
            result = execute_external_capability(
                gateway_request,
                _run_sdk,
                db=db,
                metadata={
                    "sdk": "openai-agents",
                    "workflow_name": run_config.workflow_name,
                },
            )
        except AiExternalCapabilityPolicyViolation as exc:
            raise ImageRuntimeProviderError(str(exc)) from exc
        except Exception as exc:
            raise ImageRuntimeProviderError(str(exc)) from exc
        return ImageBriefRuntimeResult(text=extract_agent_text(result), raw_result=result)

    async def generate_image(
        self,
        *,
        brief_text: str,
        style: dict[str, Any],
        layout: dict[str, Any],
        reference_images: list[tuple[str, str, bytes]],
        max_turns: int,
        supervisor_model: str,
        image_model: str,
        api_key: str,
        base_url: str,
        enable_web_search: bool,
        workspace_id: str = "unknown",
        user_id: str | None = None,
        generation_id: str | None = None,
        execution_profile: Mapping[str, Any] | None = None,
        db: Session | None = None,
    ) -> ImageGenerationRuntimeResult:
        del execution_profile
        gateway_request = AiExternalCapabilityRequest(
            source="images.generate",
            workspace_id=workspace_id,
            actor_user_id=user_id,
            principal_id=user_id,
            task_kind="image_generation",
            capability="image_generation",
            provider=self.provider_id,
            input_texts=[brief_text],
            entity_id=generation_id,
            metadata={
                "adapter_id": self.adapter_id,
                "supervisor_model": supervisor_model,
                "image_model": image_model,
                "reference_image_count": len(reference_images),
                "web_search_enabled": enable_web_search,
            },
        )
        # Local import so plain DB-only tests can run without the SDK installed.
        from agents import (
            Agent,
            ImageGenerationTool,
            ModelSettings,
            OpenAIProvider,
            RunConfig,
            Runner,
            WebSearchTool,
        )

        provider_brief_text = brief_text
        success_metadata: dict[str, Any] = {
            "sdk": "openai-agents",
            "workflow_name": "Open ALM Image Generation",
            "provider_input_sanitized": False,
        }
        size = _normalize_size(str((layout or {}).get("aspect") or ""))
        background = self._normalize_background_for_model(
            str((style or {}).get("background") or ""),
            image_model=image_model,
        )
        quality = _normalize_quality(str((style or {}).get("quality") or ""))

        tool = ImageGenerationTool(
            tool_config={
                "type": "image_generation",
                "model": image_model,
                "size": size,
                "background": background,
                "quality": quality,
                "moderation": "auto",
                "output_format": "png",
            }
        )
        agent = Agent(
            name="infographic-illustrator",
            instructions=ILLUSTRATOR_SYSTEM_PROMPT,
            model=supervisor_model,
            model_settings=ModelSettings(tool_choice="auto"),
            tools=(
                [WebSearchTool(search_context_size="high"), tool] if enable_web_search else [tool]
            ),
        )
        run_config = RunConfig(
            model_provider=OpenAIProvider(api_key=_require_api_key(api_key), base_url=base_url),
            workflow_name="Open ALM Image Generation",
            trace_metadata={
                "source": "images.generate",
                "image_model": image_model,
                "supervisor_model": supervisor_model,
            },
        )

        async def _run_sdk(execution):
            nonlocal provider_brief_text
            provider_brief_text = execution.sanitized_text(fallback=brief_text)
            success_metadata["provider_input_sanitized"] = provider_brief_text != brief_text
            input_items = _build_agent_input_items(
                brief_text=provider_brief_text,
                style=style,
                layout=layout,
                reference_images=reference_images,
            )
            return await Runner.run(
                agent,
                input=input_items,
                max_turns=max_turns,
                run_config=run_config,
            )

        try:
            result = await execute_external_capability_async(
                gateway_request,
                _run_sdk,
                db=db,
                metadata=success_metadata,
            )
        except AiExternalCapabilityPolicyViolation as exc:
            raise ImageRuntimeProviderError(str(exc)) from exc
        except Exception as exc:
            raise ImageRuntimeProviderError(str(exc)) from exc
        return _extract_image_result(result)


__all__ = [
    "ImageAgentRuntimeAdapter",
    "ImageBriefRuntimeResult",
    "ImageGenerationRuntimeResult",
    "ImageRuntimeConfigurationError",
    "ImageRuntimeProviderError",
    "OpenAIImageAgentRuntimeAdapter",
    "ensure_builtin_image_agent_runtime_adapters_registered",
    "get_image_agent_runtime_adapter_by_id",
    "extract_agent_text",
    "get_image_agent_runtime_adapter",
    "has_image_agent_runtime_adapter",
    "image_agent_runtime_adapter_id",
    "image_agent_runtime_adapter_ids",
    "image_agent_runtime_provider_ids",
    "normalize_image_adapter_id",
    "normalize_image_provider_id",
    "register_image_agent_runtime_adapter",
    "reset_image_agent_runtime_adapters",
    "select_image_agent_runtime_adapter",
]
