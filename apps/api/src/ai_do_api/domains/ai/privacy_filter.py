from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from threading import Lock
from typing import Any

import httpx

from ai_do_api.core.settings import Settings, get_settings


DEFAULT_OPF_REPOSITORY = "openai/privacy-filter"


@dataclass(frozen=True)
class PrivacyFilterSpan:
    text_index: int
    start: int
    end: int
    label: str
    blocker_type: str
    entity_type: str


@dataclass(frozen=True)
class PrivacyFilterDetection:
    status: str
    spans: tuple[PrivacyFilterSpan, ...] = ()
    entity_types: tuple[str, ...] = ()
    blocker_types: tuple[str, ...] = ()
    pii_hits: tuple[str, ...] = ()
    enabled: bool = False
    used: bool = False
    error: str | None = None


@dataclass(frozen=True)
class PrivacyFilterHealth:
    enabled: bool
    ready: bool
    status: str
    checkpoint: str
    device: str
    detail: str | None = None


class PrivacyFilterUnavailable(RuntimeError):
    pass


_EXECUTOR_LOCK = Lock()
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_WORKERS = 0
_REDACTOR_LOCK = Lock()
_REDACTORS: dict[tuple[str, str], Any] = {}
_MASKED_PLACEHOLDER_PATTERN = re.compile(
    r"\[(?:masked|redacted):[a-z0-9_:-]+\]",
    re.IGNORECASE,
)


def detect_privacy_filter_spans(
    texts: list[str] | tuple[str, ...],
    *,
    settings: Settings | None = None,
    use_service: bool = True,
) -> PrivacyFilterDetection:
    resolved_settings = settings or get_settings()
    if not resolved_settings.opf_enabled:
        return PrivacyFilterDetection(status="disabled", enabled=False, used=False)

    normalized_texts = tuple(_suppress_masked_placeholders(text or "") for text in texts)
    total_chars = sum(len(text) for text in normalized_texts)
    if total_chars > resolved_settings.opf_max_input_chars:
        return PrivacyFilterDetection(status="input_too_large", enabled=True, used=False)

    if use_service and resolved_settings.opf_service_base_url:
        return _detect_privacy_filter_spans_service(normalized_texts, resolved_settings)

    executor = _executor(max_workers=resolved_settings.opf_max_concurrency)
    future = executor.submit(
        _detect_privacy_filter_spans_sync,
        normalized_texts,
        resolved_settings,
    )
    try:
        return future.result(timeout=resolved_settings.opf_timeout_ms / 1000)
    except TimeoutError:
        return PrivacyFilterDetection(status="timeout", enabled=True, used=True)
    except PrivacyFilterUnavailable as error:
        return PrivacyFilterDetection(
            status="unavailable",
            enabled=True,
            used=False,
            error=_safe_error(error),
        )
    except Exception as error:  # noqa: BLE001 - detector failure must fail closed.
        return PrivacyFilterDetection(
            status="error",
            enabled=True,
            used=True,
            error=_safe_error(error),
        )


def prepare_privacy_filter(
    *,
    settings: Settings | None = None,
    download: bool | None = None,
    use_service: bool = True,
) -> PrivacyFilterHealth:
    resolved_settings = settings or get_settings()
    if not resolved_settings.opf_enabled:
        return PrivacyFilterHealth(
            enabled=False,
            ready=False,
            status="disabled",
            checkpoint=resolved_settings.opf_checkpoint,
            device=resolved_settings.opf_device,
        )

    if use_service and resolved_settings.opf_service_base_url:
        return _check_privacy_filter_service_health(resolved_settings)

    try:
        _redactor(resolved_settings, download=download)
    except PrivacyFilterUnavailable as error:
        return PrivacyFilterHealth(
            enabled=True,
            ready=False,
            status="unavailable",
            checkpoint=resolved_settings.opf_checkpoint,
            device=resolved_settings.opf_device,
            detail=_safe_error(error),
        )
    except Exception as error:  # noqa: BLE001 - health must not crash app startup.
        return PrivacyFilterHealth(
            enabled=True,
            ready=False,
            status="error",
            checkpoint=resolved_settings.opf_checkpoint,
            device=resolved_settings.opf_device,
            detail=_safe_error(error),
        )

    return PrivacyFilterHealth(
        enabled=True,
        ready=True,
        status="ready",
        checkpoint=resolved_settings.opf_checkpoint,
        device="cpu",
    )


def check_privacy_filter_health(
    *,
    settings: Settings | None = None,
    deep: bool = False,
    use_service: bool = True,
) -> PrivacyFilterHealth:
    resolved_settings = settings or get_settings()
    if not resolved_settings.opf_enabled:
        return PrivacyFilterHealth(
            enabled=False,
            ready=False,
            status="disabled",
            checkpoint=resolved_settings.opf_checkpoint,
            device=resolved_settings.opf_device,
        )
    if use_service and resolved_settings.opf_service_base_url:
        return _check_privacy_filter_service_health(resolved_settings)
    if deep:
        return prepare_privacy_filter(
            settings=resolved_settings,
            download=resolved_settings.opf_download_on_startup,
            use_service=False,
        )

    key = _redactor_key(resolved_settings)
    with _REDACTOR_LOCK:
        ready = key in _REDACTORS
    return PrivacyFilterHealth(
        enabled=True,
        ready=ready,
        status="ready" if ready else "not_loaded",
        checkpoint=resolved_settings.opf_checkpoint,
        device="cpu",
    )


def _detect_privacy_filter_spans_service(
    texts: tuple[str, ...],
    settings: Settings,
) -> PrivacyFilterDetection:
    url = f"{settings.opf_service_base_url}/detect"
    try:
        with httpx.Client(timeout=settings.opf_service_timeout_ms / 1000) as client:
            response = client.post(url, json={"texts": list(texts)})
            response.raise_for_status()
        payload = response.json()
        return PrivacyFilterDetection(
            status=str(payload.get("status") or "error"),
            spans=tuple(
                PrivacyFilterSpan(
                    text_index=int(span.get("text_index", 0)),
                    start=int(span.get("start", 0)),
                    end=int(span.get("end", 0)),
                    label=str(span.get("label") or ""),
                    blocker_type=str(span.get("blocker_type") or ""),
                    entity_type=str(span.get("entity_type") or ""),
                )
                for span in payload.get("spans", ())
                if isinstance(span, dict)
            ),
            entity_types=tuple(
                str(item) for item in payload.get("entity_types", ()) if item
            ),
            blocker_types=tuple(
                str(item) for item in payload.get("blocker_types", ()) if item
            ),
            pii_hits=tuple(str(item) for item in payload.get("pii_hits", ()) if item),
            enabled=bool(payload.get("enabled", True)),
            used=bool(payload.get("used", True)),
            error=payload.get("error") if isinstance(payload.get("error"), str) else None,
        )
    except Exception as error:  # noqa: BLE001 - unavailable service must fail closed.
        return PrivacyFilterDetection(
            status="service_unavailable",
            enabled=True,
            used=False,
            error=_safe_error(error),
        )


def _suppress_masked_placeholders(text: str) -> str:
    return _MASKED_PLACEHOLDER_PATTERN.sub(lambda match: " " * len(match.group(0)), text)


def _check_privacy_filter_service_health(settings: Settings) -> PrivacyFilterHealth:
    url = f"{settings.opf_service_base_url}/healthz"
    try:
        with httpx.Client(timeout=settings.opf_service_timeout_ms / 1000) as client:
            response = client.get(url)
            response.raise_for_status()
        payload = response.json()
        return PrivacyFilterHealth(
            enabled=bool(payload.get("enabled", True)),
            ready=bool(payload.get("ready", False)),
            status=str(payload.get("status") or "error"),
            checkpoint=str(payload.get("checkpoint") or settings.opf_checkpoint),
            device=str(payload.get("device") or "cpu"),
            detail=(
                payload.get("detail")
                if isinstance(payload.get("detail"), str)
                else None
            ),
        )
    except Exception as error:  # noqa: BLE001 - readiness should report concise failure.
        return PrivacyFilterHealth(
            enabled=True,
            ready=False,
            status="service_unavailable",
            checkpoint=settings.opf_checkpoint,
            device="cpu",
            detail=_safe_error(error),
        )


def _detect_privacy_filter_spans_sync(
    texts: tuple[str, ...],
    settings: Settings,
) -> PrivacyFilterDetection:
    redactor = _redactor(settings)
    spans: list[PrivacyFilterSpan] = []
    for text_index, text in enumerate(texts):
        if not text:
            continue
        result = redactor.redact(text)
        for raw_span in getattr(result, "detected_spans", ()) or ():
            parsed = _parse_span(raw_span, text_index=text_index, text_length=len(text))
            if parsed is not None:
                spans.append(parsed)

    entity_types = _dedupe_tuple(span.entity_type for span in spans)
    blocker_types = _dedupe_tuple(span.blocker_type for span in spans)
    pii_hits = _dedupe_tuple(span.label for span in spans if span.blocker_type == "pii")
    return PrivacyFilterDetection(
        status="ok",
        spans=tuple(spans),
        entity_types=entity_types,
        blocker_types=blocker_types,
        pii_hits=pii_hits,
        enabled=True,
        used=True,
    )


def _executor(*, max_workers: int) -> ThreadPoolExecutor:
    global _EXECUTOR, _EXECUTOR_WORKERS
    workers = max(1, min(int(max_workers or 1), 8))
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None or _EXECUTOR_WORKERS != workers:
            if _EXECUTOR is not None:
                _EXECUTOR.shutdown(wait=False, cancel_futures=True)
            _EXECUTOR = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="opf")
            _EXECUTOR_WORKERS = workers
        return _EXECUTOR


def _redactor(settings: Settings, *, download: bool | None = None) -> Any:
    key = _redactor_key(settings)
    with _REDACTOR_LOCK:
        existing = _REDACTORS.get(key)
        if existing is not None:
            return existing
        redactor = _build_redactor(settings, download=download)
        _REDACTORS[key] = redactor
        return redactor


def _redactor_key(settings: Settings) -> tuple[str, str]:
    return (settings.opf_checkpoint.strip(), "cpu")


def _build_redactor(settings: Settings, *, download: bool | None = None) -> Any:
    try:
        try:
            from opf._api import OPF  # type: ignore[import-not-found]
        except ImportError:
            from opf import OPF  # type: ignore[import-not-found,no-redef]
    except ImportError as error:
        raise PrivacyFilterUnavailable("opf package is not installed") from error

    checkpoint = _resolve_checkpoint(settings, download=download)
    device = "cpu"
    kwargs = {"device": device, "output_mode": "typed"}
    if checkpoint:
        try:
            return OPF(checkpoint, **kwargs)
        except TypeError:
            return OPF(model=checkpoint, **kwargs)
    return OPF(**kwargs)


def _resolve_checkpoint(settings: Settings, *, download: bool | None = None) -> str:
    checkpoint = settings.opf_checkpoint.strip()
    if not checkpoint:
        return checkpoint

    local_path = Path(checkpoint).expanduser()
    if local_path.exists():
        return str(local_path)

    should_download = settings.opf_download_on_startup if download is None else download
    if not should_download:
        return checkpoint

    return _download_checkpoint_repository(settings, repo_id=checkpoint)


def _download_checkpoint_repository(settings: Settings, *, repo_id: str) -> str:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise PrivacyFilterUnavailable("huggingface_hub package is not installed") from error

    target = _checkpoint_repository_target(settings, repo_id=repo_id)
    if _is_valid_checkpoint_dir(target):
        return str(target)

    try:
        target.mkdir(parents=True, exist_ok=True)
        hf_cache_dir = target / ".cache" / "huggingface"
        snapshot_download(
            repo_id=repo_id,
            cache_dir=str(hf_cache_dir),
            local_dir=str(target),
            allow_patterns=["original/*"],
        )
        _promote_original_checkpoint(target)
        if not _is_valid_checkpoint_dir(target):
            raise PrivacyFilterUnavailable(
                "privacy filter checkpoint is incomplete after download",
            )
        return str(target)
    except Exception as error:  # noqa: BLE001 - model preparation should report a concise cause.
        raise PrivacyFilterUnavailable("privacy filter model download failed") from error


def _checkpoint_repository_target(settings: Settings, *, repo_id: str) -> Path:
    root = Path(settings.opf_cache_dir).expanduser()
    return root / _checkpoint_repository_slug(repo_id)


def _checkpoint_repository_slug(repo_id: str) -> str:
    slug = repo_id.strip().replace("\\", "/").replace("/", "--")
    return slug.replace(":", "-") or DEFAULT_OPF_REPOSITORY.replace("/", "--")


def _is_valid_checkpoint_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "config.json").is_file()
        and any(child.is_file() for child in path.glob("*.safetensors"))
    )


def _promote_original_checkpoint(target: Path) -> None:
    original_dir = target / "original"
    if not original_dir.is_dir():
        return
    for source in original_dir.iterdir():
        destination = target / source.name
        if destination.exists():
            raise PrivacyFilterUnavailable(
                f"privacy filter checkpoint file already exists: {destination.name}",
            )
        shutil.move(str(source), str(destination))
    original_dir.rmdir()


def _parse_span(
    raw_span: Any,
    *,
    text_index: int,
    text_length: int,
) -> PrivacyFilterSpan | None:
    start = _span_int(raw_span, "start", "start_index", "begin")
    end = _span_int(raw_span, "end", "end_index", "stop")
    label = _span_str(raw_span, "label", "type", "entity_type", "category")
    if start is None or end is None or not label:
        return None
    start = max(0, min(start, text_length))
    end = max(0, min(end, text_length))
    if end <= start:
        return None
    normalized_label = label.strip().lower().replace("-", "_").replace(" ", "_")
    blocker_type, entity_type = _classify_label(normalized_label)
    return PrivacyFilterSpan(
        text_index=text_index,
        start=start,
        end=end,
        label=normalized_label,
        blocker_type=blocker_type,
        entity_type=entity_type,
    )


def _classify_label(label: str) -> tuple[str, str]:
    if label == "secret":
        return "credential", "credential"
    if label == "private_url":
        return "internal_url", "internal_url"
    return "pii", f"pii:{label}"


def _span_int(raw_span: Any, *names: str) -> int | None:
    value = _span_value(raw_span, *names)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _span_str(raw_span: Any, *names: str) -> str | None:
    value = _span_value(raw_span, *names)
    return value if isinstance(value, str) and value.strip() else None


def _span_value(raw_span: Any, *names: str) -> Any:
    if isinstance(raw_span, dict):
        for name in names:
            if name in raw_span:
                return raw_span[name]
    for name in names:
        if hasattr(raw_span, name):
            return getattr(raw_span, name)
    if hasattr(raw_span, "model_dump"):
        dumped = raw_span.model_dump()
        if isinstance(dumped, dict):
            for name in names:
                if name in dumped:
                    return dumped[name]
    return None


def _dedupe_tuple(values: Any) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in out:
            out.append(normalized)
    return tuple(out)


def _safe_error(error: BaseException) -> str:
    text = str(error).strip()
    if not text:
        return error.__class__.__name__
    return text[:200]
