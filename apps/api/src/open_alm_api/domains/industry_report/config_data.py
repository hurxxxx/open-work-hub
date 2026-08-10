"""Static configuration for the industry-report aggregator.

Ported from the legacy Flask portal (``C:\\server\\routes\\research.py``) so the
three sources behave like the original "산업 리포트" feature:

* **Trend** — 자동차 리서치 자료. Company-tagged report files uploaded by admins.
* **Autojournal** — 오토저널 magazine issues (fliphtml5 bookcase).
* **KDI** — 경제연구 자료 (나라경제 / 경제정책자료 / 국내연구자료).
"""
from __future__ import annotations

# ── Trend (자동차 리서치 자료) ─────────────────────────────────
# Canonical company catalogue. ``code`` is the stable identifier stored on
# uploaded files; the Korean label is shown in the UI. Ported from the legacy
# ``COMPANY_MAP`` and extended with the directories that existed under
# ``static/trend`` so admins can file reports under any known maker.
# 자동 수집(KATECH 크롤)만 사용한다. 과거 관리자 업로드용 메이커 버킷
# (현대기아·테슬라 등)은 업로드 기능 제거에 따라 더 이상 노출하지 않는다.
COMPANY_MAP: dict[str, str] = {
    "KATECH": "자동차연구원",
}

# File ``source`` tags (industry_report_files.source).
UPLOAD_SOURCE = "upload"  # admin manual upload
KATECH_SOURCE = "katech"  # crawled from 자동차연구원

# ── KATECH crawler (자동차연구원 산업동향) ────────────────────
# The legacy ``www.katech.re.kr`` board currently serves an incomplete TLS
# chain. KATECH mirrors the same 산업 동향 board on this TLS-valid official
# service, with PDF attachment links embedded in the list rows.
KATECH_BASE_URL = "https://biz.katech.re.kr"
KATECH_LIST_PAGE = "/core/"
KATECH_BOARD_CID = "28"
KATECH_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}
# Backfill-friendly defaults: one run sweeps the whole board; already-imported
# posts (matched by post_key) are skipped, so steady-state runs are cheap.
KATECH_MAX_PAGES = 30
KATECH_MAX_NEW = 500
KATECH_MAX_FILE_BYTES = 50 * 1024 * 1024
KATECH_COMPANY = "KATECH"

# ── Autojournal (오토저널) ────────────────────────────────────
AJ_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://online.webbook.kr/",
}
AJ_BASE_URL = "https://online.webbook.kr/books"
AJ_BOOKCASE_URL = "https://online.webbook.kr/bookcase/hsqxe"

# Fallback issue-id generation when the bookcase scrape returns nothing.
AJ_BASE_YEAR = 2026
AJ_BASE_VOL = 48

# Issue ids are user-supplied path components; validate before fetching.
AJ_ISSUE_ID_RE = r"^[a-zA-Z0-9_-]{2,20}$"

# ── KDI (경제연구 자료) ───────────────────────────────────────
KDI_BASE = "https://eiec.kdi.re.kr"
KDI_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://eiec.kdi.re.kr/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
KDI_KEYWORDS: list[str] = ["자동차", "모빌리티"]
NARA_FCODE = "00002000040000100001"

# How many recent months of 나라경제 to sweep on a full collection.
KDI_NARA_MONTHS = 6

# ── Crawled item sources ──────────────────────────────────────
# Every row in ``industry_report_items`` carries one of these ``source`` tags.
AUTOJOURNAL_SOURCE = "autojournal"
KDI_NARA_SOURCE = "kdi_nara"
KDI_MATERIAL_SOURCE = "kdi_material"
KDI_DOMESTIC_SOURCE = "kdi_domestic"

ITEM_SOURCES: tuple[str, str, str, str] = (
    AUTOJOURNAL_SOURCE,
    KDI_NARA_SOURCE,
    KDI_MATERIAL_SOURCE,
    KDI_DOMESTIC_SOURCE,
)

# Maps the public ``/kdi/{source}`` path segment to the stored source tag.
KDI_PATH_TO_SOURCE: dict[str, str] = {
    "nara": KDI_NARA_SOURCE,
    "material": KDI_MATERIAL_SOURCE,
    "domestic": KDI_DOMESTIC_SOURCE,
}
