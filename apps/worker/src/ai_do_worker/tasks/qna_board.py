"""Worker task: ingest the groupware "주요공지사항(관리팀)" board into the Q&A corpus.

The source of truth for this task is the groupware web UI. It logs in with
``AI_DO_QNA_BOARD_WEB_*``, reads the mobile board DataTables endpoint, fetches
each selected notice's detail page, downloads attachments, and stores the notice
as a QnaDocument (``kind='notice'``) for the existing RAG sync pipeline.

Scheduled daily via Celery beat and triggered on demand by
``POST /api/v1/qna/board/sync``.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import unquote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from ai_do_worker.celery_app import celery_app
from ai_do_worker.runtime import (
    db_session as _db_session,
    ensure_api_src_on_path as _ensure_api_src_on_path,
)
from ai_do_worker.settings import Settings, get_settings


_ensure_api_src_on_path()

from ai_do_api.domains.auth.workspace_app_gate import is_platform_app_enabled  # noqa: E402
from ai_do_api.domains.qna import service  # noqa: E402
from ai_do_api.domains.qna.app_catalog import QA_ASSISTANT_WORKSPACE_APP  # noqa: E402
from ai_do_api.domains.qna.extraction import (  # noqa: E402
    AttachmentExtraction,
    combine_attachment_texts,
    extract_attachment,
)
from ai_do_api.domains.qna.object_storage import (  # noqa: E402
    build_company_notice_attachment_storage_key,
    put_qna_object,
)


logger = logging.getLogger(__name__)

_QNA_BOARD_TASK_TIME_LIMIT = 900
_QNA_BOARD_TASK_SOFT_TIME_LIMIT = 840

_QNA_BOARD_CATEGORY_FALLBACK = "주요공지사항(관리팀)"
_QNA_BOARD_LIST_ENDPOINT = (
    "/mobile/common/controller/GetBbsList.ashx?"
    "sfiltertype=ALL&sUser_num=0&sReply=0&sauthtype=&sresult=&num=&bbs_num=0"
    "&isadmin=False&isgroup=False&isoneonone=False&sfind=&sfindtype=subject"
)
_QNA_BOARD_LIST_REFERER = "/mobile/bbs/bbs_list.aspx"
_QNA_BOARD_LIST_COLUMNS = (
    "chk",
    "num",
    "ref",
    "re_step",
    "numidx",
    "priority",
    "attach",
    "w_grade",
    "w_rst",
    "subject",
    "user_name",
    "modify_date",
    "p_class",
    "like_str",
    "w_cnt",
)
_QNA_BOARD_WEB_PAGE_SIZE = 100
_QNA_BOARD_WEB_MAX_SCAN_PAGES = 20
_MAX_NOTICE_CHARS = 20_000
_ATTACHMENT_CHUNK_BYTES = 64 * 1024

_DOWNLOAD_RE = re.compile(r"download\.aspx\?[^\"'\s)]*DownType=bbs[^\"'\s)]*")
_FILE_PARAM_RE = re.compile(r"[?&]file=([^&\"'\s)]+)")


@dataclass
class NoticeRecord:
    num: str
    title: str
    author: str
    date: str
    body: str
    attachments: list[str] = field(default_factory=list)
    detail_html: str = ""


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _clean_inline_text(raw: str | None) -> str:
    text = BeautifulSoup(str(raw or ""), "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _has_web_credentials(settings: Settings) -> bool:
    return bool(
        settings.qna_board_web_base_url.strip()
        and settings.qna_board_web_username.strip()
        and settings.qna_board_web_password.strip()
    )


def _web_login(settings: Settings) -> httpx.Client | None:
    """Log into the groupware web and return an authenticated httpx client."""
    base = settings.qna_board_web_base_url.rstrip("/")
    login_url = f"{base}/index.aspx"
    client = httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        page = client.get(login_url).text

        def _hidden(name: str) -> str:
            match = re.search(rf'name="{name}"[^>]*value="([^"]*)"', page)
            return match.group(1) if match else ""

        hashed = "!SHA!" + hashlib.sha256(settings.qna_board_web_password.encode()).hexdigest()
        client.post(
            login_url,
            data={
                "txtUserid": settings.qna_board_web_username,
                "txtPassword": hashed,
                "txtClientType": "W",
                "__VIEWSTATE": _hidden("__VIEWSTATE"),
                "__VIEWSTATEGENERATOR": _hidden("__VIEWSTATEGENERATOR"),
                "__EVENTVALIDATION": _hidden("__EVENTVALIDATION"),
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__LASTFOCUS": "",
                "btnLogin": "Login",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": login_url,
                "Origin": base,
            },
        )
        if not any("gware" in name.lower() for name in client.cookies.keys()):
            logger.warning("qna.crawl_board: groupware web login failed (no session cookie)")
            client.close()
            return None
        return client
    except Exception as error:  # noqa: BLE001
        logger.warning("qna.crawl_board: groupware web login error: %s", error)
        client.close()
        return None


def _selected_text(soup: BeautifulSoup, selector: str) -> str:
    element = soup.select_one(selector)
    return _clean_inline_text(str(element)) if element is not None else ""


def _attachment_names_from_detail_html(html_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for link in _DOWNLOAD_RE.findall(html_text):
        file_match = _FILE_PARAM_RE.search(link)
        if not file_match:
            continue
        filename = service.normalize_attachment_name(unquote_plus(file_match.group(1)))
        if filename and filename not in seen:
            seen.add(filename)
            names.append(filename)
    return names


def _attachment_names_from_list_cell(raw: str | None) -> list[str]:
    if not raw:
        return []
    soup = BeautifulSoup(str(raw), "html.parser")
    names: list[str] = []
    for element in soup.find_all(attrs={"alt": True}):
        names.extend((element.get("alt") or "").split(","))
    return service.normalize_attachment_names(names)


def _subject_href(raw: str | None) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(str(raw), "html.parser")
    link = soup.find("a", href=True)
    return str(link["href"]) if link else ""


def _num_from_href(href: str) -> str:
    match = re.search(r"[?&]num=(\d+)", href)
    return match.group(1) if match else ""


def _normalize_board_category(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip())


def _matches_board_category(row_category: str, expected_category: str) -> bool:
    category = _normalize_board_category(row_category)
    expected = _normalize_board_category(expected_category) or _QNA_BOARD_CATEGORY_FALLBACK
    if not category:
        return False
    return category == expected


def _list_request_data(*, page: int, page_size: int) -> dict[str, str]:
    data = {
        "draw": str(page),
        "start": str((page - 1) * page_size),
        "length": str(page_size),
        "curPage": str(page),
        "search[value]": "",
        "search[regex]": "false",
        "order[0][column]": "modify_date",
        "order[0][dir]": "desc",
    }
    for index, column in enumerate(_QNA_BOARD_LIST_COLUMNS):
        data[f"columns[{index}][data]"] = column
        data[f"columns[{index}][name]"] = column
        data[f"columns[{index}][searchable]"] = "true"
        data[f"columns[{index}][orderable]"] = "true"
        data[f"columns[{index}][search][value]"] = ""
        data[f"columns[{index}][search][regex]"] = "false"
    return data


def _parse_groupware_json(response: httpx.Response) -> dict:
    response.raise_for_status()
    text = response.text.strip()
    json_start = text.find("{")
    if json_start < 0:
        raise RuntimeError("Groupware board list response is not JSON.")
    return json.loads(text[json_start:])


def _build_detail_url(base: str, row: dict) -> str:
    href = _subject_href(row.get("subject"))
    if href:
        return urljoin(f"{base}/mobile/bbs/", href)
    num = str(row.get("num") or "")
    return f"{base}/mobile/bbs/read_bbs.aspx?num={num}"


def _notice_from_web_row(
    client: httpx.Client,
    settings: Settings,
    row: dict,
) -> NoticeRecord:
    base = settings.qna_board_web_base_url.rstrip("/")
    href = _subject_href(row.get("subject"))
    num = str(row.get("num") or _num_from_href(href))
    title = _clean_inline_text(row.get("subject")) or f"공지 {num}"
    author = _clean_inline_text(row.get("user_name"))
    posted_at = str(row.get("modify_date") or "").strip()
    attachments = _attachment_names_from_list_cell(row.get("attach"))
    detail_html = ""

    try:
        response = client.get(_build_detail_url(base, row))
        if response.status_code == 200:
            detail_html = response.text
    except Exception as error:  # noqa: BLE001
        logger.warning("qna.crawl_board: notice detail fetch failed (%s): %s", num, error)

    if detail_html:
        soup = BeautifulSoup(detail_html, "html.parser")
        title = _selected_text(soup, "#lblSubject") or title
        author = _selected_text(soup, "#lblWriter") or author
        posted_at = _selected_text(soup, "#lblDate") or posted_at
        body = _selected_text(soup, "#lblContents") or _selected_text(soup, "#diarycontent")
        detail_attachments = _attachment_names_from_detail_html(detail_html)
        if detail_attachments:
            attachments = detail_attachments
    else:
        body = ""

    if len(body) > _MAX_NOTICE_CHARS:
        body = body[:_MAX_NOTICE_CHARS] + "\n[이하 생략]"
    return NoticeRecord(
        num=num,
        title=title,
        author=author,
        date=posted_at,
        body=body,
        attachments=attachments,
        detail_html=detail_html,
    )


def _fetch_notices(settings: Settings, client: httpx.Client) -> list[NoticeRecord]:
    base = settings.qna_board_web_base_url.rstrip("/")
    page_size = _QNA_BOARD_WEB_PAGE_SIZE
    max_posts = max(int(settings.qna_board_max_posts), 1)
    expected_category = settings.qna_board_category.strip()
    records: list[NoticeRecord] = []
    seen: set[str] = set()

    for page in range(1, _QNA_BOARD_WEB_MAX_SCAN_PAGES + 1):
        response = client.post(
            f"{base}{_QNA_BOARD_LIST_ENDPOINT}",
            data=_list_request_data(page=page, page_size=page_size),
            headers={"Referer": f"{base}{_QNA_BOARD_LIST_REFERER}"},
        )
        payload = _parse_groupware_json(response)
        rows = payload.get("data") or []
        for row in rows:
            category = _clean_inline_text(row.get("p_class"))
            if not _matches_board_category(category, expected_category):
                continue
            href = _subject_href(row.get("subject"))
            num = str(row.get("num") or _num_from_href(href))
            if not num or num in seen:
                continue
            seen.add(num)
            records.append(_notice_from_web_row(client, settings, row))
            if len(records) >= max_posts:
                return records

        total = int(payload.get("recordsFiltered") or payload.get("recordsTotal") or 0)
        if not rows or page * page_size >= total:
            break

    return records


def _download_response_limited(
    response: httpx.Response,
    *,
    max_file_bytes: int,
    num: str,
    filename: str,
) -> bytes | None:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_file_bytes:
                logger.warning(
                    "qna.crawl_board: attachment too large by Content-Length (%s/%s, max=%s)",
                    num,
                    filename,
                    max_file_bytes,
                )
                return None
        except ValueError:
            pass

    data = bytearray()
    for chunk in response.iter_bytes(chunk_size=_ATTACHMENT_CHUNK_BYTES):
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > max_file_bytes:
            logger.warning(
                "qna.crawl_board: attachment exceeds byte limit (%s/%s, max=%s)",
                num,
                filename,
                max_file_bytes,
            )
            return None
    return bytes(data)


def _download_attachments(
    client: httpx.Client, settings: Settings, *, num: str, detail_html: str = ""
) -> tuple[list[str], str, list[str]]:
    """Download a notice's attachments via the web, store bytes, return (names, text, content_hashes)."""
    base = settings.qna_board_web_base_url.rstrip("/")
    html_text = detail_html
    if not html_text:
        try:
            html_text = client.get(f"{base}/mobile/bbs/read_bbs.aspx?num={num}").text
        except Exception as error:  # noqa: BLE001
            logger.warning("qna.crawl_board: read page fetch failed (%s): %s", num, error)
            return [], "", []

    names: list[str] = []
    extractions: list[AttachmentExtraction] = []
    content_hashes: list[str] = []
    seen: set[str] = set()
    downloaded_bytes = 0
    per_file_limit = int(settings.qna_board_attachment_max_bytes)
    total_limit = int(settings.qna_board_attachments_max_total_bytes)
    for link in _DOWNLOAD_RE.findall(html_text):
        remaining_total = total_limit - downloaded_bytes
        if remaining_total <= 0:
            logger.warning(
                "qna.crawl_board: notice attachment total limit reached (%s, max=%s)",
                num,
                total_limit,
            )
            break
        file_match = _FILE_PARAM_RE.search(link)
        if not file_match:
            continue
        filename = service.normalize_attachment_name(unquote_plus(file_match.group(1)))
        if not filename or filename in seen:
            continue
        seen.add(filename)
        try:
            with client.stream("GET", f"{base}/common/{link}") as response:
                if response.status_code != 200:
                    continue
                content = _download_response_limited(
                    response,
                    max_file_bytes=min(per_file_limit, remaining_total),
                    num=num,
                    filename=filename,
                )
                if content is None or len(content) < 100:
                    continue
                content_type = response.headers.get("content-type")
                downloaded_bytes += len(content)
            put_qna_object(
                storage_key=build_company_notice_attachment_storage_key(
                    notice_external_id=str(num), filename=filename
                ),
                content=content,
                content_type=content_type,
            )
            names.append(filename)
            content_hashes.append(hashlib.sha256(content).hexdigest())
            extractions.append(extract_attachment(filename=filename, content=content))
        except Exception as error:  # noqa: BLE001
            logger.warning("qna.crawl_board: attachment failed (%s/%s): %s", num, filename, error)
    return names, combine_attachment_texts(extractions), content_hashes


@celery_app.task(
    name="qna.crawl_board",
    bind=True,
    acks_late=True,
    task_time_limit=_QNA_BOARD_TASK_TIME_LIMIT,
    task_soft_time_limit=_QNA_BOARD_TASK_SOFT_TIME_LIMIT,
)
def crawl_board(self) -> str:
    del self
    settings = get_settings()
    if not settings.qna_board_crawl_enabled:
        return "disabled"

    session = _db_session()
    if not is_platform_app_enabled(session, QA_ASSISTANT_WORKSPACE_APP.app_id):
        session.close()
        return "platform-disabled"
    if not _has_web_credentials(settings):
        logger.warning("qna.crawl_board: groupware web credentials are not configured")
        session.close()
        return "missing-credentials"

    web_client = _web_login(settings)
    if web_client is None:
        session.close()
        return "login-failed"
    try:
        notices = _fetch_notices(settings, web_client)

        try:
            changed = 0
            for notice in notices:
                names, attach_text, attach_hashes = _download_attachments(
                    web_client,
                    settings,
                    num=notice.num,
                    detail_html=notice.detail_html,
                )
                if names:
                    notice.attachments = names
                if attach_text:
                    notice.body = (notice.body + "\n\n" + attach_text).strip()[
                        :_MAX_NOTICE_CHARS
                    ]
                _, was_changed = service.upsert_notice(
                    session,
                    num=notice.num,
                    title=notice.title,
                    author=notice.author,
                    posted_at=notice.date,
                    body=notice.body,
                    attachments=notice.attachments,
                    attachment_content_hashes=attach_hashes,
                    category=settings.qna_board_category,
                )
                if was_changed:
                    changed += 1
        finally:
            web_client.close()
        session.commit()
        logger.info("qna.crawl_board done: total=%s changed=%s", len(notices), changed)
        return f"synced:total={len(notices)},changed={changed}"
    except Exception:
        session.rollback()
        logger.exception("qna.crawl_board failed")
        raise
    finally:
        session.close()
