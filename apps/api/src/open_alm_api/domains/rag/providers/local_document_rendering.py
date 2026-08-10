from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from open_alm_api.domains.rag.providers.base import RagProviderConfigurationError


DOC_SUFFIX_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "text/plain": ".txt",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
OFFICE_SUFFIXES = {".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls"}


def suffix_for_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".bin"
    normalized = content_type.split(";", 1)[0].strip().lower()
    return DOC_SUFFIX_BY_CONTENT_TYPE.get(normalized, ".bin")


def text_too_short(text: str, min_chars: int) -> bool:
    return len(text.strip()) < max(min_chars, 0)


def render_document_pages(
    input_path: Path,
    *,
    work_dir: Path,
    max_pages: int,
    dpi: int,
) -> list[Path]:
    suffix = input_path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return [input_path]
    pdf_path = input_path
    if suffix in OFFICE_SUFFIXES:
        pdf_path = convert_office_to_pdf(input_path, work_dir)
    if pdf_path.suffix.lower() != ".pdf":
        raise RagProviderConfigurationError(
            f"Vision OCR fallback cannot render content suffix {input_path.suffix!r}."
        )
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RagProviderConfigurationError("pdftoppm is required for Vision OCR PDF rendering.")
    prefix = work_dir / "qwen-page"
    command = [pdftoppm, "-png", "-r", str(dpi)]
    if max_pages > 0:
        command += ["-f", "1", "-l", str(max_pages)]
    command += [str(pdf_path), str(prefix)]
    proc = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        raise RagProviderConfigurationError(f"pdftoppm failed: {proc.stderr.strip()}")
    images = sorted(work_dir.glob("qwen-page-*.png"))
    if not images:
        raise RagProviderConfigurationError("Vision OCR rendering produced no page images.")
    return images


def convert_office_to_pdf(input_path: Path, work_dir: Path) -> Path:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise RagProviderConfigurationError(
            "libreoffice/soffice is required for Vision OCR Office document rendering."
        )
    proc = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work_dir),
            str(input_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        raise RagProviderConfigurationError(
            f"Office to PDF conversion failed: {proc.stderr.strip()}"
        )
    expected = work_dir / f"{input_path.stem}.pdf"
    if expected.exists():
        return expected
    candidates = sorted(work_dir.glob("*.pdf"))
    if candidates:
        return candidates[0]
    raise RagProviderConfigurationError("Office to PDF conversion produced no PDF.")
