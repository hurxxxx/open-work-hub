from __future__ import annotations

from types import SimpleNamespace

from aidoo_api.domains.images import service


def test_brief_input_skips_system_message() -> None:
    assert (
        service._brief_input_from_messages(
            [
                {"role": "system", "content": "rules"},
                {"role": "user", "content": "make a product launch image"},
            ]
        )
        == "make a product launch image"
    )


def test_run_brief_agent_uses_agents_sdk_provider(monkeypatch) -> None:
    captured = {}

    def fake_run_sync(agent, *, input, max_turns, run_config):
        captured["agent"] = agent
        captured["input"] = input
        captured["max_turns"] = max_turns
        captured["run_config"] = run_config
        return SimpleNamespace(final_output="TITLE: SDK brief")

    from agents import Runner

    monkeypatch.setattr(Runner, "run_sync", fake_run_sync)

    result = service._run_brief_agent(
        input_text="brief context",
        model="gpt-5.5",
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        workspace_id="workspace-1",
        user_id="user-1",
        generation_id="generation-1",
    )

    assert service._extract_agent_text(result) == "TITLE: SDK brief"
    assert captured["agent"].model == "gpt-5.5"
    assert captured["input"] == "brief context"
    assert captured["max_turns"] == 1
    assert type(captured["run_config"].model_provider).__name__ == "OpenAIProvider"
    assert captured["run_config"].workflow_name == "AIDOO Image Brief"
