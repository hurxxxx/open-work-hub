# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_work_hub_api.domains.images.agent_runtime import (
    ImageGenerationRuntimeResult,
    register_image_agent_runtime_adapter,
    reset_image_agent_runtime_adapters,
)
from open_work_hub_worker.tasks import images


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
        images.run_image_agent(
            provider_id="openai",
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
        images.run_image_agent(
            provider_id="openai",
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


def test_run_image_agent_delegates_empty_api_key_to_extension_provider() -> None:
    captured = {}
    execution_profile = {
        "version": "image_execution_profile.v1",
        "provider_id": "local",
        "adapter_id": "local",
    }

    class ExtensionImageRuntimeAdapter:
        provider_id = "local"

        def run_brief(self, **kwargs):
            del kwargs
            raise AssertionError("run_brief should not run")

        async def generate_image(self, **kwargs) -> ImageGenerationRuntimeResult:
            captured.update(kwargs)
            return ImageGenerationRuntimeResult(image_bytes=b"png")

    reset_image_agent_runtime_adapters()
    try:
        register_image_agent_runtime_adapter(ExtensionImageRuntimeAdapter())

        result = asyncio.run(
            images.run_image_agent(
                provider_id="local",
                brief_text="local brief",
                style={},
                layout={},
                reference_images=[],
                max_turns=3,
                supervisor_model="local-planner",
                image_model="local-image",
                api_key="",
                base_url="",
                enable_web_search=False,
                execution_profile=execution_profile,
            )
        )

        assert result.image_bytes == b"png"
        assert captured["api_key"] == ""
        assert captured["execution_profile"] == execution_profile
    finally:
        reset_image_agent_runtime_adapters()


def test_run_image_agent_threads_security_db_to_runtime_adapter() -> None:
    captured = {}
    security_db = object()

    class ExtensionImageRuntimeAdapter:
        provider_id = "local"

        def run_brief(self, **kwargs):
            del kwargs
            raise AssertionError("run_brief should not run")

        async def generate_image(self, **kwargs) -> ImageGenerationRuntimeResult:
            captured.update(kwargs)
            return ImageGenerationRuntimeResult(image_bytes=b"png")

    reset_image_agent_runtime_adapters()
    try:
        register_image_agent_runtime_adapter(ExtensionImageRuntimeAdapter())

        result = asyncio.run(
            images.run_image_agent(
                provider_id="local",
                brief_text="local brief",
                style={},
                layout={},
                reference_images=[],
                max_turns=3,
                supervisor_model="local-planner",
                image_model="local-image",
                api_key="",
                base_url="",
                enable_web_search=False,
                db=security_db,
            )
        )

        assert result.image_bytes == b"png"
        assert captured["db"] is security_db
    finally:
        reset_image_agent_runtime_adapters()


def test_run_image_agent_pins_execution_adapter_id() -> None:
    captured = {}

    class DefaultLocalImageRuntimeAdapter:
        provider_id = "local"
        adapter_id = "local-default"

        def run_brief(self, **kwargs):
            del kwargs
            raise AssertionError("run_brief should not run")

        async def generate_image(self, **kwargs) -> ImageGenerationRuntimeResult:
            captured["adapter"] = self.adapter_id
            captured.update(kwargs)
            return ImageGenerationRuntimeResult(image_bytes=b"default")

    class ReplacementLocalImageRuntimeAdapter:
        provider_id = "local"
        adapter_id = "local-replacement"

        def run_brief(self, **kwargs):
            del kwargs
            raise AssertionError("run_brief should not run")

        async def generate_image(self, **kwargs) -> ImageGenerationRuntimeResult:
            captured["adapter"] = self.adapter_id
            captured.update(kwargs)
            return ImageGenerationRuntimeResult(image_bytes=b"replacement")

    execution_profile = {
        "version": "image_execution_profile.v1",
        "provider_id": "local",
        "adapter_id": "local-replacement",
    }

    reset_image_agent_runtime_adapters()
    try:
        register_image_agent_runtime_adapter(DefaultLocalImageRuntimeAdapter())
        register_image_agent_runtime_adapter(ReplacementLocalImageRuntimeAdapter())

        result = asyncio.run(
            images.run_image_agent(
                provider_id="local",
                adapter_id="local-replacement",
                brief_text="local brief",
                style={},
                layout={},
                reference_images=[],
                max_turns=3,
                supervisor_model="local-planner",
                image_model="local-image",
                api_key="",
                base_url="",
                enable_web_search=False,
                execution_profile=execution_profile,
            )
        )

        assert result.image_bytes == b"replacement"
        assert captured["adapter"] == "local-replacement"
        assert captured["execution_profile"] == execution_profile
    finally:
        reset_image_agent_runtime_adapters()


def test_image_failure_helpers_roll_back_before_status_commit(monkeypatch) -> None:
    row = SimpleNamespace(
        id="generation-1",
        owner_id="user-1",
        workspace_id="workspace-1",
        image_status="running",
        failure_reason=None,
        celery_task_id="task-1",
        updated_at=None,
        trashed_at=None,
    )

    class FakeSession:
        def __init__(self) -> None:
            self.events: list[str] = []

        def rollback(self) -> None:
            self.events.append("rollback")

        def get(self, _model, _row_id, *, populate_existing=False):
            self.events.append(f"get:{populate_existing}")
            return row

        def add(self, _value) -> None:
            self.events.append("add")

        def commit(self) -> None:
            self.events.append("commit")

    notified: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        images,
        "_notify_generation_finished",
        lambda _session, _row, *, outcome, reason=None: notified.append((outcome, reason)),
    )
    session = FakeSession()

    images._mark_failed(session, "generation-1", "storage failed")

    assert session.events == ["rollback", "get:True", "add", "commit"]
    assert row.image_status == "failed"
    assert row.failure_reason == "storage failed"
    assert row.celery_task_id is None
    assert notified == [("failed", "storage failed")]

    session.events.clear()
    notified.clear()
    row.image_status = "running"
    row.failure_reason = None
    row.celery_task_id = "task-2"

    images._mark_retrying(session, "generation-1", "retrying")

    assert session.events == ["rollback", "get:True", "add", "commit"]
    assert row.image_status == "queued"
    assert row.failure_reason == "retrying"
    assert row.celery_task_id == "task-2"
    assert notified == []
