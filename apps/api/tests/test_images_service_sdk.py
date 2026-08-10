from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from open_alm_api.domains.ai import external_gateway
from open_alm_api.domains.images import service
from open_alm_api.domains.images.agent_runtime import (
    ImageBriefRuntimeResult,
    register_image_agent_runtime_adapter,
    reset_image_agent_runtime_adapters,
)
from open_alm_api.domains.images.execution_profile import build_image_execution_profile
from open_alm_api.domains.images.template_catalog import BUILTIN_IMAGE_TEMPLATES
from open_alm_api.domains.images.prompt import (
    build_agent_prompt,
    sanitize_image_plan_text,
)


def test_builtin_template_catalog_assets_exist() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    assert len(BUILTIN_IMAGE_TEMPLATES) == 22
    for template in BUILTIN_IMAGE_TEMPLATES.values():
        asset_path = repo_root / "apps" / "web" / "public" / template.asset_path.lstrip("/")
        assert asset_path.exists(), template.id
        assert asset_path.stat().st_size > 1024, template.id


def test_brief_input_skips_system_message() -> None:
    assert (
        service.brief_input_from_messages(
            [
                {"role": "system", "content": "rules"},
                {"role": "user", "content": "make a product launch image"},
            ]
        )
        == "make a product launch image"
    )


def test_run_brief_agent_uses_agents_sdk_provider(monkeypatch) -> None:
    captured = {}
    audit_records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: audit_records.append(kwargs),
    )

    def fake_run_sync(agent, *, input, max_turns, run_config):
        captured["agent"] = agent
        captured["input"] = input
        captured["max_turns"] = max_turns
        captured["run_config"] = run_config
        return SimpleNamespace(final_output="TITLE: SDK brief")

    from agents import Runner

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    result = service.run_brief_agent(
        provider_id="openai",
        input_text="brief context",
        model="gpt-5.5",
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        workspace_id="workspace-1",
        user_id="user-1",
        generation_id="generation-1",
        enable_web_search=True,
    )

    assert result.text == "TITLE: SDK brief"
    assert captured["agent"].model == "gpt-5.5"
    assert captured["agent"].model_settings.tool_choice == "auto"
    assert [tool.name for tool in captured["agent"].tools] == ["web_search"]
    assert captured["input"] == "brief context"
    assert captured["max_turns"] == 10
    assert type(captured["run_config"].model_provider).__name__ == "OpenAIProvider"
    assert captured["run_config"].workflow_name == "Open ALM Image Plan"
    assert audit_records[0]["status"] == "ok"
    assert audit_records[0]["capability"] == "image_brief"


def test_run_brief_agent_delegates_empty_api_key_to_extension_provider() -> None:
    captured = {}
    execution_profile = {
        "version": "image_execution_profile.v1",
        "provider_id": "local",
        "adapter_id": "local",
    }

    class ExtensionImageRuntimeAdapter:
        provider_id = "local"

        def run_brief(self, **kwargs) -> ImageBriefRuntimeResult:
            captured.update(kwargs)
            return ImageBriefRuntimeResult(text="local brief")

        async def generate_image(self, **kwargs):
            del kwargs
            raise AssertionError("generate_image should not run")

    reset_image_agent_runtime_adapters()
    try:
        register_image_agent_runtime_adapter(ExtensionImageRuntimeAdapter())

        result = service.run_brief_agent(
            provider_id="local",
            input_text="brief context",
            model="local-planner",
            api_key="",
            base_url="",
            workspace_id="workspace-1",
            user_id="user-1",
            generation_id="generation-1",
            enable_web_search=False,
            execution_profile=execution_profile,
        )

        assert result.text == "local brief"
        assert captured["api_key"] == ""
        assert captured["execution_profile"] == execution_profile
    finally:
        reset_image_agent_runtime_adapters()


def test_run_brief_agent_threads_security_db_to_runtime_adapter() -> None:
    captured = {}
    security_db = object()

    class ExtensionImageRuntimeAdapter:
        provider_id = "local"

        def run_brief(self, **kwargs) -> ImageBriefRuntimeResult:
            captured.update(kwargs)
            return ImageBriefRuntimeResult(text="local brief")

        async def generate_image(self, **kwargs):
            del kwargs
            raise AssertionError("generate_image should not run")

    reset_image_agent_runtime_adapters()
    try:
        register_image_agent_runtime_adapter(ExtensionImageRuntimeAdapter())

        result = service.run_brief_agent(
            provider_id="local",
            input_text="brief context",
            model="local-planner",
            api_key="",
            base_url="",
            workspace_id="workspace-1",
            user_id="user-1",
            generation_id="generation-1",
            enable_web_search=False,
            db=security_db,
        )

        assert result.text == "local brief"
        assert captured["db"] is security_db
    finally:
        reset_image_agent_runtime_adapters()


def test_image_execution_profile_snapshots_db_resolved_runtime_without_secret() -> None:
    resolved = SimpleNamespace(
        provider_id="openai",
        adapter_id="openai",
        supervisor_model_id="configured-supervisor",
        generation_model_id="configured-image-model",
        generation_web_search_enabled=False,
        max_iterations=7,
    )
    row = SimpleNamespace(
        style={"background": "transparent", "quality": "high"},
        layout={"aspect": "1536x1024"},
    )

    profile = build_image_execution_profile(
        row,
        resolved,
        max_reference_uploads=3,
    )

    assert profile == {
        "version": "image_execution_profile.v2",
        "provider_id": "openai",
        "adapter_id": "openai",
        "credential_ref": "image-provider:openai",
        "generation_model_id": "configured-image-model",
        "supervisor_model_id": "configured-supervisor",
        "requested_options": {
            "background": "transparent",
            "quality": "high",
            "aspect": "1536x1024",
            "web_search_enabled": False,
            "max_iterations": 7,
            "max_reference_uploads": 3,
        },
    }


def test_sanitize_image_plan_text_removes_placeholder_tokens() -> None:
    text = sanitize_image_plan_text(
        "제목: <title>\n"
        "구성: <클라이언트>와 <서비스 계층>\n"
        "- <metric>\n"
        "- 실제 항목\n"
        "화면에 넣을 텍스트: <설명 텍스트>"
    )

    assert "<" not in text
    assert ">" not in text
    assert "metric" not in text
    assert "설명 텍스트" not in text
    assert "클라이언트와 서비스 계층" in text
    assert "실제 항목" in text


def test_build_agent_prompt_sanitizes_approved_plan() -> None:
    prompt = build_agent_prompt(
        brief_text="구성: <클라이언트> <metric>\n화면에 넣을 텍스트: 없음",
        style={"chips": [], "palette": "", "background": "", "quality": "high"},
        layout={"layout_id": "top_title_grid", "aspect": "1024x1024"},
        reference_roles=[],
    )

    approved_block = prompt.split("[스타일 메타]", 1)[0]
    assert "[승인된 이미지 계획]" in approved_block
    assert "<metric>" not in approved_block
    assert "metric" not in approved_block
    assert "클라이언트" in approved_block
