"""KIPRIS (Korean Intellectual Property Rights Information Service) client.

Ports the KIPRIS request building and XML parsing from the legacy Flask
``routes/patent.py``. Uses httpx (the pattern used by other outbound clients
such as ``domains/search/opensearch.py``). PDF full-text extraction from the
legacy tool is intentionally not ported in v1 — claims/abstract come from the
bibliography API, which needs no PDF parser.
"""

from __future__ import annotations

import html
import ipaddress
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from urllib.parse import quote, quote_plus, urlparse

import httpx

_CONNECT_TIMEOUT_SECONDS = 5.0
_READ_TIMEOUT_SECONDS = 60.0
_SYNC_OPERATION_TIMEOUT_SECONDS = 15.0
_MAX_REQUEST_RETRIES = 3
_RETRYABLE_HTTP_STATUSES = frozenset({429, 502, 503, 504})
_FOREIGN_PROVIDER_PAGE_SIZE = 30
_MAX_SEARCH_PAGE_SIZE = 30
_MAX_SEARCH_QUERY_CHARS = 8_000
_MAX_SEARCH_FILTER_VALUES = 30
_MAX_SEARCH_FILTER_CHARS = 256
_MAX_SEARCH_XML_BYTES = 8 * 1024 * 1024
_MAX_SEARCH_IDENTIFIER_CHARS = 128
_MAX_SEARCH_NUMBER_CHARS = 96
_MAX_SEARCH_JURISDICTION_CHARS = 8
_MAX_SEARCH_TITLE_CHARS = 1_000
_MAX_SEARCH_ABSTRACT_CHARS = 32_000
_MAX_SEARCH_APPLICANTS = 30
_MAX_SEARCH_APPLICANT_CHARS = 320
_MAX_SEARCH_CLASSIFICATIONS = 50
_MAX_SEARCH_CLASSIFICATION_CHARS = 64
_MAX_SEARCH_URL_CHARS = 2_048
_MAX_SEARCH_TOTAL_COUNT = 2_147_483_647

_BLOCK_TAG_RE = re.compile(r"(?i)</p\s*>|<br\s*/?>")
_TAG_RE = re.compile(r"<[^>]+>")
# KIPRIS auth params are sent in the query string, so upstream/httpx error
# strings (which echo the request URL) can leak the API key. Redact them.
_SECRET_QUERY_RE = re.compile(r"(?i)((?:accessKey|ServiceKey)=)[^&\s'\"]+")


class KiprisError(Exception):
    """Raised when a KIPRIS request fails or returns malformed XML."""


class KiprisNotConfiguredError(KiprisError):
    """Raised when the platform-owned KIPRIS credential is unavailable."""


class KiprisRetryableError(KiprisError):
    """Raised after a temporary KIPRIS failure exhausts request retries."""


class KiprisTimeoutError(KiprisRetryableError):
    """Raised after a KIPRIS timeout or the caller's search deadline."""


PatentDomesticSearchMode = Literal["auto", "word", "advanced"]

# KIPRIS collections intentionally exposed by the generic patent search
# contract. Callers must opt into every jurisdiction; the client never adds a
# jurisdiction, applicant, classification, or keyword on their behalf.
SUPPORTED_PATENT_SEARCH_COUNTRIES = frozenset({"KR", "US", "EP", "CN", "JP", "WO"})


def _request_timeout(deadline_monotonic: float | None = None) -> httpx.Timeout:
    remaining = None if deadline_monotonic is None else deadline_monotonic - time.monotonic()
    if remaining is not None and remaining <= 0:
        raise KiprisTimeoutError("KIPRIS 검색 제한 시간을 초과했습니다.")
    read_timeout = (
        _READ_TIMEOUT_SECONDS
        if remaining is None
        else max(0.001, min(_READ_TIMEOUT_SECONDS, remaining))
    )
    connect_timeout = (
        _CONNECT_TIMEOUT_SECONDS
        if remaining is None
        else max(0.001, min(_CONNECT_TIMEOUT_SECONDS, remaining))
    )
    return httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=read_timeout,
        pool=connect_timeout,
    )


def _wait_before_retry(attempt: int, *, deadline_monotonic: float | None) -> None:
    delay = float(2**attempt)
    if deadline_monotonic is not None:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise KiprisTimeoutError("KIPRIS 검색 제한 시간을 초과했습니다.")
        delay = min(delay, remaining)
    time.sleep(delay)


def _normalise_string_values(
    values: tuple[str, ...],
    *,
    field_name: str,
    uppercase: bool = False,
    max_items: int = _MAX_SEARCH_FILTER_VALUES,
    max_chars: int = _MAX_SEARCH_FILTER_CHARS,
) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string.")
    if len(values) > max_items:
        raise ValueError(f"{field_name} must contain at most {max_items} values.")

    normalised: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must contain only strings.")
        cleaned = value.strip()
        if not cleaned:
            continue
        if len(cleaned) > max_chars:
            raise ValueError(f"{field_name} values must be at most {max_chars} characters.")
        if uppercase:
            cleaned = cleaned.upper()
        if cleaned not in seen:
            normalised.append(cleaned)
            seen.add(cleaned)
            if len(normalised) > max_items:
                raise ValueError(f"{field_name} must contain at most {max_items} values.")
    return tuple(normalised)


@dataclass(frozen=True, slots=True)
class PatentSearchCriteria:
    """Caller-owned search criteria for one or more KIPRIS jurisdictions.

    ``domestic_search_mode="auto"`` uses the simple Korean word endpoint when
    only ``query`` is supplied, and the Korean advanced endpoint when an IPC or
    applicant filter is supplied. Foreign collections always use their advanced
    endpoint. No implicit domain terms, companies, or jurisdictions are added.
    """

    query: str
    countries: tuple[str, ...]
    classification_codes: tuple[str, ...] = ()
    applicants: tuple[str, ...] = ()
    domestic_search_mode: PatentDomesticSearchMode = "auto"

    def __post_init__(self) -> None:
        if not isinstance(self.query, str):
            raise TypeError("query must be a string.")
        query = self.query.strip()
        if not query:
            raise ValueError("query must not be empty.")
        if len(query) > _MAX_SEARCH_QUERY_CHARS:
            raise ValueError(f"query must be at most {_MAX_SEARCH_QUERY_CHARS} characters.")

        countries = _normalise_string_values(
            self.countries,
            field_name="countries",
            uppercase=True,
            max_items=len(SUPPORTED_PATENT_SEARCH_COUNTRIES),
            max_chars=8,
        )
        if not countries:
            raise ValueError("countries must contain at least one jurisdiction.")
        unsupported = sorted(set(countries) - SUPPORTED_PATENT_SEARCH_COUNTRIES)
        if unsupported:
            raise ValueError(f"Unsupported KIPRIS country code(s): {', '.join(unsupported)}")

        classification_codes = _normalise_string_values(
            self.classification_codes,
            field_name="classification_codes",
            uppercase=True,
        )
        applicants = _normalise_string_values(
            self.applicants,
            field_name="applicants",
        )
        if self.domestic_search_mode not in {"auto", "word", "advanced"}:
            raise ValueError("domestic_search_mode must be one of: auto, word, advanced.")
        if (
            "KR" in countries
            and self.domestic_search_mode == "word"
            and (classification_codes or applicants)
        ):
            raise ValueError(
                "domestic word search cannot apply classification_codes or applicants."
            )

        object.__setattr__(self, "query", query)
        object.__setattr__(self, "countries", countries)
        object.__setattr__(self, "classification_codes", classification_codes)
        object.__setattr__(self, "applicants", applicants)


@dataclass(frozen=True, slots=True)
class PatentSearchResult:
    """Provider-neutral patent search projection.

    ``provider_document_id`` is the opaque KIPRIS identifier needed for later
    enrichment. Provider response dictionaries are deliberately not exposed.
    """

    canonical_number: str
    publication_number: str
    application_number: str
    title: str
    abstract: str
    applicants: tuple[str, ...]
    jurisdiction: str
    ipc_codes: tuple[str, ...]
    filing_date: date | None
    publication_date: date | None
    external_url: str
    provider_document_id: str


@dataclass(frozen=True, slots=True)
class PatentSearchJurisdictionPage:
    jurisdiction: str
    total_count: int
    returned_count: int
    has_next: bool


@dataclass(frozen=True, slots=True)
class PatentSearchPage:
    """One logical page per requested jurisdiction, in caller-supplied order.

    ``page_size`` is a per-jurisdiction limit. A multi-jurisdiction response may
    therefore contain up to ``page_size * len(jurisdictions)`` results.
    """

    results: tuple[PatentSearchResult, ...]
    page: int
    page_size: int
    total_count: int
    jurisdictions: tuple[PatentSearchJurisdictionPage, ...]
    has_next: bool


def _is_local_http_host(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _strip_markup(text: str) -> str:
    """Remove KIPRIS inline markup (``<P>``/``</P>``/``<BR>`` etc.) from text.

    Claim/abstract fields from KIPRIS embed pseudo-HTML paragraph tags. Convert
    block tags to newlines, drop the rest, and normalise whitespace so the text
    renders cleanly.
    """
    if not text:
        return text
    text = html.unescape(text)
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _text(item: ET.Element, tag: str) -> str:
    return (item.findtext(tag) or "").strip()


def _parse_item(item: ET.Element) -> dict[str, str]:
    return {
        "app_no": _text(item, "applicationNumber"),
        "reg_no": _text(item, "registrationNumber"),
        "title": _text(item, "inventionTitle"),
        "applicant": _text(item, "applicantName"),
        "date": _text(item, "applicationDate"),
        "status": _text(item, "registerStatus"),
        "ipc": _text(item, "ipcNumber"),
        "abstract": _strip_markup(_text(item, "astrtCont")),
    }


def _first_text(item: ET.Element, *tags: str) -> str:
    for tag in tags:
        value = _text(item, tag)
        if value:
            return value
    return ""


def _bounded_provider_text(value: str, *, max_chars: int) -> str:
    """Bound one provider field before it enters an aggregated result page."""

    return (value or "")[:max_chars].strip()


def _bounded_provider_markup_text(value: str, *, max_chars: int) -> str:
    # Inline markup consumes part of the raw field, so permit a small bounded
    # amount of markup overhead while keeping the projected text strictly capped.
    bounded_source = (value or "")[: max_chars * 2]
    return _strip_markup(bounded_source)[:max_chars].strip()


def _split_provider_values(
    value: str,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[str, ...]:
    # Slice before splitting so one malformed upstream list cannot create an
    # unbounded collection or retain an oversized remainder.
    bounded_source = (value or "")[: max_items * (max_chars + 1)]
    values: list[str] = []
    for part in re.split(r"[|;\n]+", bounded_source):
        cleaned = _bounded_provider_text(part, max_chars=max_chars)
        if cleaned:
            values.append(cleaned)
        if len(values) >= max_items:
            break
    return tuple(values)


def _parse_provider_date(value: str) -> date | None:
    digits = re.sub(
        r"[^0-9]",
        "",
        _bounded_provider_text(value, max_chars=32),
    )
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _parse_total_count(root: ET.Element) -> int | None:
    for path in (".//count/totalCount", ".//totalCount", ".//totalSearchCount"):
        raw = root.findtext(path)
        if raw:
            normalized = _bounded_provider_text(raw, max_chars=32).replace(",", "")
            if normalized.isdigit() and len(normalized) > 10:
                return _MAX_SEARCH_TOTAL_COUNT
            try:
                return max(0, min(int(normalized), _MAX_SEARCH_TOTAL_COUNT))
            except ValueError:
                continue
    return None


def _canonical_number(jurisdiction: str, value: str) -> str:
    compact = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    if not compact:
        return ""
    country = jurisdiction.upper()
    return compact if compact.startswith(country) else f"{country}{compact}"


def _foreign_kind_code(provider_document_id: str) -> str:
    match = re.search(r"([A-Z]\d?)$", (provider_document_id or "").strip().upper())
    return match.group(1) if match else ""


def _foreign_provider_publication_number(provider_document_id: str) -> str:
    """Recover an unpadded publication number and kind from KIPRIS ``ltrtno``."""

    match = re.fullmatch(
        r"0*([0-9]+)([A-Z]\d?)",
        (provider_document_id or "").strip().upper(),
    )
    if not match:
        return ""
    return f"{match.group(1)}{match.group(2)}"


def _parse_domestic_search_result(item: ET.Element) -> PatentSearchResult:
    application_number = _bounded_provider_text(
        _text(item, "applicationNumber"),
        max_chars=_MAX_SEARCH_NUMBER_CHARS,
    )
    publication_number = _bounded_provider_text(
        _first_text(
            item,
            "openNumber",
            "publicationNumber",
            "registrationNumber",
            "registerNumber",
        ),
        max_chars=_MAX_SEARCH_NUMBER_CHARS,
    )
    canonical_number = _bounded_provider_text(
        _canonical_number("KR", publication_number or application_number),
        max_chars=_MAX_SEARCH_IDENTIFIER_CHARS,
    )
    application_digits = re.sub(r"[^0-9]", "", application_number)
    external_url = (
        f"https://doi.org/10.8080/{application_digits}"
        if application_digits
        else (f"https://patents.google.com/patent/{canonical_number}" if canonical_number else "")
    )
    return PatentSearchResult(
        canonical_number=canonical_number,
        publication_number=publication_number,
        application_number=application_number,
        title=_bounded_provider_text(
            _text(item, "inventionTitle"),
            max_chars=_MAX_SEARCH_TITLE_CHARS,
        ),
        abstract=_bounded_provider_markup_text(
            _text(item, "astrtCont"),
            max_chars=_MAX_SEARCH_ABSTRACT_CHARS,
        ),
        applicants=_split_provider_values(
            _text(item, "applicantName"),
            max_items=_MAX_SEARCH_APPLICANTS,
            max_chars=_MAX_SEARCH_APPLICANT_CHARS,
        ),
        jurisdiction="KR",
        ipc_codes=_split_provider_values(
            _text(item, "ipcNumber"),
            max_items=_MAX_SEARCH_CLASSIFICATIONS,
            max_chars=_MAX_SEARCH_CLASSIFICATION_CHARS,
        ),
        filing_date=_parse_provider_date(_text(item, "applicationDate")),
        publication_date=_parse_provider_date(
            _first_text(item, "openDate", "publicationDate", "registrationDate")
        ),
        external_url=_bounded_provider_text(
            external_url,
            max_chars=_MAX_SEARCH_URL_CHARS,
        ),
        provider_document_id=_bounded_provider_text(
            application_number or publication_number,
            max_chars=_MAX_SEARCH_IDENTIFIER_CHARS,
        ),
    )


def _parse_foreign_search_result(
    item: ET.Element,
    *,
    requested_country: str,
) -> PatentSearchResult:
    provider_document_id = _bounded_provider_text(
        _first_text(item, "ltrtno", "vdkVgwKey"),
        max_chars=_MAX_SEARCH_IDENTIFIER_CHARS,
    )
    provider_country = _bounded_provider_text(
        _text(item, "countryCode"),
        max_chars=_MAX_SEARCH_JURISDICTION_CHARS,
    ).upper()
    jurisdiction = (
        provider_country
        if provider_country in SUPPORTED_PATENT_SEARCH_COUNTRIES
        else requested_country
    )
    application_number = _bounded_provider_text(
        _text(item, "applicationNo"),
        max_chars=_MAX_SEARCH_NUMBER_CHARS,
    )
    publication_number = _bounded_provider_text(
        _first_text(item, "publishrNo", "openNumber", "openNo"),
        max_chars=_MAX_SEARCH_NUMBER_CHARS,
    )

    publication_for_canonical = publication_number
    kind_code = _foreign_kind_code(provider_document_id)
    if (
        publication_for_canonical
        and kind_code
        and not publication_for_canonical.upper().endswith(kind_code)
    ):
        publication_for_canonical = f"{publication_for_canonical}{kind_code}"
    if not publication_for_canonical:
        publication_for_canonical = _foreign_provider_publication_number(provider_document_id)
    canonical_number = _bounded_provider_text(
        _canonical_number(
            jurisdiction,
            publication_for_canonical or application_number,
        ),
        max_chars=_MAX_SEARCH_IDENTIFIER_CHARS,
    )
    external_url = (
        f"https://patents.google.com/patent/{canonical_number}" if canonical_number else ""
    )

    return PatentSearchResult(
        canonical_number=canonical_number,
        publication_number=publication_number,
        application_number=application_number,
        title=_bounded_provider_text(
            _first_text(item, "inventionName", "inventionTitle"),
            max_chars=_MAX_SEARCH_TITLE_CHARS,
        ),
        abstract=_bounded_provider_markup_text(
            _first_text(item, "astrtCont", "abstract"),
            max_chars=_MAX_SEARCH_ABSTRACT_CHARS,
        ),
        applicants=_split_provider_values(
            _first_text(item, "applicant", "applicantName"),
            max_items=_MAX_SEARCH_APPLICANTS,
            max_chars=_MAX_SEARCH_APPLICANT_CHARS,
        ),
        jurisdiction=jurisdiction,
        ipc_codes=_split_provider_values(
            _first_text(item, "ipc", "ipcNumber"),
            max_items=_MAX_SEARCH_CLASSIFICATIONS,
            max_chars=_MAX_SEARCH_CLASSIFICATION_CHARS,
        ),
        filing_date=_parse_provider_date(_text(item, "applicationDate")),
        publication_date=_parse_provider_date(
            _first_text(item, "openDate", "publicationDate", "registerDate")
        ),
        external_url=_bounded_provider_text(
            external_url,
            max_chars=_MAX_SEARCH_URL_CHARS,
        ),
        provider_document_id=_bounded_provider_text(
            provider_document_id or application_number or publication_number,
            max_chars=_MAX_SEARCH_IDENTIFIER_CHARS,
        ),
    )


# KIPRIS has a Korea-only DB (patUtiModInfoSearchSevice) and a separate foreign
# service (ForeignPatent*). A foreign number sent to the Korean DB mis-matches on
# stray digits, so detect the country and route to the foreign service instead.
_FOREIGN_PREFIX_RE = re.compile(r"^([A-Z]{2})\s*[-/]?\s*\d")

# Foreign services share the same host as the Korean base URL, different path.
_FOREIGN_ADV_PATH = "/openapi/rest/ForeignPatentAdvencedSearchService/advancedSearch"
_FOREIGN_BIBLIO_PATH = "/openapi/rest/ForeignPatentBibliographicService/bibliographicInfo"


def detect_foreign_country(num: str) -> str | None:
    """Return the foreign country code (EP/US/CN/JP/WO ...) if ``num`` starts with
    one, else None. ``KR`` is treated as a normal domestic input (returns None)."""
    s = (num or "").strip().upper()
    m = _FOREIGN_PREFIX_RE.match(s)
    if m and m.group(1) != "KR":
        return m.group(1)
    return None


def _foreign_core_digits(num_raw: str) -> str:
    """Strip the country code and document-kind code, return the serial digits.

    ``EP 4 344 910 B1`` -> ``4344910`` (the ``1`` from kind code ``B1`` must not
    leak into the serial number)."""
    s = num_raw.strip().upper()
    s = re.sub(r"^[A-Z]{2}\s*", "", s)  # country code
    s = re.sub(r"\s*[A-Z]\d*$", "", s)  # document-kind code (B1, A1, ...)
    return re.sub(r"[^0-9]", "", s)


def foreign_google_patents_url(country: str, num_raw: str) -> str:
    """Build a Google Patents direct link, e.g. ``EP 4 344 910 B1`` -> ``EP4344910B1``."""
    digits = _foreign_core_digits(num_raw)
    km = re.search(r"([AB]\d?|[UY]\d?)\s*$", num_raw.strip().upper())
    kind = km.group(1) if km else ""
    return f"https://patents.google.com/patent/{country}{digits}{kind}"


def _split_foreign_claims(claims_text: str) -> list[str]:
    """Split English claim text on leading ``1.``/``2.`` markers; whole if none."""
    if not claims_text:
        return []
    parts = re.split(r"(?=(?:^|\n)\s*\d{1,3}\s*[.)])", claims_text)
    claims = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
    return claims or [claims_text.strip()]


_GOOGLE_CLAIMS_BLOCK_RE = re.compile(r"<claims\b[^>]*>(.*?)</claims>", re.S)
_GOOGLE_CLAIM_RE = re.compile(r'<claim\b[^>]*\bnum="?(\w+)"?[^>]*>(.*?)</claim>', re.S)
_GOOGLE_SRC_TEXT_RE = re.compile(r'<span[^>]*class="google-src-text"[^>]*>.*?</span>', re.S)


def fetch_google_patents_claims(google_url: str, *, timeout: float = 20.0) -> list[str]:
    """Best-effort claim scrape from Google Patents for foreign docs whose claims
    KIPRIS does not carry (WO/PCT etc.).

    Parses the English page's ``<claims><claim num><claim-text>`` structure,
    stripping the embedded source-language span (``google-src-text``). Returns
    ``[]`` on any failure — the caller falls back to the abstract."""
    url = google_url.rstrip("/")
    if not url.endswith("/en"):
        url += "/en"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    }
    try:
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        if response.status_code != 200:
            return []
        block_match = _GOOGLE_CLAIMS_BLOCK_RE.search(response.text)
        if not block_match:
            return []
        claims: list[str] = []
        for cm in _GOOGLE_CLAIM_RE.finditer(block_match.group(1)):
            num, body = cm.group(1), cm.group(2)
            body = _GOOGLE_SRC_TEXT_RE.sub("", body)
            text = re.sub(r"<[^>]+>", " ", body)
            text = re.sub(r"\s+", " ", html.unescape(text)).strip()
            if text:
                claims.append(f"{num}. {text}")
        return claims
    except (httpx.HTTPError, ValueError):
        return []


def _normalize_patent_number(num: str) -> str:
    num = num.strip().upper()
    num = re.sub(r"^KR\s*", "", num)
    num = re.sub(r"\s*[A-Z]\d*$", "", num)  # drop document-kind code (B1, A1, ...)
    return num.strip()


def _extract_search_numbers(num: str) -> list[str]:
    cleaned = _normalize_patent_number(num)
    candidates = [cleaned]
    no_dash = cleaned.replace("-", "")
    if no_dash != cleaned:
        candidates.append(no_dash)
    digits_only = re.sub(r"[^0-9]", "", cleaned)
    if digits_only and digits_only not in candidates:
        candidates.append(digits_only)
    m = re.match(r"^10[-\s]*(\d{5,})$", cleaned)
    if m and m.group(1) not in candidates:
        candidates.append(m.group(1))
    return candidates


def _to_13digit_reg(num: str) -> str:
    digits = re.sub(r"[^0-9]", "", num)
    if len(digits) < 13:
        digits = digits.ljust(13, "0")
    return digits[:13]


class KiprisClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    def _scrub(self, text: str) -> str:
        """Strip the API key from an error string before it reaches users."""
        cleaned = _SECRET_QUERY_RE.sub(r"\1***", text)
        if self.api_key:
            for secret_form in {
                self.api_key,
                quote(self.api_key, safe=""),
                quote_plus(self.api_key, safe=""),
            }:
                cleaned = cleaned.replace(secret_form, "***")
        return cleaned

    @property
    def _host_root(self) -> str:
        """Scheme+host of the configured base URL (foreign services live on the
        same host but under a different path: ``/openapi/rest/ForeignPatent*``)."""
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _validate_transport(self, url: str | None = None) -> None:
        parsed = urlparse(url or self.base_url)
        if parsed.scheme == "https":
            return
        if parsed.scheme == "http" and _is_local_http_host(parsed.hostname):
            return
        raise KiprisError("KIPRIS base URL must use HTTPS.")

    def _get_abs(
        self,
        url: str,
        params: dict[str, Any],
        *,
        deadline_monotonic: float | None = None,
    ) -> ET.Element:
        self._validate_transport(url)
        operation_deadline = (
            deadline_monotonic
            if deadline_monotonic is not None
            else time.monotonic() + _SYNC_OPERATION_TIMEOUT_SECONDS
        )
        response: httpx.Response | None = None
        for attempt in range(_MAX_REQUEST_RETRIES + 1):
            try:
                response = httpx.get(
                    url,
                    params=params,
                    timeout=_request_timeout(operation_deadline),
                    verify=True,
                )
                response.raise_for_status()
                if time.monotonic() >= operation_deadline:
                    raise KiprisTimeoutError("KIPRIS 검색 제한 시간을 초과했습니다.")
                break
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                if status_code in _RETRYABLE_HTTP_STATUSES and attempt < _MAX_REQUEST_RETRIES:
                    _wait_before_retry(
                        attempt,
                        deadline_monotonic=operation_deadline,
                    )
                    continue
                # ``str(error)`` includes the complete request URL. KIPRIS sends
                # credentials and private search values through query parameters,
                # so only retain non-sensitive status metadata.
                error_type = (
                    KiprisRetryableError if status_code in _RETRYABLE_HTTP_STATUSES else KiprisError
                )
                raise error_type(f"KIPRIS 요청 실패 (HTTP {status_code}).") from error
            except httpx.TimeoutException as error:
                if attempt < _MAX_REQUEST_RETRIES:
                    _wait_before_retry(
                        attempt,
                        deadline_monotonic=operation_deadline,
                    )
                    continue
                raise KiprisTimeoutError("KIPRIS 요청 시간이 초과되었습니다.") from error
            except httpx.HTTPError as error:
                raise KiprisError(f"KIPRIS 요청 실패 ({type(error).__name__}).") from error
        if response is None:  # pragma: no cover - loop exits through response or exception
            raise KiprisError("KIPRIS 요청에 실패했습니다.")
        try:
            return ET.fromstring(response.text)
        except ET.ParseError as error:
            raise KiprisError(f"KIPRIS 응답 파싱 실패: {self._scrub(str(error))}") from error

    def _get(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        deadline_monotonic: float | None = None,
    ) -> ET.Element:
        return self._get_abs(
            f"{self.base_url}/{endpoint}",
            params,
            deadline_monotonic=deadline_monotonic,
        )

    def _get_search_abs(
        self,
        url: str,
        params: dict[str, Any],
        *,
        deadline_monotonic: float | None = None,
    ) -> ET.Element:
        """Read a generic-search XML response with a strict streaming cap."""

        self._validate_transport(url)
        body: bytearray | None = None
        for attempt in range(_MAX_REQUEST_RETRIES + 1):
            try:
                with httpx.stream(
                    "GET",
                    url,
                    params=params,
                    timeout=_request_timeout(deadline_monotonic),
                    verify=True,
                ) as response:
                    response.raise_for_status()
                    raw_length = response.headers.get("content-length")
                    if (
                        raw_length
                        and raw_length.isdigit()
                        and int(raw_length) > _MAX_SEARCH_XML_BYTES
                    ):
                        raise KiprisError("KIPRIS 응답 크기 제한을 초과했습니다.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if (
                            deadline_monotonic is not None
                            and time.monotonic() >= deadline_monotonic
                        ):
                            raise KiprisTimeoutError("KIPRIS 검색 제한 시간을 초과했습니다.")
                        body.extend(chunk)
                        if len(body) > _MAX_SEARCH_XML_BYTES:
                            raise KiprisError("KIPRIS 응답 크기 제한을 초과했습니다.")
                break
            except KiprisError:
                raise
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                if status_code in _RETRYABLE_HTTP_STATUSES and attempt < _MAX_REQUEST_RETRIES:
                    _wait_before_retry(
                        attempt,
                        deadline_monotonic=deadline_monotonic,
                    )
                    continue
                error_type = (
                    KiprisRetryableError if status_code in _RETRYABLE_HTTP_STATUSES else KiprisError
                )
                raise error_type(f"KIPRIS 요청 실패 (HTTP {status_code}).") from error
            except httpx.TimeoutException as error:
                if attempt < _MAX_REQUEST_RETRIES:
                    _wait_before_retry(
                        attempt,
                        deadline_monotonic=deadline_monotonic,
                    )
                    continue
                raise KiprisTimeoutError("KIPRIS 요청 시간이 초과되었습니다.") from error
            except httpx.HTTPError as error:
                raise KiprisError(f"KIPRIS 요청 실패 ({type(error).__name__}).") from error

        if body is None:  # pragma: no cover - loop exits through response or exception
            raise KiprisError("KIPRIS 요청에 실패했습니다.")
        try:
            return ET.fromstring(bytes(body))
        except ET.ParseError as error:
            raise KiprisError("KIPRIS 응답 파싱 실패.") from error

    def _get_search(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        deadline_monotonic: float | None = None,
    ) -> ET.Element:
        return self._get_search_abs(
            f"{self.base_url}/{endpoint}",
            params,
            deadline_monotonic=deadline_monotonic,
        )

    def search(
        self,
        criteria: PatentSearchCriteria,
        *,
        page: int = 1,
        page_size: int = _FOREIGN_PROVIDER_PAGE_SIZE,
        deadline_monotonic: float | None = None,
    ) -> PatentSearchPage:
        """Search caller-selected KIPRIS jurisdictions with typed results.

        Results are grouped in the same order as ``criteria.countries``. Page
        size is applied independently to each jurisdiction because KIPRIS has
        separate domestic and foreign indexes and no cross-index ordering.
        """
        if not isinstance(criteria, PatentSearchCriteria):
            raise TypeError("criteria must be a PatentSearchCriteria instance.")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be an integer greater than or equal to 1.")
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= _MAX_SEARCH_PAGE_SIZE
        ):
            raise ValueError(f"page_size must be an integer between 1 and {_MAX_SEARCH_PAGE_SIZE}.")

        results: list[PatentSearchResult] = []
        jurisdiction_pages: list[PatentSearchJurisdictionPage] = []
        for country in criteria.countries:
            if country == "KR":
                country_results, total_count = self._search_domestic_page(
                    criteria,
                    page=page,
                    page_size=page_size,
                    deadline_monotonic=deadline_monotonic,
                )
            else:
                country_results, total_count = self._search_foreign_page(
                    criteria,
                    country=country,
                    page=page,
                    page_size=page_size,
                    deadline_monotonic=deadline_monotonic,
                )
            results.extend(country_results)
            jurisdiction_pages.append(
                PatentSearchJurisdictionPage(
                    jurisdiction=country,
                    total_count=total_count,
                    returned_count=len(country_results),
                    has_next=page * page_size < total_count,
                )
            )

        return PatentSearchPage(
            results=tuple(results),
            page=page,
            page_size=page_size,
            total_count=min(
                sum(item.total_count for item in jurisdiction_pages),
                _MAX_SEARCH_TOTAL_COUNT,
            ),
            jurisdictions=tuple(jurisdiction_pages),
            has_next=any(item.has_next for item in jurisdiction_pages),
        )

    def _search_domestic_page(
        self,
        criteria: PatentSearchCriteria,
        *,
        page: int,
        page_size: int,
        deadline_monotonic: float | None,
    ) -> tuple[list[PatentSearchResult], int]:
        advanced = criteria.domestic_search_mode == "advanced" or (
            criteria.domestic_search_mode == "auto"
            and bool(criteria.classification_codes or criteria.applicants)
        )
        params: dict[str, Any] = {
            "accessKey": self.api_key,
            "ServiceKey": self.api_key,
            "pageNo": page,
            "numOfRows": page_size,
        }
        if advanced:
            endpoint = "getAdvancedSearch"
            params["astrtCont"] = criteria.query
            if criteria.classification_codes:
                params["ipcNumber"] = "|".join(criteria.classification_codes)
            if criteria.applicants:
                params["applicantName"] = "|".join(criteria.applicants)
        else:
            endpoint = "getWordSearch"
            params["word"] = criteria.query

        root = self._get_search(
            endpoint,
            params,
            deadline_monotonic=deadline_monotonic,
        )
        items = root.findall(".//item")[:page_size]
        results = [_parse_domestic_search_result(item) for item in items]
        total_count = _parse_total_count(root)
        if total_count is None:
            total_count = (page - 1) * page_size + len(items)
        return results, total_count

    def _search_foreign_page(
        self,
        criteria: PatentSearchCriteria,
        *,
        country: str,
        page: int,
        page_size: int,
        deadline_monotonic: float | None,
    ) -> tuple[list[PatentSearchResult], int]:
        """Translate a logical page to KIPRIS's 30-row, one-based offsets."""
        logical_start = (page - 1) * page_size
        logical_end = logical_start + page_size
        provider_start = (
            logical_start // _FOREIGN_PROVIDER_PAGE_SIZE
        ) * _FOREIGN_PROVIDER_PAGE_SIZE
        total_count: int | None = None
        results: list[PatentSearchResult] = []
        advanced_url = f"{self._host_root}{_FOREIGN_ADV_PATH}"

        while provider_start < logical_end:
            params: dict[str, Any] = {
                "free": criteria.query,
                "collectionValues": country,
                "currentPage": provider_start + 1,
                "sortField": "AD",
                "sortState": "true",
                "accessKey": self.api_key,
            }
            if criteria.classification_codes:
                params["ipc"] = "+".join(criteria.classification_codes)
            if criteria.applicants:
                params["applicant"] = "+".join(criteria.applicants)

            root = self._get_search_abs(
                advanced_url,
                params,
                deadline_monotonic=deadline_monotonic,
            )
            if total_count is None:
                total_count = _parse_total_count(root)
            provider_items = root.findall(".//searchResult")
            for index, item in enumerate(provider_items):
                absolute_index = provider_start + index
                if logical_start <= absolute_index < logical_end:
                    results.append(
                        _parse_foreign_search_result(
                            item,
                            requested_country=country,
                        )
                    )

            if len(provider_items) < _FOREIGN_PROVIDER_PAGE_SIZE:
                break
            provider_start += _FOREIGN_PROVIDER_PAGE_SIZE

        if total_count is None:
            total_count = logical_start + len(results)
        return results, total_count

    def word_search(
        self,
        word: str,
        *,
        page: int = 1,
        num_rows: int = 15,
        deadline_monotonic: float | None = None,
    ) -> tuple[list[dict[str, str]], int]:
        """getWordSearch — keyword search. Returns (items, total_count)."""
        root = self._get(
            "getWordSearch",
            {
                "word": word,
                "accessKey": self.api_key,
                "ServiceKey": self.api_key,
                "pageNo": page,
                "numOfRows": num_rows,
            },
            deadline_monotonic=deadline_monotonic,
        )
        items = [_parse_item(it) for it in root.findall(".//item")]
        total = int(root.findtext(".//totalCount") or 0)
        return items, total

    def applicant_names(
        self,
        word: str,
        *,
        page: int = 1,
        num_rows: int = 30,
        deadline_monotonic: float | None = None,
    ) -> list[str]:
        """Applicant names on one getWordSearch page (for top-applicant aggregation)."""
        root = self._get(
            "getWordSearch",
            {
                "word": word,
                "accessKey": self.api_key,
                "ServiceKey": self.api_key,
                "pageNo": page,
                "numOfRows": num_rows,
            },
            deadline_monotonic=deadline_monotonic,
        )
        names = []
        for item in root.findall(".//item"):
            name = _text(item, "applicantName")
            if name:
                names.append(name)
        return names

    def fetch_full(self, patent_number: str) -> dict[str, Any] | None:
        """Resolve a patent number to bibliography + claims (no PDF in v1)."""
        candidates = _extract_search_numbers(patent_number)
        item: ET.Element | None = None
        app_no = ""

        # 1) getAdvancedSearch by application/open/publication/registration number.
        for num in candidates:
            if item is not None:
                break
            digit_only = re.sub(r"[^0-9]", "", num)
            if not digit_only:
                continue
            for field, val in (
                ("applicationNumber", digit_only),
                ("openNumber", digit_only),
                ("publicationNumber", digit_only),
                ("registerNumber", _to_13digit_reg(num)),
            ):
                if not val:
                    continue
                try:
                    root = self._get(
                        "getAdvancedSearch",
                        {"ServiceKey": self.api_key, field: val, "numOfRows": 1},
                    )
                except KiprisError:
                    continue
                found = root.find(".//item")
                if found is not None:
                    item = found
                    app_no = _text(found, "applicationNumber")
                    break

        # 2) keyword-search fallback — digit-only candidates only.
        #    Passing a string like "EP 4 344 910" as ``word`` makes KIPRIS treat
        #    it as free text, so a stray numeric token matches an unrelated patent
        #    (e.g. "넥틴-4"). Restrict to pure digits and verify the hit.
        if item is None:
            for num in candidates:
                digit_only = re.sub(r"[^0-9]", "", num)
                if not digit_only or digit_only != num.replace("-", "").replace(" ", ""):
                    continue
                try:
                    root = self._get(
                        "getWordSearch",
                        {"word": digit_only, "ServiceKey": self.api_key, "numOfRows": 1},
                    )
                except KiprisError:
                    continue
                found = root.find(".//item")
                if found is not None:
                    nums_blob = "".join(
                        re.sub(r"[^0-9]", "", _text(found, tag))
                        for tag in (
                            "applicationNumber",
                            "openNumber",
                            "publicationNumber",
                            "registrationNumber",
                        )
                    )
                    if digit_only in nums_blob:
                        item = found
                        app_no = _text(found, "applicationNumber")
                        break

        if item is None:
            return None

        result: dict[str, Any] = {
            "app_no": app_no or _text(item, "applicationNumber"),
            "reg_no": _text(item, "registrationNumber"),
            "open_no": _text(item, "openNumber"),
            "pub_no": _text(item, "publicationNumber"),
            "title": _text(item, "inventionTitle"),
            "applicant": _text(item, "applicantName"),
            "date": _text(item, "applicationDate"),
            "status": _text(item, "registerStatus"),
            "ipc": _text(item, "ipcNumber"),
            "abstract": _strip_markup(_text(item, "astrtCont")),
            "claims": [],
            "description": "",
        }

        # 3) getBibliographyDetailInfoSearch — claims + richer bibliography.
        if result["app_no"]:
            try:
                detail = self._get(
                    "getBibliographyDetailInfoSearch",
                    {"applicationNumber": result["app_no"], "ServiceKey": self.api_key},
                )
            except KiprisError:
                detail = None
            if detail is not None:
                claims = []
                for ci in detail.findall(".//claimInfo"):
                    claim_text = _strip_markup((ci.findtext("claim") or "").strip())
                    if claim_text:
                        claims.append(claim_text)
                if claims:
                    result["claims"] = claims

                abstract = _strip_markup((detail.findtext(".//astrtCont") or "").strip())
                if abstract and len(abstract) > len(result["abstract"]):
                    result["abstract"] = abstract

                title_eng = (detail.findtext(".//inventionTitleEng") or "").strip()
                if title_eng:
                    result["title_eng"] = title_eng

                applicants = [
                    name
                    for ai in detail.findall(".//applicantInfo")
                    if (name := (ai.findtext("applicantName") or "").strip())
                ]
                if applicants:
                    result["applicant"] = ", ".join(applicants)

                ipcs = [
                    ipc
                    for ii in detail.findall(".//ipcInfo")
                    if (ipc := (ii.findtext("ipcNumber") or "").strip())
                ]
                if ipcs:
                    result["ipc"] = ", ".join(ipcs)

                for src, dst in (
                    ("registerDate", "reg_date"),
                    ("openDate", "open_date"),
                    ("publicationDate", "pub_date"),
                    ("finalDisposal", "final_disposal"),
                ):
                    val = (detail.findtext(f".//{src}") or "").strip()
                    if val:
                        result[dst] = val

        # Claims fallback to abstract so downstream analysis still has input.
        if not result["claims"] and result["abstract"]:
            result["claims"] = [result["abstract"]]
            result["warning"] = "청구항을 가져올 수 없어 초록만 표시합니다."

        return result

    def fetch_foreign_full(self, patent_number: str, country: str) -> dict[str, Any]:
        """Resolve a foreign patent number via the KIPRIS foreign services.

        Returns a result dict shaped like :meth:`fetch_full`, or an error dict
        ``{"error": "foreign_not_found", "country", "google_patents_url"}`` when
        the number can't be resolved (KIPRIS foreign coverage indexes by WO/PCT
        and country-specific numbers, so e.g. EP grant numbers may not match)."""
        google = foreign_google_patents_url(country, patent_number)
        not_found: dict[str, Any] = {
            "error": "foreign_not_found",
            "country": country,
            "google_patents_url": google,
        }

        digits = _foreign_core_digits(patent_number)
        if not digits:
            return not_found

        adv_url = f"{self._host_root}{_FOREIGN_ADV_PATH}"
        bib_url = f"{self._host_root}{_FOREIGN_BIBLIO_PATH}"

        # 1) Resolve number -> ltrtno via the foreign advanced search. KIPRIS's
        #    foreign number search behaves differently per country/format (e.g.
        #    WO matches free="WO<digits>" exactly, while US/CN only match bare
        #    digits), so try several (field, query) attempts in order and verify
        #    the searched digits actually appear in the returned document number.
        attempts = (
            ("applicationNo", digits),
            ("registerNo", digits),
            ("openNo", digits),
            ("internationalOpenNo", digits),
            ("free", f"{country}{digits}"),  # WO etc.: country+number → exact n=1
            ("free", digits),  # US/CN etc.: bare digits (fallback)
        )
        found: ET.Element | None = None
        for field, query in attempts:
            try:
                root = self._get_abs(
                    adv_url,
                    {
                        field: query,
                        "collectionValues": country,
                        "accessKey": self.api_key,
                        "currentPage": 1,
                    },
                )
            except KiprisError:
                continue
            for sr in root.findall(".//searchResult"):
                blob = "".join(
                    re.sub(r"[^0-9]", "", _text(sr, tag))
                    for tag in ("ltrtno", "publishrNo", "registerNo", "applicationNo", "openNumber")
                )
                if digits in blob:
                    found = sr
                    break
            if found is not None:
                break

        if found is None:
            return not_found

        ltrtno = _text(found, "ltrtno")
        cc = (_text(found, "countryCode") or country).upper()
        result: dict[str, Any] = {
            "app_no": _text(found, "applicationNo"),
            "reg_no": _text(found, "registerNo"),
            "open_no": _text(found, "openNumber") or _text(found, "openNo"),
            "pub_no": _text(found, "publishrNo"),
            "title": _text(found, "inventionName"),
            "applicant": _text(found, "applicant"),
            "date": _text(found, "applicationDate"),
            "ipc": _text(found, "ipc"),
            "abstract": "",
            "claims": [],
            "description": "",
            "foreign": True,
            "google_patents_url": google,
        }

        # 2) Enrich abstract / claims / IPC via the foreign bibliographic service.
        if ltrtno:
            try:
                bib = self._get_abs(
                    bib_url,
                    {"literatureNumber": ltrtno, "countryCode": cc, "accessKey": self.api_key},
                )
            except KiprisError:
                bib = None
            if bib is not None:
                abstract = _strip_markup((bib.findtext(".//astrtCont") or "").strip())
                if abstract:
                    result["abstract"] = abstract
                claims_text = _strip_markup((bib.findtext(".//claimText") or "").strip())
                if claims_text:
                    result["claims"] = _split_foreign_claims(claims_text)
                ipcs = [
                    code
                    for el in bib.findall(".//ipcInfo/ipcCd")
                    if (code := (el.text or "").strip())
                ]
                if ipcs:
                    result["ipc"] = ", ".join(ipcs)

        # Hybrid: KIPRIS doesn't carry claims for some foreign docs (WO/PCT) —
        # scrape them from Google Patents, then fall back to abstract if that fails.
        if result["claims"]:
            result["claims_source"] = "kipris"
        else:
            google_claims = fetch_google_patents_claims(google)
            if google_claims:
                result["claims"] = google_claims
                result["claims_source"] = "google_patents"
            elif result["abstract"]:
                result["claims"] = [result["abstract"]]
                result["claims_source"] = "abstract_fallback"
                result["warning"] = (
                    "KIPRIS가 이 해외 문헌의 청구항을 제공하지 않고 Google Patents "
                    f"보강도 실패하여 초록만 표시합니다. 원문: {google}"
                )

        if not result["title"] and not result["abstract"]:
            return not_found

        return result

    def resolve_view_urls(self, app_no: str) -> dict[str, str]:
        """Build Google Patents + KIPRIS web URLs for an application number."""
        clean_app = re.sub(r"[-\s]", "", app_no)

        def _to_google_no(num: str, *, registered: bool) -> str:
            # KIPRIS numbers are ``<doc-type><year><serial>`` where the doc-type
            # code is ``10`` for patents and ``20`` for utility models. Google
            # Patents kind codes: patent A (published) / B1 (granted), utility
            # model U (published) / Y1 (granted). Published numbers drop the
            # leading doc-type code; granted numbers drop the trailing padding.
            clean = re.sub(r"[-\s]", "", num)
            utility = clean.startswith("20")
            if registered:
                if clean.endswith("0000") and len(clean) > 9:
                    clean = clean[:-4]
                kind = "Y1" if utility else "B1"
            else:
                if (clean.startswith("10") or clean.startswith("20")) and len(clean) >= 11:
                    clean = clean[2:]
                kind = "U" if utility else "A"
            return f"KR{clean}{kind}"

        google_no = ""
        try:
            root = self._get(
                "getAdvancedSearch",
                {"applicationNumber": clean_app, "ServiceKey": self.api_key, "numOfRows": 1},
            )
            item = root.find(".//item")
            if item is not None:
                reg = _text(item, "registerNumber")
                opn = _text(item, "openNumber")
                pub = _text(item, "publicationNumber")
                if reg:
                    google_no = _to_google_no(reg, registered=True)
                elif opn:
                    google_no = _to_google_no(opn, registered=False)
                elif pub:
                    google_no = _to_google_no(pub, registered=True)
        except KiprisError:
            pass

        if not google_no:
            google_no = _to_google_no(clean_app, registered=False)

        return {
            "pdf_url": f"https://patents.google.com/patent/{google_no}",
            "kipris_url": f"https://kipris.or.kr/khome/main.jsp#term={clean_app}",
            "type": "google_patents",
        }


def get_kipris_client() -> KiprisClient:
    """Build a KIPRIS client from platform-owned settings without exposing its key."""

    from ai_do_api.core.settings import get_settings

    settings = get_settings()
    client = KiprisClient(
        settings.patent_kipris_api_key,
        settings.patent_kipris_base_url,
    )
    if not client.configured:
        raise KiprisNotConfiguredError("KIPRIS is not configured.")
    return client
