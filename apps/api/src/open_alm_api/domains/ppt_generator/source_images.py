"""PPT 자동 생성 — 첨부 파일에서 사진 추출 + 비고칸 '텍스트 근접' 매칭.

업로드된 PDF/PPTX 에서 의미있는 이미지(로고·아이콘 같은 소형 장식은 크기로 제외)를
추출하고, 각 이미지가 있던 **페이지/슬라이드의 텍스트**를 함께 담는다. 사내엔 비전 모델이
없으므로(Qwen 텍스트 전용·Claude 은 주제 100자만), 이미지 '내용'을 이해하는 대신 그 이미지
주변 텍스트를 보고칸(사진 자리)의 주제·내용 텍스트와 키워드로 대조해 가장 맞는 칸에 배치한다.

보안: 추출·매칭·임베드는 전부 서버 내부에서만 수행한다(외부 전송 없음).
"""

from __future__ import annotations

import base64
import io
import os
import re
import time
import zipfile

from open_alm_api.domains.document_processing.pptx import archive_exceeds_limits

_MIN_W = 80          # 이 미만(가로/세로)이면 로고·아이콘으로 보고 제외
_MIN_H = 80
_MAX_EMBED_W = 720   # 임베드(data URI) 시 가로 상한 — 덱 HTML 비대화 억제
_MAX_IMAGES = 12     # 한 작업에서 다룰 최대 이미지 수
_MAX_PDF_PAGES = 80
_MAX_PDF_EXTRACT_SECONDS = 10.0
_MAX_IMAGE_PIXELS = 16_000_000

# PPT→PDF 로 평탄화돼 get_images() 로는 안 잡히는 '벡터 도식'을 캡션 기준으로 렌더링하기 위한 설정.
_FIG_CAPTION = re.compile(r"(그\s*림|figure|fig\.?)\s*\d", re.I)
_FIG_BAND_PT = 340.0      # 캡션 위로 도식을 탐색하는 최대 높이(pt)
_FIG_RENDER_SCALE = 2.2   # 도식 클립 렌더 배율(선명도)


# ── 추출 ──────────────────────────────────────────────────────
def _pil_dims(data: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return None


def _extract_pdf_images(data: bytes) -> list[dict]:
    out: list[dict] = []
    try:
        import fitz
    except Exception:
        return out
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return out
    started_at = time.monotonic()
    try:
        for pno in range(min(doc.page_count, _MAX_PDF_PAGES)):
            if time.monotonic() - started_at > _MAX_PDF_EXTRACT_SECONDS:
                break
            try:
                page = doc.load_page(pno)
                ptext = page.get_text("text") or ""
            except Exception:
                continue
            seen: set[int] = set()
            for img in page.get_images(full=True):
                if time.monotonic() - started_at > _MAX_PDF_EXTRACT_SECONDS:
                    return out
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    raw_w = int(img[2]) if len(img) > 2 else 0
                    raw_h = int(img[3]) if len(img) > 3 else 0
                    if raw_w * raw_h > _MAX_IMAGE_PIXELS:
                        continue
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha >= 4:  # CMYK 등 → RGB 변환
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    if pix.width * pix.height > _MAX_IMAGE_PIXELS:
                        pix = None
                        continue
                    if pix.width < _MIN_W or pix.height < _MIN_H:
                        pix = None
                        continue
                    png = pix.tobytes("png")
                    w, h = pix.width, pix.height
                    pix = None
                    out.append({"data": png, "ext": "png", "w": w, "h": h, "text": ptext})
                except Exception:
                    continue
                if len(out) >= _MAX_IMAGES:
                    return out
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return out


def _extract_pdf_figures(data: bytes) -> list[dict]:
    """임베드 래스터가 없는 PDF에서 '그림 N' 캡션 위의 벡터 도식 영역을 렌더해 이미지화.

    PPT→PDF 로 내보내며 도식이 벡터로 평탄화되면 ``get_images()`` 로는 한 장도 안 잡힌다.
    이런 자료는 캡션('그림 N'/'Figure N')이 붙은 페이지만 골라, 캡션 바로 위의 도식 사각형
    합집합을 잘라 PNG 로 렌더한다(본문 단락은 제외, 오검출 최소화). 외부 전송 없음.
    """
    out: list[dict] = []
    try:
        import fitz
    except Exception:
        return out
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return out
    started_at = time.monotonic()
    try:
        for pno in range(min(doc.page_count, _MAX_PDF_PAGES)):
            if time.monotonic() - started_at > _MAX_PDF_EXTRACT_SECONDS:
                break
            try:
                page = doc.load_page(pno)
                blocks = page.get_text("dict").get("blocks", [])
                ptext = page.get_text("text") or ""
            except Exception:
                continue
            # 캡션 라인의 상단 y 찾기(페이지당 첫 캡션만)
            cap_top = None
            for b in blocks:
                for ln in b.get("lines", []):
                    t = "".join(sp.get("text", "") for sp in ln.get("spans", []))
                    if _FIG_CAPTION.search(t):
                        cap_top = ln["bbox"][1]
                        break
                if cap_top is not None:
                    break
            if cap_top is None:
                continue
            # 캡션 위 밴드(_FIG_BAND_PT) 안의 도식 사각형 합집합
            rects = []
            for dr in page.get_drawings():
                r = fitz.Rect(dr["rect"])
                if (r.y1 < cap_top + 2 and r.y1 > cap_top - _FIG_BAND_PT
                        and r.width > 15 and r.height > 8):
                    rects.append(r)
            if not rects:
                continue
            union = rects[0]
            for r in rects[1:]:
                union |= r
            pr = page.rect
            max_h = pr.height * 0.55  # 페이지 절반 이상은 안 자름(본문 침범 방지)
            clip = fitz.Rect(
                max(pr.x0 + 18, union.x0 - 6),
                max(pr.y0, union.y0 - 6, cap_top - max_h),
                min(pr.x1 - 18, union.x1 + 6),
                min(cap_top - 2, union.y1 + 6),
            )
            if clip.width < 120 or clip.height < 60:
                continue
            try:
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(_FIG_RENDER_SCALE, _FIG_RENDER_SCALE), clip=clip
                )
                if pix.width * pix.height > _MAX_IMAGE_PIXELS:
                    continue
                png = pix.tobytes("png")
                out.append({"data": png, "ext": "png", "w": pix.width,
                            "h": pix.height, "text": ptext})
            except Exception:
                continue
            if len(out) >= _MAX_IMAGES:
                break
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return out


def _extract_pptx_images(data: bytes) -> list[dict]:
    out: list[dict] = []
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
    except Exception:
        return out
    # zip 폭탄 방어: python-pptx 로 펼치기 전에 목차(infolist)만 보고 한도를 확인한다.
    # 텍스트 추출기와 동일한 상한을 공유한다. 의심되면 사진 추출을 건너뛴다(메모리 폭증 차단).
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if archive_exceeds_limits(zf.infolist()):
                return out
    except Exception:
        return out
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception:
        return out

    for slide in prs.slides:
        texts: list[str] = []
        for shp in slide.shapes:
            try:
                if shp.has_text_frame and shp.text_frame.text.strip():
                    texts.append(shp.text_frame.text.strip())
            except Exception:
                continue
        stext = "\n".join(texts)

        def _walk(shapes):
            for shp in shapes:
                try:
                    if shp.shape_type == MSO_SHAPE_TYPE.GROUP:
                        _walk(shp.shapes)
                        continue
                except Exception:
                    pass
                try:
                    image = shp.image  # PICTURE 가 아니면 ValueError
                except Exception:
                    continue
                try:
                    blob = image.blob
                    dims = _pil_dims(blob)
                    if not dims or dims[0] < _MIN_W or dims[1] < _MIN_H:
                        continue
                    out.append({"data": blob, "ext": (image.ext or "png").lower(),
                                "w": dims[0], "h": dims[1], "text": stext})
                except Exception:
                    continue

        _walk(slide.shapes)
        if len(out) >= _MAX_IMAGES:
            break
    return out[:_MAX_IMAGES]


_XL_NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}


def _col_to_num(ref: str) -> int:
    """'B3' → 2 (열 번호, 1-indexed). 숫자 없는 글자만 사용."""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    import xml.etree.ElementTree as ET

    out: list[str] = []
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except Exception:
        return out
    for si in root.findall("main:si", _XL_NS):
        out.append("".join(t.text or "" for t in si.iter(f'{{{_XL_NS["main"]}}}t')))
    return out


def _xlsx_sheet_cells(zf: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> dict:
    """sheet xml → {(row, col): 셀 문자열}. col/row 는 1-indexed."""
    import xml.etree.ElementTree as ET

    cells: dict[tuple[int, int], str] = {}
    try:
        root = ET.fromstring(zf.read(sheet_path))
    except Exception:
        return cells
    for c in root.iter(f'{{{_XL_NS["main"]}}}c'):
        ref = c.get("r") or ""
        if not ref:
            continue
        row = int("".join(ch for ch in ref if ch.isdigit()) or 0)
        col = _col_to_num(ref)
        v = c.find("main:v", _XL_NS)
        is_el = c.find("main:is", _XL_NS)
        txt = ""
        if c.get("t") == "s" and v is not None and v.text and v.text.isdigit():
            idx = int(v.text)
            txt = shared[idx] if 0 <= idx < len(shared) else ""
        elif is_el is not None:
            txt = "".join(t.text or "" for t in is_el.iter(f'{{{_XL_NS["main"]}}}t'))
        elif v is not None and v.text:
            txt = v.text
        if txt and txt.strip():
            cells[(row, col)] = txt.strip()
    return cells


def _xlsx_rels(zf: zipfile.ZipFile, rels_path: str) -> dict:
    """rels xml → {Id: 정규화된 target 경로}."""
    import posixpath
    import xml.etree.ElementTree as ET

    out: dict[str, str] = {}
    try:
        root = ET.fromstring(zf.read(rels_path))
    except Exception:
        return out
    base = posixpath.dirname(posixpath.dirname(rels_path))  # _rels 의 부모
    for rel in root:
        rid = rel.get("Id")
        tgt = rel.get("Target") or ""
        if not rid or not tgt:
            continue
        out[rid] = posixpath.normpath(posixpath.join(base, tgt))
    return out


def _extract_xlsx_images(data: bytes) -> list[dict]:
    """.xlsx 임베드 이미지(xl/media)를 추출하고, drawing 앵커 주변 셀 텍스트를 함께 담는다.

    매칭용 text 는 사진이 앵커된 셀 부근(±행) 캡션 텍스트를 우선 사용하고, 못 찾으면 빈 문자열.
    앵커 해석에 실패해도 xl/media 의 이미지는 그대로 추출한다(매칭은 폴백 배정으로 처리).
    """
    import posixpath
    import xml.etree.ElementTree as ET

    out: list[dict] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return out
    with zf:
        try:
            if archive_exceeds_limits(zf.infolist()):
                return out
        except Exception:
            return out
        names = set(zf.namelist())

        # media → 캡션 텍스트 매핑(베스트 에포트). 실패하면 빈 dict.
        media_text: dict[str, str] = {}
        try:
            shared = _xlsx_shared_strings(zf)
            # sheet → drawing 매핑
            for sheet_path in [n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]:
                base = posixpath.basename(sheet_path)
                srels = f"xl/worksheets/_rels/{base}.rels"
                if srels not in names:
                    continue
                drawings = [t for t in _xlsx_rels(zf, srels).values() if "/drawings/" in t]
                if not drawings:
                    continue
                cells = _xlsx_sheet_cells(zf, sheet_path, shared)
                for draw_path in drawings:
                    if draw_path not in names:
                        continue
                    drels = (
                        f"{posixpath.dirname(draw_path)}/_rels/"
                        f"{posixpath.basename(draw_path)}.rels"
                    )
                    rid_to_media = _xlsx_rels(zf, drels) if drels in names else {}
                    try:
                        droot = ET.fromstring(zf.read(draw_path))
                    except Exception:
                        continue
                    for anc in list(droot):
                        frm = anc.find("xdr:from", _XL_NS)
                        blip = anc.find(".//a:blip", _XL_NS)
                        if frm is None or blip is None:
                            continue
                        rid = blip.get(f'{{{_XL_NS["r"]}}}embed')
                        media = rid_to_media.get(rid)
                        if not media:
                            continue
                        try:
                            fc = int(frm.findtext("xdr:col", "0", _XL_NS)) + 1
                            fr = int(frm.findtext("xdr:row", "0", _XL_NS)) + 1
                        except Exception:
                            fc, fr = 1, 1
                        # 앵커 셀 부근(위아래 ±4행, 좌우 ±4열)의 텍스트를 캡션으로 모은다.
                        near = [
                            t for (rr, cc), t in cells.items()
                            if fr - 4 <= rr <= fr + 6 and fc - 4 <= cc <= fc + 6
                        ]
                        if near:
                            media_text.setdefault(media, " ".join(near[:8]))
        except Exception:
            media_text = {}

        for name in sorted(n for n in names if n.startswith("xl/media/")):
            if os.path.splitext(name)[1].lower() not in _IMG_EXTS:
                continue
            try:
                blob = zf.read(name)
            except Exception:
                continue
            dims = _pil_dims(blob)
            if not dims or dims[0] < _MIN_W or dims[1] < _MIN_H:
                continue
            if dims[0] * dims[1] > _MAX_IMAGE_PIXELS:
                continue
            out.append({
                "data": blob,
                "ext": (os.path.splitext(name)[1].lstrip(".") or "png").lower(),
                "w": dims[0],
                "h": dims[1],
                "text": media_text.get(name, ""),
            })
            if len(out) >= _MAX_IMAGES:
                break
    return out[:_MAX_IMAGES]


# ── 스프레드시트 시트 → 이미지 렌더(A: 복잡한 표를 원본 그대로 슬라이드에 삽입) ─────
_SCHED_EXTS = {".xlsx", ".xlsm", ".xls"}
_MAX_SCHEDULE_IMAGES = 3       # 한 작업에서 삽입할 최대 일정표 이미지(작업시트 남발 방지)
_SCHEDULE_RENDER_SCALE = 2.0   # PDF→PNG 렌더 배율(선명도)
_SCHED_MIN_PAGE_TOKENS = 8     # 이 미만 토큰의 페이지는 빈 스필오버로 보고 제외
_SOFFICE_TIMEOUT = 90.0        # LibreOffice 변환 1건 상한(초)
# 이 렌더는 POST /generate 요청 스레드에서 동기로 돈다(job 생성 전). 사용자가 job id 를 받기 전
# HTTP 타임아웃을 맞거나 API 스레드풀이 오래 점유되지 않도록 **전체 벽시계 예산**을 둔다. 예산을
# 넘기면 남은 시트/파일 렌더를 건너뛰고 지금까지의 결과만 반환(degrade) — 일정표 똑딱이만 일부/
# 생략되고 덱 생성 자체는 정상 진행된다.
_SCHED_TOTAL_BUDGET = 40.0     # 일정표 렌더 전체 예산(초)
_SCHED_MIN_CONV_BUDGET = 6.0   # 남은 예산이 이 미만이면 새 변환을 시작하지 않음(콜드스타트 여유)
_SOFFICE_NAMES = ("soffice", "soffice.bin", "libreoffice")
_SOFFICE_ABS_PATHS = (
    # Windows
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    # Linux (배포판/스냅/직접설치)
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/snap/bin/libreoffice",
    "/opt/libreoffice/program/soffice",
    # macOS
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def _find_soffice() -> str | None:
    """LibreOffice 실행 파일 경로 해석. env(OPEN_ALM_PPT_SOFFICE) → PATH → 알려진 설치 경로."""
    import shutil

    env = os.environ.get("OPEN_ALM_PPT_SOFFICE") or os.environ.get("OPEN_ALM_SOFFICE")
    if env and os.path.exists(env):
        return env
    for name in _SOFFICE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for path in _SOFFICE_ABS_PATHS:
        if os.path.exists(path):
            return path
    return None


def _kill_process_tree(proc) -> None:
    """soffice 런처가 fork/re-exec 한 soffice.bin 자식까지 정리(타임아웃 시 고아 방지).

    POSIX: 새 세션으로 띄웠으므로 프로세스 그룹째 SIGKILL. Windows: taskkill /T 로 트리 종료.
    """
    import signal
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            subprocess.run(  # noqa: S603,S607
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
    except Exception:
        pass
    finally:
        # kill 후 파이프를 드레인하며 프로세스를 reap 한다(파일 디스크립터 누수 방지).
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass


def _office_to_pdf(
    soffice: str, data: bytes, ext: str, *, timeout: float = _SOFFICE_TIMEOUT
) -> bytes | None:
    """스프레드시트 바이트 → PDF 바이트. LibreOffice headless 변환(전 서식·도형 보존).

    실행 중인 LibreOffice 인스턴스와 충돌하지 않도록 격리된 UserInstallation 프로필을 쓴다.
    """
    import subprocess
    import sys
    import tempfile

    # ignore_cleanup_errors: 타임아웃 후 kill 된 soffice.bin 자식이 Windows 에서 프로필 디렉터리
    # 핸들을 잠깐 붙들고 있어도 __exit__ 의 rmtree 가 예외를 던져 배치 전체를 중단하지 않도록.
    with tempfile.TemporaryDirectory(prefix="ppt-sched-", ignore_cleanup_errors=True) as tmp:
        src = os.path.join(tmp, f"in{ext if ext.startswith('.') else '.' + ext}")
        with open(src, "wb") as f:
            f.write(data)
        profile = os.path.join(tmp, "profile")
        # file:// URI(POSIX 슬래시) — Windows 경로도 슬래시로 정규화.
        profile_uri = "file:///" + profile.replace("\\", "/").lstrip("/")
        cmd = [
            soffice,
            f"-env:UserInstallation={profile_uri}",
            "--headless",
            "--calc",
            "--convert-to",
            "pdf",
            "--outdir",
            tmp,
            src,
        ]
        # run() 은 타임아웃 시 런처만 죽이고 fork 된 soffice.bin 은 고아로 남으므로,
        # 새 프로세스 그룹으로 띄운 뒤 타임아웃에 트리째 정리한다.
        popen_kwargs: dict = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(  # noqa: S603 — 고정 인자, 사용자 입력은 파일 경로뿐
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_kwargs,
            )
        except Exception:
            return None
        try:
            proc.communicate(timeout=max(1.0, timeout))
        except Exception:
            _kill_process_tree(proc)
            return None
        pdf = os.path.join(tmp, "in.pdf")
        if not os.path.exists(pdf):
            return None
        try:
            with open(pdf, "rb") as f:
                return f.read()
        except Exception:
            return None


def _sheet_render_meta(data: bytes) -> list[dict]:
    """워크북 순서대로 시트 메타 [{visible, eligible, tokens}] 반환(.xlsx/.xlsm만).

    - visible : 시트가 표시(visible) 상태인가
    - eligible: **도형(xdr:sp) 또는 화살표/연결선(xdr:cxnSp)** 이 하나라도 있는가.
      색·화살표·도형이 있어 '표로 만들기 애매한' 시트(간트/일정/도식)를 고르는 신호.
      사진만 있는 시트(xdr:pic 만)나 평범한 숫자표(도형 없음)는 eligible=False → 이미지화 제외.
      (주의: XML substring 이 아니라 element 카운트로 판정 — ``<xdr:sp`` 는 ``<xdr:spPr>`` 에도 걸림.)
    - tokens  : 셀 텍스트 토큰(PDF 페이지를 시트에 배정하는 근접매칭용)
    실패 시 빈 리스트.
    """
    import posixpath
    import xml.etree.ElementTree as ET

    out: list[dict] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return out
    with zf:
        if archive_exceeds_limits(zf.infolist()):
            return out
        names = set(zf.namelist())
        try:
            wb = ET.fromstring(zf.read("xl/workbook.xml"))
        except Exception:
            return out
        sheets_el = wb.find(f'{{{_XL_NS["main"]}}}sheets')
        if sheets_el is None:
            return out
        shared = _xlsx_shared_strings(zf)
        wbrels = _xlsx_rels(zf, "xl/_rels/workbook.xml.rels")
        for sh in sheets_el:
            state = sh.get("state") or "visible"
            spath = wbrels.get(sh.get(f'{{{_XL_NS["r"]}}}id'))
            toks: set[str] = set()
            shapes = 0
            if spath and spath in names:
                for v in _xlsx_sheet_cells(zf, spath, shared).values():
                    toks |= _tokens(v)
                base = posixpath.basename(spath)
                srels = f"xl/worksheets/_rels/{base}.rels"
                if srels in names:
                    for dp in [t for t in _xlsx_rels(zf, srels).values() if "/drawings/" in t]:
                        if dp not in names:
                            continue
                        try:
                            droot = ET.fromstring(zf.read(dp))
                        except Exception:
                            continue
                        shapes += len(droot.findall(f'.//{{{_XL_NS["xdr"]}}}sp'))
                        shapes += len(droot.findall(f'.//{{{_XL_NS["xdr"]}}}cxnSp'))
            out.append({"visible": state == "visible", "eligible": shapes >= 1, "tokens": toks})
    return out


def _force_fit_to_page(sheet_xml: str) -> str:
    """워크시트 XML 에 '한 페이지로 맞춤'(fit-to-page)을 주입 → 넓은 시트가 여러 페이지로
    쪼개지지 않고 한 장에 담긴다. pageSetUpPr fitToPage=1 + pageSetup 의 scale 제거
    (scale 과 fitTo 는 배타 — scale 이 있으면 fit 이 무시됨). fitToWidth/Height 기본값(1)을 사용."""
    import re

    if "<pageSetUpPr" in sheet_xml:
        sheet_xml = re.sub(
            r'<pageSetUpPr\b(?![^>]*\bfitToPage=)([^>]*?)/>',
            r'<pageSetUpPr\1 fitToPage="1"/>',
            sheet_xml,
            count=1,
        )
        sheet_xml = re.sub(r'fitToPage="0"', 'fitToPage="1"', sheet_xml, count=1)
    elif re.search(r"<sheetPr\b[^>]*/>", sheet_xml):
        sheet_xml = re.sub(
            r"<sheetPr\b([^>]*)/>",
            r'<sheetPr\1><pageSetUpPr fitToPage="1"/></sheetPr>',
            sheet_xml,
            count=1,
        )
    elif "<sheetPr" in sheet_xml:
        sheet_xml = re.sub(
            r"(<sheetPr\b[^>]*>)", r'\1<pageSetUpPr fitToPage="1"/>', sheet_xml, count=1
        )
    else:
        sheet_xml = re.sub(
            r"(<worksheet\b[^>]*>)",
            r'\1<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>',
            sheet_xml,
            count=1,
        )
    # scale 속성 제거(있으면 fit 무시됨).
    sheet_xml = re.sub(r'(<pageSetup\b[^>]*?)\sscale="[^"]*"', r"\1", sheet_xml, count=1)
    return sheet_xml


def _xlsx_keep_only_sheet(data: bytes, keep_index: int) -> bytes | None:
    """workbook.xml 의 ``<sheet>`` 중 keep_index(0-based 순서) 하나만 남긴 xlsx 바이트 반환.

    문자열 편집으로 workbook.xml + rels 만 손대고 나머지 파트(시트 xml·drawing·media·styles)는
    그대로 복사 → **남긴 시트의 도형/화살표가 보존**된다(openpyxl 저장은 도형을 잃어 부적합).
    전체 워크북을 PDF 로 만들면 시트 경계가 뭉개져 페이지→시트 매핑이 불안정하므로, eligible
    시트만 남겨 변환한다. definedNames 는 통째 제거(제거된 시트 참조로 인한 로드 실패 방지).
    LibreOffice 는 xlsx 를 기본적으로 재계산하지 않아 캐시 값으로 렌더되므로 값도 유지된다.
    """
    import re

    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    with zin:
        if archive_exceeds_limits(zin.infolist()):
            return None
        try:
            wbxml = zin.read("xl/workbook.xml").decode("utf-8")
            relsxml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        except Exception:
            return None
        block_m = re.search(r"<sheets>.*?</sheets>", wbxml, re.S)
        if not block_m:
            return None
        block = block_m.group(0)
        sheet_tags = re.findall(r"<sheet\b[^>]*?/>", block)
        if keep_index < 0 or keep_index >= len(sheet_tags):
            return None
        removed_rids: list[str] = []
        kept: list[str] = []
        for i, tag in enumerate(sheet_tags):
            if i == keep_index:
                kept.append(tag)
            else:
                m = re.search(r'r:id="([^"]+)"', tag)
                if m:
                    removed_rids.append(m.group(1))
        wbxml = wbxml.replace(block, "<sheets>" + "".join(kept) + "</sheets>")
        wbxml = re.sub(r"<definedNames>.*?</definedNames>", "", wbxml, flags=re.S)
        for rid in removed_rids:
            relsxml = re.sub(
                r'<Relationship\b[^>]*\bId="' + re.escape(rid) + r'"[^>]*/>', "", relsxml
            )
        # 남긴 시트의 worksheet 경로 해석 → 그 시트에 fit-to-page 주입(넓은 시트 한 장에 담기).
        import posixpath

        kept_path = None
        kept_rid_m = re.search(r'r:id="([^"]+)"', kept[0]) if kept else None
        if kept_rid_m:
            kept_rid = kept_rid_m.group(1)
            # Relationship 요소를 먼저 통째로 찾고 그 안에서 Target 을 뽑는다 — Id/Target 속성
            # 순서에 의존하지 않도록(일부 생성기는 Target 을 Id 앞에 쓴다).
            for rel in re.findall(r"<Relationship\b[^>]*?/>", relsxml):
                if f'Id="{kept_rid}"' not in rel:
                    continue
                tgt_m = re.search(r'\bTarget="([^"]+)"', rel)
                if tgt_m:
                    kept_path = posixpath.normpath(posixpath.join("xl", tgt_m.group(1)))
                break
        out = io.BytesIO()
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "xl/workbook.xml":
                        zout.writestr(item, wbxml)
                    elif item.filename == "xl/_rels/workbook.xml.rels":
                        zout.writestr(item, relsxml)
                    elif kept_path and item.filename == kept_path:
                        try:
                            sheet_xml = zin.read(item.filename).decode("utf-8")
                            zout.writestr(item, _force_fit_to_page(sheet_xml))
                        except Exception:
                            zout.writestr(item, zin.read(item.filename))
                    else:
                        zout.writestr(item, zin.read(item.filename))
        except Exception:
            return None
        return out.getvalue()


def _xlsx_archive_safe(data: bytes) -> bool:
    """업로드 .xlsx/.xlsm(zip)이 압축폭탄 한도 안에 있는지 검사(엔트리 수·해제 크기·팽창비).

    _extract_xlsx_images 와 동일한 ``archive_exceeds_limits`` 를 렌더 경로에도 적용해, 작은 압축
    파일 하나로 API 메모리/디스크를 크게 소모하는 것을 막는다. 열 수 없으면 안전하지 않다고 본다.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return not archive_exceeds_limits(zf.infolist())
    except Exception:
        return False


def render_schedule_images(
    files: list[tuple[str, bytes, str]],
    *,
    max_images: int = _MAX_SCHEDULE_IMAGES,
    total_budget_s: float = _SCHED_TOTAL_BUDGET,
) -> list[dict]:
    """첨부 스프레드시트에서 **표시 + 도형/화살표가 있는 시트**만 이미지(PNG)로 렌더.
    반환: [{data,ext,w,h,text,sheet}].

    색·화살표·도형이 있어 표로 만들기 애매한 시트(간트/일정/도식)만 골라, 그 시트만 남긴 임시
    워크북(``_xlsx_keep_only_sheet``)을 LibreOffice 로 PDF 변환 후 래스터화한다. 시트 단위로
    변환하므로 페이지↔시트 매핑 문제 없이 정확히 그 시트만 담긴다. 사진만 있는 시트(사진은 비고칸
    매칭 경로가 처리)·평범한 숫자표(텍스트로 들어감)·숨김(작업)시트는 제외. 내용이 거의 없는
    스필오버 페이지는 건너뛴다. 최대 ``max_images`` 장. LibreOffice 없으면 빈 리스트(폴백).
    렌더·판정은 전부 서버 내부에서만 수행(외부 전송 없음).
    """
    out: list[dict] = []
    if max_images <= 0:
        return out
    soffice = _find_soffice()
    if not soffice:
        return out
    try:
        import fitz
    except Exception:
        return out

    deadline = time.monotonic() + max(0.0, total_budget_s)

    for filename, content, _mime in files:
        if len(out) >= max_images:
            break
        if time.monotonic() >= deadline:
            break  # 전체 예산 초과 → 남은 파일 렌더 생략(degrade)
        if not filename or not content:
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext not in _SCHED_EXTS:
            continue
        # 압축폭탄 방지: zip 기반 포맷은 열기/시트 복사 전에 archive 한도를 검사한다.
        if ext != ".xls" and not _xlsx_archive_safe(content):
            continue
        meta = _sheet_render_meta(content) if ext != ".xls" else []
        eligible_idxs = [i for i, m in enumerate(meta) if m["visible"] and m["eligible"]]
        if meta and not eligible_idxs:
            continue  # 도형/화살표를 가진 표시 시트가 없으면 변환 자체를 건너뛴다.
        targets: list[bytes] = []
        if eligible_idxs:
            for idx in eligible_idxs[:max_images]:
                one = _xlsx_keep_only_sheet(content, idx)
                if one:
                    targets.append(one)
            # eligible 시트를 알았는데 서저리가 전부 실패한 경우: 전체 워크북을 통째로 변환하면
            # 도형/화살표 없는 무관한 시트까지 '일정표'로 삽입되므로 이 파일은 건너뛴다.
            if not targets:
                continue
        elif ext == ".xls":
            # 시트 서저리가 불가능한 레거시 .xls 만 최후수단으로 전체 변환한다.
            # (파싱 실패한 .xlsx 를 여기로 흘리면 도형 없는 무관 시트까지 통째로 삽입됨 → 제외.)
            targets = [content]
        if not targets:
            continue
        for target in targets:
            if len(out) >= max_images:
                break
            remaining = deadline - time.monotonic()
            if remaining < _SCHED_MIN_CONV_BUDGET:
                break  # 남은 예산으로 콜드스타트+변환을 마치기 어려움 → degrade
            pdf = _office_to_pdf(
                soffice, target, ext, timeout=min(_SOFFICE_TIMEOUT, remaining)
            )
            if not pdf:
                continue
            try:
                doc = fitz.open(stream=pdf, filetype="pdf")
            except Exception:
                continue
            started_at = time.monotonic()
            try:
                for page in doc:
                    if len(out) >= max_images:
                        break
                    if time.monotonic() - started_at > _MAX_PDF_EXTRACT_SECONDS * 2:
                        break
                    ptext = page.get_text("text") or ""
                    # 내용이 거의 없는 스필오버(빈) 페이지는 건너뛴다.
                    if len(_tokens(ptext)) < _SCHED_MIN_PAGE_TOKENS:
                        continue
                    try:
                        # 픽셀 캡을 넘길 배율은 '렌더 전에' 걸러 거대한 래스터를 아예 할당하지
                        # 않는다(사후 검사는 이미 수백 MB 를 잡은 뒤라 OOM 위험). page.rect 는
                        # 포인트 단위이므로 배율을 곱해 예상 픽셀 수를 추정한다.
                        pr = page.rect
                        scale = _SCHEDULE_RENDER_SCALE
                        if (pr.width * scale) * (pr.height * scale) > _MAX_IMAGE_PIXELS:
                            scale = 1.4
                        if (pr.width * scale) * (pr.height * scale) > _MAX_IMAGE_PIXELS:
                            continue
                        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                        png = pix.tobytes("png")
                        out.append({
                            "data": png,
                            "ext": "png",
                            "w": pix.width,
                            "h": pix.height,
                            "text": ptext.strip()[:600],
                            "sheet": filename,
                        })
                    except Exception:
                        continue
            finally:
                try:
                    doc.close()
                except Exception:
                    pass
    return out[:max_images]


def extract_source_images(files: list[tuple[str, bytes, str]]) -> list[dict]:
    """업로드 파일 리스트에서 사진 추출. 반환: [{data, ext, w, h, text}] (최대 _MAX_IMAGES)."""
    images: list[dict] = []
    for filename, content, _mime in files:
        if not filename or not content:
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf":
            pdf_imgs = _extract_pdf_images(content)
            # PPT→PDF 로 평탄화돼 임베드 래스터가 한 장도 없으면, '그림 N' 캡션 도식을 렌더해 보완.
            if not pdf_imgs:
                pdf_imgs = _extract_pdf_figures(content)
            images.extend(pdf_imgs)
        elif ext == ".pptx":
            images.extend(_extract_pptx_images(content))
        elif ext in (".xlsx", ".xlsm"):
            images.extend(_extract_xlsx_images(content))
        if len(images) >= _MAX_IMAGES:
            break
    return images[:_MAX_IMAGES]


# ── 매칭 ──────────────────────────────────────────────────────
_STOP = set(
    "및 등 의 를 을 이 가 은 는 에 와 과 로 으로 한 그 저 것 수 외 명 위 관련 내용 주요 "
    "the of and for to in on a an is are with".split()
)
_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}|\d{2,}")


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(s or "") if w.lower() not in _STOP}


def match_images_to_slots(slot_texts: list[str], images: list[dict]) -> list[int | None]:
    """각 사진 자리(slot)에 가장 잘 맞는 image 인덱스를 그리디로 배정(중복 없음).

    1) 키워드 교집합 점수가 가장 높은 이미지를 slot 에 배정.
    2) 점수 0 으로 미배정된 slot 은 남은 이미지를 순서대로 폴백 배정.
    반환: slot 별 image 인덱스(or None).
    """
    n_slot = len(slot_texts)
    assigned: list[int | None] = [None] * n_slot
    if not images or not n_slot:
        return assigned
    used: set[int] = set()
    img_tokens = [_tokens(im.get("text", "")) for im in images]
    slot_tokens = [_tokens(t) for t in slot_texts]

    for si in range(n_slot):
        best, best_score = None, 0
        for ii in range(len(images)):
            if ii in used:
                continue
            score = len(slot_tokens[si] & img_tokens[ii])
            if score > best_score:
                best_score, best = score, ii
        if best is not None:
            assigned[si] = best
            used.add(best)

    rem = [ii for ii in range(len(images)) if ii not in used]
    ri = 0
    for si in range(n_slot):
        if assigned[si] is None and ri < len(rem):
            assigned[si] = rem[ri]
            ri += 1
    return assigned


# ── 임베드 ────────────────────────────────────────────────────
def to_data_uri(data: bytes, *, max_w: int = _MAX_EMBED_W) -> str | None:
    """이미지 바이트 → 가로 max_w 로 다운사이즈한 JPEG data URI (덱 HTML 임베드용)."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > _MAX_IMAGE_PIXELS:
                return None
            im = im.convert("RGB")
            if im.width > max_w:
                new_h = max(1, round(im.height * max_w / im.width))
                im = im.resize((max_w, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None
