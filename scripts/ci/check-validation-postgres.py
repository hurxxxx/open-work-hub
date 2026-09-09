#!/usr/bin/env python3
"""Read-only check of the image's PostgreSQL clients and the CI server major."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


class ValidationError(Exception):
    pass


def check_postgres(major_file: Path, dsn: str) -> int:
    if not major_file.is_file():
        raise ValidationError("Image PostgreSQL identity is missing; rebuild the validation image.")
    expected = major_file.read_text().strip()
    if not re.fullmatch(r"[1-9][0-9]+", expected):
        raise ValidationError("Image PostgreSQL identity is invalid; rebuild the validation image.")
    if not dsn:
        raise ValidationError("OPEN_WORK_HUB_CI_POSTGRES_DSN is required for release validation.")

    for tool in ("pg_dump", "pg_restore", "psql"):
        result = subprocess.run(
            [tool, "--version"], capture_output=True, text=True, check=True, timeout=10
        )
        match = re.match(rf"^{tool} \(PostgreSQL\) ([0-9]+)\.", result.stdout)
        if not match or match.group(1) != expected:
            raise ValidationError(f"{tool} does not match PostgreSQL {expected}; rebuild the image.")

    import psycopg

    # Keep credentials out of command arguments and diagnostics. The libpq
    # connection handshake supplies server_version without accessing app data.
    conninfo = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(conninfo, connect_timeout=10) as connection:
        actual = connection.info.server_version // 10000
    if actual != int(expected):
        raise ValidationError(
            f"CI PostgreSQL server is {actual}, but the image clients are {expected}; "
            "align the CI database with the project server and rebuild the image with "
            "--postgres-major."
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        major = check_postgres(args.major_file, os.getenv("OPEN_WORK_HUB_CI_POSTGRES_DSN", ""))
    except ValidationError as error:
        print(f"[validation-postgres] {error}", file=sys.stderr)
        return 2
    except Exception:
        # Connection/driver errors can contain credentials, hostnames or DSNs.
        print(
            "[validation-postgres] Check failed; verify CI DB connectivity/authentication "
            "and the image's PostgreSQL tools. Connection details are omitted.",
            file=sys.stderr,
        )
        return 2
    print(f"[validation-postgres] server and image clients match PostgreSQL {major}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
