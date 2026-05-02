from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from aidoo_api.core import asr


def test_deepinfra_backend_posts_audio_and_parses_segments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "sample.webm"
    audio_path.write_bytes(b"audio-bytes")
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, files, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["files"] = files
        captured["data"] = data
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "text": "안녕하세요. 회의 녹음입니다.",
                "language": "ko",
                "duration": 3.5,
                "segments": [
                    {"start": 0, "end": 1.4, "text": "안녕하세요."},
                    {"start": 1.4, "end": 3.5, "text": "회의 녹음입니다."},
                ],
            },
        )

    monkeypatch.setattr(asr.httpx, "post", fake_post)
    backend = asr.DeepInfraASRBackend(
        api_key="deepinfra-key",
        model="openai/whisper-large-v3",
        base_url="https://api.deepinfra.com/v1/inference",
        timeout_seconds=30,
    )
    progress: list[float] = []

    result = backend.transcribe(audio_path, language_hint="ko", on_progress=progress.append)

    assert captured["url"] == "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3"
    assert captured["headers"] == {"Authorization": "Bearer deepinfra-key"}
    assert captured["data"] == {"language": "ko"}
    assert captured["timeout"] == 30
    assert "audio" in captured["files"]
    assert result.text == "안녕하세요. 회의 녹음입니다."
    assert result.language == "ko"
    assert result.duration_sec == 3.5
    assert [segment.text for segment in result.segments] == [
        "안녕하세요.",
        "회의 녹음입니다.",
    ]
    assert progress == [0.1, 1.0]


def test_deepinfra_backend_treats_rate_limit_as_transient(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "sample.webm"
    audio_path.write_bytes(b"audio-bytes")
    monkeypatch.setattr(asr.httpx, "post", lambda *args, **kwargs: httpx.Response(429))
    backend = asr.DeepInfraASRBackend(
        api_key="deepinfra-key",
        model="openai/whisper-large-v3",
        base_url="https://api.deepinfra.com/v1/inference",
        timeout_seconds=30,
    )

    with pytest.raises(asr.TransientError):
        backend.transcribe(audio_path)


def test_deepinfra_backend_health_requires_api_key() -> None:
    backend = asr.DeepInfraASRBackend(
        api_key="",
        model="openai/whisper-large-v3",
        base_url="https://api.deepinfra.com/v1/inference",
        timeout_seconds=30,
    )

    health = backend.healthcheck()

    assert health.backend == "deepinfra"
    assert health.ready is False
    assert health.detail == "Missing DeepInfra API key."
