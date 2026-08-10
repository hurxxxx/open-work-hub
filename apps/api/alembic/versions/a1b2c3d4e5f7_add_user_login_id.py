"""add user login id

Revision ID: a1b2c3d4e5f7
Revises: f2c9d1a8b7e4
Create Date: 2026-05-07 00:00:00.000000
"""

from __future__ import annotations

import re
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "f2c9d1a8b7e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_login_id(email: str | None) -> str:
    local_part = (email or "").strip().lower().split("@", 1)[0]
    candidate = re.sub(r"[^a-z0-9._-]+", "-", local_part).strip("._-")[:40]
    if len(candidate) < 3:
        candidate = f"user-{candidate}" if candidate else "user"
    candidate = candidate[:40].strip("._-")
    if not candidate or not candidate[0].isalnum():
        candidate = f"user-{candidate}"[:40].strip("._-")
    return candidate or "user"


def _unique_login_id(base: str, used: set[str]) -> str:
    candidate = base[:40].strip("._-") or "user"
    suffix = 2
    while candidate in used:
        suffix_text = f"-{suffix}"
        candidate = f"{base[: 40 - len(suffix_text)]}{suffix_text}".strip("._-")
        suffix += 1
    used.add(candidate)
    return candidate


def upgrade() -> None:
    op.add_column("users", sa.Column("login_id", sa.String(length=40), nullable=True))

    users = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("email", sa.String(length=320)),
        sa.column("login_id", sa.String(length=40)),
    )
    bind = op.get_bind()
    used: set[str] = set()
    rows = bind.execute(sa.select(users.c.id, users.c.email).order_by(users.c.email)).mappings()
    for row in rows:
        login_id = _unique_login_id(_base_login_id(row["email"]), used)
        bind.execute(
            users.update()
            .where(users.c.id == row["id"])
            .values(login_id=login_id)
        )

    op.alter_column("users", "login_id", existing_type=sa.String(length=40), nullable=False)
    op.create_index(op.f("ix_users_login_id"), "users", ["login_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_login_id"), table_name="users")
    op.drop_column("users", "login_id")
