"""Connection credentials and company/app/workload model inheritance."""

from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "llm_connections_20260918"
down_revision = "hermes_initial_snapshot_20260914"
branch_labels = None
depends_on = None

# Immutable ownership/cap snapshot for this migration, not a runtime registry.
WORKLOADS = {
    "chatbot": (("chatbot",), 32768, 65536),
    "web_search.answer": (("web-search",), 32768, 65536),
    "files.grounded_chat": (("files",), 8192, 8192),
    "files.rag_query_rewrite": (("files",), 1024, 1024),
    "mail_summarize": (("mail",), 32768, 65536),
    "mail_reply_draft": (("mail",), 32768, 65536),
    "bento.edit_presentation": (("bento",), 32768, 32768),
    "bento.generate_presentation": (("bento",), 32768, 32768),
    "bento.plan_presentation": (("bento",), 16384, 16384),
    "meeting_summary": (("meeting", "recording"), 32768, 65536),
    "meeting_insight_actions": (("meeting",), 32768, 65536),
    "meeting_insight_decisions": (("meeting",), 32768, 65536),
    "meeting_insight_followup": (("meeting",), 32768, 65536),
    "rag_grounded_answer": (("retrieval-search",), 32768, 65536),
}


def upgrade() -> None:
    connection = op.get_bind()
    for name, length in (
        ("provider_kind", 32),
        ("display_name", 160),
        ("route_mode", 16),
        ("credential_kind", 16),
        ("preset", 32),
    ):
        op.add_column(
            "ai_model_provider_configs", sa.Column(name, sa.String(length), nullable=True)
        )
    op.add_column(
        "ai_model_provider_configs", sa.Column("verified_version", sa.Integer(), nullable=True)
    )
    op.execute(
        "UPDATE ai_model_provider_configs SET provider_kind = provider_id, display_name = provider_id, route_mode = CASE WHEN provider_id = 'local' THEN 'local' ELSE 'external' END, credential_kind = CASE WHEN provider_id = 'local' AND api_key_ciphertext IS NULL THEN 'none' ELSE 'api_key' END, preset = ''"
    )
    for name in ("provider_kind", "display_name", "route_mode", "credential_kind", "preset"):
        op.alter_column("ai_model_provider_configs", name, nullable=False)
    op.add_column("ai_model_route_overrides", sa.Column("app_id", sa.String(64), nullable=True))
    op.alter_column("ai_model_route_overrides", "route_mode", nullable=True)
    op.drop_constraint(
        "uq_ai_model_route_overrides_workload", "ai_model_route_overrides", type_="unique"
    )
    op.create_unique_constraint(
        "uq_ai_model_route_overrides_app_workload",
        "ai_model_route_overrides",
        ["app_id", "workload_id"],
    )
    op.create_index("ix_ai_model_route_overrides_app_id", "ai_model_route_overrides", ["app_id"])
    metadata = sa.MetaData()
    overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=connection)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for workload_id, (app_ids, local_cap, external_cap) in WORKLOADS.items():
        row = (
            connection.execute(sa.select(overrides).where(overrides.c.workload_id == workload_id))
            .mappings()
            .first()
        )
        for index, app_id in enumerate(app_ids):
            values = (
                dict(row)
                if row
                else {
                    "id": str(uuid4()),
                    "workload_id": workload_id,
                    "model_ids_json": {},
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            values["app_id"] = app_id
            if values.get("local_max_output_tokens") is None and local_cap != 32768:
                values["local_max_output_tokens"] = local_cap
            if values.get("external_max_output_tokens") is None and external_cap != 65536:
                values["external_max_output_tokens"] = external_cap
            if row and index == 0:
                connection.execute(
                    overrides.update().where(overrides.c.id == row["id"]).values(**values)
                )
            elif row or local_cap != 32768 or external_cap != 65536:
                values["id"] = str(uuid4())
                connection.execute(overrides.insert().values(**values))
    op.create_table(
        "ai_model_policy_defaults",
        sa.Column("app_id", sa.String(64), primary_key=True),
        sa.Column("route_mode", sa.String(16), primary_key=True),
        sa.Column(
            "provider_id",
            sa.String(32),
            sa.ForeignKey("ai_model_provider_configs.provider_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "model_id",
            sa.String(64),
            sa.ForeignKey("ai_model_catalog_entries.id", ondelete="RESTRICT"),
        ),
        sa.Column("max_output_tokens", sa.Integer()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "route_mode IN ('local', 'external')", name="ck_ai_model_policy_default_route"
        ),
        sa.CheckConstraint(
            "max_output_tokens IS NULL OR (max_output_tokens BETWEEN 1024 AND 65536 AND max_output_tokens % 1024 = 0)",
            name="ck_ai_model_policy_default_cap",
        ),
    )
    defaults = sa.Table("ai_model_policy_defaults", metadata, autoload_with=connection)
    providers = sa.Table("ai_model_provider_configs", metadata, autoload_with=connection)
    for route, cap in (("local", 32768), ("external", 65536)):
        enabled = (
            connection.execute(
                sa.select(providers.c.provider_id).where(
                    providers.c.route_mode == route, providers.c.enabled.is_(True)
                )
            )
            .scalars()
            .all()
        )
        connection.execute(
            defaults.insert().values(
                app_id="",
                route_mode=route,
                provider_id=enabled[0] if len(enabled) == 1 else None,
                max_output_tokens=cap,
                version=1,
                updated_at=now,
            )
        )


def downgrade() -> None:
    raise RuntimeError(
        "Connection and app policy cutover requires a paired database/configuration restore; it cannot merge independent credentials or app overrides."
    )
