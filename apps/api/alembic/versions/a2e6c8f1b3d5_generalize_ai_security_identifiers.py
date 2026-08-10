"""generalize AI security identifier categories

Revision ID: a2e6c8f1b3d5
Revises: 9d4a6f8b2c1e
Create Date: 2026-08-10 22:00:00.000000

The upgrade maps the retired manufacturing-oriented security category to the
generic internal-identifier category in active settings, exception scopes, and
audit metadata. Downgrade does not reconstruct the narrower legacy meaning.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a2e6c8f1b3d5"
down_revision: str | Sequence[str] | None = "9d4a6f8b2c1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LEGACY_BLOCKER = "company_sensitive_entity"
_GENERIC_BLOCKER = "sensitive_identifier"
_LEGACY_ENTITY_TYPES = {
    "order_id",
    "product_code",
    "customer",
    "price",
    "cost",
    "contract",
}


def _replace_blocker_list(value: object) -> object:
    if not isinstance(value, list):
        return value
    replaced: list[object] = []
    for item in value:
        next_item = _GENERIC_BLOCKER if item == _LEGACY_BLOCKER else item
        if next_item not in replaced:
            replaced.append(next_item)
    return replaced


def _replace_action_map(value: object) -> object:
    if not isinstance(value, dict) or _LEGACY_BLOCKER not in value:
        return value
    replaced = dict(value)
    legacy_action = replaced.pop(_LEGACY_BLOCKER)
    replaced.setdefault(_GENERIC_BLOCKER, legacy_action)
    return replaced


def _clean_data_protection_settings() -> None:
    settings = sa.table(
        "ai_security_data_protection_settings",
        sa.column("id", sa.String(length=36)),
        sa.column("blocker_actions_json", sa.JSON()),
        sa.column("external_app_actions_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(settings)).mappings().all()
    for row in rows:
        blocker_actions = _replace_action_map(row["blocker_actions_json"])
        raw_external_actions = row["external_app_actions_json"]
        external_actions = raw_external_actions
        if isinstance(raw_external_actions, dict):
            external_actions = {
                app_id: _replace_action_map(actions)
                for app_id, actions in raw_external_actions.items()
            }
        if (
            blocker_actions == row["blocker_actions_json"]
            and external_actions == raw_external_actions
        ):
            continue
        connection.execute(
            sa.update(settings)
            .where(settings.c.id == row["id"])
            .values(
                blocker_actions_json=blocker_actions,
                external_app_actions_json=external_actions,
            )
        )


def _clean_exception_scopes() -> None:
    exceptions = sa.table(
        "ai_security_external_transfer_exceptions",
        sa.column("id", sa.String(length=36)),
        sa.column("allowed_blocker_types_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(exceptions)).mappings().all()
    for row in rows:
        replaced = _replace_blocker_list(row["allowed_blocker_types_json"])
        if replaced == row["allowed_blocker_types_json"]:
            continue
        connection.execute(
            sa.update(exceptions)
            .where(exceptions.c.id == row["id"])
            .values(allowed_blocker_types_json=replaced)
        )


def upgrade() -> None:
    """Map domain-specific security metadata to generic identifiers."""
    _clean_data_protection_settings()
    _clean_exception_scopes()

    detected_values = sa.table(
        "ai_security_detected_values",
        sa.column("entity_type", sa.String(length=120)),
        sa.column("blocker_type", sa.String(length=80)),
    )
    connection = op.get_bind()
    connection.execute(
        sa.update(detected_values)
        .where(detected_values.c.entity_type.in_(_LEGACY_ENTITY_TYPES))
        .values(entity_type="internal_identifier", blocker_type=_GENERIC_BLOCKER)
    )
    connection.execute(
        sa.update(detected_values)
        .where(detected_values.c.blocker_type == _LEGACY_BLOCKER)
        .values(blocker_type=_GENERIC_BLOCKER)
    )


def downgrade() -> None:
    """Generic identifier metadata cannot be mapped back without ambiguity."""
