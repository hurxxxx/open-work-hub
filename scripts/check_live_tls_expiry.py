#!/usr/bin/env python3
"""Fail-closed health check for the public OPEN_ALM TLS certificate."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, TextIO


DEFAULT_HOST = "open-alm.example"
DEFAULT_PORT = 443
DEFAULT_REQUIRED_SANS = ("*.open-alm.example", "open-alm.example")
DEFAULT_THRESHOLD_DAYS = 30

Certificate = dict[str, Any]
CertificateFetcher = Callable[[str, int, float], Certificate]


def fetch_live_certificate(host: str, port: int, timeout_seconds: float) -> Certificate:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        with context.wrap_socket(connection, server_hostname=host) as tls_connection:
            certificate = tls_connection.getpeercert()
    if not certificate:
        raise RuntimeError("peer did not provide a verified certificate")
    return certificate


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("must include a UTC offset or Z")
    return parsed.astimezone(UTC)


def _non_negative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def run(
    argv: Sequence[str] | None = None,
    *,
    certificate_fetcher: CertificateFetcher = fetch_live_certificate,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--required-san",
        action="append",
        dest="required_sans",
        help="Required DNS SAN. Repeat for multiple names.",
    )
    parser.add_argument(
        "--threshold-days",
        type=_non_negative_integer,
        default=DEFAULT_THRESHOLD_DAYS,
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--now",
        type=_parse_utc_datetime,
        help="Override the UTC clock for deterministic diagnostics.",
    )
    args = parser.parse_args(argv)

    try:
        certificate = certificate_fetcher(args.host, args.port, args.timeout_seconds)
    except (OSError, RuntimeError, ssl.SSLError, TimeoutError):
        json.dump(
            {
                "host": args.host,
                "port": args.port,
                "reason": "tls_connection_failed",
                "status": "failed",
            },
            stderr,
            sort_keys=True,
        )
        stderr.write("\n")
        return 1
    try:
        expires_at = datetime.fromtimestamp(
            ssl.cert_time_to_seconds(certificate["notAfter"]),
            UTC,
        )
        dns_sans = sorted(
            value
            for kind, value in certificate.get("subjectAltName", ())
            if kind == "DNS"
        )
    except (KeyError, TypeError, ValueError):
        json.dump(
            {
                "host": args.host,
                "port": args.port,
                "reason": "certificate_invalid",
                "status": "failed",
            },
            stderr,
            sort_keys=True,
        )
        stderr.write("\n")
        return 1
    required_sans = sorted(args.required_sans or DEFAULT_REQUIRED_SANS)
    checked_at = args.now or now().astimezone(UTC)
    remaining = expires_at - checked_at
    threshold = timedelta(days=args.threshold_days)

    missing_sans = sorted(set(required_sans) - set(dns_sans))
    if missing_sans:
        json.dump(
            {
                "certificate_dns_sans": dns_sans,
                "host": args.host,
                "missing_sans": missing_sans,
                "reason": "required_san_missing",
                "required_sans": required_sans,
                "status": "failed",
            },
            stderr,
            sort_keys=True,
        )
        stderr.write("\n")
        return 1

    if remaining <= threshold:
        json.dump(
            {
                "checked_at": _utc_timestamp(checked_at),
                "expires_at": _utc_timestamp(expires_at),
                "host": args.host,
                "reason": "certificate_expiring",
                "remaining_seconds": max(0, int(remaining.total_seconds())),
                "status": "failed",
                "threshold_days": args.threshold_days,
            },
            stderr,
            sort_keys=True,
        )
        stderr.write("\n")
        return 1

    json.dump(
        {
            "certificate_dns_sans": dns_sans,
            "checked_at": _utc_timestamp(checked_at),
            "expires_at": _utc_timestamp(expires_at),
            "host": args.host,
            "port": args.port,
            "remaining_seconds": int(remaining.total_seconds()),
            "required_sans": required_sans,
            "status": "ok",
            "threshold_days": args.threshold_days,
        },
        stdout,
        sort_keys=True,
    )
    stdout.write("\n")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
