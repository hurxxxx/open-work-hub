from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import httpx

from open_work_hub_api.core.asr_backend_registry import (
    ASRBackendDescriptor,
    build_registered_asr_backend,
    has_asr_backend,
    register_asr_backend,
)
from open_work_hub_api.core.asr_contracts import (
    ASRBackend,
    ASRBackendName,
    ASRHealth,
    PermanentError,
    TranscriptResult,
    TranscriptSegment,
    TransientError,
)
from open_work_hub_api.core.asr_payloads import parse_transcript_payload
from open_work_hub_api.core.settings import get_settings


class CohereASRBackend:
    name: ASRBackendName = "cohere"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def healthcheck(self, *, deep: bool = False) -> ASRHealth:
        del deep
        if not self.api_key:
            return ASRHealth(backend="cohere", ready=False, detail="Missing Cohere API key.")
        return ASRHealth(backend="cohere", ready=True)

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptResult:
        if not self.api_key:
            raise PermanentError("Cohere API key is not configured.")
        if on_progress is not None:
            on_progress(0.1)
        try:
            with audio_path.open("rb") as audio_file:
                response = httpx.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (audio_path.name, audio_file, "application/octet-stream")},
                    data={
                        "model": self.model,
                        **({"language": language_hint} if language_hint else {}),
                    },
                    timeout=self.timeout_seconds,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise PermanentError(str(exc)) from exc

        if response.status_code >= 500:
            raise TransientError(f"Cohere transcription failed: {response.status_code}")
        if response.status_code >= 400:
            raise PermanentError(
                f"Cohere transcription failed: {response.status_code} {response.text}"
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise PermanentError("Cohere returned an invalid transcription payload.")
        if on_progress is not None:
            on_progress(1.0)
        return parse_transcript_payload(payload, language_hint=language_hint)


class QwenASRBackend:
    name: ASRBackendName = "qwen_asr"

    def __init__(self, *, model_repo: str, device: str) -> None:
        self.model_repo = model_repo
        self.device = device
        self._model = None
        self._processor = None

    def _load(self) -> tuple[object, object]:
        if self._model is not None and self._processor is not None:
            return self._model, self._processor
        try:
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor  # type: ignore
        except ImportError as exc:
            raise PermanentError("transformers is required for qwen_asr backend.") from exc
        self._model = AutoModelForSpeechSeq2Seq.from_pretrained(self.model_repo)
        if hasattr(self._model, "to"):
            self._model = self._model.to(self.device)
        self._processor = AutoProcessor.from_pretrained(self.model_repo)
        return self._model, self._processor

    def healthcheck(self, *, deep: bool = False) -> ASRHealth:
        try:
            import torch  # type: ignore  # noqa: F401
            import torchaudio  # type: ignore  # noqa: F401
            from transformers import (  # type: ignore  # noqa: F401
                AutoModelForSpeechSeq2Seq,
                AutoProcessor,
            )
        except ImportError as exc:
            return ASRHealth(backend="qwen_asr", ready=False, detail=str(exc))
        if not deep:
            return ASRHealth(backend="qwen_asr", ready=True)
        try:
            self._load()
        except Exception as exc:  # noqa: BLE001 - deep readiness surfaces backend load failures.
            return ASRHealth(backend="qwen_asr", ready=False, detail=str(exc))
        return ASRHealth(backend="qwen_asr", ready=True)

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptResult:
        model, processor = self._load()
        try:
            import torch  # type: ignore
            import torchaudio  # type: ignore
        except ImportError as exc:
            raise PermanentError("torch and torchaudio are required for qwen_asr backend.") from exc

        waveform, sample_rate = torchaudio.load(str(audio_path))
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
        if on_progress is not None:
            on_progress(0.25)
        inputs = processor(waveform.squeeze(0), sampling_rate=16000, return_tensors="pt")
        if self.device and hasattr(inputs, "to"):
            inputs = inputs.to(self.device)
        with torch.no_grad():
            generated = model.generate(**inputs)
        text = processor.batch_decode(generated, skip_special_tokens=True)[0]
        if on_progress is not None:
            on_progress(1.0)
        return TranscriptResult(
            text=text.strip(), segments=[], language=language_hint, duration_sec=None
        )


class WhisperASRBackend:
    name: ASRBackendName = "whisper"

    def __init__(self, *, model_size: str, device: str, compute_type: str) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise PermanentError("faster-whisper is required for whisper backend.") from exc
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model

    def healthcheck(self, *, deep: bool = False) -> ASRHealth:
        try:
            from faster_whisper import WhisperModel  # type: ignore  # noqa: F401
        except ImportError as exc:
            return ASRHealth(backend="whisper", ready=False, detail=str(exc))
        if not deep:
            return ASRHealth(backend="whisper", ready=True)
        try:
            self._load()
        except Exception as exc:  # noqa: BLE001 - deep readiness surfaces backend load failures.
            return ASRHealth(backend="whisper", ready=False, detail=str(exc))
        return ASRHealth(backend="whisper", ready=True)

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptResult:
        model = self._load()
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language_hint,
            vad_filter=True,
        )
        segments: list[TranscriptSegment] = []
        parts: list[str] = []
        for segment in segments_iter:
            segments.append(
                TranscriptSegment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=str(segment.text).strip(),
                )
            )
            parts.append(str(segment.text).strip())
            if on_progress is not None and getattr(info, "duration", None):
                on_progress(min(1.0, float(segment.end) / float(info.duration)))
        if on_progress is not None:
            on_progress(1.0)
        return TranscriptResult(
            text=" ".join(part for part in parts if part).strip(),
            segments=segments,
            language=getattr(info, "language", language_hint),
            duration_sec=getattr(info, "duration", None),
        )


class InferenceGatewayASRBackend:
    name: ASRBackendName = "inference_gateway"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = _inference_gateway_v1_base_url(base_url)
        self.health_base_url = _inference_gateway_root_base_url(base_url)
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds

    def healthcheck(self, *, deep: bool = False) -> ASRHealth:
        del deep
        if not self.base_url:
            return ASRHealth(
                backend="inference_gateway",
                ready=False,
                detail="Missing inference-gateway base URL.",
            )
        try:
            response = httpx.get(
                f"{self.health_base_url}/health",
                headers=_bearer_headers(self.api_key),
                timeout=min(self.timeout_seconds, 5.0),
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return ASRHealth(backend="inference_gateway", ready=False, detail=str(exc))
        except httpx.HTTPError as exc:
            return ASRHealth(backend="inference_gateway", ready=False, detail=str(exc))
        if response.status_code >= 400:
            return ASRHealth(
                backend="inference_gateway",
                ready=False,
                detail=f"inference-gateway healthcheck failed: {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict) and payload.get("ready") is False:
            return ASRHealth(
                backend="inference_gateway",
                ready=False,
                detail="inference-gateway is not ready.",
            )
        return ASRHealth(backend="inference_gateway", ready=True)

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptResult:
        if on_progress is not None:
            on_progress(0.1)
        data = {"model": self.model}
        if language_hint:
            data["language"] = language_hint
        try:
            with audio_path.open("rb") as audio_file:
                response = httpx.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=_bearer_headers(self.api_key),
                    files={
                        "file": (
                            audio_path.name,
                            audio_file,
                            "application/octet-stream",
                        )
                    },
                    data=data,
                    timeout=self.timeout_seconds,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise PermanentError(str(exc)) from exc

        if response.status_code >= 500:
            raise TransientError(f"inference-gateway transcription failed: {response.status_code}")
        if response.status_code >= 400:
            raise PermanentError(
                f"inference-gateway transcription failed: {response.status_code} {response.text}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PermanentError("inference-gateway returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise PermanentError("inference-gateway returned an invalid transcription payload.")
        if on_progress is not None:
            on_progress(1.0)
        return parse_transcript_payload(payload, language_hint=language_hint)


@lru_cache(maxsize=1)
def get_asr_backend() -> ASRBackend:
    return build_asr_backend(get_settings())


def build_asr_backend(settings: Any) -> ASRBackend:
    ensure_default_asr_backends_registered()
    try:
        return build_registered_asr_backend(settings.asr_backend, settings)
    except LookupError as exc:
        raise PermanentError(f"Unknown ASR backend: {settings.asr_backend}") from exc


def ensure_default_asr_backends_registered() -> None:
    for descriptor in (
        ASRBackendDescriptor(
            backend="inference_gateway",
            builder=_build_inference_gateway_asr_backend,
            label="Inference Gateway ASR",
        ),
        ASRBackendDescriptor(
            backend="cohere",
            builder=_build_cohere_asr_backend,
            label="Cohere ASR",
        ),
        ASRBackendDescriptor(
            backend="qwen_asr",
            builder=_build_qwen_asr_backend,
            label="Qwen ASR",
        ),
        ASRBackendDescriptor(
            backend="whisper",
            builder=_build_whisper_asr_backend,
            label="Whisper ASR",
        ),
    ):
        if has_asr_backend(descriptor.backend):
            continue
        register_asr_backend(descriptor)


def _build_inference_gateway_asr_backend(settings: Any) -> ASRBackend:
    return InferenceGatewayASRBackend(
        base_url=settings.inference_gateway_base_url,
        api_key=settings.inference_gateway_api_key,
        model=settings.asr_inference_gateway_model,
        timeout_seconds=settings.asr_request_timeout_seconds,
    )


def _build_cohere_asr_backend(settings: Any) -> ASRBackend:
    return CohereASRBackend(
        api_key=settings.asr_cohere_api_key,
        model=settings.asr_cohere_model,
        base_url=settings.asr_cohere_base_url,
        timeout_seconds=settings.asr_request_timeout_seconds,
    )


def _build_qwen_asr_backend(settings: Any) -> ASRBackend:
    return QwenASRBackend(
        model_repo=settings.asr_qwen_model,
        device=settings.asr_qwen_device,
    )


def _build_whisper_asr_backend(settings: Any) -> ASRBackend:
    return WhisperASRBackend(
        model_size=settings.asr_whisper_model,
        device=settings.asr_whisper_device,
        compute_type=settings.asr_whisper_compute_type,
    )


def check_asr_health(*, deep: bool = False) -> ASRHealth:
    try:
        backend = get_asr_backend()
        if deep:
            return backend.healthcheck(deep=True)
        return backend.healthcheck()
    except Exception as exc:
        configured_backend = str(get_settings().asr_backend).strip() or "unknown"
        return ASRHealth(backend=configured_backend, ready=False, detail=str(exc))


def _bearer_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _inference_gateway_v1_base_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    if not stripped:
        return ""
    return stripped if stripped.endswith("/v1") else f"{stripped}/v1"


def _inference_gateway_root_base_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    return stripped[: -len("/v1")] if stripped.endswith("/v1") else stripped
