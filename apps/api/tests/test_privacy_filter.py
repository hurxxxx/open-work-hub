from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from ai_do_api.core.settings import Settings
from ai_do_api.domains.ai import privacy_filter


def _settings(**overrides: object) -> Settings:
    values = {
        "postgres_dsn": (
            "postgresql+psycopg://ai_do_test:ai_do_test@127.0.0.1:5432/ai_do_test"
        ),
        "opf_enabled": True,
        "opf_checkpoint": "openai/privacy-filter",
        "opf_device": "cuda",
    }
    values.update(overrides)
    return Settings(**values)


def test_prepare_privacy_filter_downloads_missing_checkpoint_and_loads_cpu(
    monkeypatch,
    tmp_path,
) -> None:
    privacy_filter._REDACTORS.clear()
    cache_dir = tmp_path / "opf-cache"
    model_dir = cache_dir / "openai--privacy-filter"
    downloads: list[dict[str, object]] = []
    loads: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_snapshot_download(
        *,
        repo_id: str,
        cache_dir: str,
        local_dir: str,
        allow_patterns: list[str],
    ) -> str:
        downloads.append(
            {
                "repo_id": repo_id,
                "cache_dir": cache_dir,
                "local_dir": local_dir,
                "allow_patterns": allow_patterns,
            },
        )
        original_dir = model_dir / "original"
        original_dir.mkdir(parents=True)
        (original_dir / "config.json").write_text("{}", encoding="utf-8")
        (original_dir / "model.safetensors").write_bytes(b"model")
        return str(model_dir)

    class FakeOPF:
        def __init__(self, *args: object, **kwargs: object) -> None:
            loads.append((args, kwargs))

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )
    monkeypatch.setitem(sys.modules, "opf", SimpleNamespace(OPF=FakeOPF))

    health = privacy_filter.prepare_privacy_filter(
        settings=_settings(opf_service_base_url="", opf_cache_dir=str(cache_dir)),
        download=True,
    )

    assert health.ready is True
    assert health.status == "ready"
    assert downloads == [
        {
            "repo_id": "openai/privacy-filter",
            "cache_dir": str(model_dir / ".cache" / "huggingface"),
            "local_dir": str(model_dir),
            "allow_patterns": ["original/*"],
        },
    ]
    assert (model_dir / "config.json").is_file()
    assert (model_dir / "model.safetensors").is_file()
    assert not (model_dir / "original").exists()
    assert loads == [((str(model_dir),), {"device": "cpu", "output_mode": "typed"})]


def test_prepare_privacy_filter_reports_disabled_without_loading(monkeypatch) -> None:
    privacy_filter._REDACTORS.clear()
    monkeypatch.setitem(sys.modules, "opf", SimpleNamespace(OPF=object))

    health = privacy_filter.prepare_privacy_filter(
        settings=_settings(opf_enabled=False),
        download=True,
    )

    assert health.enabled is False
    assert health.ready is False
    assert health.status == "disabled"


def test_detect_privacy_filter_spans_uses_configured_service(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["json"] = request.read()
        return privacy_filter.httpx.Response(
            200,
            json={
                "status": "ok",
                "spans": [
                    {
                        "text_index": 0,
                        "start": 0,
                        "end": 5,
                        "label": "email",
                        "blocker_type": "pii",
                        "entity_type": "pii:email",
                    }
                ],
                "entity_types": ["pii:email"],
                "blocker_types": ["pii"],
                "pii_hits": ["email"],
                "enabled": True,
                "used": True,
                "error": None,
            },
        )

    transport = privacy_filter.httpx.MockTransport(handler)
    client_class = privacy_filter.httpx.Client
    monkeypatch.setattr(
        privacy_filter.httpx,
        "Client",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )

    detection = privacy_filter.detect_privacy_filter_spans(
        ["owner@example.com"],
        settings=_settings(opf_service_base_url="http://privacy.local"),
    )

    assert captured["url"] == "http://privacy.local/detect"
    assert detection.status == "ok"
    assert detection.spans[0].entity_type == "pii:email"


def test_detect_privacy_filter_suppresses_masked_placeholders_for_service(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def handler(request):
        captured["json"] = request.read()
        return privacy_filter.httpx.Response(
            200,
            json={
                "status": "ok",
                "spans": [],
                "entity_types": [],
                "blocker_types": [],
                "pii_hits": [],
                "enabled": True,
                "used": True,
                "error": None,
            },
        )

    transport = privacy_filter.httpx.MockTransport(handler)
    client_class = privacy_filter.httpx.Client
    monkeypatch.setattr(
        privacy_filter.httpx,
        "Client",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )

    detection = privacy_filter.detect_privacy_filter_spans(
        ["[masked:pii] 및 [redacted:internal_url]"],
        settings=_settings(opf_service_base_url="http://privacy.local"),
    )

    payload = json.loads(captured["json"])
    sanitized_text = payload["texts"][0]
    assert "[masked:pii]" not in sanitized_text
    assert "[redacted:internal_url]" not in sanitized_text
    assert "및" in sanitized_text
    assert len(sanitized_text) == len("[masked:pii] 및 [redacted:internal_url]")
    assert detection.status == "ok"


def test_privacy_filter_service_failure_fails_closed(monkeypatch) -> None:
    def raising_client(**_kwargs):
        raise RuntimeError("service down")

    monkeypatch.setattr(privacy_filter.httpx, "Client", raising_client)

    detection = privacy_filter.detect_privacy_filter_spans(
        ["public"],
        settings=_settings(opf_service_base_url="http://privacy.local"),
    )

    assert detection.enabled is True
    assert detection.status == "service_unavailable"
