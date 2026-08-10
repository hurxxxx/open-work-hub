"""IMDS PDF 파싱 + 아이콘 색상 기반 분류.

레거시 ``imds_responsible_minerals.py`` 의 파싱 로직을 그대로 옮기되, 파일 경로 대신
업로드된 바이트 스트림을 입력으로 받는다. 외부 상태나 디스크 임시 파일 없이 동작한다.

분류 (IMDS 아이콘 색상):
    RED 팔각형  = 부품 (component)
    YELLOW 공   = 제품 (product)
    GREEN 잎    = 재료 (material)
    BLUE 다이아 = 화학물질 (chemical)
"""

from __future__ import annotations

import colorsys
import io
import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import numpy as np
import pdfplumber
from PIL import Image

CAS = re.compile(r"^\d{2,7}-\d{1,2}-\d$")

# 책임광물 22종 - CAS 매핑 (pure + 일반 화합물)
CAS_TO_MINERAL: dict[str, str] = {
    "7440-25-7": "탄탈럼",
    "7440-31-5": "주석",
    "7440-57-5": "금",
    "7440-33-7": "텅스텐",
    "7440-48-4": "코발트",
    "21041-93-0": "코발트",
    "7440-50-8": "구리",
    "1317-38-0": "구리",
    "1317-39-1": "구리",
    "147-14-8": "구리",
    "68186-91-4": "구리",
    "7782-42-5": "흑연",
    "7620-77-1": "리튬",
    "12001-26-2": "운모",
    "7440-02-0": "니켈",
    "11099-02-8": "니켈",
    "1313-99-1": "니켈",
    "10101-97-0": "니켈",
    "7440-06-4": "백금",
    "7440-05-3": "팔라듐",
    "7440-16-6": "로듐",
    "7439-89-6": "철광석",
    "1309-37-1": "철광석",
    "1310-43-6": "철광석",
    "7429-90-5": "알루미늄",
    "1344-28-1": "알루미늄",
    "21645-51-2": "알루미늄",
    "13939-25-8": "알루미늄",
    "7440-66-6": "아연",
    "1314-13-2": "아연",
    "20427-58-1": "아연",
    "138265-88-0": "아연",
    "61617-00-3": "아연",
    "7439-96-5": "망간",
    "1313-13-9": "망간",
    "1317-35-7": "망간",
    "7440-47-3": "크롬",
    "1308-14-1": "크롬",
    "1308-38-9": "크롬",
    "13548-38-4": "크롬",
    "7789-02-8": "크롬",
    "59178-46-0": "크롬",
    "117527-94-3": "크롬",
    "7440-32-6": "티타늄",
    "13463-67-7": "티타늄",
    "12047-27-7": "티타늄",
    "12626-81-2": "티타늄",
    "7440-18-8": "루테늄",
    "12036-10-1": "루테늄",
    "7440-04-2": "오스뮴",
    "7439-88-5": "이리듐",
}
NAME_TO_MINERAL: dict[str, str] = {
    "Tantalum": "탄탈럼",
    "Tin": "주석",
    "Gold": "금",
    "Tungsten": "텅스텐",
    "Cobalt": "코발트",
    "Copper": "구리",
    "Graphite": "흑연",
    "Lithium": "리튬",
    "Nickel": "니켈",
    "Platinum": "백금",
    "Palladium": "팔라듐",
    "Rhodium": "로듐",
    "Iron": "철광석",
    "Aluminium": "알루미늄",
    "Aluminium (metal)": "알루미늄",
    "Zinc": "아연",
    "Zinc (metal)": "아연",
    "Manganese": "망간",
    "Chromium": "크롬",
    "Titanium": "티타늄",
    "Ruthenium": "루테늄",
    "Osmium": "오스뮴",
    "Iridium": "이리듐",
    "Mica-group minerals": "운모",
}
COLOR_TYPE = {"RED": "component", "YELLOW": "product", "GREEN": "material", "BLUE": "chemical"}


class ImdsParseError(Exception):
    """IMDS PDF 를 인식하지 못했을 때 발생한다."""


@dataclass
class ParsedImds:
    """파싱 결과. ``rows`` 는 IMDS 트리 행, ``relevant`` 는 책임광물 가지 인덱스."""

    rows: list[dict] = field(default_factory=list)
    relevant: list[int] = field(default_factory=list)


def get_mineral(row: dict) -> str | None:
    if row["code"] in CAS_TO_MINERAL:
        return CAS_TO_MINERAL[row["code"]]
    if row["name"].strip() in NAME_TO_MINERAL:
        return NAME_TO_MINERAL[row["name"].strip()]
    return None


def classify_icon_color(doc, xref: int, cache: dict) -> str | None:
    """아이콘 이미지 xref → 색상 라벨 (HSV 기반)."""
    if xref in cache:
        return cache[xref]
    label = None
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha < 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        if not (5 <= pix.width <= 20 and 5 <= pix.height <= 20):
            cache[xref] = None
            return None
        pil = Image.open(io.BytesIO(pix.tobytes("ppm")))
        arr = np.array(pil)
        mask = np.any(arr < 230, axis=-1)
        if mask.sum() < 5:
            cache[xref] = None
            return None
        pixels = arr[mask].astype(float)
        mx = pixels.max(axis=1)
        mn = pixels.min(axis=1)
        sat = (mx - mn) / np.maximum(mx, 1)
        colored = pixels[sat > 0.2]
        if len(colored) < 3:
            cache[xref] = None
            return None
        hues = [colorsys.rgb_to_hsv(*(p / 255.0))[0] * 360 for p in colored]
        hue = float(np.median(hues))
        if hue < 25 or hue >= 330:
            label = "RED"
        elif hue < 70:
            label = "YELLOW"
        elif hue < 170:
            label = "GREEN"
        elif hue < 280:
            label = "BLUE"
        else:
            label = "RED"
    except Exception:
        pass
    cache[xref] = label
    return label


def fallback_type(row: list, lv: int) -> str:
    """아이콘 없을 때 휴리스틱 백업 분류."""
    code = (row[2] or "").strip()
    qty = (row[4] or "").strip()
    imds = (row[3] or "").strip()
    weight = (row[5] or "").strip()
    pct = (row[6] or "").strip() if len(row) > 6 else ""
    if CAS.match(code) or code in ("-", "system"):
        return "chemical"
    if qty:
        return "component"
    if lv == 1:
        return "component"
    if imds or weight:
        return "material"
    if pct:
        return "chemical"
    return "material"


def parse_and_classify(content: bytes) -> list[dict]:
    """PDF 바이트 파싱 + 아이콘 기반 분류."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as error:  # noqa: BLE001 - PyMuPDF raises broad errors
        raise ImdsParseError(str(error)) from error
    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except Exception as error:  # noqa: BLE001 - pdfplumber raises broad errors
        doc.close()
        raise ImdsParseError(str(error)) from error

    rows: list[dict] = []
    xref_cache: dict = {}
    try:
        for pi in range(len(pdf.pages)):
            page = doc[pi]
            ppage = pdf.pages[pi]
            rot_mat = page.rotation_matrix
            # 페이지 내 모든 아이콘 (회전 적용 후 좌표)
            icons = []
            for img in page.get_images(full=True):
                xref = img[0]
                col = classify_icon_color(doc, xref, xref_cache)
                if not col:
                    continue
                for r in page.get_image_rects(xref):
                    rotated = r * rot_mat
                    icons.append(
                        ((rotated.x0 + rotated.x1) / 2, (rotated.y0 + rotated.y1) / 2, col)
                    )
            tables = ppage.find_tables()
            if not tables:
                continue
            tbl = tables[0]
            rows_data = tbl.extract()
            for ri, row in enumerate(rows_data):
                if not row or not row[0] or row[0].strip() == "트리 레벨":
                    continue
                try:
                    lv = int(row[0].strip())
                except (TypeError, ValueError):
                    continue
                if ri >= len(tbl.rows):
                    continue
                if tbl.rows[ri].cells[1] is None:
                    continue
                cx0, cy0, cx1, cy1 = tbl.rows[ri].cells[1]
                in_cell = [
                    (ix, iy, c) for (ix, iy, c) in icons if cx0 <= ix <= cx1 and cy0 <= iy <= cy1
                ]
                icon_type = None
                if in_cell:
                    in_cell.sort(key=lambda t: t[0])
                    icon_type = COLOR_TYPE.get(in_cell[0][2])
                rows.append(
                    {
                        "level": lv,
                        "name": (row[1] or "").strip().replace("\n", " "),
                        "code": (row[2] or "").strip().replace("\n", " "),
                        "imds": (row[3] or "").strip(),
                        "qty": (row[4] or "").strip(),
                        "weight": (row[5] or "").strip(),
                        "pct": (row[6] or "").strip() if len(row) > 6 else "",
                        "page": pi + 1,
                        "type": icon_type or fallback_type(row, lv),
                    }
                )
    finally:
        pdf.close()
        doc.close()
    return rows


def find_relevant(rows: list[dict]) -> list[int]:
    """책임광물 화학물질과 그 상위 가지 인덱스를 추출한다."""
    stack: list[tuple[int, int]] = []
    rel: set[int] = set()
    for i, r in enumerate(rows):
        while stack and stack[-1][0] >= r["level"]:
            stack.pop()
        if r["type"] == "chemical" and get_mineral(r):
            rel.add(i)
            for _, ai in stack:
                rel.add(ai)
        stack.append((r["level"], i))
    return sorted(rel)


def analyze(content: bytes) -> ParsedImds:
    """PDF 를 파싱하고 책임광물 가지를 추출한 결과를 돌려준다."""
    rows = parse_and_classify(content)
    if not rows:
        raise ImdsParseError("no IMDS tree rows recognized")
    return ParsedImds(rows=rows, relevant=find_relevant(rows))
