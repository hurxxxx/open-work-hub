from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr
import pytest

from open_work_hub_api.domains.ai.agent_runtime import (
    AgentRuntimeRequest,
    agent_runtime_adapter_ids,
    reset_agent_runtime_adapters,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    _require_runtime_route_compatibility,
)
from open_work_hub_api.domains.ai.registry import RegisteredLlmWorkload
from open_work_hub_api.domains.bento.agent_runtime import (
    CodexSdkBentoAdapter,
    _sanitized_current_document_json,
    ensure_bento_agent_runtime_adapters_registered,
)
from open_work_hub_api.domains.bento import agent_runtime as bento_agent_runtime
from open_work_hub_api.domains.bento.agent_tools import (
    inspect_document,
    render_document,
    validate_document,
)


def test_bento_agent_runtime_registers_both_explicit_adapters() -> None:
    reset_agent_runtime_adapters()
    ensure_bento_agent_runtime_adapters_registered()

    assert agent_runtime_adapter_ids() == ("codex_sdk", "fixed_bento_pipeline")


def test_bento_runtime_adapter_rejects_incompatible_routes() -> None:
    ensure_bento_agent_runtime_adapters_registered()
    workload = RegisteredLlmWorkload(
        workload_id="bento.test",
        task_kind="bento_test",
        owner_domain="bento",
        app_ids=("bento",),
        description="Runtime compatibility test",
        execution_kind="agent",
        allowed_routes=("local", "external"),
        allowed_providers=("openai",),
        default_runtime_adapter="fixed_bento_pipeline",
        allowed_runtime_adapters=("fixed_bento_pipeline", "codex_sdk"),
    )

    _require_runtime_route_compatibility(
        workload,
        runtime_adapter_id="fixed_bento_pipeline",
        route="local",
        provider_id=None,
        status_code=422,
    )
    _require_runtime_route_compatibility(
        workload,
        runtime_adapter_id="codex_sdk",
        route="external",
        provider_id="openai",
        status_code=422,
    )

    with pytest.raises(AiModelSettingsError) as local_codex_error:
        _require_runtime_route_compatibility(
            workload,
            runtime_adapter_id="codex_sdk",
            route="local",
            provider_id=None,
            status_code=422,
        )
    assert local_codex_error.value.code == "admin.ai_model_runtime_route_mismatch"

    with pytest.raises(AiModelSettingsError) as external_fixed_error:
        _require_runtime_route_compatibility(
            workload,
            runtime_adapter_id="fixed_bento_pipeline",
            route="external",
            provider_id="openai",
            status_code=422,
        )
    assert external_fixed_error.value.code == "admin.ai_model_runtime_route_mismatch"


def test_codex_adapter_runs_sdk_in_isolated_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    progress: list[tuple[str, int]] = []

    class FakeTurn:
        def __init__(self, workdir: Path) -> None:
            self.workdir = workdir

        def stream(self):
            document_path = self.workdir / "document.json"
            document = json.loads(document_path.read_text(encoding="utf-8"))
            document["title"] = "SDK-authored deck"
            document_path.write_text(json.dumps(document), encoding="utf-8")
            yield SimpleNamespace(method="item/started", payload=SimpleNamespace())
            yield SimpleNamespace(method="item/completed", payload=SimpleNamespace())
            yield SimpleNamespace(
                method="turn/completed",
                payload=SimpleNamespace(
                    turn=SimpleNamespace(status=SimpleNamespace(value="completed"))
                ),
            )

        def interrupt(self) -> None:
            raise AssertionError("completed turn must not be interrupted")

    class FakeThread:
        id = "thread-test"

        def __init__(self, workdir: Path) -> None:
            self.workdir = workdir

        def turn(self, prompt: str, **kwargs):
            captured["turn_prompt"] = prompt
            captured["turn_kwargs"] = kwargs
            return FakeTurn(self.workdir)

    class FakeCodex:
        def __init__(self, config) -> None:
            captured["config"] = config
            self.workdir = Path(config.cwd)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def thread_start(self, **kwargs):
            captured["thread_kwargs"] = kwargs
            assert (self.workdir / "BENTO_GUIDE.md").exists()
            assert (self.workdir / "BRIEF.md").read_text(encoding="utf-8") == "Brief"
            assert (self.workdir / "bento_tool.py").exists()
            return FakeThread(self.workdir)

    monkeypatch.setattr("openai_codex.Codex", FakeCodex)
    monkeypatch.setattr(
        bento_agent_runtime,
        "_apply_external_gateway_policy",
        lambda _request: ("Brief", None, SimpleNamespace()),
    )
    monkeypatch.setattr(bento_agent_runtime, "_audit_codex_run", lambda *_args, **_kwargs: None)

    route = SimpleNamespace(
        route="external",
        provider_id="openai",
        api_key=SecretStr("test-key"),
        endpoint_url="https://api.openai.com/v1",
        model_key="gpt-5.6-sol",
    )
    result = CodexSdkBentoAdapter().run(
        AgentRuntimeRequest(
            run_id="run-test",
            actor_user_id="user-test",
            workload_id="bento.generate_presentation",
            route=route,
            input_payload={
                "db": object(),
                "kind": "create",
                "prompt": "Brief",
                "current_document_json": None,
                "slide_count": 3,
                "language": "en",
            },
            progress=lambda stage, percent: progress.append((stage, percent)),
            cancelled=lambda: False,
        )
    )

    document = json.loads(str(result.output_payload["document_json"]))
    assert document["title"] == "SDK-authored deck"
    assert len(document["slides"]) == 3
    assert result.thread_id == "thread-test"
    assert captured["thread_kwargs"]["model"] == "gpt-5.6-sol"
    assert captured["thread_kwargs"]["ephemeral"] is True
    assert 'web_search="live"' in captured["config"].config_overrides
    assert 'shell_environment_policy.inherit="none"' in captured["config"].config_overrides
    assert ("bento.ai.validating", 88) in progress


def test_bento_agent_tools_detect_invalid_frames_and_renderable_document(tmp_path) -> None:
    document = {
        "format": "bento/slides",
        "version": 1,
        "docId": "doc-1",
        "title": "Agent tool contract",
        "size": {"width": 1280, "height": 720},
        "theme": {
            "background": "#ffffff",
            "color": "#111827",
            "accent": "#2563eb",
            "fontFamily": "Arial, sans-serif",
        },
        "slides": [
            {
                "id": "slide-01",
                "background": "#ffffff",
                "transition": "fade",
                "notes": "Explain the contract.",
                "elements": [
                    {
                        "id": "title-01",
                        "type": "text",
                        "x": 96,
                        "y": 72,
                        "w": 1088,
                        "h": 90,
                        "rotation": 0,
                        "opacity": 1,
                        "html": "Editable Bento",
                        "fontSize": 52,
                        "fontFamily": "Arial, sans-serif",
                        "fontWeight": 700,
                        "color": "#111827",
                        "align": "left",
                        "valign": "top",
                        "lineHeight": 1.1,
                    }
                ],
            }
        ],
        "modified": "2026-08-12T00:00:00Z",
    }

    assert validate_document(document) == []
    assert inspect_document(document)["errors"] == []
    previews = render_document(document, tmp_path / "previews")
    assert any(path.endswith("slide-01.svg") for path in previews)

    invalid = json.loads(json.dumps(document))
    invalid["slides"][0]["elements"][0]["x"] = 1200
    assert any("overflows canvas" in error for error in validate_document(invalid))


def test_codex_edit_payload_excludes_server_owned_extension_fields() -> None:
    document = {
        "format": "bento/slides",
        "version": 1,
        "docId": "doc-1",
        "title": "Safe edit input",
        "size": {"width": 1280, "height": 720},
        "theme": {
            "background": "#ffffff",
            "color": "#111827",
            "accent": "#2563eb",
            "fontFamily": "Arial, sans-serif",
        },
        "collab": {"secret": "never-send"},
        "slides": [
            {
                "id": "slide-01",
                "background": "#ffffff",
                "transition": "fade",
                "notes": "",
                "comments": [{"text": "server-owned"}],
                "elements": [],
            }
        ],
        "modified": "2026-08-12T00:00:00Z",
    }

    sanitized = json.loads(_sanitized_current_document_json(json.dumps(document)) or "{}")

    assert "collab" not in sanitized
    assert "comments" not in sanitized["slides"][0]
