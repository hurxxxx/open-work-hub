from __future__ import annotations

from types import SimpleNamespace

from aidoo_api.domains.images import service
from aidoo_api.domains.images.prompt import (
    BRIEF_SYSTEM_PROMPT,
    build_direct_edit_prompt,
    build_agent_prompt,
    sanitize_image_plan_text,
)


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
    assert captured["run_config"].workflow_name == "AIDOO Image Plan"


def test_image_plan_prompt_forbids_placeholder_tokens() -> None:
    assert "write a placeholder" not in BRIEF_SYSTEM_PROMPT
    assert "Never output placeholder tokens" in BRIEF_SYSTEM_PROMPT


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


def test_build_direct_edit_prompt_uses_instruction_without_placeholders() -> None:
    prompt = build_direct_edit_prompt(
        edit_instruction="배경을 더 밝게 하고 <metric>은 넣지 마세요",
        style={"chips": ["corporate"], "palette": "auto", "background": "auto"},
    )

    assert "수정 요청:" in prompt
    assert "배경을 더 밝게" in prompt
    assert "<metric>" not in prompt
    assert "composition 참고 이미지" in prompt
