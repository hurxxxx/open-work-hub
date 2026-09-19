import argparse
import getpass
import json
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import delete

from .app import create_app
from .auth import password_hash
from .config import Settings
from .models import Owner, WebSession, database

ROOT = Path(__file__).resolve().parents[2]


def migrate(url):
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


def main():
    parser = argparse.ArgumentParser(description="Private Codex console")
    parser.add_argument("command", choices=("serve", "migrate", "set-password", "openapi"))
    args = parser.parse_args()
    if args.command == "openapi":
        print(json.dumps(create_app().openapi(), ensure_ascii=False))
        return
    settings = Settings()
    if args.command == "migrate":
        migrate(settings.database_url)
    elif args.command == "set-password":
        password = getpass.getpass("Console owner password (at least 12 characters): ")
        if len(password) < 12 or password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords must match and contain at least 12 characters")
        engine, factory = database(settings.database_url)
        with factory.begin() as db:
            owner = db.get(Owner, 1)
            if owner:
                owner.password_hash = password_hash(password)
                owner.failed_logins, owner.locked_until = 0, None
            else:
                db.add(Owner(password_hash=password_hash(password)))
            db.execute(delete(WebSession))
        engine.dispose()
        print("Owner password updated; web sessions revoked. Codex login is unchanged.")
    else:
        uvicorn.run(
            create_app(settings),
            host=settings.bind_host,
            port=settings.port,
            workers=1,
            access_log=False,
            proxy_headers=False,
        )


if __name__ == "__main__":
    main()
