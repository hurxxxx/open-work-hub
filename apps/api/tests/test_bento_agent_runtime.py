from __future__ import annotations

import json
from types import SimpleNamespace
import pytest
from open_work_hub_api.domains.ai.agent_runtime import (
    AgentRuntimeRequest,
    agent_runtime_adapter_ids,
    reset_agent_runtime_adapters,
)
from open_work_hub_api.domains.bento import agent_runtime as bento_agent_runtime
from open_work_hub_api.domains.bento.agent_runtime import (
    AgentRuntimeCancelled,
    HermesBentoPipelineAdapter,
    ensure_bento_agent_runtime_adapters_registered,
)
from open_work_hub_api.domains.bento.agent_tools import (
    inspect_document,
    render_document,
    validate_document,
)
from open_work_hub_api.domains.bento.generation import _normalize_generated_document


def test_bento_has_one_hermes_adapter_for_both_routes():
    reset_agent_runtime_adapters()
    ensure_bento_agent_runtime_adapters_registered()
    assert agent_runtime_adapter_ids() == ("hermes",)
    assert HermesBentoPipelineAdapter.allowed_routes == ("local", "external")


@pytest.mark.parametrize("kind", ["create", "edit"])
def test_bento_hermes_adapter_preserves_stage_inputs_and_cancellation(monkeypatch, kind):
    calls = []

    def generate(db, **kwargs):
        calls.append((db, kwargs))
        return '{"title":"generated"}', {"title": "generated"}

    monkeypatch.setattr(bento_agent_runtime, "generate_bento_document_json", generate)
    monkeypatch.setattr(bento_agent_runtime, "revise_bento_document_json", generate)
    payload = {
        "db": object(),
        "kind": kind,
        "prompt": "Build a deck",
        "slide_count": 3,
        "language": "ko",
        "current_document_json": "{}",
    }
    request = AgentRuntimeRequest(
        run_id="run",
        actor_user_id="owner",
        workload_id="bento.generate_presentation",
        route=SimpleNamespace(route="local"),
        input_payload=payload,
        progress=lambda *_: None,
        cancelled=lambda: False,
    )
    assert (
        HermesBentoPipelineAdapter().run(request).output_payload["document_json"]
        == '{"title":"generated"}'
    )
    assert calls[0][1]["actor_user_id"] == "owner"
    assert calls[0][1]["prompt"] == "Build a deck"
    cancelled = AgentRuntimeRequest(
        run_id="run",
        actor_user_id="owner",
        workload_id=request.workload_id,
        route=request.route,
        input_payload=payload,
        progress=lambda *_: None,
        cancelled=lambda: True,
    )
    with pytest.raises(AgentRuntimeCancelled):
        HermesBentoPipelineAdapter().run(cancelled)
    assert len(calls) == 1


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


def test_hermes_edit_payload_excludes_server_owned_extension_fields() -> None:
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

    sanitized = _normalize_generated_document(
        document, expected_slide_count=None, document_id="doc-1"
    )

    assert "collab" not in sanitized
    assert "comments" not in sanitized["slides"][0]
