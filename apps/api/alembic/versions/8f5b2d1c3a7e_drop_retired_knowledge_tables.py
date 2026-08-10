"""Drop the retired Knowledge schema after writer shutdown.

Revision ID: 8f5b2d1c3a7e
Revises: 7e4a9c2f1b6d
Create Date: 2026-08-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "8f5b2d1c3a7e"
down_revision: str | Sequence[str] | None = "7e4a9c2f1b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_KNOWLEDGE_RESOURCE_TYPE = "knowledge_source_document"
_KNOWLEDGE_TABLES = (
    "knowledge_connectors",
    "knowledge_source_documents",
    "knowledge_document_artifacts",
    "knowledge_ingest_jobs",
)
_REQUIRED_TABLES = frozenset(
    {
        *_KNOWLEDGE_TABLES,
        "meeting_file_attachments",
        "meetings",
        "pms_attachments",
        "pms_task_lists",
        "pms_tasks",
        "rag_sync_jobs",
        "retrieval_partitions",
        "retrieval_projection_events",
        "retrieval_projection_heads",
        "search_index_jobs",
        "teams",
    }
)
_DROP_ORDER = (
    "knowledge_ingest_jobs",
    "knowledge_document_artifacts",
    "knowledge_source_documents",
    "knowledge_connectors",
)
_RETIREMENT_CONTROL_LOCK_TABLES = frozenset(
    {
        "meeting_file_attachments",
        "meetings",
        "pms_attachments",
        "pms_task_lists",
        "pms_tasks",
        "rag_sync_jobs",
        "retrieval_partitions",
        "retrieval_projection_events",
        "retrieval_projection_heads",
        "search_index_jobs",
        "teams",
    }
)
_ALLOWED_INBOUND_FOREIGN_KEYS = frozenset(
    {
        (
            "knowledge_source_documents",
            ("connector_id",),
            "knowledge_connectors",
            ("id",),
        ),
        (
            "knowledge_document_artifacts",
            ("source_document_id",),
            "knowledge_source_documents",
            ("id",),
        ),
        (
            "knowledge_ingest_jobs",
            ("source_document_id",),
            "knowledge_source_documents",
            ("id",),
        ),
    }
)
_POSTGRESQL_LOCK_TIMEOUT = "5s"

_EXPECTED_KNOWLEDGE_COLUMNS = {
    "knowledge_connectors": (
        ("id", "character varying(36)", True, None),
        ("workspace_id", "character varying(36)", True, None),
        ("source_type", "character varying(64)", True, None),
        ("display_name", "character varying(160)", True, None),
        ("enabled", "boolean", True, "true"),
        ("status", "character varying(24)", True, "'ready'::character varying"),
        ("config", "jsonb", False, None),
        ("last_synced_at", "timestamp without time zone", False, None),
        ("created_at", "timestamp without time zone", True, None),
        ("updated_at", "timestamp without time zone", True, None),
    ),
    "knowledge_document_artifacts": (
        ("id", "character varying(36)", True, None),
        ("source_document_id", "character varying(36)", True, None),
        ("artifact_type", "character varying(40)", True, None),
        ("storage_provider", "character varying(40)", False, None),
        ("storage_key", "character varying(1024)", False, None),
        ("mime_type", "character varying(160)", False, None),
        ("text_content", "text", False, None),
        ("content_hash", "character varying(128)", False, None),
        ("metadata", "jsonb", False, None),
        ("created_at", "timestamp without time zone", True, None),
    ),
    "knowledge_ingest_jobs": (
        ("id", "character varying(36)", True, None),
        ("workspace_id", "character varying(36)", True, None),
        ("source_document_id", "character varying(36)", True, None),
        ("operation", "character varying(24)", True, "'upsert'::character varying"),
        ("status", "character varying(24)", True, "'pending'::character varying"),
        ("attempts", "integer", True, "0"),
        ("last_error", "text", False, None),
        ("created_at", "timestamp without time zone", True, None),
        ("updated_at", "timestamp without time zone", True, None),
    ),
    "knowledge_source_documents": (
        ("id", "character varying(36)", True, None),
        ("workspace_id", "character varying(36)", True, None),
        ("connector_id", "character varying(36)", False, None),
        ("source_type", "character varying(64)", True, None),
        ("external_id", "character varying(256)", True, None),
        ("title", "character varying(512)", True, None),
        ("filename", "character varying(512)", False, None),
        ("mime_type", "character varying(160)", True, None),
        ("size_bytes", "integer", True, "0"),
        ("storage_provider", "character varying(40)", False, None),
        ("storage_key", "character varying(1024)", False, None),
        ("external_uri", "character varying(2048)", False, None),
        ("version_ref", "character varying(256)", False, None),
        ("content_hash", "character varying(128)", False, None),
        ("acl_fingerprint", "character varying(128)", False, None),
        ("origin_ref_type", "character varying(80)", False, None),
        ("origin_ref_id", "character varying(80)", False, None),
        ("owner_id", "character varying(36)", False, None),
        ("visibility_refs", "jsonb", False, None),
        ("metadata", "jsonb", False, None),
        ("ingest_status", "character varying(24)", True, "'pending'::character varying"),
        ("rag_status", "character varying(24)", True, "'pending'::character varying"),
        ("chunk_count", "integer", True, "0"),
        ("last_error", "text", False, None),
        ("source_updated_at", "timestamp without time zone", False, None),
        ("ingested_at", "timestamp without time zone", False, None),
        ("indexed_at", "timestamp without time zone", False, None),
        ("disabled_at", "timestamp without time zone", False, None),
        ("deleted_at", "timestamp without time zone", False, None),
        ("created_at", "timestamp without time zone", True, None),
        ("updated_at", "timestamp without time zone", True, None),
        ("access_scope_kind", "character varying(24)", False, None),
        ("access_scope_id", "character varying(80)", False, None),
        ("retrieval_partition_id", "uuid", False, None),
    ),
}

_ACCESS_SCOPE_CHECK_CANONICAL = (
    "CHECK access_scope_kind IS NULL OR one of workspace/org_unit/team/user"
)
_EXPECTED_ACCESS_SCOPE_CHECK_DEFINITIONS = frozenset(
    {
        "CHECK (access_scope_kind IS NULL OR (access_scope_kind::text = ANY "
        "(ARRAY['workspace'::character varying::text, "
        "'org_unit'::character varying::text, 'team'::character varying::text, "
        "'user'::character varying::text])))",
        "CHECK (access_scope_kind IS NULL OR (access_scope_kind::text = ANY "
        "(ARRAY['workspace'::character varying, 'org_unit'::character varying, "
        "'team'::character varying, 'user'::character varying]::text[])))",
    }
)


_EXPECTED_KNOWLEDGE_CONSTRAINTS = frozenset(
    {
        (
            "knowledge_connectors",
            "knowledge_connectors_pkey",
            "p",
            True,
            "PRIMARY KEY (id)",
        ),
        (
            "knowledge_connectors",
            "knowledge_connectors_workspace_id_fkey",
            "f",
            True,
            "FOREIGN KEY (workspace_id) REFERENCES workspaces(id)",
        ),
        (
            "knowledge_connectors",
            "uq_knowledge_connector_workspace_source",
            "u",
            True,
            "UNIQUE (workspace_id, source_type)",
        ),
        (
            "knowledge_document_artifacts",
            "knowledge_document_artifacts_pkey",
            "p",
            True,
            "PRIMARY KEY (id)",
        ),
        (
            "knowledge_document_artifacts",
            "knowledge_document_artifacts_source_document_id_fkey",
            "f",
            True,
            "FOREIGN KEY (source_document_id) REFERENCES knowledge_source_documents(id) "
            "ON DELETE CASCADE",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_pkey",
            "p",
            True,
            "PRIMARY KEY (id)",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_source_document_id_fkey",
            "f",
            True,
            "FOREIGN KEY (source_document_id) REFERENCES knowledge_source_documents(id) "
            "ON DELETE CASCADE",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_workspace_id_fkey",
            "f",
            True,
            "FOREIGN KEY (workspace_id) REFERENCES workspaces(id)",
        ),
        (
            "knowledge_source_documents",
            "ck_knowledge_docs_access_scope_kind",
            "c",
            True,
            _ACCESS_SCOPE_CHECK_CANONICAL,
        ),
        (
            "knowledge_source_documents",
            "fk_knowledge_source_documents_retrieval_partition_id",
            "f",
            False,
            "FOREIGN KEY (retrieval_partition_id) REFERENCES retrieval_partitions(id) "
            "ON DELETE RESTRICT NOT VALID",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_connector_id_fkey",
            "f",
            True,
            "FOREIGN KEY (connector_id) REFERENCES knowledge_connectors(id)",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_owner_id_fkey",
            "f",
            True,
            "FOREIGN KEY (owner_id) REFERENCES users(id)",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_pkey",
            "p",
            True,
            "PRIMARY KEY (id)",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_workspace_id_fkey",
            "f",
            True,
            "FOREIGN KEY (workspace_id) REFERENCES workspaces(id)",
        ),
        (
            "knowledge_source_documents",
            "uq_knowledge_doc_workspace_source_external",
            "u",
            True,
            "UNIQUE (workspace_id, source_type, external_id)",
        ),
    }
)

_EXPECTED_KNOWLEDGE_INTERNAL_TRIGGERS = frozenset(
    {
        (
            "knowledge_connectors",
            "knowledge_connectors_workspace_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_connectors",
            "knowledge_connectors_workspace_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_connectors",
            "knowledge_source_documents_connector_id_fkey",
            "O",
            9,
            "RI_FKey_noaction_del",
        ),
        (
            "knowledge_connectors",
            "knowledge_source_documents_connector_id_fkey",
            "O",
            17,
            "RI_FKey_noaction_upd",
        ),
        (
            "knowledge_document_artifacts",
            "knowledge_document_artifacts_source_document_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_document_artifacts",
            "knowledge_document_artifacts_source_document_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_source_document_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_source_document_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_workspace_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_ingest_jobs",
            "knowledge_ingest_jobs_workspace_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_source_documents",
            "fk_knowledge_source_documents_retrieval_partition_id",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_source_documents",
            "fk_knowledge_source_documents_retrieval_partition_id",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_source_documents",
            "knowledge_document_artifacts_source_document_id_fkey",
            "O",
            9,
            "RI_FKey_cascade_del",
        ),
        (
            "knowledge_source_documents",
            "knowledge_document_artifacts_source_document_id_fkey",
            "O",
            17,
            "RI_FKey_noaction_upd",
        ),
        (
            "knowledge_source_documents",
            "knowledge_ingest_jobs_source_document_id_fkey",
            "O",
            9,
            "RI_FKey_cascade_del",
        ),
        (
            "knowledge_source_documents",
            "knowledge_ingest_jobs_source_document_id_fkey",
            "O",
            17,
            "RI_FKey_noaction_upd",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_connector_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_connector_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_owner_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_owner_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_workspace_id_fkey",
            "O",
            5,
            "RI_FKey_check_ins",
        ),
        (
            "knowledge_source_documents",
            "knowledge_source_documents_workspace_id_fkey",
            "O",
            17,
            "RI_FKey_check_upd",
        ),
    }
)

_EXPECTED_KNOWLEDGE_INDEXES = frozenset(
    {
        (
            "knowledge_connectors",
            "CREATE INDEX ix_knowledge_connectors_source_type ON knowledge_connectors USING btree (source_type)",
        ),
        (
            "knowledge_connectors",
            "CREATE INDEX ix_knowledge_connectors_workspace_enabled ON knowledge_connectors USING btree (workspace_id, enabled)",
        ),
        (
            "knowledge_connectors",
            "CREATE INDEX ix_knowledge_connectors_workspace_id ON knowledge_connectors USING btree (workspace_id)",
        ),
        (
            "knowledge_connectors",
            "CREATE UNIQUE INDEX knowledge_connectors_pkey ON knowledge_connectors USING btree (id)",
        ),
        (
            "knowledge_connectors",
            "CREATE UNIQUE INDEX uq_knowledge_connector_workspace_source ON knowledge_connectors USING btree (workspace_id, source_type)",
        ),
        (
            "knowledge_document_artifacts",
            "CREATE INDEX ix_knowledge_artifacts_document_type ON knowledge_document_artifacts USING btree (source_document_id, artifact_type)",
        ),
        (
            "knowledge_document_artifacts",
            "CREATE INDEX ix_knowledge_document_artifacts_artifact_type ON knowledge_document_artifacts USING btree (artifact_type)",
        ),
        (
            "knowledge_document_artifacts",
            "CREATE INDEX ix_knowledge_document_artifacts_content_hash ON knowledge_document_artifacts USING btree (content_hash)",
        ),
        (
            "knowledge_document_artifacts",
            "CREATE INDEX ix_knowledge_document_artifacts_source_document_id ON knowledge_document_artifacts USING btree (source_document_id)",
        ),
        (
            "knowledge_document_artifacts",
            "CREATE UNIQUE INDEX knowledge_document_artifacts_pkey ON knowledge_document_artifacts USING btree (id)",
        ),
        (
            "knowledge_ingest_jobs",
            "CREATE INDEX ix_knowledge_ingest_jobs_document_status ON knowledge_ingest_jobs USING btree (source_document_id, status)",
        ),
        (
            "knowledge_ingest_jobs",
            "CREATE INDEX ix_knowledge_ingest_jobs_source_document_id ON knowledge_ingest_jobs USING btree (source_document_id)",
        ),
        (
            "knowledge_ingest_jobs",
            "CREATE INDEX ix_knowledge_ingest_jobs_workspace_id ON knowledge_ingest_jobs USING btree (workspace_id)",
        ),
        (
            "knowledge_ingest_jobs",
            "CREATE INDEX ix_knowledge_ingest_jobs_workspace_status ON knowledge_ingest_jobs USING btree (workspace_id, status, created_at)",
        ),
        (
            "knowledge_ingest_jobs",
            "CREATE UNIQUE INDEX knowledge_ingest_jobs_pkey ON knowledge_ingest_jobs USING btree (id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_docs_access_scope ON knowledge_source_documents USING btree (workspace_id, access_scope_kind, access_scope_id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_docs_origin ON knowledge_source_documents USING btree (origin_ref_type, origin_ref_id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_docs_source_updated ON knowledge_source_documents USING btree (workspace_id, source_updated_at)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_docs_workspace_status ON knowledge_source_documents USING btree (workspace_id, ingest_status, rag_status)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_access_scope_id ON knowledge_source_documents USING btree (access_scope_id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_access_scope_kind ON knowledge_source_documents USING btree (access_scope_kind)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_connector_id ON knowledge_source_documents USING btree (connector_id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_content_hash ON knowledge_source_documents USING btree (content_hash)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_deleted_at ON knowledge_source_documents USING btree (deleted_at)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_disabled_at ON knowledge_source_documents USING btree (disabled_at)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_owner_id ON knowledge_source_documents USING btree (owner_id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_source_type ON knowledge_source_documents USING btree (source_type)",
        ),
        (
            "knowledge_source_documents",
            "CREATE INDEX ix_knowledge_source_documents_workspace_id ON knowledge_source_documents USING btree (workspace_id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE UNIQUE INDEX knowledge_source_documents_pkey ON knowledge_source_documents USING btree (id)",
        ),
        (
            "knowledge_source_documents",
            "CREATE UNIQUE INDEX uq_knowledge_doc_workspace_source_external ON knowledge_source_documents USING btree (workspace_id, source_type, external_id)",
        ),
    }
)

_EXPECTED_PARTITION_CONSUMER_FOREIGN_KEYS = frozenset(
    {
        (
            "docs_native_docs",
            "fk_docs_native_docs_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "file_manager_corpora",
            "fk_file_corpora_partition",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "file_manager_files",
            "fk_file_manager_files_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "file_manager_folders",
            "fk_file_manager_folders_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "knowledge_source_documents",
            "fk_knowledge_source_documents_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "legacy_issue_ai_chunks",
            "fk_legacy_issue_ai_chunks_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "legacy_issue_attachment_index_jobs",
            "fk_legacy_issue_attachment_index_jobs_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "legacy_issue_attachments",
            "fk_legacy_issue_attachments_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "legacy_issue_data_revisions",
            "fk_legacy_issue_data_revisions_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "legacy_issue_records",
            "fk_legacy_issue_records_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "meetings",
            "fk_meetings_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "planner_events",
            "fk_planner_events_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "pms_tasks",
            "fk_pms_tasks_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "qna_documents",
            "fk_qna_documents_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "rag_sync_jobs",
            "fk_rag_sync_jobs_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "retrieval_projection_events",
            "retrieval_projection_events_retrieval_partition_id_fkey",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "retrieval_projection_heads",
            "retrieval_projection_heads_retrieval_partition_id_fkey",
            ("retrieval_partition_id",),
            ("id",),
        ),
        (
            "search_index_jobs",
            "fk_search_index_jobs_retrieval_partition_id",
            ("retrieval_partition_id",),
            ("id",),
        ),
    }
)


def upgrade() -> None:
    _set_postgresql_lock_timeout()

    # Resolve every destructive and canonical target before locking so a partial
    # schema fails with an actionable retirement error.
    _assert_expected_retirement_schema()
    _lock_retirement_tables()

    # Re-read the schema contract after acquiring the locks. This closes the DDL
    # race between the initial inspection and the destructive preflight.
    _assert_expected_retirement_schema()
    _assert_knowledge_data_is_retirable()

    # Retrieval partitions are permanent control-plane history. Retire them in
    # place only after the entire allowlist has passed under the same locks.
    op.execute(
        sa.text(
            """
            UPDATE retrieval_partitions
            SET state = 'retired',
                is_default_ingest = false,
                updated_at = CURRENT_TIMESTAMP
            WHERE source_namespace = 'knowledge'
            """
        )
    )

    for table_name in _DROP_ORDER:
        op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge schema retirement is irreversible; restore the pre-deploy "
        "database backup together with the previous application binary"
    )


def _assert_expected_retirement_schema() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    current_schema = inspector.default_schema_name
    existing_tables = set(inspector.get_table_names(schema=current_schema))
    missing_tables = sorted(_REQUIRED_TABLES - existing_tables)
    unexpected_knowledge_tables = sorted(
        table_name
        for table_name in existing_tables
        if table_name.startswith("knowledge_") and table_name not in _KNOWLEDGE_TABLES
    )
    if missing_tables or unexpected_knowledge_tables:
        raise RuntimeError(
            "Knowledge schema retirement refused: expected retirement schema mismatch "
            f"(missing={missing_tables}, "
            f"unexpected_knowledge={unexpected_knowledge_tables})"
        )

    inbound_foreign_keys = (
        _postgresql_inbound_foreign_keys()
        if bind.dialect.name == "postgresql"
        else _inspected_inbound_foreign_keys(inspector, existing_tables, current_schema)
    )
    unexpected = sorted(inbound_foreign_keys - _ALLOWED_INBOUND_FOREIGN_KEYS)
    missing = sorted(_ALLOWED_INBOUND_FOREIGN_KEYS - inbound_foreign_keys)
    if unexpected or missing:
        formatted_unexpected = "; ".join(_format_foreign_key(item) for item in unexpected)
        formatted_missing = "; ".join(_format_foreign_key(item) for item in missing)
        raise RuntimeError(
            "Knowledge schema retirement refused: inbound foreign key contract mismatch "
            f"(unexpected=[{formatted_unexpected}], missing=[{formatted_missing}])"
        )

    if bind.dialect.name == "postgresql":
        _assert_exact_postgresql_knowledge_schema()
        _postgresql_partition_consumer_foreign_keys()


def _normalize_constraint_definition(constraint_name: str, definition: str) -> str:
    if (
        constraint_name == "ck_knowledge_docs_access_scope_kind"
        and definition in _EXPECTED_ACCESS_SCOPE_CHECK_DEFINITIONS
    ):
        return _ACCESS_SCOPE_CHECK_CANONICAL
    return definition


def _assert_exact_postgresql_knowledge_schema() -> None:
    bind = op.get_bind()
    parameters = {"knowledge_tables": list(_KNOWLEDGE_TABLES)}

    actual_columns: dict[str, list[tuple[str, str, bool, str | None]]] = {
        table_name: [] for table_name in _KNOWLEDGE_TABLES
    }
    column_rows = (
        bind.execute(
            sa.text(
                """
                SELECT table_row.relname AS table_name,
                       attribute_row.attname AS column_name,
                       format_type(
                           attribute_row.atttypid,
                           attribute_row.atttypmod
                       ) AS data_type,
                       attribute_row.attnotnull AS not_null,
                       pg_get_expr(
                           default_row.adbin,
                           default_row.adrelid
                       ) AS server_default
                FROM pg_catalog.pg_class AS table_row
                JOIN pg_catalog.pg_namespace AS namespace_row
                  ON namespace_row.oid = table_row.relnamespace
                JOIN pg_catalog.pg_attribute AS attribute_row
                  ON attribute_row.attrelid = table_row.oid
                LEFT JOIN pg_catalog.pg_attrdef AS default_row
                  ON default_row.adrelid = table_row.oid
                 AND default_row.adnum = attribute_row.attnum
                WHERE namespace_row.nspname = current_schema()
                  AND table_row.relname = ANY(:knowledge_tables)
                  AND attribute_row.attnum > 0
                  AND NOT attribute_row.attisdropped
                ORDER BY table_row.relname, attribute_row.attnum
                """
            ),
            parameters,
        )
        .mappings()
        .all()
    )
    for row in column_rows:
        actual_columns[str(row["table_name"])].append(
            (
                str(row["column_name"]),
                str(row["data_type"]),
                bool(row["not_null"]),
                None if row["server_default"] is None else str(row["server_default"]),
            )
        )
    normalized_columns = {
        table_name: tuple(columns) for table_name, columns in actual_columns.items()
    }
    if normalized_columns != _EXPECTED_KNOWLEDGE_COLUMNS:
        changed_tables = sorted(
            table_name
            for table_name in _KNOWLEDGE_TABLES
            if normalized_columns.get(table_name) != _EXPECTED_KNOWLEDGE_COLUMNS.get(table_name)
        )
        raise RuntimeError(
            "Knowledge schema retirement refused: exact column contract mismatch "
            f"(tables={changed_tables})"
        )

    actual_constraints = frozenset(
        (
            str(row["table_name"]),
            str(row["constraint_name"]),
            str(row["constraint_type"]),
            bool(row["validated"]),
            _normalize_constraint_definition(str(row["constraint_name"]), str(row["definition"])),
        )
        for row in bind.execute(
            sa.text(
                """
                SELECT table_row.relname AS table_name,
                       constraint_row.conname AS constraint_name,
                       constraint_row.contype AS constraint_type,
                       constraint_row.convalidated AS validated,
                       pg_get_constraintdef(
                           constraint_row.oid,
                           true
                       ) AS definition
                FROM pg_catalog.pg_constraint AS constraint_row
                JOIN pg_catalog.pg_class AS table_row
                  ON table_row.oid = constraint_row.conrelid
                JOIN pg_catalog.pg_namespace AS namespace_row
                  ON namespace_row.oid = table_row.relnamespace
                WHERE namespace_row.nspname = current_schema()
                  AND table_row.relname = ANY(:knowledge_tables)
                  AND constraint_row.contype <> 'n'
                ORDER BY table_row.relname, constraint_row.conname
                """
            ),
            parameters,
        ).mappings()
    )
    if actual_constraints != _EXPECTED_KNOWLEDGE_CONSTRAINTS:
        expected_by_name = {
            (table_name, constraint_name): (constraint_type, validated, definition)
            for (
                table_name,
                constraint_name,
                constraint_type,
                validated,
                definition,
            ) in _EXPECTED_KNOWLEDGE_CONSTRAINTS
        }
        actual_by_name = {
            (table_name, constraint_name): (constraint_type, validated, definition)
            for (
                table_name,
                constraint_name,
                constraint_type,
                validated,
                definition,
            ) in actual_constraints
        }
        changed = sorted(
            (
                name,
                expected_by_name[name],
                actual_by_name[name],
            )
            for name in expected_by_name.keys() & actual_by_name.keys()
            if expected_by_name[name] != actual_by_name[name]
        )
        raise RuntimeError(
            "Knowledge schema retirement refused: exact constraint contract mismatch "
            f"(missing={sorted(expected_by_name.keys() - actual_by_name.keys())}, "
            f"unexpected={sorted(actual_by_name.keys() - expected_by_name.keys())}, "
            f"changed={changed})"
        )

    index_rows = (
        bind.execute(
            sa.text(
                """
                SELECT table_row.relname AS table_name,
                       index_row.indisvalid AS valid,
                       index_row.indisready AS ready,
                       pg_get_indexdef(
                           index_row.indexrelid,
                           0,
                           true
                       ) AS definition
                FROM pg_catalog.pg_index AS index_row
                JOIN pg_catalog.pg_class AS table_row
                  ON table_row.oid = index_row.indrelid
                JOIN pg_catalog.pg_namespace AS namespace_row
                  ON namespace_row.oid = table_row.relnamespace
                WHERE namespace_row.nspname = current_schema()
                  AND table_row.relname = ANY(:knowledge_tables)
                ORDER BY table_row.relname, index_row.indexrelid
                """
            ),
            parameters,
        )
        .mappings()
        .all()
    )
    invalid_indexes = sorted(
        str(row["definition"])
        for row in index_rows
        if not bool(row["valid"]) or not bool(row["ready"])
    )
    actual_indexes = frozenset(
        (str(row["table_name"]), str(row["definition"])) for row in index_rows
    )
    if invalid_indexes or actual_indexes != _EXPECTED_KNOWLEDGE_INDEXES:
        raise RuntimeError(
            "Knowledge schema retirement refused: exact index contract mismatch "
            f"(invalid={invalid_indexes}, expected={len(_EXPECTED_KNOWLEDGE_INDEXES)}, "
            f"actual={len(actual_indexes)})"
        )

    actual_internal_triggers = frozenset(
        (
            str(row["table_name"]),
            str(row["constraint_name"]),
            str(row["enabled"]),
            int(row["trigger_type"]),
            str(row["function_name"]),
        )
        for row in bind.execute(
            sa.text(
                """
                SELECT table_row.relname AS table_name,
                       constraint_row.conname AS constraint_name,
                       trigger_row.tgenabled AS enabled,
                       trigger_row.tgtype AS trigger_type,
                       function_row.proname AS function_name
                FROM pg_catalog.pg_trigger AS trigger_row
                JOIN pg_catalog.pg_class AS table_row
                  ON table_row.oid = trigger_row.tgrelid
                JOIN pg_catalog.pg_namespace AS namespace_row
                  ON namespace_row.oid = table_row.relnamespace
                JOIN pg_catalog.pg_constraint AS constraint_row
                  ON constraint_row.oid = trigger_row.tgconstraint
                JOIN pg_catalog.pg_proc AS function_row
                  ON function_row.oid = trigger_row.tgfoid
                WHERE namespace_row.nspname = current_schema()
                  AND table_row.relname = ANY(:knowledge_tables)
                  AND trigger_row.tgisinternal
                """
            ),
            parameters,
        ).mappings()
    )
    if actual_internal_triggers != _EXPECTED_KNOWLEDGE_INTERNAL_TRIGGERS:
        raise RuntimeError(
            "Knowledge schema retirement refused: exact internal trigger contract "
            f"mismatch (expected={len(_EXPECTED_KNOWLEDGE_INTERNAL_TRIGGERS)}, "
            f"actual={len(actual_internal_triggers)})"
        )

    unexpected_triggers = sorted(
        (str(row["table_name"]), str(row["trigger_name"]))
        for row in bind.execute(
            sa.text(
                """
                SELECT table_row.relname AS table_name,
                       trigger_row.tgname AS trigger_name
                FROM pg_catalog.pg_trigger AS trigger_row
                JOIN pg_catalog.pg_class AS table_row
                  ON table_row.oid = trigger_row.tgrelid
                JOIN pg_catalog.pg_namespace AS namespace_row
                  ON namespace_row.oid = table_row.relnamespace
                WHERE namespace_row.nspname = current_schema()
                  AND table_row.relname = ANY(:knowledge_tables)
                  AND NOT trigger_row.tgisinternal
                """
            ),
            parameters,
        ).mappings()
    )
    if unexpected_triggers:
        raise RuntimeError(
            "Knowledge schema retirement refused: exact trigger contract mismatch "
            f"(unexpected={unexpected_triggers})"
        )


def _format_foreign_key(
    foreign_key: tuple[str, tuple[str, ...], str, tuple[str, ...]],
) -> str:
    table_name, columns, referred_table, referred_columns = foreign_key
    return f"{table_name}({', '.join(columns)}) -> {referred_table}({', '.join(referred_columns)})"


def _postgresql_inbound_foreign_keys() -> set[tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT child_namespace.nspname AS child_schema,
                       child_table.relname AS child_table,
                       parent_table.relname AS parent_table,
                       ARRAY(
                           SELECT child_attribute.attname
                           FROM unnest(constraint_row.conkey) WITH ORDINALITY
                                AS child_key(attnum, position)
                           JOIN pg_catalog.pg_attribute AS child_attribute
                             ON child_attribute.attrelid = constraint_row.conrelid
                            AND child_attribute.attnum = child_key.attnum
                           ORDER BY child_key.position
                       ) AS child_columns,
                       ARRAY(
                           SELECT parent_attribute.attname
                           FROM unnest(constraint_row.confkey) WITH ORDINALITY
                                AS parent_key(attnum, position)
                           JOIN pg_catalog.pg_attribute AS parent_attribute
                             ON parent_attribute.attrelid = constraint_row.confrelid
                            AND parent_attribute.attnum = parent_key.attnum
                           ORDER BY parent_key.position
                       ) AS parent_columns
                FROM pg_catalog.pg_constraint AS constraint_row
                JOIN pg_catalog.pg_class AS child_table
                  ON child_table.oid = constraint_row.conrelid
                JOIN pg_catalog.pg_namespace AS child_namespace
                  ON child_namespace.oid = child_table.relnamespace
                JOIN pg_catalog.pg_class AS parent_table
                  ON parent_table.oid = constraint_row.confrelid
                JOIN pg_catalog.pg_namespace AS parent_namespace
                  ON parent_namespace.oid = parent_table.relnamespace
                WHERE constraint_row.contype = 'f'
                  AND parent_namespace.nspname = current_schema()
                  AND parent_table.relname = ANY(:knowledge_tables)
                """
            ).bindparams(knowledge_tables=list(_KNOWLEDGE_TABLES))
        )
        .mappings()
    )

    current_schema = sa.inspect(op.get_bind()).default_schema_name
    inbound: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
    for row in rows:
        child_table = str(row["child_table"])
        if row["child_schema"] != current_schema:
            child_table = f"{row['child_schema']}.{child_table}"
        inbound.add(
            (
                child_table,
                tuple(row["child_columns"]),
                str(row["parent_table"]),
                tuple(row["parent_columns"]),
            )
        )
    return inbound


def _postgresql_partition_consumer_foreign_keys() -> frozenset[
    tuple[str, str, tuple[str, ...], tuple[str, ...]]
]:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT child_namespace.nspname AS child_schema,
                       child_table.relname AS child_table,
                       constraint_row.conname AS constraint_name,
                       ARRAY(
                           SELECT child_attribute.attname
                           FROM unnest(constraint_row.conkey) WITH ORDINALITY
                                AS child_key(attnum, position)
                           JOIN pg_catalog.pg_attribute AS child_attribute
                             ON child_attribute.attrelid = constraint_row.conrelid
                            AND child_attribute.attnum = child_key.attnum
                           ORDER BY child_key.position
                       ) AS child_columns,
                       ARRAY(
                           SELECT parent_attribute.attname
                           FROM unnest(constraint_row.confkey) WITH ORDINALITY
                                AS parent_key(attnum, position)
                           JOIN pg_catalog.pg_attribute AS parent_attribute
                             ON parent_attribute.attrelid = constraint_row.confrelid
                            AND parent_attribute.attnum = parent_key.attnum
                           ORDER BY parent_key.position
                       ) AS parent_columns
                FROM pg_catalog.pg_constraint AS constraint_row
                JOIN pg_catalog.pg_class AS child_table
                  ON child_table.oid = constraint_row.conrelid
                JOIN pg_catalog.pg_namespace AS child_namespace
                  ON child_namespace.oid = child_table.relnamespace
                JOIN pg_catalog.pg_class AS parent_table
                  ON parent_table.oid = constraint_row.confrelid
                JOIN pg_catalog.pg_namespace AS parent_namespace
                  ON parent_namespace.oid = parent_table.relnamespace
                WHERE constraint_row.contype = 'f'
                  AND parent_namespace.nspname = current_schema()
                  AND parent_table.relname = 'retrieval_partitions'
                """
            )
        )
        .mappings()
        .all()
    )
    current_schema = sa.inspect(op.get_bind()).default_schema_name
    actual = frozenset(
        (
            (
                str(row["child_table"])
                if row["child_schema"] == current_schema
                else f"{row['child_schema']}.{row['child_table']}"
            ),
            str(row["constraint_name"]),
            tuple(row["child_columns"]),
            tuple(row["parent_columns"]),
        )
        for row in rows
    )
    if actual != _EXPECTED_PARTITION_CONSUMER_FOREIGN_KEYS:
        expected_names = {
            (table_name, constraint_name)
            for table_name, constraint_name, *_ in _EXPECTED_PARTITION_CONSUMER_FOREIGN_KEYS
        }
        actual_names = {(table_name, constraint_name) for table_name, constraint_name, *_ in actual}
        raise RuntimeError(
            "Knowledge schema retirement refused: retrieval partition consumer FK "
            f"contract mismatch (missing={sorted(expected_names - actual_names)}, "
            f"unexpected={sorted(actual_names - expected_names)})"
        )
    return actual


def _inspected_inbound_foreign_keys(
    inspector: sa.Inspector,
    table_names: set[str],
    schema: str | None,
) -> set[tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
    inbound: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
    for table_name in table_names:
        for foreign_key in inspector.get_foreign_keys(table_name, schema=schema):
            referred_table = foreign_key["referred_table"]
            if referred_table not in _KNOWLEDGE_TABLES:
                continue
            inbound.add(
                (
                    table_name,
                    tuple(foreign_key["constrained_columns"]),
                    referred_table,
                    tuple(foreign_key["referred_columns"]),
                )
            )
    return inbound


def _set_postgresql_lock_timeout() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"SET LOCAL lock_timeout = '{_POSTGRESQL_LOCK_TIMEOUT}'"))


def _lock_retirement_tables() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            LOCK TABLE
                knowledge_ingest_jobs,
                knowledge_document_artifacts,
                knowledge_source_documents,
                knowledge_connectors
            IN ACCESS EXCLUSIVE MODE
            """
        )
    )
    partition_consumer_tables = {
        table_name
        for table_name, *_ in _postgresql_partition_consumer_foreign_keys()
        if table_name not in _KNOWLEDGE_TABLES
    }
    lock_tables = sorted(_RETIREMENT_CONTROL_LOCK_TABLES | partition_consumer_tables)
    bind = op.get_bind()
    current_schema = sa.inspect(bind).default_schema_name
    preparer = bind.dialect.identifier_preparer
    quoted_tables = ",\n                ".join(
        f"{preparer.quote_schema(current_schema)}.{preparer.quote(table_name)}"
        for table_name in lock_tables
    )
    op.execute(
        sa.text(
            f"LOCK TABLE\n                {quoted_tables}\n            IN SHARE ROW EXCLUSIVE MODE"
        )
    )


def _assert_knowledge_data_is_retirable() -> None:
    _refuse_if_rows_remain(
        "SELECT count(*) FROM knowledge_document_artifacts",
        "Knowledge document artifacts remain",
    )
    _refuse_if_rows_remain(
        "SELECT count(*) FROM knowledge_ingest_jobs",
        "Knowledge ingest jobs remain",
    )
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM knowledge_source_documents
        WHERE source_type NOT IN ('meeting_attachment', 'pms_attachment')
        """,
        "unsupported Knowledge source types remain",
    )
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM knowledge_connectors
        WHERE source_type NOT IN ('meeting_attachment', 'pms_attachment')
        """,
        "unsupported Knowledge connector types remain",
    )
    _assert_no_duplicate_mirrors()
    _assert_source_connector_contract()
    _assert_source_partition_contract()
    _assert_no_surviving_partition_references()
    _assert_attachment_mirror_state()
    _assert_canonical_parent_chains()
    _assert_canonical_mirror_identity()
    _assert_all_connectors_are_referenced()
    _assert_delivery_control_plane_is_retirable()


def _refuse_if_rows_remain(statement: str, reason: str) -> None:
    count = int(op.get_bind().scalar(sa.text(statement)) or 0)
    if count:
        raise RuntimeError(f"Knowledge schema retirement refused: {reason} (count={count})")


def _assert_no_surviving_partition_references() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    bind = op.get_bind()
    current_schema = sa.inspect(bind).default_schema_name
    preparer = bind.dialect.identifier_preparer
    violations: list[tuple[str, int]] = []
    for table_name, _, child_columns, _ in sorted(_postgresql_partition_consumer_foreign_keys()):
        if table_name in _KNOWLEDGE_TABLES:
            continue
        column_name = child_columns[0]
        quoted_table = f"{preparer.quote_schema(current_schema)}.{preparer.quote(table_name)}"
        quoted_column = preparer.quote(column_name)
        count = int(
            bind.scalar(
                sa.text(
                    f"""
                    SELECT count(*)
                    FROM {quoted_table} AS consumer
                    JOIN retrieval_partitions AS partition
                      ON partition.id = consumer.{quoted_column}
                    WHERE partition.source_namespace = :source_namespace
                    """
                ),
                {"source_namespace": "knowledge"},
            )
            or 0
        )
        if count:
            violations.append((table_name, count))

    if violations:
        raise RuntimeError(
            "Knowledge schema retirement refused: surviving retrieval partition "
            f"references remain (tables={violations})"
        )


def _assert_no_duplicate_mirrors() -> None:
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM (
            SELECT source_type, external_id
            FROM knowledge_source_documents
            GROUP BY source_type, external_id
            HAVING count(*) > 1
        ) AS duplicate
        """,
        "duplicate canonical mirrors remain",
    )


def _assert_source_connector_contract() -> None:
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM knowledge_source_documents AS source
        LEFT JOIN knowledge_connectors AS connector
          ON connector.id = source.connector_id
        WHERE source.connector_id IS NULL
           OR connector.id IS NULL
           OR connector.workspace_id IS DISTINCT FROM source.workspace_id
           OR connector.source_type IS DISTINCT FROM source.source_type
        """,
        "source connector contract violations remain",
    )


def _assert_all_connectors_are_referenced() -> None:
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM knowledge_connectors AS connector
        WHERE NOT EXISTS (
            SELECT 1
            FROM knowledge_source_documents AS source
            WHERE source.connector_id = connector.id
              AND source.workspace_id = connector.workspace_id
              AND source.source_type = connector.source_type
        )
        """,
        "unreferenced Knowledge connectors remain",
    )


def _assert_source_partition_contract() -> None:
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM knowledge_source_documents AS source
        LEFT JOIN retrieval_partitions AS partition
          ON partition.id = source.retrieval_partition_id
        WHERE source.retrieval_partition_id IS NOT NULL
          AND (
              partition.id IS NULL
              OR partition.source_namespace IS DISTINCT FROM 'knowledge'
              OR partition.managed_workspace_id IS DISTINCT FROM source.workspace_id
              OR partition.candidate_scope_kind IS DISTINCT FROM 'workspace'
              OR partition.candidate_workspace_id IS DISTINCT FROM source.workspace_id
              OR partition.candidate_user_id IS NOT NULL
              OR partition.state IS DISTINCT FROM 'active'
              OR partition.is_default_ingest IS DISTINCT FROM true
          )
        """,
        "source partition contract violations remain",
    )


def _assert_attachment_mirror_state() -> None:
    _refuse_if_rows_remain(
        """
        SELECT count(*)
        FROM knowledge_source_documents
        WHERE ingest_status IS DISTINCT FROM 'succeeded'
           OR rag_status IS DISTINCT FROM 'excluded'
           OR chunk_count IS DISTINCT FROM 0
           OR ingested_at IS NOT NULL
           OR indexed_at IS NOT NULL
           OR last_error IS NOT NULL
           OR deleted_at IS NOT NULL
           OR disabled_at IS NOT NULL
        """,
        "attachment mirror state violations remain",
    )


def _assert_canonical_parent_chains() -> None:
    pms_violations = _count_rows(
        """
        SELECT count(*)
        FROM knowledge_source_documents AS source
        LEFT JOIN pms_attachments AS attachment
          ON attachment.id = source.external_id
        LEFT JOIN pms_tasks AS task
          ON task.id = attachment.task_id
        LEFT JOIN pms_task_lists AS task_list
          ON task_list.id = task.list_id
        LEFT JOIN teams AS team
          ON team.id = task_list.team_id
        WHERE source.source_type = 'pms_attachment'
          AND (
              attachment.id IS NULL
              OR task.id IS NULL
              OR task_list.id IS NULL
              OR team.id IS NULL
              OR team.workspace_id IS DISTINCT FROM source.workspace_id
          )
        """
    )
    meeting_violations = _count_rows(
        """
        SELECT count(*)
        FROM knowledge_source_documents AS source
        LEFT JOIN meeting_file_attachments AS attachment
          ON attachment.id = source.external_id
        LEFT JOIN meetings AS meeting
          ON meeting.id = attachment.meeting_id
        WHERE source.source_type = 'meeting_attachment'
          AND (
              attachment.id IS NULL
              OR meeting.id IS NULL
              OR meeting.workspace_id IS DISTINCT FROM source.workspace_id
          )
        """
    )
    if pms_violations or meeting_violations:
        raise RuntimeError(
            "Knowledge schema retirement refused: canonical parent chain violations remain "
            f"(pms={pms_violations}, meeting={meeting_violations})"
        )


def _assert_canonical_mirror_identity() -> None:
    pms_violations = _count_rows(
        """
        SELECT count(*)
        FROM knowledge_source_documents AS source
        LEFT JOIN pms_attachments AS attachment
          ON attachment.id = source.external_id
        WHERE source.source_type = 'pms_attachment'
          AND (
              attachment.id IS NULL
              OR source.origin_ref_type IS DISTINCT FROM 'pms_task'
              OR source.origin_ref_id IS DISTINCT FROM attachment.task_id
              OR source.storage_provider IS DISTINCT FROM 'minio'
              OR source.storage_key IS DISTINCT FROM attachment.storage_key
              OR source.owner_id IS DISTINCT FROM attachment.uploaded_by_id
              OR source.title IS DISTINCT FROM attachment.filename
              OR source.filename IS DISTINCT FROM attachment.filename
              OR source.mime_type IS DISTINCT FROM attachment.content_type
              OR source.size_bytes IS DISTINCT FROM attachment.size_bytes
              OR source.metadata IS DISTINCT FROM jsonb_build_object(
                  'task_id', attachment.task_id,
                  'attachment_id', attachment.id
              )
          )
        """
    )
    meeting_violations = _count_rows(
        """
        SELECT count(*)
        FROM knowledge_source_documents AS source
        LEFT JOIN meeting_file_attachments AS attachment
          ON attachment.id = source.external_id
        WHERE source.source_type = 'meeting_attachment'
          AND (
              attachment.id IS NULL
              OR source.origin_ref_type IS DISTINCT FROM 'meeting'
              OR source.origin_ref_id IS DISTINCT FROM attachment.meeting_id
              OR source.storage_provider IS DISTINCT FROM 'minio'
              OR source.storage_key IS DISTINCT FROM attachment.storage_key
              OR source.owner_id IS DISTINCT FROM attachment.added_by_id
              OR source.title IS DISTINCT FROM attachment.filename
              OR source.filename IS DISTINCT FROM attachment.filename
              OR source.mime_type IS DISTINCT FROM attachment.content_type
              OR source.size_bytes IS DISTINCT FROM attachment.size_bytes
              OR source.metadata IS DISTINCT FROM jsonb_build_object(
                  'meeting_id', attachment.meeting_id,
                  'attachment_id', attachment.id
              )
          )
        """
    )
    if pms_violations or meeting_violations:
        raise RuntimeError(
            "Knowledge schema retirement refused: canonical mirror identity violations remain "
            f"(pms={pms_violations}, meeting={meeting_violations})"
        )


def _assert_delivery_control_plane_is_retirable() -> None:
    projection_heads = _count_rows(
        """
        SELECT count(*)
        FROM retrieval_projection_heads
        WHERE resource_type = :resource_type
        """,
        {"resource_type": _KNOWLEDGE_RESOURCE_TYPE},
    )
    projection_events = _count_rows(
        """
        SELECT count(*)
        FROM retrieval_projection_events
        WHERE resource_type = :resource_type
        """,
        {"resource_type": _KNOWLEDGE_RESOURCE_TYPE},
    )
    if projection_heads or projection_events:
        raise RuntimeError(
            "Knowledge schema retirement refused: projection control-plane references remain "
            f"(heads={projection_heads}, events={projection_events})"
        )

    search_jobs = _count_rows(
        """
        SELECT count(*)
        FROM search_index_jobs
        WHERE resource_type = :resource_type
           OR entity_type = :resource_type
        """,
        {"resource_type": _KNOWLEDGE_RESOURCE_TYPE},
    )
    if search_jobs:
        raise RuntimeError(
            "Knowledge schema retirement refused: Knowledge search index jobs remain "
            f"(count={search_jobs})"
        )

    unsafe_rag_receipts = _count_rows(
        """
        SELECT count(*)
        FROM rag_sync_jobs AS job
        WHERE job.resource_type = :resource_type
          AND NOT (
              job.operation = 'delete'
              AND job.status = 'succeeded'
              AND NOT EXISTS (
                  SELECT 1
                  FROM knowledge_source_documents AS source
                  WHERE source.id = job.resource_id
              )
              AND job.desired_state IS NULL
              AND job.retrieval_partition_id IS NULL
              AND job.projection_event_sequence IS NULL
              AND job.projection_version IS NULL
              AND job.content_checksum IS NULL
              AND job.visibility_checksum IS NULL
              AND job.last_error IS NULL
          )
        """,
        {"resource_type": _KNOWLEDGE_RESOURCE_TYPE},
    )
    if unsafe_rag_receipts:
        raise RuntimeError(
            "Knowledge schema retirement refused: unapproved Knowledge RAG delete "
            f"receipts remain (count={unsafe_rag_receipts})"
        )


def _count_rows(statement: str, parameters: dict[str, object] | None = None) -> int:
    return int(op.get_bind().scalar(sa.text(statement), parameters or {}) or 0)
