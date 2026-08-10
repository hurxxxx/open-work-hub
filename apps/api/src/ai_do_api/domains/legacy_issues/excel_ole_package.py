"""Stream arbitrary files into an XLSX workbook as icon-only OLE Package objects.

``openpyxl`` deliberately does not create embedded OLE objects.  This module is
therefore a small, low-level OOXML/Compound File Binary (CFB) writer used after
the workbook itself has been saved.  Attachment payloads are copied in bounded
chunks; they are never accumulated in memory.
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import struct
import tempfile
import uuid
import zipfile
import zlib
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final
from xml.etree import ElementTree as ET

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string
from openpyxl.utils.exceptions import CellCoordinatesException


StreamFactory = Callable[[], BinaryIO]
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class OleAttachmentPlacement:
    """One attachment icon to place in an existing worksheet cell."""

    sheet_name: str
    cell_coordinate: str
    filename: str
    size_bytes: int
    stream_factory: StreamFactory


_MAIN_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_DRAWING_NS: Final = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_CONTENT_TYPES_NS: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
_VML_NS: Final = "urn:schemas-microsoft-com:vml"
_OFFICE_NS: Final = "urn:schemas-microsoft-com:office:office"
_EXCEL_NS: Final = "urn:schemas-microsoft-com:office:excel"

_REL_OLE: Final = f"{_DOC_REL_NS}/oleObject"
_REL_IMAGE: Final = f"{_DOC_REL_NS}/image"
_REL_VML: Final = f"{_DOC_REL_NS}/vmlDrawing"
_OLE_CONTENT_TYPE: Final = "application/vnd.openxmlformats-officedocument.oleObject"
_VML_CONTENT_TYPE: Final = "application/vnd.openxmlformats-officedocument.vmlDrawing"

_FREESECT: Final = 0xFFFFFFFF
_ENDOFCHAIN: Final = 0xFFFFFFFE
_FATSECT: Final = 0xFFFFFFFD
_DIFSECT: Final = 0xFFFFFFFC
_NOSTREAM: Final = 0xFFFFFFFF
_CFB_SECTOR_SIZE: Final = 512
_CFB_MINI_SECTOR_SIZE: Final = 64
_CFB_MINI_STREAM_CUTOFF: Final = 4096
_COPY_CHUNK_SIZE: Final = 1024 * 1024
_MAX_CFB_V3_STREAM: Final = (1 << 31) - 1
_PACKAGE_CLSID: Final = uuid.UUID("0003000c-0000-0000-c000-000000000046")

_ICON_SIZE_PX: Final = 24
_ICON_GAP_PX: Final = 3
_ICON_MARGIN_PX: Final = 2
_MAX_ICONS_PER_LINE: Final = 4
_EMU_PER_PIXEL: Final = 9525
_WORKSHEET_CHILD_ORDER: Final = {
    name: index
    for index, name in enumerate(
        (
            "sheetPr",
            "dimension",
            "sheetViews",
            "sheetFormatPr",
            "cols",
            "sheetData",
            "sheetCalcPr",
            "sheetProtection",
            "protectedRanges",
            "scenarios",
            "autoFilter",
            "sortState",
            "dataConsolidate",
            "customSheetViews",
            "mergeCells",
            "phoneticPr",
            "conditionalFormatting",
            "dataValidations",
            "hyperlinks",
            "printOptions",
            "pageMargins",
            "pageSetup",
            "headerFooter",
            "rowBreaks",
            "colBreaks",
            "customProperties",
            "cellWatches",
            "ignoredErrors",
            "smartTags",
            "drawing",
            "legacyDrawing",
            "legacyDrawingHF",
            "picture",
            "oleObjects",
            "controls",
            "webPublishItems",
            "tableParts",
            "extLst",
        )
    )
}


ET.register_namespace("", _MAIN_NS)
ET.register_namespace("r", _DOC_REL_NS)
ET.register_namespace("xdr", _DRAWING_NS)
ET.register_namespace("v", _VML_NS)
ET.register_namespace("o", _OFFICE_NS)
ET.register_namespace("x", _EXCEL_NS)


@dataclass(frozen=True, slots=True)
class _ValidatedPlacement:
    source: OleAttachmentPlacement
    cell_coordinate: str
    row: int
    column: int


@dataclass(frozen=True, slots=True)
class _CompoundFilePlan:
    native_size: int
    use_mini_stream: bool
    native_sector_count: int
    root_mini_sector_count: int
    mini_sector_count: int
    directory_start: int
    mini_fat_start: int
    mini_fat_sector_count: int
    difat_start: int
    difat_sector_count: int
    fat_start: int
    fat_sector_count: int
    total_sector_count: int


def embed_ole_attachments(
    workbook_path: str | Path,
    output_path: str | Path,
    placements: Sequence[OleAttachmentPlacement],
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Embed ``placements`` into an XLSX workbook and atomically replace output.

    ``stream_factory`` is called exactly once per placement.  The returned
    stream is closed after use and must yield exactly ``size_bytes`` bytes.
    ``progress_callback``, when supplied, receives cumulative
    ``(completed_count, completed_bytes)`` after each complete OLE part.
    """

    source_path = Path(workbook_path)
    destination_path = Path(output_path)
    validated = _validate_placements(placements)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if not validated:
        if source_path.resolve() != destination_path.resolve():
            _atomic_copy(source_path, destination_path)
        return

    temporary_path = _temporary_output_path(destination_path)
    try:
        _embed_to_temporary(
            source_path,
            temporary_path,
            validated,
            progress_callback=progress_callback,
        )
        os.replace(temporary_path, destination_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _embed_to_temporary(
    source_path: Path,
    temporary_path: Path,
    placements: Sequence[_ValidatedPlacement],
    *,
    progress_callback: ProgressCallback | None,
) -> None:
    with zipfile.ZipFile(source_path, "r", allowZip64=True) as source_zip:
        source_names = set(source_zip.namelist())
        if "[Content_Types].xml" not in source_names:
            raise ValueError("The input file is not a valid XLSX package")

        updates, added_parts, embedding_parts = _prepare_package_changes(
            source_zip,
            source_names,
            placements,
        )

        with zipfile.ZipFile(
            temporary_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as output_zip:
            for item in source_zip.infolist():
                replacement = updates.get(item.filename)
                if replacement is not None:
                    output_zip.writestr(item, replacement)
                    continue
                with (
                    source_zip.open(item, "r") as source,
                    output_zip.open(
                        item,
                        "w",
                        force_zip64=True,
                    ) as target,
                ):
                    shutil.copyfileobj(source, target, length=_COPY_CHUNK_SIZE)

            for part_name, content in added_parts.items():
                if part_name not in source_names:
                    output_zip.writestr(part_name, content)

            completed_count = 0
            completed_bytes = 0
            for placement, part_name in embedding_parts:
                with output_zip.open(part_name, "w", force_zip64=True) as target:
                    _write_compound_package(target, placement.source)
                completed_count += 1
                completed_bytes += placement.source.size_bytes
                if progress_callback is not None:
                    progress_callback(completed_count, completed_bytes)


def _prepare_package_changes(
    source_zip: zipfile.ZipFile,
    source_names: set[str],
    placements: Sequence[_ValidatedPlacement],
) -> tuple[dict[str, bytes], dict[str, bytes], list[tuple[_ValidatedPlacement, str]]]:
    workbook_root = _parse_xml(source_zip.read("xl/workbook.xml"), "workbook")
    workbook_rels = _parse_xml(source_zip.read("xl/_rels/workbook.xml.rels"), "relationships")
    sheet_parts = _sheet_part_map(workbook_root, workbook_rels)

    for placement in placements:
        if placement.source.sheet_name not in sheet_parts:
            raise ValueError(f"Worksheet not found: {placement.source.sheet_name}")

    used_part_names = set(source_names)
    icon_part = _allocate_part_name(used_part_names, "xl/media/image", ".png")
    used_part_names.add(icon_part)

    placements_by_sheet: dict[str, list[_ValidatedPlacement]] = defaultdict(list)
    for placement in placements:
        placements_by_sheet[placement.source.sheet_name].append(placement)

    updates: dict[str, bytes] = {}
    additions: dict[str, bytes] = {icon_part: _generic_package_icon_png()}
    embedding_part_by_placement: dict[int, str] = {}
    content_type_overrides: list[str] = []

    sheet_indexes = {name: index for index, name in enumerate(sheet_parts, start=1)}
    for sheet_name, sheet_placements in placements_by_sheet.items():
        sheet_index = sheet_indexes[sheet_name]
        sheet_part = sheet_parts[sheet_name]
        sheet_rels_part = _relationships_part_name(sheet_part)
        sheet_root = _parse_xml(source_zip.read(sheet_part), f"worksheet {sheet_name}")
        if sheet_rels_part in source_names:
            sheet_rels_root = _parse_xml(
                source_zip.read(sheet_rels_part),
                f"worksheet relationships {sheet_name}",
            )
        else:
            sheet_rels_root = ET.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")

        legacy_drawing = sheet_root.find(f"{{{_MAIN_NS}}}legacyDrawing")
        if legacy_drawing is None:
            vml_part = _allocate_part_name(used_part_names, "xl/drawings/vmlDrawing", ".vml")
            used_part_names.add(vml_part)
            legacy_rel_id = _next_relationship_id(sheet_rels_root)
            ET.SubElement(
                sheet_rels_root,
                f"{{{_PACKAGE_REL_NS}}}Relationship",
                {
                    "Id": legacy_rel_id,
                    "Type": _REL_VML,
                    "Target": _relative_target(sheet_part, vml_part),
                },
            )
            legacy_drawing = ET.Element(
                f"{{{_MAIN_NS}}}legacyDrawing",
                {f"{{{_DOC_REL_NS}}}id": legacy_rel_id},
            )
            _insert_worksheet_child(sheet_root, legacy_drawing)
            vml_root = _new_vml_root(sheet_index)
            vml_rels_root = ET.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")
            vml_rels_part = _relationships_part_name(vml_part)
            vml_is_new = True
        else:
            legacy_rel_id = legacy_drawing.get(f"{{{_DOC_REL_NS}}}id")
            vml_part = _relationship_target_part(sheet_part, sheet_rels_root, legacy_rel_id)
            if vml_part is None or vml_part not in source_names:
                raise ValueError(
                    f"Worksheet {sheet_name} has an invalid legacy drawing relationship"
                )
            vml_root = _parse_xml(source_zip.read(vml_part), f"VML drawing {sheet_name}")
            vml_rels_part = _relationships_part_name(vml_part)
            if vml_rels_part in source_names:
                vml_rels_root = _parse_xml(
                    source_zip.read(vml_rels_part),
                    f"VML relationships {sheet_name}",
                )
            else:
                vml_rels_root = ET.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")
            vml_is_new = False

        _ensure_picture_shape_type(vml_root)
        vml_icon_rel_id = _ensure_image_relationship(vml_part, vml_rels_root, icon_part)
        sheet_icon_rel_id = _ensure_image_relationship(sheet_part, sheet_rels_root, icon_part)
        ole_objects = sheet_root.find(f"{{{_MAIN_NS}}}oleObjects")
        if ole_objects is None:
            ole_objects = ET.Element(f"{{{_MAIN_NS}}}oleObjects")
            _insert_worksheet_child(sheet_root, ole_objects)

        used_shape_ids = _existing_shape_ids(sheet_root, vml_root)
        next_shape_id = max(sheet_index * 1024 + 1, 1025)
        cell_groups: dict[str, list[_ValidatedPlacement]] = defaultdict(list)
        for placement in sheet_placements:
            cell_groups[placement.cell_coordinate].append(placement)

        layout_by_placement: dict[int, tuple[int, int, int, int]] = {}
        for group in cell_groups.values():
            column_pixels = _column_width_pixels(sheet_root, group[0].column)
            icons_per_line = min(
                _MAX_ICONS_PER_LINE,
                max(
                    1,
                    (max(column_pixels - 2 * _ICON_MARGIN_PX, _ICON_SIZE_PX) + _ICON_GAP_PX)
                    // (_ICON_SIZE_PX + _ICON_GAP_PX),
                ),
            )
            line_count = (len(group) + icons_per_line - 1) // icons_per_line
            required_row_pixels = (
                2 * _ICON_MARGIN_PX + line_count * _ICON_SIZE_PX + (line_count - 1) * _ICON_GAP_PX
            )
            row_pixels = _ensure_row_height(sheet_root, group[0].row, required_row_pixels)
            for index, placement in enumerate(group):
                line, slot = divmod(index, icons_per_line)
                x = _ICON_MARGIN_PX + slot * (_ICON_SIZE_PX + _ICON_GAP_PX)
                y = _ICON_MARGIN_PX + line * (_ICON_SIZE_PX + _ICON_GAP_PX)
                layout_by_placement[id(placement)] = (x, y, column_pixels, row_pixels)

        for placement in sheet_placements:
            while next_shape_id in used_shape_ids:
                next_shape_id += 1
            shape_id = next_shape_id
            used_shape_ids.add(shape_id)
            next_shape_id += 1

            embedding_part = _allocate_part_name(
                used_part_names,
                "xl/embeddings/oleObject",
                ".bin",
            )
            used_part_names.add(embedding_part)
            ole_rel_id = _next_relationship_id(sheet_rels_root)
            ET.SubElement(
                sheet_rels_root,
                f"{{{_PACKAGE_REL_NS}}}Relationship",
                {
                    "Id": ole_rel_id,
                    "Type": _REL_OLE,
                    "Target": _relative_target(sheet_part, embedding_part),
                },
            )

            x, y, column_pixels, row_pixels = layout_by_placement[id(placement)]
            _append_ole_object(
                ole_objects,
                placement,
                shape_id=shape_id,
                ole_relationship_id=ole_rel_id,
                icon_relationship_id=sheet_icon_rel_id,
                x=x,
                y=y,
            )
            _append_vml_shape(
                vml_root,
                placement,
                shape_id=shape_id,
                icon_relationship_id=vml_icon_rel_id,
                x=x,
                y=y,
                column_pixels=column_pixels,
                row_pixels=row_pixels,
            )
            _clear_cell_value(sheet_root, placement.cell_coordinate)
            embedding_part_by_placement[id(placement)] = embedding_part
            content_type_overrides.append(embedding_part)

        updates[sheet_part] = _serialize_xml(sheet_root)
        serialized_sheet_rels = _serialize_xml(sheet_rels_root)
        if sheet_rels_part in source_names:
            updates[sheet_rels_part] = serialized_sheet_rels
        else:
            additions[sheet_rels_part] = serialized_sheet_rels

        serialized_vml = _serialize_xml(vml_root)
        if vml_is_new:
            additions[vml_part] = serialized_vml
        else:
            updates[vml_part] = serialized_vml
        serialized_vml_rels = _serialize_xml(vml_rels_root)
        if vml_rels_part in source_names:
            updates[vml_rels_part] = serialized_vml_rels
        else:
            additions[vml_rels_part] = serialized_vml_rels

    content_types = _parse_xml(source_zip.read("[Content_Types].xml"), "content types")
    _ensure_content_type_default(content_types, "png", "image/png")
    _ensure_content_type_default(content_types, "vml", _VML_CONTENT_TYPE)
    for embedding_part in content_type_overrides:
        _ensure_content_type_override(content_types, embedding_part, _OLE_CONTENT_TYPE)
    updates["[Content_Types].xml"] = _serialize_xml(content_types)
    embedding_parts = [
        (placement, embedding_part_by_placement[id(placement)]) for placement in placements
    ]
    return updates, additions, embedding_parts


def _validate_placements(
    placements: Sequence[OleAttachmentPlacement],
) -> list[_ValidatedPlacement]:
    validated: list[_ValidatedPlacement] = []
    for placement in placements:
        if not placement.sheet_name:
            raise ValueError("sheet_name must not be empty")
        if not placement.filename:
            raise ValueError("filename must not be empty")
        if "\x00" in placement.filename:
            raise ValueError("filename must not contain a NUL character")
        if placement.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if not callable(placement.stream_factory):
            raise TypeError("stream_factory must be callable")
        try:
            column_name, row = coordinate_from_string(placement.cell_coordinate.upper())
            column = column_index_from_string(column_name)
        except (TypeError, ValueError, CellCoordinatesException) as error:
            raise ValueError(f"Invalid cell coordinate: {placement.cell_coordinate}") from error
        coordinate = f"{column_name.upper()}{row}"
        validated.append(
            _ValidatedPlacement(
                source=placement,
                cell_coordinate=coordinate,
                row=row,
                column=column,
            )
        )
    return validated


def _sheet_part_map(workbook_root: ET.Element, relationships_root: ET.Element) -> dict[str, str]:
    targets_by_id = {
        relationship.get("Id"): relationship.get("Target")
        for relationship in relationships_root
        if relationship.get("Id") and relationship.get("Target")
    }
    result: dict[str, str] = {}
    sheets = workbook_root.find(f"{{{_MAIN_NS}}}sheets")
    if sheets is None:
        return result
    for sheet in sheets:
        name = sheet.get("name")
        relationship_id = sheet.get(f"{{{_DOC_REL_NS}}}id")
        target = targets_by_id.get(relationship_id)
        if not name or not target:
            continue
        if target.startswith("/"):
            result[name] = target.lstrip("/")
        else:
            result[name] = posixpath.normpath(posixpath.join("xl", target))
    return result


def _append_ole_object(
    ole_objects: ET.Element,
    placement: _ValidatedPlacement,
    *,
    shape_id: int,
    ole_relationship_id: str,
    icon_relationship_id: str,
    x: int,
    y: int,
) -> None:
    ole_object = ET.SubElement(
        ole_objects,
        f"{{{_MAIN_NS}}}oleObject",
        {
            "progId": "Package",
            "dvAspect": "DVASPECT_ICON",
            "shapeId": str(shape_id),
            f"{{{_DOC_REL_NS}}}id": ole_relationship_id,
        },
    )
    object_properties = ET.SubElement(
        ole_object,
        f"{{{_MAIN_NS}}}objectPr",
        {
            "defaultSize": "0",
            "autoPict": "0",
            f"{{{_DOC_REL_NS}}}id": icon_relationship_id,
        },
    )
    anchor = ET.SubElement(
        object_properties,
        f"{{{_MAIN_NS}}}anchor",
        {"moveWithCells": "1", "sizeWithCells": "1"},
    )
    from_marker = ET.SubElement(anchor, f"{{{_MAIN_NS}}}from")
    to_marker = ET.SubElement(anchor, f"{{{_MAIN_NS}}}to")
    column = placement.column - 1
    row = placement.row - 1
    for marker, marker_x, marker_y in (
        (from_marker, x, y),
        (to_marker, x + _ICON_SIZE_PX, y + _ICON_SIZE_PX),
    ):
        ET.SubElement(marker, f"{{{_DRAWING_NS}}}col").text = str(column)
        ET.SubElement(marker, f"{{{_DRAWING_NS}}}colOff").text = str(marker_x * _EMU_PER_PIXEL)
        ET.SubElement(marker, f"{{{_DRAWING_NS}}}row").text = str(row)
        ET.SubElement(marker, f"{{{_DRAWING_NS}}}rowOff").text = str(marker_y * _EMU_PER_PIXEL)


def _append_vml_shape(
    vml_root: ET.Element,
    placement: _ValidatedPlacement,
    *,
    shape_id: int,
    icon_relationship_id: str,
    x: int,
    y: int,
    column_pixels: int,
    row_pixels: int,
) -> None:
    shape = ET.SubElement(
        vml_root,
        f"{{{_VML_NS}}}shape",
        {
            "id": f"_x0000_s{shape_id}",
            "type": "#_x0000_t75",
            "style": (
                f"position:absolute;width:{_ICON_SIZE_PX * 0.75:g}pt;"
                f"height:{_ICON_SIZE_PX * 0.75:g}pt;"
                f"z-index:{shape_id};mso-wrap-style:tight"
            ),
            "filled": "f",
            "stroked": "f",
        },
    )
    ET.SubElement(
        shape,
        f"{{{_VML_NS}}}imagedata",
        {f"{{{_OFFICE_NS}}}relid": icon_relationship_id, f"{{{_OFFICE_NS}}}title": ""},
    )
    client_data = ET.SubElement(
        shape,
        f"{{{_EXCEL_NS}}}ClientData",
        {"ObjectType": "Pict"},
    )
    ET.SubElement(client_data, f"{{{_EXCEL_NS}}}SizeWithCells")
    anchor = ET.SubElement(client_data, f"{{{_EXCEL_NS}}}Anchor")
    column = placement.column - 1
    row = placement.row - 1
    x1 = min(1023, max(0, round(x * 1024 / max(column_pixels, 1))))
    x2 = min(1023, max(x1 + 1, round((x + _ICON_SIZE_PX) * 1024 / max(column_pixels, 1))))
    y1 = min(255, max(0, round(y * 256 / max(row_pixels, 1))))
    y2 = min(255, max(y1 + 1, round((y + _ICON_SIZE_PX) * 256 / max(row_pixels, 1))))
    anchor.text = f"{column}, {x1}, {row}, {y1}, {column}, {x2}, {row}, {y2}"
    ET.SubElement(client_data, f"{{{_EXCEL_NS}}}CF").text = "Pict"


def _new_vml_root(sheet_index: int) -> ET.Element:
    root = ET.Element("xml")
    shape_layout = ET.SubElement(
        root, f"{{{_OFFICE_NS}}}shapelayout", {f"{{{_VML_NS}}}ext": "edit"}
    )
    ET.SubElement(
        shape_layout,
        f"{{{_OFFICE_NS}}}idmap",
        {f"{{{_VML_NS}}}ext": "edit", "data": str(sheet_index)},
    )
    return root


def _ensure_picture_shape_type(vml_root: ET.Element) -> None:
    if any(
        child.tag == f"{{{_VML_NS}}}shapetype" and child.get("id") == "_x0000_t75"
        for child in vml_root
    ):
        return
    shape_type = ET.Element(
        f"{{{_VML_NS}}}shapetype",
        {
            "id": "_x0000_t75",
            "coordsize": "21600,21600",
            f"{{{_OFFICE_NS}}}spt": "75",
            f"{{{_OFFICE_NS}}}preferrelative": "t",
            "path": "m@4@5l@4@11@9@11@9@5xe",
            "filled": "f",
            "stroked": "f",
        },
    )
    ET.SubElement(shape_type, f"{{{_VML_NS}}}stroke", {"joinstyle": "miter"})
    formulas = ET.SubElement(shape_type, f"{{{_VML_NS}}}formulas")
    for equation in (
        "if lineDrawn pixelLineWidth 0",
        "sum @0 1 0",
        "sum 0 0 @1",
        "prod @2 1 2",
        "prod @3 21600 pixelWidth",
        "prod @3 21600 pixelHeight",
        "sum @0 0 1",
        "prod @6 1 2",
        "prod @7 21600 pixelWidth",
        "sum @8 21600 0",
        "prod @7 21600 pixelHeight",
        "sum @10 21600 0",
    ):
        ET.SubElement(formulas, f"{{{_VML_NS}}}f", {"eqn": equation})
    ET.SubElement(
        shape_type,
        f"{{{_VML_NS}}}path",
        {
            f"{{{_OFFICE_NS}}}extrusionok": "f",
            "gradientshapeok": "t",
            f"{{{_OFFICE_NS}}}connecttype": "rect",
        },
    )
    ET.SubElement(
        shape_type,
        f"{{{_OFFICE_NS}}}lock",
        {f"{{{_VML_NS}}}ext": "edit", "aspectratio": "t"},
    )
    insertion_index = next(
        (index for index, child in enumerate(vml_root) if child.tag == f"{{{_VML_NS}}}shape"),
        len(vml_root),
    )
    vml_root.insert(insertion_index, shape_type)


def _clear_cell_value(sheet_root: ET.Element, coordinate: str) -> None:
    for cell in sheet_root.findall(f".//{{{_MAIN_NS}}}c"):
        if cell.get("r", "").upper() != coordinate:
            continue
        for child in list(cell):
            if child.tag in {
                f"{{{_MAIN_NS}}}f",
                f"{{{_MAIN_NS}}}v",
                f"{{{_MAIN_NS}}}is",
            }:
                cell.remove(child)
        cell.attrib.pop("t", None)
        return


def _column_width_pixels(sheet_root: ET.Element, column: int) -> int:
    width: float | None = None
    columns = sheet_root.find(f"{{{_MAIN_NS}}}cols")
    if columns is not None:
        for column_definition in columns:
            minimum = int(column_definition.get("min", "0"))
            maximum = int(column_definition.get("max", "0"))
            if minimum <= column <= maximum and column_definition.get("width"):
                width = float(column_definition.get("width", "8.43"))
    if width is None:
        sheet_format = sheet_root.find(f"{{{_MAIN_NS}}}sheetFormatPr")
        if sheet_format is not None and sheet_format.get("defaultColWidth"):
            width = float(sheet_format.get("defaultColWidth", "8.43"))
        else:
            width = 8.43
    return max(_ICON_SIZE_PX + 2 * _ICON_MARGIN_PX, int(width * 7 + 5))


def _ensure_row_height(sheet_root: ET.Element, row_number: int, required_pixels: int) -> int:
    sheet_data = sheet_root.find(f"{{{_MAIN_NS}}}sheetData")
    if sheet_data is None:
        raise ValueError("Worksheet is missing sheetData")
    row_element = next(
        (row for row in sheet_data if int(row.get("r", "0")) == row_number),
        None,
    )
    if row_element is None:
        row_element = ET.Element(f"{{{_MAIN_NS}}}row", {"r": str(row_number)})
        insertion_index = next(
            (index for index, row in enumerate(sheet_data) if int(row.get("r", "0")) > row_number),
            len(sheet_data),
        )
        sheet_data.insert(insertion_index, row_element)

    existing_points: float | None = None
    if row_element.get("ht"):
        existing_points = float(row_element.get("ht", "15"))
    if existing_points is None:
        sheet_format = sheet_root.find(f"{{{_MAIN_NS}}}sheetFormatPr")
        existing_points = (
            float(sheet_format.get("defaultRowHeight", "15")) if sheet_format is not None else 15.0
        )
    existing_pixels = max(1, round(existing_points * 4 / 3))
    final_pixels = max(existing_pixels, required_pixels)
    if final_pixels > existing_pixels or row_element.get("ht") is not None:
        row_element.set("ht", f"{final_pixels * 0.75:g}")
        row_element.set("customHeight", "1")
    return final_pixels


def _insert_worksheet_child(
    sheet_root: ET.Element,
    child: ET.Element,
) -> None:
    child_name = child.tag.rsplit("}", 1)[-1]
    child_order = _WORKSHEET_CHILD_ORDER[child_name]
    for index, existing in enumerate(sheet_root):
        local_name = existing.tag.rsplit("}", 1)[-1]
        existing_order = _WORKSHEET_CHILD_ORDER.get(local_name)
        if existing_order is not None and existing_order > child_order:
            sheet_root.insert(index, child)
            return
    sheet_root.append(child)


def _existing_shape_ids(sheet_root: ET.Element, vml_root: ET.Element) -> set[int]:
    shape_ids: set[int] = set()
    for ole_object in sheet_root.findall(f".//{{{_MAIN_NS}}}oleObject"):
        value = ole_object.get("shapeId")
        if value and value.isdigit():
            shape_ids.add(int(value))
    for shape in vml_root.findall(f".//{{{_VML_NS}}}shape"):
        match = re.fullmatch(r"_x0000_s(\d+)", shape.get("id", ""))
        if match:
            shape_ids.add(int(match.group(1)))
    return shape_ids


def _next_relationship_id(relationships_root: ET.Element) -> str:
    used = {relationship.get("Id") for relationship in relationships_root if relationship.get("Id")}
    number = 1
    while f"rId{number}" in used:
        number += 1
    return f"rId{number}"


def _ensure_image_relationship(
    source_part: str,
    relationships_root: ET.Element,
    image_part: str,
) -> str:
    target = _relative_target(source_part, image_part)
    for relationship in relationships_root:
        if relationship.get("Type") == _REL_IMAGE and relationship.get("Target") == target:
            relationship_id = relationship.get("Id")
            if relationship_id:
                return relationship_id
    relationship_id = _next_relationship_id(relationships_root)
    ET.SubElement(
        relationships_root,
        f"{{{_PACKAGE_REL_NS}}}Relationship",
        {"Id": relationship_id, "Type": _REL_IMAGE, "Target": target},
    )
    return relationship_id


def _relationship_target_part(
    source_part: str,
    relationships_root: ET.Element,
    relationship_id: str | None,
) -> str | None:
    if relationship_id is None:
        return None
    for relationship in relationships_root:
        if relationship.get("Id") != relationship_id:
            continue
        target = relationship.get("Target")
        if not target or relationship.get("TargetMode") == "External":
            return None
        if target.startswith("/"):
            return target.lstrip("/")
        return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))
    return None


def _relative_target(source_part: str, target_part: str) -> str:
    return posixpath.relpath(target_part, posixpath.dirname(source_part))


def _relationships_part_name(part_name: str) -> str:
    return posixpath.join(
        posixpath.dirname(part_name),
        "_rels",
        f"{posixpath.basename(part_name)}.rels",
    )


def _allocate_part_name(used_names: set[str], prefix: str, suffix: str) -> str:
    directory = posixpath.dirname(prefix)
    basename = posixpath.basename(prefix)
    pattern = re.compile(rf"^{re.escape(directory)}/{re.escape(basename)}(\d+)(?:\.[^/]+)$")
    used_numbers = {
        int(match.group(1)) for name in used_names if (match := pattern.fullmatch(name)) is not None
    }
    number = 1
    while number in used_numbers or f"{prefix}{number}{suffix}" in used_names:
        number += 1
    return f"{prefix}{number}{suffix}"


def _ensure_content_type_default(root: ET.Element, extension: str, content_type: str) -> None:
    for child in root:
        if (
            child.tag.endswith("Default")
            and child.get("Extension", "").lower() == extension.lower()
        ):
            return
    ET.SubElement(
        root,
        f"{{{_CONTENT_TYPES_NS}}}Default",
        {"Extension": extension, "ContentType": content_type},
    )


def _ensure_content_type_override(root: ET.Element, part_name: str, content_type: str) -> None:
    normalized_name = f"/{part_name.lstrip('/')}"
    for child in root:
        if child.tag.endswith("Override") and child.get("PartName") == normalized_name:
            child.set("ContentType", content_type)
            return
    ET.SubElement(
        root,
        f"{{{_CONTENT_TYPES_NS}}}Override",
        {"PartName": normalized_name, "ContentType": content_type},
    )


def _parse_xml(content: bytes, description: str) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError(f"Invalid {description} XML") from error


def _serialize_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _generic_package_icon_png() -> bytes:
    """Return a small generic package icon with no filename or text."""

    width = height = _ICON_SIZE_PX
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if 3 <= x <= 14 and 2 <= y <= 15:
                if x in {3, 14} or y in {2, 15}:
                    rgba = (57, 88, 133, 255)
                elif x >= 11 and y <= 5:
                    rgba = (174, 202, 231, 255)
                else:
                    rgba = (232, 241, 250, 255)
            elif 5 <= x <= 12 and 11 <= y <= 13:
                rgba = (245, 166, 35, 255)
            else:
                rgba = (0, 0, 0, 0)
            rows.extend(rgba)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + chunk(b"IEND", b"")
    )


def _write_compound_package(target: BinaryIO, placement: OleAttachmentPlacement) -> None:
    prefix, suffix, native_size = _ole10native_metadata(placement.filename, placement.size_bytes)
    plan = _plan_compound_file(native_size)
    target.write(_compound_file_header(plan))

    payload = placement.stream_factory()
    if payload is None or not hasattr(payload, "read"):
        raise TypeError("stream_factory must return a binary readable stream")
    try:
        target.write(prefix)
        _copy_exactly(payload, target, placement.size_bytes)
        target.write(suffix)
    finally:
        try:
            payload.close()
        finally:
            release_connection = getattr(payload, "release_conn", None)
            if callable(release_connection):
                release_connection()

    native_padding = (
        (_CFB_MINI_SECTOR_SIZE if plan.use_mini_stream else _CFB_SECTOR_SIZE)
        - native_size % (_CFB_MINI_SECTOR_SIZE if plan.use_mini_stream else _CFB_SECTOR_SIZE)
    ) % (_CFB_MINI_SECTOR_SIZE if plan.use_mini_stream else _CFB_SECTOR_SIZE)
    if native_padding:
        target.write(b"\x00" * native_padding)
    if plan.use_mini_stream:
        mini_stream_size = plan.mini_sector_count * _CFB_MINI_SECTOR_SIZE
        regular_padding = (-mini_stream_size) % _CFB_SECTOR_SIZE
        if regular_padding:
            target.write(b"\x00" * regular_padding)

    target.write(_directory_sector(plan))
    _write_mini_fat(target, plan)
    _write_difat(target, plan)
    _write_fat(target, plan)


def _ole10native_metadata(filename: str, payload_size: int) -> tuple[bytes, bytes, int]:
    if payload_size > 0xFFFFFFFF:
        raise ValueError("Attachment is too large for an Ole10Native stream")
    ascii_name = filename.encode("latin-1", errors="replace") + b"\x00"
    command = ascii_name
    prefix_after_size = (
        struct.pack("<H", 2)
        + ascii_name
        + ascii_name
        + struct.pack("<HHI", 0, 3, len(command))
        + command
        + struct.pack("<I", payload_size)
    )
    unicode_value = filename.encode("utf-16le") + b"\x00\x00"
    character_count = len(filename.encode("utf-16le")) // 2 + 1
    unicode_field = struct.pack("<I", character_count) + unicode_value
    suffix = unicode_field * 3
    total_after_size = len(prefix_after_size) + payload_size + len(suffix)
    if total_after_size > 0xFFFFFFFF:
        raise ValueError("Attachment is too large for an Ole10Native stream")
    prefix = struct.pack("<I", total_after_size) + prefix_after_size
    native_size = len(prefix) + payload_size + len(suffix)
    if native_size > _MAX_CFB_V3_STREAM:
        raise ValueError("Attachment is too large for a version 3 compound file")
    return prefix, suffix, native_size


def _copy_exactly(source: BinaryIO, target: BinaryIO, expected_size: int) -> None:
    remaining = expected_size
    while remaining:
        chunk = source.read(min(_COPY_CHUNK_SIZE, remaining))
        if not chunk:
            raise ValueError("Attachment stream ended before size_bytes")
        if not isinstance(chunk, bytes | bytearray | memoryview):
            raise TypeError("Attachment stream must return bytes")
        if len(chunk) > remaining:
            raise ValueError("Attachment stream returned more bytes than requested")
        target.write(chunk)
        remaining -= len(chunk)
    extra = source.read(1)
    if extra:
        raise ValueError("Attachment stream contains more data than size_bytes")


def _plan_compound_file(native_size: int) -> _CompoundFilePlan:
    if native_size <= 0 or native_size > _MAX_CFB_V3_STREAM:
        raise ValueError("Invalid compound stream size")
    use_mini_stream = native_size < _CFB_MINI_STREAM_CUTOFF
    mini_sector_count = (
        (native_size + _CFB_MINI_SECTOR_SIZE - 1) // _CFB_MINI_SECTOR_SIZE if use_mini_stream else 0
    )
    native_sector_count = (
        (native_size + _CFB_SECTOR_SIZE - 1) // _CFB_SECTOR_SIZE if not use_mini_stream else 0
    )
    root_mini_sector_count = (
        (mini_sector_count * _CFB_MINI_SECTOR_SIZE + _CFB_SECTOR_SIZE - 1) // _CFB_SECTOR_SIZE
        if use_mini_stream
        else 0
    )
    mini_fat_sector_count = (mini_sector_count + 127) // 128 if use_mini_stream else 0
    base_sector_count = native_sector_count + root_mini_sector_count + 1 + mini_fat_sector_count
    fat_sector_count = 1
    difat_sector_count = 0
    while True:
        required_fat = (base_sector_count + difat_sector_count + fat_sector_count + 127) // 128
        required_difat = max(0, (required_fat - 109 + 126) // 127)
        if required_fat == fat_sector_count and required_difat == difat_sector_count:
            break
        fat_sector_count = required_fat
        difat_sector_count = required_difat

    directory_start = native_sector_count + root_mini_sector_count
    mini_fat_start = directory_start + 1 if mini_fat_sector_count else _ENDOFCHAIN
    difat_start = base_sector_count if difat_sector_count else _ENDOFCHAIN
    fat_start = base_sector_count + difat_sector_count
    total_sector_count = fat_start + fat_sector_count
    return _CompoundFilePlan(
        native_size=native_size,
        use_mini_stream=use_mini_stream,
        native_sector_count=native_sector_count,
        root_mini_sector_count=root_mini_sector_count,
        mini_sector_count=mini_sector_count,
        directory_start=directory_start,
        mini_fat_start=mini_fat_start,
        mini_fat_sector_count=mini_fat_sector_count,
        difat_start=difat_start,
        difat_sector_count=difat_sector_count,
        fat_start=fat_start,
        fat_sector_count=fat_sector_count,
        total_sector_count=total_sector_count,
    )


def _compound_file_header(plan: _CompoundFilePlan) -> bytes:
    header = bytearray(_CFB_SECTOR_SIZE)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x003E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<I", header, 40, 0)
    struct.pack_into("<I", header, 44, plan.fat_sector_count)
    struct.pack_into("<I", header, 48, plan.directory_start)
    struct.pack_into("<I", header, 52, 0)
    struct.pack_into("<I", header, 56, _CFB_MINI_STREAM_CUTOFF)
    struct.pack_into("<I", header, 60, plan.mini_fat_start)
    struct.pack_into("<I", header, 64, plan.mini_fat_sector_count)
    struct.pack_into("<I", header, 68, plan.difat_start)
    struct.pack_into("<I", header, 72, plan.difat_sector_count)
    for index in range(109):
        value = plan.fat_start + index if index < min(plan.fat_sector_count, 109) else _FREESECT
        struct.pack_into("<I", header, 76 + index * 4, value)
    return bytes(header)


def _directory_sector(plan: _CompoundFilePlan) -> bytes:
    directory = bytearray(_CFB_SECTOR_SIZE)
    root_start = plan.native_sector_count if plan.use_mini_stream else _ENDOFCHAIN
    root_size = plan.mini_sector_count * _CFB_MINI_SECTOR_SIZE if plan.use_mini_stream else 0
    directory[0:128] = _directory_entry(
        "Root Entry",
        object_type=5,
        child=1,
        clsid=_PACKAGE_CLSID,
        start_sector=root_start,
        stream_size=root_size,
    )
    directory[128:256] = _directory_entry(
        "\x01Ole10Native",
        object_type=2,
        start_sector=0,
        stream_size=plan.native_size,
    )
    directory[256:384] = _directory_entry("", object_type=0)
    directory[384:512] = _directory_entry("", object_type=0)
    return bytes(directory)


def _directory_entry(
    name: str,
    *,
    object_type: int,
    child: int = _NOSTREAM,
    clsid: uuid.UUID | None = None,
    start_sector: int = _ENDOFCHAIN,
    stream_size: int = 0,
) -> bytes:
    entry = bytearray(128)
    if name:
        encoded_name = name.encode("utf-16le") + b"\x00\x00"
        if len(encoded_name) > 64:
            raise ValueError("Compound file directory name is too long")
        entry[: len(encoded_name)] = encoded_name
        struct.pack_into("<H", entry, 64, len(encoded_name))
    entry[66] = object_type
    entry[67] = 1
    struct.pack_into("<III", entry, 68, _NOSTREAM, _NOSTREAM, child)
    if clsid is not None:
        entry[80:96] = clsid.bytes_le
    struct.pack_into("<I", entry, 116, start_sector)
    struct.pack_into("<Q", entry, 120, stream_size)
    return bytes(entry)


def _write_mini_fat(target: BinaryIO, plan: _CompoundFilePlan) -> None:
    for entry_index in range(plan.mini_fat_sector_count * 128):
        if entry_index < plan.mini_sector_count:
            value = entry_index + 1 if entry_index + 1 < plan.mini_sector_count else _ENDOFCHAIN
        else:
            value = _FREESECT
        target.write(struct.pack("<I", value))


def _write_difat(target: BinaryIO, plan: _CompoundFilePlan) -> None:
    remaining_fat_sector_ids = list(
        range(plan.fat_start + 109, plan.fat_start + plan.fat_sector_count)
    )
    for difat_index in range(plan.difat_sector_count):
        offset = difat_index * 127
        values = remaining_fat_sector_ids[offset : offset + 127]
        values.extend([_FREESECT] * (127 - len(values)))
        next_sector = (
            plan.difat_start + difat_index + 1
            if difat_index + 1 < plan.difat_sector_count
            else _ENDOFCHAIN
        )
        target.write(struct.pack("<127I", *values))
        target.write(struct.pack("<I", next_sector))


def _write_fat(target: BinaryIO, plan: _CompoundFilePlan) -> None:
    entry_count = plan.fat_sector_count * 128
    entries_per_write = 4096
    for start in range(0, entry_count, entries_per_write):
        stop = min(start + entries_per_write, entry_count)
        values = [_fat_value(plan, sector_id) for sector_id in range(start, stop)]
        target.write(struct.pack(f"<{len(values)}I", *values))


def _fat_value(plan: _CompoundFilePlan, sector_id: int) -> int:
    if sector_id >= plan.total_sector_count:
        return _FREESECT
    if not plan.use_mini_stream and sector_id < plan.native_sector_count:
        return sector_id + 1 if sector_id + 1 < plan.native_sector_count else _ENDOFCHAIN
    root_mini_start = plan.native_sector_count
    if root_mini_start <= sector_id < root_mini_start + plan.root_mini_sector_count:
        return (
            sector_id + 1
            if sector_id + 1 < root_mini_start + plan.root_mini_sector_count
            else _ENDOFCHAIN
        )
    if sector_id == plan.directory_start:
        return _ENDOFCHAIN
    if plan.mini_fat_sector_count and (
        plan.mini_fat_start <= sector_id < plan.mini_fat_start + plan.mini_fat_sector_count
    ):
        return (
            sector_id + 1
            if sector_id + 1 < plan.mini_fat_start + plan.mini_fat_sector_count
            else _ENDOFCHAIN
        )
    if plan.difat_sector_count and plan.difat_start <= sector_id < plan.fat_start:
        return _DIFSECT
    if plan.fat_start <= sector_id < plan.fat_start + plan.fat_sector_count:
        return _FATSECT
    return _FREESECT


def _temporary_output_path(destination_path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=destination_path.parent,
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return Path(name)


def _atomic_copy(source_path: Path, destination_path: Path) -> None:
    temporary_path = _temporary_output_path(destination_path)
    try:
        with source_path.open("rb") as source, temporary_path.open("wb") as target:
            shutil.copyfileobj(source, target, length=_COPY_CHUNK_SIZE)
        os.replace(temporary_path, destination_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
