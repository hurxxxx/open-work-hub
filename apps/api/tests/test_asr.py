from __future__ import annotations

import sys
from types import SimpleNamespace

import httpx

from open_work_hub_api.core import asr
from open_work_hub_api.core.asr_backend_registry import (
    ASRBackendDescriptor,
    register_asr_backend,
    reset_asr_backends,
)
from open_work_hub_api.core.asr_payloads import parse_transcript_payload
from open_work_hub_api.core.settings import Settings


def test_get_asr_backend_builds_inference_gateway(monkeypatch) -> None:
    asr.get_asr_backend.cache_clear()
    monkeypatch.setattr(
        asr,
        "get_settings",
        lambda: SimpleNamespace(
            asr_backend="inference_gateway",
            inference_gateway_base_url="http://127.0.0.1:18080",
            inference_gateway_api_key="local",
            asr_inference_gateway_model="local-transcribe",
            asr_cohere_model="cohere-transcribe",
            asr_request_timeout_seconds=600.0,
        ),
    )

    try:
        backend = asr.get_asr_backend()
    finally:
        asr.get_asr_backend.cache_clear()

    assert isinstance(backend, asr.InferenceGatewayASRBackend)
    assert backend.base_url == "http://127.0.0.1:18080/v1"
    assert backend.model == "local-transcribe"


def test_build_asr_backend_uses_registered_backend_adapter() -> None:
    class PluginASRBackend:
        name = "plugin_asr"

        def __init__(self, marker: str) -> None:
            self.marker = marker

        def healthcheck(self):
            return asr.ASRHealth(backend=self.name, ready=True)

        def transcribe(self, audio_path, *, language_hint=None, on_progress=None):
            del audio_path, on_progress
            return asr.TranscriptResult(
                text=f"plugin:{self.marker}",
                segments=[],
                language=language_hint,
                duration_sec=None,
            )

    reset_asr_backends()
    try:
        register_asr_backend(
            ASRBackendDescriptor(
                backend="plugin_asr",
                builder=lambda settings: PluginASRBackend(settings.marker),
            )
        )

        backend = asr.build_asr_backend(SimpleNamespace(asr_backend="plugin_asr", marker="custom"))

        assert isinstance(backend, PluginASRBackend)
        assert backend.transcribe(None).text == "plugin:custom"
    finally:
        reset_asr_backends()


def test_asr_settings_follow_inference_gateway_env_names(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("OPEN_WORK_HUB_API_ASR_INFERENCE_GATEWAY_MODEL", "local-transcribe")
    monkeypatch.setenv("OPEN_WORK_HUB_API_ASR_COHERE_MODEL", "custom-transcribe")
    monkeypatch.setenv("OPEN_WORK_HUB_API_ASR_COHERE_BASE_URL", "https://cohere.example/v2")

    settings = Settings(_env_file=None)

    assert settings.asr_inference_gateway_model == "local-transcribe"
    assert settings.asr_cohere_model == "custom-transcribe"
    assert settings.asr_cohere_base_url == "https://cohere.example/v2"


def test_qwen_asr_healthcheck_reports_model_load_failure(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModelForSpeechSeq2Seq=object, AutoProcessor=object),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "torchaudio", SimpleNamespace())
    backend = asr.QwenASRBackend(model_repo="missing-model", device="cpu")

    def fail_load():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(backend, "_load", fail_load)

    health = backend.healthcheck(deep=True)

    assert health.ready is False
    assert health.backend == "qwen_asr"
    assert health.detail == "model unavailable"


def test_qwen_asr_healthcheck_is_shallow_by_default(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModelForSpeechSeq2Seq=object, AutoProcessor=object),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "torchaudio", SimpleNamespace())
    backend = asr.QwenASRBackend(model_repo="missing-model", device="cpu")

    def fail_load():
        raise AssertionError("healthcheck should not load the model by default")

    monkeypatch.setattr(backend, "_load", fail_load)

    health = backend.healthcheck()

    assert health.ready is True
    assert health.backend == "qwen_asr"


def test_whisper_asr_healthcheck_reports_model_load_failure(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=object))
    backend = asr.WhisperASRBackend(
        model_size="missing-model",
        device="cpu",
        compute_type="int8",
    )

    def fail_load():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(backend, "_load", fail_load)

    health = backend.healthcheck(deep=True)

    assert health.ready is False
    assert health.backend == "whisper"
    assert health.detail == "model unavailable"


def test_whisper_asr_healthcheck_is_shallow_by_default(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=object))
    backend = asr.WhisperASRBackend(
        model_size="missing-model",
        device="cpu",
        compute_type="int8",
    )

    def fail_load():
        raise AssertionError("healthcheck should not load the model by default")

    monkeypatch.setattr(backend, "_load", fail_load)

    health = backend.healthcheck()

    assert health.ready is True
    assert health.backend == "whisper"


def test_parse_transcript_payload_normalizes_common_backend_shapes() -> None:
    result = parse_transcript_payload(
        {
            "results": {
                "chunks": [
                    {"timestamp": [0, 1.25], "sentence": " 안녕 "},
                    {"start": "1.25", "end": "2.5", "text": "하세요"},
                ]
            },
            "duration": "2.5",
        },
        language_hint="ko",
    )

    assert result.text == "안녕 하세요"
    assert result.language == "ko"
    assert result.duration_sec == 2.5
    assert result.segments == [
        asr.TranscriptSegment(start=0.0, end=1.25, text="안녕"),
        asr.TranscriptSegment(start=1.25, end=2.5, text="하세요"),
    ]


def test_inference_gateway_asr_posts_audio_to_backend(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"audio-bytes")
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, files, data, timeout):
        uploaded = files["file"]
        captured.update(
            {
                "url": url,
                "headers": headers,
                "filename": uploaded[0],
                "content": uploaded[1].read(),
                "content_type": uploaded[2],
                "data": data,
                "timeout": timeout,
            }
        )
        return httpx.Response(
            200,
            json={
                "text": " 안녕하세요 ",
                "language": "ko",
                "duration_sec": 3.5,
            },
        )

    monkeypatch.setattr(asr.httpx, "post", fake_post)
    backend = asr.InferenceGatewayASRBackend(
        base_url="http://127.0.0.1:18080",
        api_key="local",
        model="transcribe-v1",
        timeout_seconds=123.0,
    )
    progress: list[float] = []

    result = backend.transcribe(audio_path, language_hint="ko", on_progress=progress.append)

    assert captured == {
        "url": "http://127.0.0.1:18080/v1/audio/transcriptions",
        "headers": {"Authorization": "Bearer local"},
        "filename": "sample.wav",
        "content": b"audio-bytes",
        "content_type": "application/octet-stream",
        "data": {"model": "transcribe-v1", "language": "ko"},
        "timeout": 123.0,
    }
    assert result.text == "안녕하세요"
    assert result.language == "ko"
    assert result.duration_sec == 3.5
    assert progress == [0.1, 1.0]
