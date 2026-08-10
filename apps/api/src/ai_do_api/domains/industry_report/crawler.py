"""Industry-report collection and parsing.

A faithful port of the legacy Flask portal's ``routes/research.py`` collection
logic for the Autojournal (오토저널) and KDI (경제연구 자료) sources, adapted to
``httpx``. The Trend source is admin-uploaded (see ``service``/``storage``), not
crawled, so it has no logic here.

Functions are stateless (no DB, no module-level cache): collectors return plain
item dicts shaped for ``service.upsert_items``. Pure parsing helpers (those that
take markup/text and return data) are split out from the network calls so they
can be unit-tested offline.

Item dict shape (matches ``IndustryReportItem`` columns)::

    {"source", "keyword", "title", "org", "summary", "url", "published_date", "extra"}
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import config_data as cfg
from .storage import has_pdf_signature

logger = logging.getLogger(__name__)


def is_kdi_url(url: str) -> bool:
    """True only when ``url``'s host is KDI's domain.

    A substring check (``"eiec.kdi.re.kr" in url``) is unsafe — e.g.
    ``http://attacker/?x=eiec.kdi.re.kr`` passes it — so validate the parsed
    hostname to keep the KDI fetchers from being turned into an SSRF gadget.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "eiec.kdi.re.kr" or host.endswith(".eiec.kdi.re.kr")


# ╔══════════════════════════════════════════════════════════════╗
# ║  KATECH (자동차연구원 산업분석) — Trend auto-crawl            ║
# ╚══════════════════════════════════════════════════════════════╝

def _squash_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_pdf_download(anchor) -> bool:
    href = (anchor.get("href", "") or "").lower()
    text = _squash_text(anchor.get_text(" ", strip=True)).lower()
    file_param = parse_qs(urlparse(href).query).get("file", [""])[0].lower()
    return ".pdf" in href or text.endswith(".pdf") or file_param.endswith(".pdf")


def parse_katech_list(html: str) -> list[dict]:
    """Parse the KATECH board list page (pure).

    Returns ``{post_key, no, title, date}`` rows, skipping notices and headers.
    The current official board also includes ``download_path`` and ``filename``
    in each list row, so those are returned when present.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.find("table")
    if not table:
        return []

    items: list[dict] = []
    for row in table.find_all("tr"):
        title_cell = row.find("td", class_="col_tit")
        date_cell = row.find("td", class_="col_date")
        if not title_cell or not date_cell:
            continue

        title_anchor = title_cell.find("a", href=True)
        if title_anchor is None:
            continue
        uid = parse_qs(urlparse(title_anchor["href"]).query).get("uid", [""])[0]
        if not uid:
            continue

        title_node = title_cell.find(class_="tit")
        title_text = (
            title_node.get_text(" ", strip=True)
            if title_node
            else title_anchor.get_text(" ", strip=True)
        )
        title = _squash_text(title_text)
        file_anchor = next(
            (
                anchor
                for anchor in row.find_all("a", href=re.compile(r"/bb/down\.html"))
                if _is_pdf_download(anchor)
            ),
            None,
        )
        filename = _squash_text(file_anchor.get_text(" ", strip=True)) if file_anchor else ""
        download_path = file_anchor.get("href", "") if file_anchor else ""
        items.append(
            {
                "post_key": f"biz:{uid}",
                "no": row.find("td", class_="col_num").get_text(strip=True)
                if row.find("td", class_="col_num")
                else uid,
                "title": title,
                "date": date_cell.get_text(strip=True),
                "download_path": download_path,
                "filename": filename,
            }
        )
    if items:
        return items

    for row in table.find_all("tr")[1:]:  # skip header
        post_key = row.get("data-post_key", "")
        if not post_key:
            continue
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        no = cells[0].get_text(strip=True)
        if no == "공지":
            continue
        items.append(
            {
                "post_key": post_key,
                "no": no,
                "title": cells[1].get_text(strip=True),
                "date": cells[2].get_text(strip=True),
            }
        )
    return items


def parse_katech_detail(html: str) -> tuple[str | None, str | None]:
    """Extract (download_path, filename) from a KATECH post page (pure)."""
    soup = BeautifulSoup(html or "", "html.parser")
    for anchor in soup.find_all("a", class_="download"):
        href = anchor.get("href", "")
        if "/download/" in href:
            clean = href.split(";")[0]  # strip ;jsessionid
            filename = anchor.get_text(strip=True)
            if "(" in filename:  # strip trailing "(1.2MB)" size hint
                filename = filename[: filename.rfind("(")].strip()
            return clean, filename
    return None, None


def _safe_pdf_name(filename: str) -> str:
    safe = filename.replace("/", "_").replace("\\", "_").replace(":", "_")
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    return safe


def _download_pdf_limited(
    client: httpx.Client,
    url: str,
    *,
    max_file_bytes: int,
    post_key: str,
) -> bytes | None:
    data = bytearray()
    with client.stream("GET", url) as response:
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_file_bytes:
                    logger.warning(
                        "KATECH post %s PDF exceeds %d bytes",
                        post_key,
                        max_file_bytes,
                    )
                    return None
            except ValueError:
                pass
        for chunk in response.iter_bytes(chunk_size=64 * 1024):
            if not chunk:
                continue
            data.extend(chunk)
            if len(data) > max_file_bytes:
                logger.warning(
                    "KATECH post %s PDF exceeds %d bytes",
                    post_key,
                    max_file_bytes,
                )
                return None
    return bytes(data)


def iter_katech(
    existing_keys: set[str],
    *,
    max_pages: int = cfg.KATECH_MAX_PAGES,
    max_new: int = cfg.KATECH_MAX_NEW,
    max_file_bytes: int = cfg.KATECH_MAX_FILE_BYTES,
) -> Iterator[dict]:
    """Crawl the KATECH board and yield PDFs for posts not yet imported.

    ``existing_keys`` is the set of already-stored ``post_key`` values. Yields
    one file dict at a time so callers can persist each PDF before the next
    download is retained in memory::

        {"source_key", "title", "filename", "data", "content_type", "published_date"}
    """
    yielded = 0
    with httpx.Client(headers=cfg.KATECH_HEADERS, timeout=60, follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            try:
                resp = client.get(
                    f"{cfg.KATECH_BASE_URL}{cfg.KATECH_LIST_PAGE}",
                    params={"cid": cfg.KATECH_BOARD_CID, "page": str(page)},
                )
                resp.raise_for_status()
                items = parse_katech_list(resp.text)
            except Exception as error:  # noqa: BLE001
                logger.warning("KATECH list page %d failed: %s", page, error)
                continue
            if not items:
                break
            for item in items:
                post_key = item["post_key"]
                if post_key in existing_keys:
                    continue
                if yielded >= max_new:
                    logger.info("KATECH: %d new reports", yielded)
                    return
                try:
                    download_path = item.get("download_path", "")
                    filename = item.get("filename", "")
                    if not download_path:
                        continue
                    download_url = urljoin(cfg.KATECH_BASE_URL, download_path)
                    pdf_data = _download_pdf_limited(
                        client,
                        download_url,
                        max_file_bytes=max_file_bytes,
                        post_key=post_key,
                    )
                    if pdf_data is None:
                        continue
                    if not has_pdf_signature(pdf_data):
                        logger.warning("KATECH post %s did not return a PDF", post_key)
                        continue
                except Exception as error:  # noqa: BLE001
                    logger.warning("KATECH post %s failed: %s", post_key, error)
                    continue
                existing_keys.add(post_key)
                yielded += 1
                yield {
                    "source_key": post_key,
                    "title": item["title"] or _safe_pdf_name(filename or post_key),
                    "filename": _safe_pdf_name(filename or post_key),
                    "data": pdf_data,
                    "content_type": "application/pdf",
                    "published_date": item.get("date", "") or "",
                }
    logger.info("KATECH: %d new reports", yielded)


def collect_katech(
    existing_keys: set[str],
    *,
    max_pages: int = cfg.KATECH_MAX_PAGES,
    max_new: int = cfg.KATECH_MAX_NEW,
    max_file_bytes: int = cfg.KATECH_MAX_FILE_BYTES,
) -> list[dict]:
    """Return KATECH reports as a batch for tests or offline tooling.

    Production collection uses ``iter_katech`` through the service layer so
    downloaded PDFs are persisted one at a time instead of accumulating a whole
    run in memory.
    """
    return list(
        iter_katech(
            existing_keys,
            max_pages=max_pages,
            max_new=max_new,
            max_file_bytes=max_file_bytes,
        )
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Autojournal (오토저널)                                       ║
# ╚══════════════════════════════════════════════════════════════╝

def parse_autojournal_bookcase(html: str) -> list[dict]:
    """Extract issue records from a fliphtml5 bookcase page (pure).

    Mirrors the legacy ``_aj_scrape_issues`` ``bLink`` object extraction.
    Returns item dicts (source=autojournal), newest first.
    """
    objects = re.findall(r'\{[^{}]*"bLink"[^{}]*\}', html or "")
    if not objects:
        return []

    issues: list[dict] = []
    seen: set[str] = set()
    for obj_str in objects:
        try:
            book = json.loads(obj_str)
        except (ValueError, TypeError):
            continue
        blink = book.get("bLink", "")
        if not blink or blink in seen:
            continue
        seen.add(blink)
        title = book.get("title", "") or ""
        match = re.search(r"(\d{4})[.\-](\d{1,2})", title)
        if match:
            year, month = int(match.group(1)), int(match.group(2))
            label = f"{year}년 {month}월호"
        else:
            year, month = 0, 0
            label = title
        issues.append(
            _autojournal_item(
                issue_id=blink,
                year=year,
                month=month,
                label=label,
                title=title,
                description=book.get("description", "") or "",
                pages=book.get("pages", 0) or 0,
                cover=book.get("coverimg", "") or "",
                url=f"{cfg.AJ_BASE_URL}/{blink}/",
            )
        )
    issues.sort(key=_issue_sort_key, reverse=True)
    return issues


def known_autojournal_issues(now: datetime, count: int = 36) -> list[dict]:
    """Synthesize a recent run of issue ids (fallback for ``_aj_known_issues``)."""
    issues: list[dict] = []
    for delta in range(count):
        total_months = now.year * 12 + (now.month - 1) - delta
        year = total_months // 12
        month = total_months % 12 + 1
        vol = cfg.AJ_BASE_VOL - (cfg.AJ_BASE_YEAR - year)
        issue_id = f"auto{vol:02d}-{month:02d}"
        issues.append(
            _autojournal_item(
                issue_id=issue_id,
                year=year,
                month=month,
                label=f"{year}년 {month}월호 (제{vol}권 {month}호)",
                title=f"{year}.{month:02d}",
                description="",
                pages=0,
                cover="",
                url=f"{cfg.AJ_BASE_URL}/{issue_id}/",
            )
        )
    return issues


def _autojournal_item(
    *,
    issue_id: str,
    year: int,
    month: int,
    label: str,
    title: str,
    description: str,
    pages: int,
    cover: str,
    url: str,
) -> dict:
    return {
        "source": cfg.AUTOJOURNAL_SOURCE,
        "keyword": "",
        "title": label,
        "org": "오토저널",
        "summary": description,
        "url": url,
        "published_date": f"{year:04d}-{month:02d}" if year else "",
        "extra": {
            "issue_id": issue_id,
            "year": year,
            "month": month,
            "label": label,
            "raw_title": title,
            "pages": pages,
            "cover": cover,
        },
    }


def _issue_sort_key(item: dict) -> tuple[int, int]:
    extra = item.get("extra") or {}
    return (extra.get("year", 0), extra.get("month", 0))


def collect_autojournal() -> list[dict]:
    """Scrape the bookcase; fall back to synthesized ids if it returns nothing."""
    try:
        with httpx.Client(headers=cfg.AJ_HEADERS, timeout=15) as client:
            resp = client.get(cfg.AJ_BOOKCASE_URL)
            issues = parse_autojournal_bookcase(resp.text)
    except Exception as error:  # noqa: BLE001 - network best-effort
        logger.warning("autojournal bookcase scrape failed: %s", error)
        issues = []
    if not issues:
        issues = known_autojournal_issues(datetime.now())
    logger.info("autojournal: %d issues", len(issues))
    return issues


def parse_autojournal_issue_text(text: str, issue_id: str) -> dict | None:
    """Parse a ``search_config.js`` payload into per-page text + TOC (pure).

    Mirrors the legacy ``_aj_fetch_issue_text`` ``var textForPages =[`` parser.
    """
    start = (text or "").find("var textForPages =[")
    if start < 0:
        return None
    bracket_start = text.find("[", start)
    depth, end = 0, bracket_start
    for index, char in enumerate(text[bracket_start:], bracket_start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index
                break
    pages_raw = text[bracket_start : end + 1]
    pages: list[str] = []
    try:
        pages = json.loads(pages_raw)
    except (ValueError, TypeError):
        for entry in re.findall(r'"((?:[^"\\]|\\.)*)"', pages_raw):
            try:
                pages.append(entry.encode("utf-8").decode("unicode_escape", errors="replace"))
            except (ValueError, UnicodeDecodeError):
                pages.append(entry)

    clean_pages: list[str] = []
    toc: list[dict] = []
    for index, page in enumerate(pages):
        if not page or not page.strip():
            clean_pages.append("")
            continue
        clean = page.replace("\r\n", "\n").replace("\r", "\n").strip()
        clean_pages.append(clean)
        first_line = clean.split("\n")[0].strip()
        if first_line and 5 < len(first_line) < 80:
            toc.append({"page": index + 1, "title": first_line})

    return {
        "issue_id": issue_id,
        "total_pages": len(clean_pages),
        "pages": clean_pages,
        "toc": toc,
    }


def fetch_autojournal_issue_text(issue_id: str) -> dict | None:
    """Fetch + parse one issue's page text on demand."""
    url = f"{cfg.AJ_BASE_URL}/{issue_id}/files/search/search_config.js"
    try:
        with httpx.Client(headers=cfg.AJ_HEADERS, timeout=20) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            text = resp.text
    except Exception as error:  # noqa: BLE001
        logger.warning("autojournal issue %s fetch failed: %s", issue_id, error)
        return None
    return parse_autojournal_issue_text(text, issue_id)


# ╔══════════════════════════════════════════════════════════════╗
# ║  KDI (경제연구 자료)                                          ║
# ╚══════════════════════════════════════════════════════════════╝

def _kdi_client() -> httpx.Client:
    return httpx.Client(headers=cfg.KDI_HEADERS, timeout=15)


# ── 나라경제 ─────────────────────────────────────────────────
def parse_nara_list(html: str, year: str, month: str) -> list[dict]:
    """Parse a 나라경제 month list page (pure). Mirrors ``_fetch_nara_list``."""
    items: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<a\s+href="[^"]*naraView\.do\?([^"]*)"[^>]*>([\s\S]+?)</a>',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html or ""):
        params_str, inner_html = match.group(1), match.group(2)
        cidx_match = re.search(r"cidx=(\d+)", params_str)
        if not cidx_match:
            continue
        cidx = cidx_match.group(1)
        if cidx in seen:
            continue
        fcode_match = re.search(r"fcode=(\w+)", params_str)
        fcode = fcode_match.group(1) if fcode_match else cfg.NARA_FCODE
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner_html).strip())
        if not title or len(title) < 5 or len(title) > 150:
            continue
        seen.add(cidx)
        items.append(
            {
                "source": cfg.KDI_NARA_SOURCE,
                "keyword": "",
                "title": title,
                "org": "KDI 나라경제",
                "summary": "",
                "url": (
                    f"{cfg.KDI_BASE}/publish/naraView.do"
                    f"?fcode={fcode}&cidx={cidx}&sel_year={year}&sel_month={month}"
                ),
                "published_date": f"{year}년 {int(month):02d}월호",
                "extra": {"cidx": cidx, "fcode": fcode},
            }
        )
    return items


def collect_kdi_nara(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    all_items: list[dict] = []
    seen: set[str] = set()
    with _kdi_client() as client:
        for delta in range(cfg.KDI_NARA_MONTHS):
            total = now.year * 12 + (now.month - 1) - delta
            year = str(total // 12)
            month = f"{total % 12 + 1:02d}"
            try:
                resp = client.get(
                    f"{cfg.KDI_BASE}/publish/naraList.do",
                    params={"fcode": cfg.NARA_FCODE, "sel_year": year, "sel_month": month, "pg": "1"},
                )
                items = parse_nara_list(resp.text, year, month)
            except Exception as error:  # noqa: BLE001
                logger.warning("KDI nara %s-%s failed: %s", year, month, error)
                items = []
            for item in items:
                cidx = (item.get("extra") or {}).get("cidx")
                if cidx and cidx not in seen:
                    seen.add(cidx)
                    all_items.append(item)
    all_items.sort(key=_nara_sort_key, reverse=True)
    return all_items


def _nara_sort_key(item: dict) -> tuple[int, int]:
    match = re.search(r"(\d{4})년 (\d{2})월호", item.get("published_date", ""))
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


# ── 경제정책자료 / 국내연구자료 ───────────────────────────────
def parse_material_list(html: str, keyword: str = "") -> list[dict]:
    """Parse a 경제정책자료 list page (pure). Mirrors ``_fetch_material``."""
    return _parse_kdi_doc_list(
        html,
        split_token="materialView.do?num=",
        id_field="num",
        source=cfg.KDI_MATERIAL_SOURCE,
        org="KDI 경제정책자료",
        view_url=lambda doc_id: f"{cfg.KDI_BASE}/policy/materialView.do?num={doc_id}",
        keyword=keyword,
        title_pattern=r"<p>(.*?)</p>",
    )


def parse_domestic_list(html: str, keyword: str = "") -> list[dict]:
    """Parse a 국내연구자료 list page (pure). Mirrors ``_fetch_domestic``."""
    return _parse_kdi_doc_list(
        html,
        split_token="domesticView.do?ac=",
        id_field="ac",
        source=cfg.KDI_DOMESTIC_SOURCE,
        org="KDI 국내연구자료",
        view_url=lambda doc_id: f"{cfg.KDI_BASE}/policy/domesticView.do?ac={doc_id}",
        keyword=keyword,
        title_pattern=r"<(?:p|strong)>(.*?)</(?:p|strong)>",
    )


def _parse_kdi_doc_list(
    html: str,
    *,
    split_token: str,
    id_field: str,
    source: str,
    org: str,
    view_url,
    keyword: str,
    title_pattern: str,
) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    parts = re.split(re.escape(split_token), html or "")
    for part in parts[1:]:
        id_match = re.match(r"(\d+)", part)
        if not id_match:
            continue
        doc_id = id_match.group(1)
        if doc_id in seen:
            continue
        seen.add(doc_id)
        title_match = re.search(title_pattern, part[:2000])
        if not title_match:
            continue
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        if not title:
            continue
        after = part[title_match.end() :]
        org_match = re.search(r"<span>([^<\d][^<]*?)</span>", after[:500])
        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", after[:500])
        items.append(
            {
                "source": source,
                "keyword": keyword,
                "title": title,
                "org": org_match.group(1).strip() if org_match else org,
                "summary": "",
                "url": view_url(doc_id),
                "published_date": date_match.group(1) if date_match else "",
                "extra": {id_field: doc_id},
            }
        )
    return items


def _collect_kdi_keyword_source(parse, fetch_label: str) -> list[dict]:
    all_items: list[dict] = []
    seen: set[str] = set()
    with _kdi_client() as client:
        for keyword in cfg.KDI_KEYWORDS:
            try:
                resp = client.get(
                    f"{cfg.KDI_BASE}/policy/{fetch_label}",
                    params={"search_txt": keyword, "pg": "1", "pp": "30", "type": "A"},
                )
                items = parse(resp.text, keyword)
            except Exception as error:  # noqa: BLE001
                logger.warning("KDI %s '%s' failed: %s", fetch_label, keyword, error)
                items = []
            for item in items:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    all_items.append(item)
    all_items.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    return all_items


def collect_kdi_material() -> list[dict]:
    return _collect_kdi_keyword_source(parse_material_list, "materialList.do")


def collect_kdi_domestic() -> list[dict]:
    return _collect_kdi_keyword_source(parse_domestic_list, "domesticList.do")


def resolve_kdi_pdf_url(page_url: str) -> str | None:
    """Resolve a KDI document page to its underlying PDF/download URL."""
    if not is_kdi_url(page_url):
        return None
    try:
        with _kdi_client() as client:
            html = client.get(page_url).text
    except Exception as error:  # noqa: BLE001
        logger.warning("KDI pdf-url resolve failed: %s", error)
        return None
    # 실제 PDF/다운로드 링크만 인정한다. (과거 fallback 으로 두던
    # ``location.href=...`` 패턴은 본문에 PDF가 없는 정책/연구자료 페이지에서
    # 무관한 메뉴 링크(예: /publish/naraMain.do)를 잡아 나라경제로 잘못 보냈다.)
    for pattern in (
        r'href="([^"]+\.pdf[^"]*)"',
        r'href="([^"]+/download[^"]*)"',
        r"'([^']+fileDown[^']+)'",
        r'href="([^"]+fileDown[^"]*)"',
    ):
        for match in re.finditer(pattern, html):
            url = urljoin(page_url, match.group(1))
            if is_kdi_url(url):
                return url
    return None
