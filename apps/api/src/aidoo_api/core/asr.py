from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal, Protocol

import httpx

from aidoo_api.core.settings import get_settings


ASRBackendName = Literal["cohere", "qwen_asr", "whisper"]


class TransientError(Exception):
    pass


class PermanentError(Exception):
    pass


@dataclass(frozen=True)
class ASRHealth:
    backend: ASRBackendName
    ready: bool
    detail: str | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    segments: list[TranscriptSegment]
    language: str | None = None
    duration_sec: float | None = None


class ASRBackend(Protocol):
    name: ASRBackendName

    def healthcheck(self) -> ASRHealth: ...

    def transcribe(
        self,
        audio_path: Path,
        *,
        language_hint: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptResult: ...


class CohereASRBackend:
    name: ASRBackendName = "cohere"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def healthcheck(self) -> ASRHealth:
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
            raise PermanentError(f"Cohere transcription failed: {response.status_code} {response.text}")

        payload = response.json()
        text = (
            payload.get("text")
            or payload.get("transcript")
            or payload.get("results", {}).get("text")
            or ""
        )
        segments_payload = payload.get("segments") or payload.get("results", {}).get("segments") or []
        segments = [
            TranscriptSegment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", item.get("start", 0.0))),
                text=str(item.get("text", "")),
            )
            for item in segments_payload
        ]
        if on_progress is not None:
            on_progress(1.0)
        return TranscriptResult(
            text=text.strip(),
            segments=segments,
            language=payload.get("language"),
            duration_sec=payload.get("duration") or payload.get("duration_sec"),
        )


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

    def healthcheck(self) -> ASRHealth:
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
        return TranscriptResult(text=text.strip(), segments=[], language=language_hint, duration_sec=None)


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

    def healthcheck(self) -> ASRHealth:
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


@lru_cache(maxsize=1)
def get_asr_backend() -> ASRBackend:
    settings = get_settings()
    if settings.asr_backend == "cohere":
        return CohereASRBackend(
            api_key=settings.asr_cohere_api_key,
            model=settings.asr_cohere_model,
            base_url=settings.asr_cohere_base_url,
            timeout_seconds=settings.asr_request_timeout_seconds,
        )
    if settings.asr_backend == "qwen_asr":
        return QwenASRBackend(
            model_repo=settings.asr_qwen_model,
            device=settings.asr_qwen_device,
        )
    if settings.asr_backend == "whisper":
        return WhisperASRBackend(
            model_size=settings.asr_whisper_model,
            device=settings.asr_whisper_device,
            compute_type=settings.asr_whisper_compute_type,
        )
    raise PermanentError(f"Unknown ASR backend: {settings.asr_backend}")


def check_asr_health() -> ASRHealth:
    try:
        return get_asr_backend().healthcheck()
    except Exception as exc:
        return ASRHealth(backend="cohere", ready=False, detail=str(exc))
