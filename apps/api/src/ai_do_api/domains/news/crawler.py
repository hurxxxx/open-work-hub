"""News collection and article parsing.

A faithful port of the legacy Flask portal's ``routes/news.py`` collection
logic, adapted to ``httpx`` + BeautifulSoup. Functions here are stateless (no
DB, no module-level cache): callers pass Naver API credentials and the active
filter settings, and receive plain article dicts. Pure parsing helpers
(``parse_article_html``, ``parse_rss``, ``make_summary`` …) are split out from
the network calls so they can be unit-tested offline.
"""
from __future__ import annotations

import html as _html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from . import config_data as cfg

logger = logging.getLogger(__name__)

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.naver.com/",
}
_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_BODY_SELECTORS = [
    "#dic_area", "#articleBodyContents",
    "#article-view-content-div", "#article_content",
    "#articleBody", "#article-body",
    ".article-view-content", ".article_txt", ".article-txt",
    ".article_body", ".article-body",
    ".news_end", ".view_con",
    "#content-body", ".content-body",
    "#newsct_article", ".article__body",
    "article", ".post-content", ".entry-content",
]


# ── Pure helpers ─────────────────────────────────────────────
def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return _html.unescape(text).strip()


def parse_date(pub_date: str) -> str:
    """RFC-2822 (Naver pubDate) → ``YYYY-MM-DD``, falling back to today."""
    try:
        dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return datetime.now().strftime("%Y-%m-%d")


def extract_source(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    if not match:
        return "알 수 없음"
    domain = match.group(1)
    for key, val in cfg.SOURCE_DOMAIN_MAP.items():
        if key in domain:
            return val
    return domain


def make_summary(text: str) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?。])\s+", text)
    result: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            continue
        if any(kw in sentence for kw in ["기자", "ⓒ", "무단 전재", "저작권", "©"]):
            continue
        result.append(sentence)
        if len(result) >= 2:
            break
    return " ".join(result)


def expand_car_keywords(keyword: str) -> list[str]:
    for key, variants in cfg.CAR_BRAND_MAP.items():
        if keyword == key or keyword in variants:
            return list(set(variants))
    return [keyword]


def _parse_width(img_tag) -> int | None:
    width = img_tag.get("width")
    if width:
        try:
            return int(str(width).replace("px", "").strip())
        except ValueError:
            pass
    match = re.search(r"width\s*:\s*(\d+)", img_tag.get("style", ""))
    if match:
        return int(match.group(1))
    return None


def parse_article_html(
    markup: str | bytes,
    *,
    max_images: int = cfg.MAX_IMAGES_PER_ARTICLE,
    min_image_width: int = cfg.MIN_IMAGE_WIDTH,
) -> dict:
    """Extract body text, summary, images and tables from an article page.

    Mirrors the legacy ``_crawl_article`` selector list, the largest-``<p>``
    fallback, and the image-filtering heuristics.
    """
    soup = BeautifulSoup(markup, "html.parser")

    body_el = None
    for selector in _BODY_SELECTORS:
        body_el = soup.select_one(selector)
        if body_el:
            break

    if not body_el:
        best_parent, best_len = None, 0
        for paragraph in soup.find_all("p"):
            parent = paragraph.parent
            if parent and parent.name not in ("html", "body", "head"):
                text_len = len(parent.get_text(strip=True))
                if text_len > best_len:
                    best_len = text_len
                    best_parent = parent
        if best_parent and best_len > 100:
            body_el = best_parent

    full_text = ""
    if body_el:
        for tag in body_el.select(
            "script, style, .ad, .related, button, .reporter, nav"
        ):
            tag.decompose()
        full_text = body_el.get_text(separator="\n", strip=True)
        if len(full_text) < 50:
            full_text = ""

    summary = make_summary(full_text)

    images: list[dict[str, str]] = []
    search_area = body_el if body_el else soup
    for img in search_area.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if not src.startswith("http"):
            continue
        if any(kw in src.lower() for kw in ["logo", "icon", "banner", "ad_", "/ads/", "spacer"]):
            continue
        width = _parse_width(img)
        if width and width < min_image_width:
            continue
        parent = img.parent
        cap_el = (
            parent.find("figcaption")
            or parent.find("em")
            or parent.find("span", class_=re.compile(r"cap", re.I))
        )
        caption = cap_el.get_text(strip=True) if cap_el else ""
        images.append({"url": src, "caption": caption})
        if len(images) >= max_images:
            break

    tables: list[str] = []
    if body_el:
        for table in body_el.find_all("table"):
            tables.append(str(table))

    return {"full_text": full_text, "summary": summary, "images": images, "tables": tables}


def parse_rss(content: bytes, max_items: int = 5) -> list[dict[str, str]]:
    root = ET.fromstring(content)
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = strip_html((item.findtext("title", "") or "").strip())
        link = (
            (item.findtext("link", "") or "").strip()
            or (item.findtext("guid", "") or "").strip()
        )
        if not title or not link or len(title) < 5:
            continue
        items.append({"title": title, "url": link})
        if len(items) >= max_items:
            break
    return items


# ── Network calls ────────────────────────────────────────────
def _naver_headers(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def naver_search(
    client: httpx.Client,
    client_id: str,
    client_secret: str,
    keyword: str,
    date: str | None = None,
    display: int = 10,
) -> list[dict]:
    params = {"query": keyword, "display": display, "sort": "date"}
    try:
        resp = client.get(
            NAVER_NEWS_API,
            headers=_naver_headers(client_id, client_secret),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as error:  # noqa: BLE001 - network best-effort
        logger.warning("naver_search failed for %r: %s", keyword, error)
        return []
    if not date:
        return items
    filtered = [
        item
        for item in items
        if date[4:6] in item.get("pubDate", "") and date[6:] in item.get("pubDate", "")
    ]
    return filtered if filtered else items


def search_by_press(
    client: httpx.Client,
    client_id: str,
    client_secret: str,
    press_name: str,
    max_items: int = 5,
    keyword: str = "",
) -> list[dict[str, str]]:
    query = f"{press_name} {keyword}".strip() if keyword else press_name
    seen: set[str] = set()
    result: list[dict] = []
    for sort in ("sim", "date"):
        params = {"query": query, "display": max_items * 2, "sort": sort}
        try:
            resp = client.get(
                NAVER_NEWS_API,
                headers=_naver_headers(client_id, client_secret),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                title = strip_html(item.get("title", "")).strip()
                link = item.get("originallink") or item.get("link", "")
                if not title or not link or link in seen:
                    continue
                seen.add(link)
                result.append(
                    {
                        "title": title,
                        "url": link,
                        "_sim": 1 if sort == "sim" else 0,
                        "_tlen": len(title),
                    }
                )
        except Exception as error:  # noqa: BLE001
            logger.warning("search_by_press %s/%s failed: %s", press_name, sort, error)
    result.sort(key=lambda x: (-x["_sim"], -x["_tlen"]))
    return [{"title": r["title"], "url": r["url"]} for r in result[:max_items]]


def try_rss(client: httpx.Client, rss_url: str, max_items: int = 5) -> list[dict[str, str]]:
    try:
        resp = client.get(rss_url, headers=_RSS_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        return parse_rss(resp.content, max_items)
    except Exception as error:  # noqa: BLE001
        logger.warning("try_rss %s failed: %s", rss_url, error)
        return []


def scrape_naver_media(client: httpx.Client, oid: str, name: str = "") -> list[dict[str, str]]:
    """Scrape the Naver media press page — MBC/KBS/YTN fallback."""
    try:
        url = f"https://media.naver.com/press/{oid}"
        resp = client.get(
            url,
            headers={**_BROWSER_HEADERS, "Referer": "https://news.naver.com/"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.content, "html.parser")
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            if "n.news.naver.com" not in href and "news.naver.com/article" not in href:
                continue
            if href in seen:
                continue
            title = re.sub(r"\s+", " ", anchor.get_text(separator=" ", strip=True))
            if not title or len(title) < 8 or len(title) > 120:
                continue
            seen.add(href)
            items.append({"title": title, "url": href})
            if len(items) >= 5:
                break
        return items
    except Exception as error:  # noqa: BLE001
        logger.warning("scrape_naver_media %s(%s) failed: %s", name, oid, error)
        return []


def scrape_homepage(
    client: httpx.Client, url: str, selectors: list[str], name: str = ""
) -> list[dict[str, str]]:
    """Scrape a newspaper homepage directly via CSS selectors."""
    try:
        resp = client.get(url, headers=_BROWSER_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.content, "html.parser")
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for selector in selectors:
            for el in soup.select(selector):
                anchor = el if el.name == "a" else el.find("a", href=True)
                href = (anchor.get("href", "") if anchor else "") or ""
                title = re.sub(r"\s+", " ", el.get_text(strip=True))
                if not title or len(title) < 8 or len(title) > 120:
                    continue
                if title in seen:
                    continue
                if any(kw in title for kw in ["구독", "로그인", "광고", "더보기", "운세"]):
                    continue
                seen.add(title)
                if href and not href.startswith("http"):
                    base = "/".join(url.split("/")[:3])
                    href = base + href
                items.append({"title": title, "url": href})
                if len(items) >= 5:
                    break
            if items:
                break
        return items
    except Exception as error:  # noqa: BLE001
        logger.warning("scrape_homepage %s failed: %s", name, error)
        return []


def crawl_newsstand_main(client: httpx.Client, oid: str) -> list[dict[str, str]]:
    """Fetch a newspaper's headline articles from its best available source."""
    if oid in cfg.RSS_MAP:
        result = try_rss(client, cfg.RSS_MAP[oid])
        if result:
            return result
    if oid in cfg.HOMEPAGE_MAP:
        url, selectors = cfg.HOMEPAGE_MAP[oid]
        result = scrape_homepage(client, url, selectors, oid)
        if result:
            return result
    return scrape_naver_media(client, oid)


def crawl_article(url: str) -> dict:
    """Fetch + parse a single article page (used on demand by the API)."""
    try:
        with httpx.Client(follow_redirects=True) as client:
            resp = client.get(url, headers=_BROWSER_HEADERS, timeout=10)
            resp.raise_for_status()
            markup = resp.content
    except Exception as error:  # noqa: BLE001
        logger.warning("crawl_article %s failed: %s", url, error)
        return {"full_text": "", "summary": "", "images": [], "tables": []}
    return parse_article_html(markup)


# ── Channel collectors ───────────────────────────────────────
def _new_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, headers=_BROWSER_HEADERS)


def collect_keyword(
    client_id: str,
    client_secret: str,
    *,
    keyword_filter: list[str],
    keyword_ui_filters: list[str],
    sleep_seconds: float = 0.5,
) -> list[dict]:
    """Collect the keyword channel (legacy ``_collect_keyword``)."""
    date_range = [
        (datetime.now() - timedelta(days=d)).strftime("%Y%m%d")
        for d in range(0, cfg.RECENT_DAYS)  # 오늘(0) 포함 최근 RECENT_DAYS일
    ]
    oldest = date_range[-1]
    all_keywords = list(cfg.SEARCH_KEYWORDS)
    for kw in keyword_ui_filters:
        if kw not in all_keywords:
            all_keywords.append(kw)

    articles: list[dict] = []
    seen_urls: set[str] = set()
    with _new_client() as client:
        for keyword in all_keywords:
            items = naver_search(client, client_id, client_secret, keyword, None, display=30)
            if sleep_seconds:
                time.sleep(sleep_seconds)
            for item in items:
                title = strip_html(item.get("title", ""))
                if any(ex in title for ex in cfg.EXCLUDE_KEYWORDS):
                    continue
                kw_words = keyword.split()
                if (
                    keyword_filter
                    and not any(rel in title for rel in keyword_filter)
                    and not any(w in title for w in kw_words)
                ):
                    continue
                link = item.get("originallink") or item.get("link", "")
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                pub_date = parse_date(item.get("pubDate", ""))
                pub_ymd = pub_date.replace("-", "") if pub_date else ""
                if pub_ymd and pub_ymd < oldest:
                    continue
                articles.append(_article(keyword, link, pub_date, title, channel="keyword"))
    articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    return articles


def collect_front(
    client_id: str,
    client_secret: str,
    *,
    sleep_seconds: float = 1.0,
) -> list[dict]:
    """Collect the front-page channel (legacy ``_collect_front``)."""
    today = datetime.now().strftime("%Y-%m-%d")
    articles: list[dict] = []
    with _new_client() as client:
        for paper in cfg.FRONT_PAGE_PAPERS:
            items = crawl_newsstand_main(client, paper["oid"])
            if not items:
                items = search_by_press(
                    client, client_id, client_secret, paper["name"], max_items=3
                )
            for item in items:
                articles.append(
                    _article(
                        keyword="",
                        link=item["url"],
                        date=today,
                        title=item["title"],
                        channel="front",
                        source=paper["name"],
                    )
                )
            if sleep_seconds:
                time.sleep(sleep_seconds)
    return articles


def collect_car(
    client_id: str,
    client_secret: str,
    *,
    car_filter: list[str],
    sleep_seconds: float = 0.5,
) -> list[dict]:
    """Collect the car channel (legacy ``_collect_car``)."""
    today = datetime.now()
    valid_dates = {
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(cfg.RECENT_DAYS)  # 오늘(0) 포함 최근 RECENT_DAYS일
    }
    articles: list[dict] = []
    seen_urls: set[str] = set()
    with _new_client() as client:
        for keyword in cfg.CAR_SEARCH_KEYWORDS:
            expanded = expand_car_keywords(keyword)
            all_items: list[dict] = []
            for kw in expanded:
                all_items.extend(
                    naver_search(client, client_id, client_secret, kw, display=100)
                )
                if len(expanded) > 1 and sleep_seconds:
                    time.sleep(sleep_seconds * 0.6)
            if sleep_seconds:
                time.sleep(sleep_seconds)
            for item in all_items:
                title = strip_html(item.get("title", ""))
                link = item.get("originallink") or item.get("link", "")
                if not link or link in seen_urls:
                    continue
                if any(ex in title for ex in cfg.EXCLUDE_KEYWORDS):
                    continue
                if car_filter and not any(rel in title for rel in car_filter):
                    continue
                pub_date = parse_date(item.get("pubDate", ""))
                if pub_date not in valid_dates:
                    continue
                seen_urls.add(link)
                articles.append(_article(keyword, link, pub_date, title, channel="car"))
    articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    return articles


def search_query(
    client_id: str,
    client_secret: str,
    query: str,
) -> list[dict]:
    """Free-text search (legacy ``/api/news/search``).

    Returns up to 100 most-recent matches (Naver ``display`` max) within the same
    recent-day window the channels use, instead of the previous 10-item cap.
    """
    today = datetime.now()
    valid_dates = {
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(cfg.RECENT_DAYS)  # 오늘(0) 포함 최근 RECENT_DAYS일
    }
    articles: list[dict] = []
    seen_urls: set[str] = set()
    with _new_client() as client:
        items = naver_search(client, client_id, client_secret, query, display=100)
    for item in items:
        title = strip_html(item.get("title", ""))
        if any(ex in title for ex in cfg.EXCLUDE_KEYWORDS):
            continue
        link = item.get("originallink") or item.get("link", "")
        if not link or link in seen_urls:
            continue
        pub_date = parse_date(item.get("pubDate", ""))
        if pub_date not in valid_dates:
            continue
        seen_urls.add(link)
        articles.append(_article(query, link, pub_date, title, channel="search"))
    articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    return articles


def _article(
    keyword: str,
    link: str,
    date: str,
    title: str,
    *,
    channel: str,
    source: str | None = None,
) -> dict:
    return {
        "channel": channel,
        "keyword": keyword,
        "source": source if source is not None else extract_source(link),
        "date": date,
        "title": title,
        "summary": "",
        "full_text": "",
        "images": [],
        "tables": [],
        "original_url": link,
    }
