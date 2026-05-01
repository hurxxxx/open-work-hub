from __future__ import annotations

import argparse
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from aidoo_api.core.db import get_engine, run_migrations
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.access import (
    DEV_LOGIN_ACCOUNTS,
    DEV_LOGIN_PASSWORD,
    ensure_dev_login_seed_data,
    ensure_seed_data,
    list_dev_login_accounts,
)


def _is_local_database_host(host: str | None) -> bool:
    if host is None:
        return True
    return host in {"127.0.0.1", "localhost", "::1", "postgres", "db"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the configured development database.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow resetting a non-local database host.",
    )
    parser.add_argument(
        "--seed-dev-accounts",
        action="store_true",
        help="Create the standard development login accounts after reset.",
    )
    args = parser.parse_args()

    settings = get_settings()
    parsed_dsn = urlparse(settings.postgres_dsn.strip())
    database_host = parsed_dsn.hostname
    database_name = (parsed_dsn.path or "/").removeprefix("/") or "<unknown>"

    if settings.environment.lower() == "production":
        raise SystemExit("Refusing to reset a production environment database.")

    if not _is_local_database_host(database_host) and not args.force:
        raise SystemExit(
            f"Refusing to reset non-local database host {database_host!r} without --force."
        )

    from aidoo_api.domains.auth import models as auth_models  # noqa: F401
    from aidoo_api.domains.docs import models as docs_models  # noqa: F401
    from aidoo_api.domains.media import models as media_models  # noqa: F401
    from aidoo_api.domains.meeting import models as meeting_models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401
    from aidoo_api.domains.whiteboard import models as whiteboard_models  # noqa: F401

    # Drop and recreate the public schema wholesale instead of letting
    # SQLAlchemy walk the metadata graph. drop_all() only knows about
    # tables still declared in Base.metadata, so orphan tables (old PR
    # leftovers like ``pms_docs`` from before the docs hub refactor) would
    # block the reset with "DependentObjectsStillExist" FK errors. A
    # schema-level drop guarantees the DB ends up in a known empty state
    # before migrations re-materialize it.
    engine = get_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    run_migrations()

    with Session(engine) as session:
        if args.seed_dev_accounts:
            ensure_dev_login_seed_data(session)
        else:
            ensure_seed_data(session)

    print(f"Reset complete for {database_host}:{parsed_dsn.port}/{database_name}")
    if args.seed_dev_accounts:
        with Session(engine) as session:
            accounts = list_dev_login_accounts(session)
        print(f"Seeded {len(accounts)} development accounts.")
        print(f"Shared password: {DEV_LOGIN_PASSWORD}")
        for account in DEV_LOGIN_ACCOUNTS:
            print(f"- {account['label']}: {account['email']}")


if __name__ == "__main__":
    main()
