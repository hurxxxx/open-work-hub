from __future__ import annotations

import ipaddress
import socket
from typing import Protocol

from ai_do_api.core.settings import get_settings


_MAIL_INCOMING_ALLOWED_PORTS = {
    "imap": {143, 993},
    "pop3": {110, 995},
}
_MAIL_SMTP_ALLOWED_PORTS = {25, 465, 587}


class MailConnectionPolicyError(ValueError):
    pass


class _MailConnectionSettingsLike(Protocol):
    protocol: str
    incoming_host: str
    incoming_port: int
    incoming_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str


def validate_connection_settings(
    settings: _MailConnectionSettingsLike,
    *,
    incoming: bool = True,
    smtp: bool = True,
) -> None:
    if incoming:
        _validate_incoming_settings(settings)
    if smtp:
        _validate_smtp_settings(settings)


def _validate_incoming_settings(settings: _MailConnectionSettingsLike) -> None:
    if settings.incoming_security == "none" and not get_settings().mail_allow_insecure_transport:
        raise MailConnectionPolicyError("Insecure mail transport is not allowed.")
    allowed_ports = _MAIL_INCOMING_ALLOWED_PORTS.get(settings.protocol, set())
    if settings.incoming_port not in allowed_ports:
        raise MailConnectionPolicyError("Mail incoming port is not allowed.")
    _validate_mail_host(settings.incoming_host)


def _validate_smtp_settings(settings: _MailConnectionSettingsLike) -> None:
    if settings.smtp_security == "none" and not get_settings().mail_allow_insecure_transport:
        raise MailConnectionPolicyError("Insecure mail transport is not allowed.")
    if settings.smtp_port not in _MAIL_SMTP_ALLOWED_PORTS:
        raise MailConnectionPolicyError("Mail SMTP port is not allowed.")
    _validate_mail_host(settings.smtp_host)


def _validate_mail_host(host: str) -> None:
    normalized_host = host.strip().lower().rstrip(".")
    if not normalized_host:
        raise MailConnectionPolicyError("Mail host is required.")
    allowed_private_hosts = {
        allowed.strip().lower().rstrip(".")
        for allowed in get_settings().mail_allowed_private_hosts.split(",")
        if allowed.strip()
    }
    if normalized_host in allowed_private_hosts:
        return
    for address in _resolve_host_addresses(normalized_host):
        if _is_blocked_mail_address(address):
            raise MailConnectionPolicyError("Mail host resolves to a blocked network.")


def _resolve_host_addresses(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {ipaddress.ip_address(host)}
    except ValueError:
        pass
    try:
        resolved = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return set()
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for item in resolved:
        try:
            addresses.add(ipaddress.ip_address(item[4][0]))
        except ValueError:
            continue
    return addresses


def _is_blocked_mail_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            not address.is_global,
            address.is_reserved,
            address.is_unspecified,
        )
    )
