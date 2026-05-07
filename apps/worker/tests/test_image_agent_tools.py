from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ai_do_worker.tasks import images


def test_run_agent_gives_illustrator_autonomous_web_and_image_tools(monkeypatch) -> None:
    captured = {}

    async def fake_run(agent, *, input, max_turns, run_config):
        captured["agent"] = agent
        captured["input"] = input
        captured["max_turns"] = max_turns
        captured["run_config"] = run_config
        return SimpleNamespace(new_items=[])

    from agents import Runner

    monkeypatch.setattr(Runner, "run", fake_run)

    asyncio.run(
        images._run_agent(
            brief_text="수정 요청: 필요한 정보를 확인해서 카드에 반영",
            style={"chips": [], "palette": "auto", "background": "auto", "quality": "high"},
            layout={"aspect": "1024x1024"},
            reference_images=[],
            max_turns=10,
            supervisor_model="gpt-5.5",
            image_model="gpt-image-2",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            enable_web_search=True,
        )
    )

    assert captured["agent"].model == "gpt-5.5"
    assert captured["agent"].model_settings.tool_choice == "auto"
    assert [tool.name for tool in captured["agent"].tools] == [
        "web_search",
        "image_generation",
    ]
    assert captured["max_turns"] == 10
    assert type(captured["run_config"].model_provider).__name__ == "OpenAIProvider"


def test_run_agent_can_disable_web_search(monkeypatch) -> None:
    captured = {}

    async def fake_run(agent, *, input, max_turns, run_config):
        captured["agent"] = agent
        return SimpleNamespace(new_items=[])

    from agents import Runner

    monkeypatch.setattr(Runner, "run", fake_run)

    asyncio.run(
        images._run_agent(
            brief_text="제목만 유지하고 배경을 밝게",
            style={"chips": [], "palette": "auto", "background": "auto", "quality": "high"},
            layout={"aspect": "1024x1024"},
            reference_images=[],
            max_turns=10,
            supervisor_model="gpt-5.5",
            image_model="gpt-image-2",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            enable_web_search=False,
        )
    )

    assert [tool.name for tool in captured["agent"].tools] == ["image_generation"]
