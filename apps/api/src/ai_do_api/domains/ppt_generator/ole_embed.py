"""PPT 자동 생성 — '똑딱이'(OLE 임베드) 주입 유틸.

완성된 .pptx(host) 안의 특정 슬라이드에 다른 .pptx 파일(embed)을 **OLE 개체**로 박아넣는다.
PowerPoint 에서 그 도형(아이콘)을 더블클릭하면 임베드된 .pptx 가 열린다(=속칭 '똑딱이').

python-pptx 는 OLE 임베드를 지원하지 않으므로 .pptx(zip) 의 OOXML 을 직접 편집한다:
  1) ppt/embeddings/oleObjectN.pptx     — 임베드할 파일(통째)
  2) ppt/media/imageN.png               — 아이콘(똑딱이 표면 그림)
  3) 대상 슬라이드 XML 의 spTree 에 <p:graphicFrame><a:graphic>...<p:oleObj showAsIcon="1">
  4) 슬라이드 .rels 에 package(임베드) + image(아이콘) 관계 추가
  5) [Content_Types].xml 에 png Default + 임베드 pptx Override 보강

브라우저(HTML 미리보기)에는 OLE 개념이 없어 재현되지 않는다 — 내려받은 .pptx 전용.
"""

from __future__ import annotations

import io
import logging
import re
import struct
import zipfile

logger = logging.getLogger(__name__)


def _png_size(data: bytes) -> tuple[int, int] | None:
    """PNG IHDR 에서 (width, height) 추출. PNG 가 아니면 None."""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    return None

_PRES_CT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_REL_PACKAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package"
_REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_OLE_URI = "http://schemas.openxmlformats.org/presentationml/2006/ole"

EMU_PER_CM = 360000


def _next_rel_id(rels_xml: str) -> str:
    ids = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels_xml)]
    return f"rId{(max(ids) + 1) if ids else 1}"


def _ensure_content_types(ct_xml: str, embed_partname: str) -> str:
    out = ct_xml
    # png Default
    if 'Extension="png"' not in out:
        out = out.replace(
            "</Types>",
            '<Default Extension="png" ContentType="image/png"/></Types>',
        )
    # 임베드 pptx Override
    if f'PartName="/{embed_partname}"' not in out:
        out = out.replace(
            "</Types>",
            f'<Override PartName="/{embed_partname}" ContentType="{_PRES_CT}"/></Types>',
        )
    return out


def _graphic_frame_xml(
    *, frame_id: int, name: str, x: int, y: int, cx: int, cy: int,
    ole_rid: str, icon_rid: str,
) -> str:
    """spTree 에 삽입할 graphicFrame(OLE, showAsIcon) XML 한 덩어리."""
    # imgW/imgH 는 EMU. 아이콘 표시 크기와 동일하게 둔다.
    return (
        f'<p:graphicFrame>'
        f'<p:nvGraphicFramePr>'
        f'<p:cNvPr id="{frame_id}" name="{name}"/>'
        f'<p:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></p:cNvGraphicFramePr>'
        f'<p:nvPr/>'
        f'</p:nvGraphicFramePr>'
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{_OLE_URI}">'
        f'<p:oleObj showAsIcon="1" r:id="{ole_rid}" imgW="{cx}" imgH="{cy}" '
        f'progId="PowerPoint.Show.12">'
        f'<p:embed/>'
        f'<p:pic>'
        f'<p:nvPicPr><p:cNvPr id="{frame_id + 1}" name="{name} icon"/>'
        f'<p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{icon_rid}"/>'
        f'<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'</p:pic>'
        f'</p:oleObj>'
        f'</a:graphicData></a:graphic>'
        f'</p:graphicFrame>'
    )


def embed_pptx_as_ole(
    host_bytes: bytes,
    embed_bytes: bytes,
    icon_png: bytes,
    *,
    slide_part: str = "ppt/slides/slide2.xml",
    x_emu: int,
    y_emu: int,
    w_emu: int,
    h_emu: int,
    name: str = "교육 결과 보고서",
) -> bytes:
    """host .pptx 의 slide_part 슬라이드에 embed .pptx 를 OLE(똑딱이)로 주입한 새 .pptx 바이트 반환."""
    zin = zipfile.ZipFile(io.BytesIO(host_bytes), "r")
    names = set(zin.namelist())

    # 다음 임베드/이미지 인덱스 결정(충돌 회피)
    def _next_idx(prefix: str, suffix: str) -> int:
        n = 1
        while f"{prefix}{n}{suffix}" in names:
            n += 1
        return n

    embed_idx = _next_idx("ppt/embeddings/oleObject", ".pptx")
    img_idx = _next_idx("ppt/media/image", ".png")
    embed_part = f"ppt/embeddings/oleObject{embed_idx}.pptx"
    media_part = f"ppt/media/image{img_idx}.png"

    rels_part = re.sub(r"ppt/slides/(slide\d+)\.xml", r"ppt/slides/_rels/\1.xml.rels", slide_part)

    # 슬라이드 rels 읽기(없으면 생성)
    if rels_part in names:
        rels_xml = zin.read(rels_part).decode("utf-8")
    else:
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "</Relationships>"
        )
    ole_rid = _next_rel_id(rels_xml)
    # icon rid 는 ole_rid 다음 번호
    tmp = rels_xml.replace("</Relationships>", f'<Relationship Id="{ole_rid}" Type="{_REL_PACKAGE}" Target="../embeddings/oleObject{embed_idx}.pptx"/></Relationships>')
    icon_rid = _next_rel_id(tmp)
    rels_xml = tmp.replace(
        "</Relationships>",
        f'<Relationship Id="{icon_rid}" Type="{_REL_IMAGE}" Target="../media/image{img_idx}.png"/></Relationships>',
    )

    # 슬라이드 XML 에 graphicFrame 삽입
    slide_xml = zin.read(slide_part).decode("utf-8")
    # 고유 cNvPr id — 기존 최대 +100
    existing_ids = [int(m) for m in re.findall(r'<p:cNvPr id="(\d+)"', slide_xml)]
    frame_id = (max(existing_ids) + 100) if existing_ids else 900
    gframe = _graphic_frame_xml(
        frame_id=frame_id, name=name, x=x_emu, y=y_emu, cx=w_emu, cy=h_emu,
        ole_rid=ole_rid, icon_rid=icon_rid,
    )
    if "</p:spTree>" not in slide_xml:
        zin.close()
        raise ValueError("slide xml 에 spTree 가 없습니다.")
    slide_xml = slide_xml.replace("</p:spTree>", gframe + "</p:spTree>", 1)

    # Content_Types 보강
    ct_xml = zin.read("[Content_Types].xml").decode("utf-8")
    ct_xml = _ensure_content_types(ct_xml, embed_part)

    # 새 zip 작성
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = ct_xml.encode("utf-8")
            elif item.filename == slide_part:
                data = slide_xml.encode("utf-8")
            elif item.filename == rels_part:
                data = rels_xml.encode("utf-8")
            zout.writestr(item, data)
        if rels_part not in names:
            zout.writestr(rels_part, rels_xml)
        zout.writestr(embed_part, embed_bytes)
        zout.writestr(media_part, icon_png)
    zin.close()
    return out.getvalue()


def inject_ole_into_pptx(
    pptx_bytes: bytes,
    embed_bytes: bytes,
    icon_bytes: bytes,
    *,
    slide_index: int = 1,
    name: str = "교육 결과 보고서",
) -> bytes:
    """완성된 pptx 안에서 icon_bytes 와 동일한 그림을 찾아 그 자리에 OLE(똑딱이)로 교체.

    렌더 단계에서 비고칸에 박아둔 '아이콘 그림'(icon_bytes)을 좌표 기준점으로 삼아,
    같은 위치·크기에 embed_bytes(.pptx)를 OLE 로 주입하고 원래 그림은 제거한다.
    못 찾으면 원본을 그대로 돌려준다(안전 폴백).
    """
    from pptx import Presentation

    try:
        prs = Presentation(io.BytesIO(pptx_bytes))
    except Exception:
        return pptx_bytes
    slides = list(prs.slides)
    if slide_index >= len(slides):
        return pptx_bytes
    slide = slides[slide_index]
    slide_w = int(prs.slide_width)

    target = None
    for shp in list(slide.shapes):
        try:
            if shp.shape_type == 13 and shp.image.blob == icon_bytes:  # 13 = PICTURE
                target = shp
                break
        except Exception:
            continue
    # 폴백 1: 바이트가 round-trip(브라우저 data-URI 재직렬화 등)으로 달라졌을 수 있으니
    # 아이콘 PNG 의 픽셀 크기(IHDR)가 일치하는 그림을 찾는다.
    if target is None:
        icon_size = _png_size(icon_bytes)
        if icon_size is not None:
            for shp in list(slide.shapes):
                try:
                    if shp.shape_type == 13 and _png_size(shp.image.blob) == icon_size:
                        target = shp
                        break
                except Exception:
                    continue
        if target is not None:
            logger.info("inject_ole_into_pptx: 아이콘 바이트 불일치 → 크기 매칭으로 대체")
    # 폴백 2: 비고 영역(오른쪽 ~30%) 안의 그림 중 하나
    if target is None:
        for shp in list(slide.shapes):
            try:
                if shp.shape_type == 13 and (int(shp.left) + int(shp.width) / 2) > slide_w * 0.7:
                    target = shp
                    break
            except Exception:
                continue
        if target is not None:
            logger.warning("inject_ole_into_pptx: 아이콘을 위치 휴리스틱으로 추정 — 오삽입 가능")
    if target is None:
        logger.warning(
            "inject_ole_into_pptx: 슬라이드 %d 에서 아이콘 그림을 찾지 못해 OLE 임베드를 건너뜀",
            slide_index,
        )
        return pptx_bytes

    x, y = int(target.left), int(target.top)
    cx, cy = int(target.width), int(target.height)
    slide_part = slide.part.partname.lstrip("/")
    target._element.getparent().remove(target._element)

    buf = io.BytesIO()
    prs.save(buf)
    host = buf.getvalue()
    return embed_pptx_as_ole(
        host, embed_bytes, icon_bytes,
        slide_part=slide_part, x_emu=x, y_emu=y, w_emu=cx, h_emu=cy, name=name,
    )


def make_ole_icon_png(
    label: str = "교육 결과\n보고서", *, w: int = 240, h: int = 240, idx: int = 0
) -> bytes:
    """똑딱이 표면 아이콘 — 안쪽 아이콘·라벨 없이 진한 회색 정사각형 하나만(PIL).

    label 인자는 호환을 위해 남겨두되 더 이상 그리지 않는다(사각형만 표시).
    셀에서는 0.6×0.6cm 정사각으로 표시되므로 PNG 도 정사각(왜곡 방지)으로 만든다.

    idx: 한 슬라이드에 똑딱이가 여러 개일 때, 각 아이콘 PNG 바이트를 **고유**하게 만들어
    OLE 주입 단계가 아이콘↔임베드를 정확히 1:1 매칭할 수 있게 한다(눈에 안 보이는 1픽셀 마커).
    idx=0 은 기존과 동일한 기본 아이콘(바이트 불변). idx>=1 은 안쪽 1픽셀의 파랑 채널만 idx 로
    바꿔(150,150,idx) 시각적으론 구분 불가하지만 바이트가 달라진다.
    """
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), (150, 150, 150))  # 진한 회색 채움
    d = ImageDraw.Draw(im)
    d.rectangle([1, 1, w - 2, h - 2], outline=(100, 100, 100), width=2)
    if idx > 0:
        im.putpixel((w - 3, h - 3), (150, 150, max(1, min(255, idx))))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def inject_multiple_ole_into_pptx(
    pptx_bytes: bytes,
    items: list[dict],
    *,
    slide_index: int = 1,
) -> bytes:
    """한 슬라이드의 여러 아이콘 그림을 각자의 임베드 .pptx 로 OLE 교체(다중 똑딱이).

    items[i] = {"icon_bytes": bytes, "embed_bytes": bytes, "name": str}. 각 icon_bytes 는
    make_ole_icon_png(idx=...) 로 만든 **고유** PNG 여야 정확히 매칭된다.

    안전성: python-pptx 는 OLE(graphicFrame/oleObject)를 모델링하지 못해, 이미 주입된 pptx 를
    다시 open→save 하면 그 파트가 유실될 수 있다. 그래서 ① python-pptx 로 **모든 아이콘 그림을
    한 번에** 찾아 제거(위치 기록) → ② 순수 zip 편집인 embed_pptx_as_ole 를 **체이닝**(open/save
    없음)해 임베드를 누적 주입한다. 매칭 실패한 아이콘은 건너뛴다(다른 것은 계속). 전부 실패하면 원본.
    """
    from pptx import Presentation

    if not items:
        return pptx_bytes
    try:
        prs = Presentation(io.BytesIO(pptx_bytes))
    except Exception:
        return pptx_bytes
    slides = list(prs.slides)
    if slide_index >= len(slides):
        return pptx_bytes
    slide = slides[slide_index]
    slide_part = slide.part.partname.lstrip("/")

    # 1) 모든 아이콘을 exact-byte 매칭으로 찾아 위치 기록 후 제거 (python-pptx 한 번만)
    matched: list[dict] = []
    for item in items:
        icon = item.get("icon_bytes")
        if not icon:
            continue
        name_tag = item.get("name_tag")
        target = None
        # 1순위: shape 이름(builders_house 가 add_picture 시 'ole-icon-{idx}' 로 표식) 매칭 —
        # python-pptx round-trip 이 PNG 바이트를 재인코딩해도 견고하다.
        if name_tag:
            for shp in list(slide.shapes):
                try:
                    if shp.shape_type == 13 and shp.name == name_tag:  # 13 = PICTURE
                        target = shp
                        break
                except Exception:
                    continue
        # 폴백: exact-byte 매칭(이름 표식이 없는 옛 경로 호환).
        if target is None:
            for shp in list(slide.shapes):
                try:
                    if shp.shape_type == 13 and shp.image.blob == icon:  # 13 = PICTURE
                        target = shp
                        break
                except Exception:
                    continue
        if target is None:
            logger.warning("inject_multiple_ole: 아이콘(%s) 매칭 실패 — 건너뜀", item.get("name"))
            continue
        matched.append(
            {
                "icon_bytes": icon,
                "embed_bytes": item.get("embed_bytes"),
                "name": item.get("name") or "상세 보기",
                "x": int(target.left),
                "y": int(target.top),
                "cx": int(target.width),
                "cy": int(target.height),
            }
        )
        target._element.getparent().remove(target._element)

    if not matched:
        return pptx_bytes

    buf = io.BytesIO()
    prs.save(buf)
    host = buf.getvalue()

    # 2) 순수 zip 편집 체이닝으로 임베드 누적(중간에 python-pptx round-trip 없음)
    for m in matched:
        if not m["embed_bytes"]:
            continue
        host = embed_pptx_as_ole(
            host,
            m["embed_bytes"],
            m["icon_bytes"],
            slide_part=slide_part,
            x_emu=m["x"],
            y_emu=m["y"],
            w_emu=m["cx"],
            h_emu=m["cy"],
            name=m["name"],
        )
    return host
