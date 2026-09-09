"""Standalone Bento document tools copied into isolated agent workspaces."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
SUPPORTED_ELEMENTS = {"text", "shape", "chart", "table"}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("document must be a JSON object")
    return value


def _write(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def validate_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("format") != "bento/slides" or document.get("version") != 1:
        errors.append('format/version must be "bento/slides"/1')
    if document.get("size") != {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT}:
        errors.append("canvas must be 1280x720")
    if not isinstance(document.get("title"), str) or not document["title"].strip():
        errors.append("title is required")
    slides = document.get("slides")
    if not isinstance(slides, list) or not slides:
        return [*errors, "at least one slide is required"]
    slide_ids: set[str] = set()
    for slide_index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"slide {slide_index} must be an object")
            continue
        slide_id = slide.get("id")
        if not isinstance(slide_id, str) or not slide_id:
            errors.append(f"slide {slide_index} id is required")
        elif slide_id in slide_ids:
            errors.append(f"duplicate slide id: {slide_id}")
        else:
            slide_ids.add(slide_id)
        elements = slide.get("elements")
        if not isinstance(elements, list):
            errors.append(f"{slide_id or slide_index}: elements must be a list")
            continue
        element_ids: set[str] = set()
        for element in elements:
            if not isinstance(element, dict):
                errors.append(f"{slide_id}: element must be an object")
                continue
            element_id = element.get("id")
            element_type = element.get("type")
            if not isinstance(element_id, str) or not element_id:
                errors.append(f"{slide_id}: element id is required")
            elif element_id in element_ids:
                errors.append(f"{slide_id}: duplicate element id {element_id}")
            else:
                element_ids.add(element_id)
            if element_type not in SUPPORTED_ELEMENTS:
                errors.append(f"{slide_id}/{element_id}: unsupported type {element_type}")
            frame = [element.get(key) for key in ("x", "y", "w", "h")]
            if any(
                isinstance(value, bool) or not isinstance(value, (int, float)) for value in frame
            ):
                errors.append(f"{slide_id}/{element_id}: invalid frame")
                continue
            x, y, width, height = frame
            if width <= 0 or height <= 0:
                errors.append(f"{slide_id}/{element_id}: frame must be positive")
            if x < 0 or y < 0 or x + width > CANVAS_WIDTH or y + height > CANVAS_HEIGHT:
                errors.append(f"{slide_id}/{element_id}: frame overflows canvas")
    return errors


def inspect_document(document: dict[str, Any]) -> dict[str, Any]:
    slides: list[dict[str, Any]] = []
    for slide in document.get("slides", []):
        elements = slide.get("elements", []) if isinstance(slide, dict) else []
        warnings: list[str] = []
        for index, left in enumerate(elements):
            if not isinstance(left, dict):
                continue
            if left.get("type") == "text":
                raw = str(left.get("html", ""))
                plain = raw.replace("<br>", "\n").replace("<br/>", "\n")
                if len(plain) > max(
                    20, int(float(left.get("w", 1)) * float(left.get("h", 1)) / 320)
                ):
                    warnings.append(f"{left.get('id')}: text may be dense for its frame")
            for right in elements[index + 1 :]:
                if not isinstance(right, dict):
                    continue
                if left.get("type") == "shape" or right.get("type") == "shape":
                    continue
                if _overlap(left, right) > 0.35:
                    warnings.append(f"{left.get('id')} overlaps {right.get('id')} by more than 35%")
        slides.append(
            {
                "id": slide.get("id") if isinstance(slide, dict) else None,
                "elementCount": len(elements),
                "warnings": warnings,
            }
        )
    return {"errors": validate_document(document), "slides": slides}


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> float:
    try:
        x1 = max(float(left["x"]), float(right["x"]))
        y1 = max(float(left["y"]), float(right["y"]))
        x2 = min(float(left["x"]) + float(left["w"]), float(right["x"]) + float(right["w"]))
        y2 = min(float(left["y"]) + float(left["h"]), float(right["y"]) + float(right["h"]))
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        smaller = min(float(left["w"]) * float(left["h"]), float(right["w"]) * float(right["h"]))
        return area / smaller if smaller > 0 else 0.0
    except (KeyError, TypeError, ValueError):
        return 0.0


def render_document(document: dict[str, Any], output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for index, slide in enumerate(document.get("slides", []), start=1):
        background = html.escape(str(slide.get("background") or "#ffffff"))
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}">',
            f'<rect width="100%" height="100%" fill="{background}"/>',
        ]
        for element in slide.get("elements", []):
            if not isinstance(element, dict):
                continue
            x, y, width, height = (element.get(key, 0) for key in ("x", "y", "w", "h"))
            if element.get("type") == "shape":
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
                    f'fill="{html.escape(str(element.get("fill") or "none"))}" '
                    f'stroke="{html.escape(str(element.get("stroke") or "none"))}"/>'
                )
            elif element.get("type") == "text":
                text = html.escape(_plain_text(str(element.get("html") or ""))[:500])
                size = element.get("fontSize", 24)
                color = html.escape(str(element.get("color") or "#111827"))
                parts.append(
                    f'<foreignObject x="{x}" y="{y}" width="{width}" height="{height}">'
                    f'<div xmlns="http://www.w3.org/1999/xhtml" style="font-size:{size}px;color:{color};'
                    f'font-family:Arial,sans-serif;overflow:hidden">{text}</div></foreignObject>'
                )
            else:
                label = "CHART" if element.get("type") == "chart" else "TABLE"
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#f3f4f6" '
                    f'stroke="#94a3b8"/><text x="{float(x) + 16}" y="{float(y) + 32}" '
                    f'font-family="Arial" font-size="18" fill="#475569">{label}</text>'
                )
        parts.append("</svg>")
        path = output_dir / f"slide-{index:02d}.svg"
        path.write_text("".join(parts), encoding="utf-8")
        paths.append(str(path))
        converter = shutil.which("rsvg-convert") or shutil.which("sips")
        if converter:
            png_path = output_dir / f"slide-{index:02d}.png"
            if Path(converter).name == "rsvg-convert":
                command = [converter, str(path), "-o", str(png_path)]
            else:
                command = [converter, "-s", "format", "png", str(path), "--out", str(png_path)]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if completed.returncode == 0 and png_path.exists():
                paths.append(str(png_path))
    return paths


def _plain_text(value: str) -> str:
    result: list[str] = []
    inside = False
    for character in value:
        if character == "<":
            inside = True
        elif character == ">":
            inside = False
        elif not inside:
            result.append(character)
    return "".join(result)


def main() -> int:
    parser = argparse.ArgumentParser(prog="bento-tool")
    parser.add_argument(
        "command", choices=("read", "validate", "inspect", "render", "replace-slide", "metadata")
    )
    parser.add_argument("--document", default="document.json")
    parser.add_argument("--input")
    parser.add_argument("--slide-id")
    parser.add_argument("--title")
    parser.add_argument("--output-dir", default="previews")
    args = parser.parse_args()
    path = Path(args.document)
    document = _load(path)
    if args.command == "read":
        print(json.dumps(document, ensure_ascii=False, indent=2))
    elif args.command == "validate":
        errors = validate_document(document)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    elif args.command == "inspect":
        report = inspect_document(document)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["errors"] else 0
    elif args.command == "render":
        print(json.dumps({"previews": render_document(document, Path(args.output_dir))}, indent=2))
    elif args.command == "replace-slide":
        if not args.input or not args.slide_id:
            parser.error("replace-slide requires --slide-id and --input")
        replacement = _load(Path(args.input))
        slides = document.get("slides", [])
        for index, slide in enumerate(slides):
            if slide.get("id") == args.slide_id:
                slides[index] = replacement
                break
        else:
            raise ValueError(f"slide not found: {args.slide_id}")
        document["modified"] = datetime.now(UTC).isoformat()
        _write(path, document)
    elif args.command == "metadata":
        if args.title:
            document["title"] = args.title.strip()
        document["modified"] = datetime.now(UTC).isoformat()
        _write(path, document)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
