from __future__ import annotations

import imaplib
import poplib
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Protocol

from open_work_hub_api.domains.mail.connection_policy import (
    MailConnectionPolicyError as MailConnectionPolicyError,
)
from open_work_hub_api.domains.mail.connection_policy import (
    validate_connection_settings as validate_connection_settings,
)

_POP3_MAX_LINE = 1024 * 1024
_HTML_TEXT_IGNORED_TAGS = {"head", "script", "style", "title", "meta", "link", "noscript"}
_HTML_TEXT_BLOCK_TAGS = {
    "article",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
}
_CSS_BLOCK_RE = re.compile(r"(?:^|\s)(?:@media[^{]*|[#.]?[-_a-zA-Z][^{}]{0,160})\{[^{}]*\}")
_CSS_BLOCK_TAIL_RE = re.compile(r"\s(?:@media[^{]*|[#.]?[-_a-zA-Z][^{}]{0,160})\{[^{}]*$")
_CSS_AT_RULE_TAIL_RE = re.compile(r"\s@media\b.*$", re.IGNORECASE | re.DOTALL)

if getattr(poplib, "_MAXLINE", 0) < _POP3_MAX_LINE:
    poplib._MAXLINE = _POP3_MAX_LINE


class _MailHtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag_name = tag.lower()
        if tag_name in _HTML_TEXT_IGNORED_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and tag_name in _HTML_TEXT_BLOCK_TAGS:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in _HTML_TEXT_IGNORED_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and tag_name in _HTML_TEXT_BLOCK_TAGS:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        cleaned = data.strip()
        if cleaned:
            self._parts.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self._parts)


@dataclass(frozen=True)
class MailConnectionSettings:
    protocol: str
    incoming_host: str
    incoming_port: int
    incoming_security: str
    incoming_username: str
    incoming_password: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_password: str
    email_address: str
    display_name: str = ""
    provider_kind: str = ""


@dataclass(frozen=True)
class FetchedAttachment:
    filename: str
    content_type: str
    size_bytes: int
    content_id: str | None = None
    disposition: str = "attachment"
    provider_part_id: str | None = None


@dataclass(frozen=True)
class FetchedMessage:
    provider_uid: str
    provider_message_id: str | None
    thread_key: str | None
    subject: str
    from_text: str
    to_text: str
    cc_text: str
    text_body: str
    html_body: str
    snippet: str
    received_at: datetime | None
    sent_at: datetime | None
    is_read: bool
    attachments: tuple[FetchedAttachment, ...] = field(default_factory=tuple)
    remote_identity: str = ""
    remote_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MailboxSyncBatch:
    messages: tuple[FetchedMessage, ...]
    cursor: dict[str, Any]
    deleted_remote_identities: tuple[str, ...] = field(default_factory=tuple)
    reset_mailbox: bool = False


@dataclass(frozen=True)
class MailboxInfo:
    provider_mailbox_id: str
    display_name: str
    role: str = "folder"
    sync_enabled: bool = True


class MailProtocolClient(Protocol):
    def test_incoming(self, settings: MailConnectionSettings) -> None: ...

    def test_smtp(self, settings: MailConnectionSettings) -> None: ...

    def list_mailboxes(self, settings: MailConnectionSettings) -> list[MailboxInfo]: ...

    def fetch_recent(
        self,
        settings: MailConnectionSettings,
        *,
        folder: str = "INBOX",
        limit: int = 50,
    ) -> list[FetchedMessage]: ...

    def sync_mailbox(
        self,
        settings: MailConnectionSettings,
        *,
        mailbox: str = "INBOX",
        cursor: dict[str, Any] | None = None,
        initial_limit: int = 50,
    ) -> MailboxSyncBatch: ...

    def send_draft(
        self,
        settings: MailConnectionSettings,
        *,
        to_text: str,
        cc_text: str,
        bcc_text: str,
        subject: str,
        text_body: str,
        html_body: str = "",
    ) -> str | None: ...


class StdlibMailClient:
    def test_incoming(self, settings: MailConnectionSettings) -> None:
        if settings.protocol == "pop3":
            with _pop3_connection(settings) as connection:
                connection.noop()
            return
        with _imap_connection(settings) as connection:
            connection.noop()

    def test_smtp(self, settings: MailConnectionSettings) -> None:
        with _smtp_connection(settings) as connection:
            connection.noop()

    def list_mailboxes(self, settings: MailConnectionSettings) -> list[MailboxInfo]:
        if settings.protocol == "pop3":
            return [MailboxInfo(provider_mailbox_id="INBOX", display_name="INBOX", role="inbox")]
        return _list_imap_mailboxes(settings)

    def fetch_recent(
        self,
        settings: MailConnectionSettings,
        *,
        folder: str = "INBOX",
        limit: int = 50,
    ) -> list[FetchedMessage]:
        if settings.protocol == "pop3":
            return _fetch_recent_pop3(settings, limit=limit)
        return _fetch_recent_imap(settings, folder=folder, limit=limit)

    def sync_mailbox(
        self,
        settings: MailConnectionSettings,
        *,
        mailbox: str = "INBOX",
        cursor: dict[str, Any] | None = None,
        initial_limit: int = 50,
    ) -> MailboxSyncBatch:
        provider_kind = (settings.provider_kind or settings.protocol).lower()
        if provider_kind == "pop3":
            return _sync_pop3_mailbox(settings, cursor=cursor or {}, initial_limit=initial_limit)
        return _sync_imap_mailbox(
            settings,
            folder=mailbox,
            cursor=cursor or {},
            initial_limit=initial_limit,
        )

    def send_draft(
        self,
        settings: MailConnectionSettings,
        *,
        to_text: str,
        cc_text: str,
        bcc_text: str,
        subject: str,
        text_body: str,
        html_body: str = "",
    ) -> str | None:
        message = EmailMessage()
        message["From"] = _format_from(settings)
        message["To"] = to_text
        if cc_text.strip():
            message["Cc"] = cc_text
        message["Subject"] = subject
        message.set_content(text_body or "")
        if html_body.strip():
            message.add_alternative(html_body, subtype="html")

        recipients = _recipient_list(to_text, cc_text, bcc_text)
        with _smtp_connection(settings) as connection:
            connection.send_message(message, from_addr=settings.email_address, to_addrs=recipients)
        return message.get("Message-ID")


def _imap_connection(settings: MailConnectionSettings):
    validate_connection_settings(settings, incoming=True, smtp=False)
    if settings.incoming_security == "ssl":
        connection = imaplib.IMAP4_SSL(
            settings.incoming_host,
            settings.incoming_port,
            ssl_context=ssl.create_default_context(),
        )
    else:
        connection = imaplib.IMAP4(settings.incoming_host, settings.incoming_port)
        if settings.incoming_security == "starttls":
            connection.starttls(ssl_context=ssl.create_default_context())
    try:
        connection.login(settings.incoming_username, settings.incoming_password)
        return _ImapContext(connection)
    except Exception:
        try:
            connection.logout()
        except Exception:
            pass
        raise


class _ImapContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args: object) -> None:
        try:
            self.connection.logout()
        except Exception:
            pass


def _pop3_connection(settings: MailConnectionSettings):
    validate_connection_settings(settings, incoming=True, smtp=False)
    if settings.incoming_security == "ssl":
        connection = poplib.POP3_SSL(
            settings.incoming_host,
            settings.incoming_port,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        connection = poplib.POP3(settings.incoming_host, settings.incoming_port, timeout=30)
        if settings.incoming_security == "starttls":
            connection.stls(context=ssl.create_default_context())
    try:
        connection.user(settings.incoming_username)
        connection.pass_(settings.incoming_password)
        return _Pop3Context(connection)
    except Exception:
        try:
            connection.quit()
        except Exception:
            pass
        raise


class _Pop3Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args: object) -> None:
        try:
            self.connection.quit()
        except Exception:
            pass


def _smtp_connection(settings: MailConnectionSettings):
    validate_connection_settings(settings, incoming=False, smtp=True)
    if settings.smtp_security == "ssl":
        connection = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_security == "starttls":
            connection.starttls(context=ssl.create_default_context())
    try:
        connection.login(settings.smtp_username, settings.smtp_password)
        return connection
    except Exception:
        try:
            connection.quit()
        except Exception:
            pass
        raise


def _fetch_recent_imap(
    settings: MailConnectionSettings,
    *,
    folder: str,
    limit: int,
) -> list[FetchedMessage]:
    messages: list[FetchedMessage] = []
    with _imap_connection(settings) as connection:
        typ, _data = connection.select(folder, readonly=True)
        if typ != "OK":
            return []
        typ, data = connection.uid("search", None, "ALL")
        if typ != "OK" or not data:
            return []
        uids = _split_imap_uid_response(data)
        for uid in _recent_imap_uids(connection, uids, limit=limit):
            typ, fetched = connection.uid("fetch", uid, "(BODY.PEEK[] FLAGS)")
            if typ != "OK":
                continue
            raw_bytes: bytes | None = None
            flags_text = ""
            for item in fetched:
                if isinstance(item, tuple):
                    meta, payload = item
                    raw_bytes = payload
                    flags_text += meta.decode("utf-8", errors="ignore")
                elif isinstance(item, bytes):
                    flags_text += item.decode("utf-8", errors="ignore")
            if raw_bytes is None:
                continue
            received_at = _parse_imap_internaldate(flags_text)
            messages.append(
                _parse_message(
                    uid.decode("ascii", errors="ignore"),
                    raw_bytes,
                    is_read="\\Seen" in flags_text,
                    received_at=received_at,
                )
            )
    return messages


def _fetch_recent_pop3(settings: MailConnectionSettings, *, limit: int) -> list[FetchedMessage]:
    with _pop3_connection(settings) as connection:
        _response, listings, _octets = connection.uidl()
        candidates = _pop3_candidate_window(_parse_pop3_uidl(listings), limit=limit)
        selected = _rank_pop3_candidates_by_date(connection, candidates, limit=limit)
        messages = _fetch_pop3_messages(connection, selected, with_provider_identity=False)
    return _sort_messages_by_received_at(messages)[:limit]


def _list_imap_mailboxes(settings: MailConnectionSettings) -> list[MailboxInfo]:
    mailboxes: dict[str, MailboxInfo] = {}
    with _imap_connection(settings) as connection:
        typ, data = connection.list()
        if typ != "OK" or not data:
            return [MailboxInfo(provider_mailbox_id="INBOX", display_name="INBOX", role="inbox")]
        for item in data:
            mailbox = _parse_imap_list_mailbox(item)
            if mailbox is None:
                continue
            mailboxes.setdefault(mailbox.provider_mailbox_id, mailbox)
    if not any(mailbox.role == "inbox" for mailbox in mailboxes.values()):
        mailboxes["INBOX"] = MailboxInfo(
            provider_mailbox_id="INBOX",
            display_name="INBOX",
            role="inbox",
        )
    return sorted(
        mailboxes.values(),
        key=lambda mailbox: (
            0 if mailbox.role == "inbox" else 1,
            mailbox.display_name.lower(),
            mailbox.provider_mailbox_id.lower(),
        ),
    )


def _parse_imap_list_mailbox(item: object) -> MailboxInfo | None:
    if isinstance(item, bytes):
        text = item.decode("utf-8", errors="ignore")
    elif item is None:
        return None
    else:
        text = str(item)
    match = re.match(r'^\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.+)$', text)
    if not match:
        return None
    flags = {flag.lower() for flag in match.group("flags").split()}
    if "\\noselect" in flags:
        return None
    provider_mailbox_id = _unquote_imap_list_name(match.group("name").strip())
    if not provider_mailbox_id:
        return None
    role = _mailbox_role(provider_mailbox_id, flags)
    return MailboxInfo(
        provider_mailbox_id=provider_mailbox_id,
        display_name=_mailbox_display_name(provider_mailbox_id),
        role=role,
        sync_enabled=role not in {"all", "drafts", "sent", "spam", "trash"},
    )


def _unquote_imap_list_name(value: str) -> str:
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
        value = value.replace(r"\"", '"').replace(r"\\", "\\")
    return value


def _mailbox_role(provider_mailbox_id: str, flags: set[str]) -> str:
    normalized = provider_mailbox_id.strip().lower()
    basename = normalized.rsplit("/", 1)[-1]
    if normalized == "inbox":
        return "inbox"
    if "\\sent" in flags or basename in {"sent", "sent mail"}:
        return "sent"
    if "\\drafts" in flags or basename == "drafts":
        return "drafts"
    if "\\trash" in flags or basename in {"trash", "deleted items"}:
        return "trash"
    if "\\junk" in flags or "\\spam" in flags or basename in {"junk", "spam"}:
        return "spam"
    if "\\all" in flags or normalized in {"[gmail]/all mail", "[google mail]/all mail"}:
        return "all"
    if "\\archive" in flags or basename == "archive":
        return "archive"
    return "folder"


def _mailbox_display_name(provider_mailbox_id: str) -> str:
    display_name = provider_mailbox_id.rsplit("/", 1)[-1].strip()
    return display_name or provider_mailbox_id


def _sync_pop3_mailbox(
    settings: MailConnectionSettings,
    *,
    cursor: dict[str, Any],
    initial_limit: int,
) -> MailboxSyncBatch:
    with _pop3_connection(settings) as connection:
        _response, listings, _octets = connection.uidl()
        parsed = _parse_pop3_uidl(listings)
        current_uidls = {uid for _number, uid in parsed}
        previous_uidls = {str(uid) for uid in cursor.get("uidls") or [] if uid}
        unseen_candidates = [(number, uid) for number, uid in parsed if uid not in previous_uidls]
        candidates = _pop3_candidate_window(unseen_candidates, limit=initial_limit)
        selected = _rank_pop3_candidates_by_date(
            connection,
            candidates,
            limit=initial_limit,
        )
        fetched_messages = _fetch_pop3_messages(
            connection,
            selected,
            with_provider_identity=True,
        )
        messages = tuple(_sort_messages_by_received_at(fetched_messages)[:initial_limit])
    deleted = tuple(_remote_identity("pop3", uid) for uid in sorted(previous_uidls - current_uidls))
    known_uidls = (previous_uidls - (previous_uidls - current_uidls)) | {
        message.provider_uid for message in messages
    }
    return MailboxSyncBatch(
        messages=messages,
        cursor={"uidls": sorted(known_uidls)},
        deleted_remote_identities=deleted,
    )


def _sync_imap_mailbox(
    settings: MailConnectionSettings,
    *,
    folder: str,
    cursor: dict[str, Any],
    initial_limit: int,
) -> MailboxSyncBatch:
    messages: list[FetchedMessage] = []
    with _imap_connection(settings) as connection:
        typ, _data = connection.select(folder, readonly=True)
        if typ != "OK":
            return MailboxSyncBatch(messages=(), cursor=cursor)
        uidvalidity = _imap_response_text(connection, "UIDVALIDITY") or str(
            cursor.get("uidvalidity") or ""
        )
        uidnext = _imap_response_text(connection, "UIDNEXT")
        previous_uidvalidity = str(cursor.get("uidvalidity") or "")
        previous_highest = _int_or_none(cursor.get("highest_seen_uid"))
        previous_known_uids = {str(uid) for uid in cursor.get("known_uids") or [] if uid}
        reset_mailbox = bool(previous_uidvalidity and uidvalidity != previous_uidvalidity)
        is_initial = previous_highest is None or reset_mailbox

        typ, data = connection.uid("search", None, "ALL")
        if typ != "OK" or not data:
            return MailboxSyncBatch(
                messages=(),
                cursor={
                    "uidvalidity": uidvalidity,
                    "uidnext": uidnext,
                    "highest_seen_uid": previous_highest or 0,
                    "known_uids": [],
                },
                reset_mailbox=reset_mailbox,
            )
        all_uids = _split_imap_uid_response(data)
        current_by_text = {uid.decode("ascii", errors="ignore"): uid for uid in all_uids}
        current_uid_texts = set(current_by_text)

        if is_initial:
            candidate_uids = _recent_imap_uids(
                connection,
                all_uids,
                limit=initial_limit,
            )
        else:
            candidate_uids = sorted(
                [uid for uid in all_uids if _uid_sort_key(uid) > (previous_highest or 0)],
                key=_uid_sort_key,
            )[:initial_limit]

        highest_seen_uid = previous_highest or 0
        fetched_uid_texts: set[str] = set()
        for uid in candidate_uids:
            uid_text = uid.decode("ascii", errors="ignore")
            typ, fetched = connection.uid("fetch", uid, "(BODY.PEEK[] FLAGS)")
            if typ != "OK":
                raise RuntimeError(f"IMAP fetch failed for UID {uid_text}.")
            raw_bytes, flags_text = _extract_imap_fetch_payload(fetched)
            if raw_bytes is None:
                raise RuntimeError(f"IMAP fetch returned no RFC822 payload for UID {uid_text}.")
            received_at = _parse_imap_internaldate(flags_text)
            highest_seen_uid = max(highest_seen_uid, _uid_sort_key(uid))
            fetched_uid_texts.add(uid_text)
            messages.append(
                _with_provider_identity(
                    _parse_message(
                        uid_text,
                        raw_bytes,
                        is_read="\\Seen" in flags_text,
                        received_at=received_at,
                    ),
                    remote_identity=_imap_remote_identity(folder, uidvalidity, uid_text),
                    remote_flags={
                        "provider": "imap",
                        "folder": folder,
                        "flags": _parse_imap_flags(flags_text),
                        "uidvalidity": uidvalidity,
                    },
                )
            )

    deleted_uid_texts = set() if reset_mailbox else previous_known_uids - current_uid_texts
    known_uids = (
        set() if reset_mailbox else previous_known_uids - deleted_uid_texts
    ) | fetched_uid_texts
    return MailboxSyncBatch(
        messages=tuple(messages),
        cursor={
            "uidvalidity": uidvalidity,
            "uidnext": uidnext,
            "highest_seen_uid": highest_seen_uid,
            "known_uids": sorted(known_uids, key=lambda uid: int(uid) if uid.isdigit() else -1),
        },
        deleted_remote_identities=tuple(
            _imap_remote_identity(folder, uidvalidity, uid_text)
            for uid_text in sorted(
                deleted_uid_texts, key=lambda uid: int(uid) if uid.isdigit() else -1
            )
        ),
        reset_mailbox=reset_mailbox,
    )


def _parse_pop3_uidl(listings: list[bytes]) -> list[tuple[int, str]]:
    parsed: list[tuple[int, str]] = []
    for line in listings:
        try:
            number, uid = line.decode("utf-8", errors="ignore").split(" ", 1)
            parsed.append((int(number), uid.strip()))
        except ValueError:
            continue
    return parsed


def _pop3_candidate_window(
    parsed: list[tuple[int, str]],
    *,
    limit: int,
) -> list[tuple[int, str]]:
    if limit <= 0 or not parsed:
        return []
    by_number = sorted(parsed, key=lambda item: item[0])
    if len(by_number) <= limit * 2:
        return by_number
    candidates: dict[int, tuple[int, str]] = {}
    for item in [*by_number[:limit], *by_number[-limit:]]:
        candidates[item[0]] = item
    return [candidates[number] for number in sorted(candidates)]


def _fetch_pop3_messages(
    connection,
    candidates: list[tuple[int, str]],
    *,
    with_provider_identity: bool,
) -> list[FetchedMessage]:
    messages: list[FetchedMessage] = []
    for number, uid in candidates:
        _response, lines, _octets = connection.retr(number)
        raw_bytes = b"\r\n".join(lines)
        message = _parse_message(uid, raw_bytes, is_read=False)
        if with_provider_identity:
            message = _with_provider_identity(
                message,
                remote_identity=_remote_identity("pop3", uid),
                remote_flags={"provider": "pop3"},
            )
        messages.append(message)
    return messages


def _rank_pop3_candidates_by_date(
    connection,
    candidates: list[tuple[int, str]],
    *,
    limit: int,
) -> list[tuple[int, str]]:
    if limit <= 0 or not candidates:
        return []
    dated_candidates = [
        (_pop3_header_date(connection, number) or datetime.min, uid, number, uid)
        for number, uid in candidates
    ]
    return [
        (number, uid)
        for _date, _uid_sort, number, uid in sorted(dated_candidates, reverse=True)[:limit]
    ]


def _pop3_header_date(connection, number: int) -> datetime | None:
    try:
        _response, lines, _octets = connection.top(number, 0)
    except Exception:
        return None
    raw_headers = b"\r\n".join(lines).split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
    parsed = BytesParser(policy=policy.default).parsebytes(raw_headers)
    return _parse_date(_header(parsed, "date"))


def _sort_messages_by_received_at(messages: list[FetchedMessage]) -> list[FetchedMessage]:
    return sorted(
        messages,
        key=lambda message: (
            message.received_at or message.sent_at or datetime.min,
            message.provider_uid,
        ),
        reverse=True,
    )


def _with_provider_identity(
    message: FetchedMessage,
    *,
    remote_identity: str,
    remote_flags: dict[str, Any],
) -> FetchedMessage:
    return FetchedMessage(
        provider_uid=message.provider_uid,
        provider_message_id=message.provider_message_id,
        thread_key=message.thread_key,
        subject=message.subject,
        from_text=message.from_text,
        to_text=message.to_text,
        cc_text=message.cc_text,
        text_body=message.text_body,
        html_body=message.html_body,
        snippet=message.snippet,
        received_at=message.received_at,
        sent_at=message.sent_at,
        is_read=message.is_read,
        attachments=message.attachments,
        remote_identity=remote_identity,
        remote_flags=remote_flags,
    )


def _remote_identity(provider: str, *parts: str) -> str:
    return ":".join([provider, *(part.replace(":", "%3A") for part in parts)])


def _imap_remote_identity(folder: str, uidvalidity: str, uid_text: str) -> str:
    if folder.strip().upper() == "INBOX":
        return _remote_identity("imap", uidvalidity, uid_text)
    return _remote_identity("imap", folder, uidvalidity, uid_text)


def _imap_response_text(connection, key: str) -> str | None:
    try:
        typ, data = connection.response(key)
    except Exception:
        return None
    if typ not in {"OK", key.upper()} or not data:
        return None
    for item in data:
        if isinstance(item, bytes):
            value = item.decode("ascii", errors="ignore").strip()
            if value:
                return value
        elif item is not None:
            value = str(item).strip()
            if value:
                return value
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_imap_fetch_payload(fetched) -> tuple[bytes | None, str]:
    raw_bytes: bytes | None = None
    flags_text = ""
    for item in fetched:
        if isinstance(item, tuple):
            meta, payload = item
            raw_bytes = payload
            flags_text += meta.decode("utf-8", errors="ignore")
        elif isinstance(item, bytes):
            flags_text += item.decode("utf-8", errors="ignore")
    return raw_bytes, flags_text


def _parse_imap_flags(flags_text: str) -> list[str]:
    match = re.search(r"FLAGS \(([^)]*)\)", flags_text, flags=re.IGNORECASE)
    if match is None:
        return []
    return [flag for flag in match.group(1).split() if flag]


def _parse_imap_internaldate(flags_text: str) -> datetime | None:
    match = re.search(r'INTERNALDATE "([^"]+)"', flags_text, flags=re.IGNORECASE)
    if match is None:
        return None
    return _parse_date(match.group(1))


def _recent_imap_uids(connection, uids: list[bytes], *, limit: int) -> list[bytes]:
    if limit <= 0 or not uids:
        return []
    sorted_uids = _imap_sort_uids_by_arrival(connection)
    if sorted_uids:
        known_uids = set(uids)
        matching_sorted_uids = [uid for uid in sorted_uids if uid in known_uids]
        if matching_sorted_uids:
            if len(matching_sorted_uids) >= limit:
                return matching_sorted_uids[:limit]
            remaining_uids = [
                uid
                for uid in sorted(uids, key=_uid_sort_key, reverse=True)
                if uid not in set(matching_sorted_uids)
            ]
            return (matching_sorted_uids + remaining_uids)[:limit]
    return sorted(uids, key=_uid_sort_key, reverse=True)[:limit]


def _imap_sort_uids_by_arrival(connection) -> list[bytes]:
    try:
        typ, data = connection.uid("sort", "(REVERSE ARRIVAL)", "UTF-8", "ALL")
    except Exception:
        return []
    if typ != "OK" or not data:
        return []
    return _split_imap_uid_response(data)


def _split_imap_uid_response(data) -> list[bytes]:
    uids: list[bytes] = []
    for item in data:
        if not isinstance(item, bytes):
            continue
        for uid in item.split():
            if uid:
                uids.append(uid)
    return uids


def _uid_sort_key(uid: bytes) -> int:
    try:
        return int(uid)
    except (TypeError, ValueError):
        return -1


def _parse_message(
    provider_uid: str,
    raw_bytes: bytes,
    *,
    is_read: bool,
    received_at: datetime | None = None,
) -> FetchedMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    text_body, html_body, attachments = _message_parts(parsed)
    subject = _header(parsed, "subject")
    from_text = _header(parsed, "from")
    to_text = _header(parsed, "to")
    cc_text = _header(parsed, "cc")
    message_id = _header(parsed, "message-id") or None
    references = _header(parsed, "references") or _header(parsed, "in-reply-to")
    sent_at = _parse_date(_header(parsed, "date"))
    snippet_source = text_body or _strip_html(html_body)
    return FetchedMessage(
        provider_uid=provider_uid,
        provider_message_id=message_id,
        thread_key=references or message_id,
        subject=subject,
        from_text=from_text,
        to_text=to_text,
        cc_text=cc_text,
        text_body=text_body,
        html_body=html_body,
        snippet=_snippet(snippet_source),
        received_at=received_at or sent_at,
        sent_at=sent_at,
        is_read=is_read,
        attachments=tuple(attachments),
    )


def _message_parts(message: Message) -> tuple[str, str, list[FetchedAttachment]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[FetchedAttachment] = []
    counter = 0
    for part in message.walk() if message.is_multipart() else [message]:
        if part.is_multipart():
            continue
        counter += 1
        content_type = part.get_content_type()
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        if filename or disposition == "attachment":
            attachments.append(
                FetchedAttachment(
                    filename=filename,
                    content_type=content_type,
                    size_bytes=len(payload),
                    content_id=part.get("Content-ID"),
                    disposition=disposition or "attachment",
                    provider_part_id=str(counter),
                )
            )
            continue
        try:
            content = part.get_content()
        except Exception:
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if content_type == "text/plain":
            text_parts.append(str(content))
        elif content_type == "text/html":
            html_parts.append(str(content))
    return "\n\n".join(text_parts).strip(), "\n\n".join(html_parts).strip(), attachments


def _header(message: Message, name: str) -> str:
    value = message.get(name, "")
    return str(value).strip() if value is not None else ""


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _strip_html(value: str) -> str:
    extractor = _MailHtmlTextExtractor()
    try:
        extractor.feed(value)
        extractor.close()
        text = extractor.get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value)
    return _strip_css_blocks(text)


def _snippet(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:320]


def _strip_css_blocks(value: str) -> str:
    current = value
    for _index in range(8):
        next_value = _CSS_BLOCK_TAIL_RE.sub(
            " ", _CSS_BLOCK_RE.sub(" ", _CSS_AT_RULE_TAIL_RE.sub(" ", current))
        )
        if next_value == current:
            break
        current = next_value
    return current


def _recipient_list(*values: str) -> list[str]:
    recipients: list[str] = []
    for value in values:
        for part in value.split(","):
            cleaned = part.strip()
            if cleaned:
                recipients.append(cleaned)
    return recipients


def _format_from(settings: MailConnectionSettings) -> str:
    if settings.display_name.strip():
        return f"{settings.display_name.strip()} <{settings.email_address}>"
    return settings.email_address
