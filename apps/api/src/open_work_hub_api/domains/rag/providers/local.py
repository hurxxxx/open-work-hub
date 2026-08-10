from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from open_work_hub_api.domains.rag.contracts import RagProviderHealth, RagVectorSearchHit
from open_work_hub_api.domains.rag.providers.base import RagProviderConfigurationError
from open_work_hub_api.domains.rag.providers.local_document_rendering import (
    suffix_for_content_type,
    text_too_short,
)
from open_work_hub_api.domains.rag.providers.rerank_text import build_rerank_document_text


logger = logging.getLogger(__name__)

class LocalSentenceTransformerEmbeddingClient:
    provider_name = "local-sentence-transformers"

    def __init__(
        self,
        *,
        model_name: str,
        revision: str | None = None,
        device: str = "auto",
        dtype: str = "auto",
        batch_size: int = 16,
        max_seq_length: int = 1024,
        normalize_embeddings: bool = True,
        query_prompt_name: str = "",
        query_prefix: str = "",
        trust_remote_code: bool = False,
        keep_loaded: bool = True,
    ) -> None:
        self._model_name = model_name.strip()
        self._revision = revision.strip() if revision else None
        self._device_setting = device.strip().lower() or "auto"
        self._dtype = dtype.strip().lower() or "auto"
        self._batch_size = batch_size
        self._max_seq_length = max_seq_length
        self._normalize_embeddings = normalize_embeddings
        self._query_prompt_name = query_prompt_name.strip()
        self._query_prefix = query_prefix
        self._trust_remote_code = trust_remote_code
        self._keep_loaded = keep_loaded
        self._model: Any | None = None
        self._lock = threading.RLock()

    def healthcheck(self) -> RagProviderHealth:
        if not self._model_name:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail="Missing local embedding model.",
            )
        try:
            _load_sentence_transformer_class()
        except Exception as error:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail=f"sentence-transformers is unavailable: {error}",
            )
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def preload(self) -> None:
        self._get_model()

    def close(self) -> None:
        with self._lock:
            self._model = None
        _empty_cuda_cache()

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]:
        del timeout_seconds
        if not texts:
            return []
        return self._encode(texts, is_query=False)

    def embed_query(
        self,
        text: str,
        timeout_seconds: float | None = None,
    ) -> list[float]:
        del timeout_seconds
        embeddings = self._encode([text], is_query=True)
        return embeddings[0] if embeddings else []

    def _encode(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        model = self._get_model()
        encoded_texts = list(texts)
        kwargs: dict[str, Any] = {
            "batch_size": self._batch_size,
            "convert_to_numpy": True,
            "normalize_embeddings": self._normalize_embeddings,
            "show_progress_bar": False,
        }
        if is_query and self._query_prompt_name:
            try:
                return _vectors_to_lists(
                    model.encode(encoded_texts, prompt_name=self._query_prompt_name, **kwargs)
                )
            except (KeyError, ValueError):
                logger.debug(
                    "Local embedding model does not expose prompt_name=%s; falling back.",
                    self._query_prompt_name,
                )
        if is_query and self._query_prefix:
            encoded_texts = [f"{self._query_prefix}{text}" for text in encoded_texts]
        return _vectors_to_lists(model.encode(encoded_texts, **kwargs))

    def _get_model(self):
        with self._lock:
            if self._model is not None:
                return self._model
            if not self._model_name:
                raise RagProviderConfigurationError("Local embedding model is not configured.")
            SentenceTransformer = _load_sentence_transformer_class()
            torch = _import_torch_optional()
            device = _resolve_device(torch, self._device_setting)
            kwargs: dict[str, Any] = {
                "trust_remote_code": self._trust_remote_code,
                "device": device,
            }
            if self._revision:
                kwargs["revision"] = self._revision
            model_kwargs = _torch_model_kwargs(torch, dtype=self._dtype, device=device)
            if model_kwargs:
                kwargs["model_kwargs"] = model_kwargs
            model = SentenceTransformer(self._model_name, **kwargs)
            if hasattr(model, "max_seq_length"):
                model.max_seq_length = self._max_seq_length
            if self._keep_loaded:
                self._model = model
            return model


class LocalCrossEncoderRerankClient:
    provider_name = "local-cross-encoder"

    def __init__(
        self,
        *,
        model_name: str,
        revision: str | None = None,
        device: str = "auto",
        dtype: str = "auto",
        batch_size: int = 16,
        max_length: int = 512,
        trust_remote_code: bool = False,
        keep_loaded: bool = True,
    ) -> None:
        self._model_name = model_name.strip()
        self._revision = revision.strip() if revision else None
        self._device_setting = device.strip().lower() or "auto"
        self._dtype = dtype.strip().lower() or "auto"
        self._batch_size = batch_size
        self._max_length = max_length
        self._trust_remote_code = trust_remote_code
        self._keep_loaded = keep_loaded
        self._model: Any | None = None
        self._lock = threading.RLock()

    def healthcheck(self) -> RagProviderHealth:
        if not self._model_name:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail="Missing local reranker model.",
            )
        try:
            _load_cross_encoder_class()
        except Exception as error:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail=f"sentence-transformers is unavailable: {error}",
            )
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def preload(self) -> None:
        self._get_model()

    def close(self) -> None:
        with self._lock:
            self._model = None
        _empty_cuda_cache()

    def rerank(
        self,
        *,
        query: str,
        hits: list[RagVectorSearchHit],
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]:
        del timeout_seconds
        if not hits:
            return []
        model = self._get_model()
        pairs = [(query, build_rerank_document_text(hit)) for hit in hits]
        raw_scores = model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        scores = _scores_to_list(raw_scores)
        reranked = [
            hit.model_copy(
                update={
                    "score": float(score),
                    "metadata": {
                        **dict(hit.metadata),
                        "dense_score": hit.score,
                        "rerank_score": float(score),
                    },
                }
            )
            for hit, score in zip(hits, scores, strict=False)
        ]
        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def _get_model(self):
        with self._lock:
            if self._model is not None:
                return self._model
            if not self._model_name:
                raise RagProviderConfigurationError("Local reranker model is not configured.")
            CrossEncoder = _load_cross_encoder_class()
            torch = _import_torch_optional()
            device = _resolve_device(torch, self._device_setting)
            kwargs: dict[str, Any] = {
                "device": device,
                "max_length": self._max_length,
                "trust_remote_code": self._trust_remote_code,
            }
            if self._revision:
                kwargs["revision"] = self._revision
            model_kwargs = _torch_model_kwargs(torch, dtype=self._dtype, device=device)
            if model_kwargs:
                kwargs["model_kwargs"] = model_kwargs
            try:
                model = CrossEncoder(self._model_name, **kwargs)
            except TypeError:
                kwargs.pop("model_kwargs", None)
                model = CrossEncoder(self._model_name, **kwargs)
            if self._keep_loaded:
                self._model = model
            return model


class DoclingOcrClient:
    provider_name = "docling"

    def __init__(
        self,
        *,
        force_ocr: bool = False,
        ocr_engine: str = "easyocr",
        ocr_langs: Sequence[str] = ("ko", "en"),
        min_text_chars: int = 128,
    ) -> None:
        self._force_ocr = force_ocr
        self._ocr_engine = ocr_engine.strip().lower() or "easyocr"
        self._ocr_langs = tuple(lang.strip() for lang in ocr_langs if lang.strip()) or ("ko", "en")
        self._min_text_chars = min_text_chars
        self._default_converter: Any | None = None
        self._ocr_converter: Any | None = None
        self._lock = threading.RLock()

    def healthcheck(self) -> RagProviderHealth:
        try:
            _load_docling_converter_class()
        except Exception as error:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail=f"docling is unavailable: {error}",
            )
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def preload(self) -> None:
        self._get_default_converter()
        self._get_ocr_converter()

    def close(self) -> None:
        with self._lock:
            self._default_converter = None
            self._ocr_converter = None
        _empty_cuda_cache()

    def extract_text(self, *, content: bytes, content_type: str | None = None) -> str:
        suffix = suffix_for_content_type(content_type)
        with tempfile.TemporaryDirectory(prefix="open-work-hub-dev-rag-docling-") as tmp:
            input_path = Path(tmp) / f"input{suffix}"
            input_path.write_bytes(content)
            text = ""
            default_error: Exception | None = None
            if not self._force_ocr:
                try:
                    text = self._convert_with_docling(input_path, force_ocr=False)
                except Exception as error:
                    default_error = error
            if self._force_ocr or text_too_short(text, self._min_text_chars):
                try:
                    text = self._convert_with_docling(input_path, force_ocr=True)
                except Exception:
                    if text:
                        return text
                    if default_error is not None:
                        raise default_error
                    raise
            return text

    def _convert_with_docling(self, path: Path, *, force_ocr: bool) -> str:
        converter = self._get_ocr_converter() if force_ocr else self._get_default_converter()
        result = converter.convert(path)
        return str(result.document.export_to_markdown())

    def _get_default_converter(self):
        with self._lock:
            if self._default_converter is None:
                DocumentConverter = _load_docling_converter_class()
                self._default_converter = DocumentConverter()
            return self._default_converter

    def _get_ocr_converter(self):
        with self._lock:
            if self._ocr_converter is None:
                self._ocr_converter = _build_docling_ocr_converter(
                    ocr_engine=self._ocr_engine,
                    ocr_langs=self._ocr_langs,
                )
            return self._ocr_converter

def _load_sentence_transformer_class():
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as error:  # pragma: no cover - depends on optional local deps
        raise RagProviderConfigurationError(
            "Install the RAG local extra to use local sentence-transformer embeddings."
        ) from error
    return SentenceTransformer


def _load_cross_encoder_class():
    try:
        from sentence_transformers import CrossEncoder
    except Exception as error:  # pragma: no cover - depends on optional local deps
        raise RagProviderConfigurationError(
            "Install the RAG local extra to use local cross-encoder reranking."
        ) from error
    return CrossEncoder


def _load_docling_converter_class():
    try:
        from docling.document_converter import DocumentConverter
    except Exception as error:  # pragma: no cover - depends on optional local deps
        raise RagProviderConfigurationError("Install the RAG OCR extra to use Docling.") from error
    return DocumentConverter


def _build_docling_ocr_converter(*, ocr_engine: str, ocr_langs: Sequence[str]):
    DocumentConverter = _load_docling_converter_class()
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
        from docling.document_converter import PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
        if ocr_engine == "rapidocr":
            from docling.datamodel.pipeline_options import RapidOcrOptions

            pipeline_options.ocr_options = RapidOcrOptions(
                force_full_page_ocr=True,
                lang=list(ocr_langs),
            )
        elif ocr_engine == "tesseract_cli":
            from docling.datamodel.pipeline_options import TesseractCliOcrOptions

            pipeline_options.ocr_options = TesseractCliOcrOptions(
                force_full_page_ocr=True,
                lang=list(ocr_langs),
            )
        else:
            from docling.datamodel.pipeline_options import EasyOcrOptions

            pipeline_options.ocr_options = EasyOcrOptions(
                force_full_page_ocr=True,
                lang=list(ocr_langs),
            )
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
    except Exception as error:  # pragma: no cover - depends on Docling version
        logger.warning("Docling OCR options unavailable; using default converter: %s", error)
        return DocumentConverter()


def _import_torch_optional():
    try:
        import torch
    except Exception:
        return None
    return torch


def _resolve_device(torch, requested: str) -> str:
    if requested == "auto":
        if torch is not None and torch.cuda.is_available():
            return "cuda"
        return "cpu"
    if requested == "cuda" and (torch is None or not torch.cuda.is_available()):
        raise RagProviderConfigurationError(
            "CUDA was requested for local RAG, but it is unavailable."
        )
    return requested


def _torch_model_kwargs(torch, *, dtype: str, device: str) -> dict[str, Any]:
    if torch is None or device != "cuda":
        return {}
    dtype_name = "bfloat16" if dtype == "auto" else dtype
    if dtype_name in {"", "float32"}:
        return {}
    torch_dtype = getattr(torch, dtype_name, None)
    return {"torch_dtype": torch_dtype} if torch_dtype is not None else {}


def _vectors_to_lists(vectors: Any) -> list[list[float]]:
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    return [[float(value) for value in vector] for vector in vectors]


def _scores_to_list(scores: Any) -> list[float]:
    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    if isinstance(scores, float | int):
        return [float(scores)]
    return [float(score[0] if isinstance(score, list | tuple) else score) for score in scores]


def _empty_cuda_cache() -> None:
    torch = _import_torch_optional()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()
