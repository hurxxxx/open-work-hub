"""add the Legacy Issues analysis v2 physical data plane

Revision ID: b5f8d3a1c7e4
Revises: a4e7c2f9d1b6
Create Date: 2026-07-26 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b5f8d3a1c7e4"
down_revision: str | Sequence[str] | None = "a4e7c2f9d1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ANALYSIS_SCHEMA = "legacy_issue_analysis"
ANALYSIS_READER_ROLE = "ai_do_analysis_reader"
VECTOR_TABLE = "data_analysis_nodes_v1"
VECTOR_DIMENSIONS = 1024
VECTOR_BACKEND = "llamaindex-pgvector"
APP_ID = "legacy-issues"
GENERATION_KEY = "1"
MIGRATION_REVISION = revision

ISSUE_VIEW_COLUMNS = (
    "issue_id",
    "stable_issue_id",
    "dataset_key",
    "module_key",
    "revision_no",
    "legacy_issue_number",
    "department",
    "major_category",
    "middle_category",
    "region_zone",
    "occurrence_stage",
    "occurrence_type",
    "oem_disclosure_status",
    "vehicle_model",
    "occurrence_date",
    "received_date",
    "issue_type",
    "cause_type",
    "supplier",
    "part_number",
    "process_name",
    "symptom",
    "cause",
    "countermeasure",
    "countermeasure_type",
    "action",
    "severity_grade",
    "confirmation_content",
    "check_plan",
    "applied",
    "reflection_result",
    "master_status",
    "search_text",
    "created_at",
    "updated_at",
)

CHECKLIST_VIEW_COLUMNS = (
    "checklist_id",
    "vehicle_model",
    "vehicle_code",
    "module_key",
    "checklist_status",
    "source_revision_no",
    "item_count",
    "completed_at",
    "created_at",
    "updated_at",
)

CHECKLIST_ITEM_VIEW_COLUMNS = (
    "checklist_item_id",
    "checklist_id",
    "source_issue_id",
    "stable_issue_id",
    "vehicle_model",
    "vehicle_code",
    "module_key",
    "checklist_status",
    "source_revision_no",
    "legacy_issue_number",
    "major_category",
    "middle_category",
    "region_zone",
    "occurrence_stage",
    "occurrence_type",
    "occurrence_date",
    "issue_type",
    "cause_type",
    "supplier",
    "part_number",
    "process_name",
    "symptom",
    "cause",
    "countermeasure",
    "severity_grade",
    "applied",
    "reflection_result",
    "search_text",
    "created_at",
    "updated_at",
)


def _require_postgresql() -> None:
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Legacy Issues analysis v2 requires PostgreSQL")


def _create_schema_and_conversion_functions() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.execute(sa.text(f"CREATE SCHEMA {ANALYSIS_SCHEMA}"))
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ANALYSIS_SCHEMA}.try_date_v1(raw_value text)
            RETURNS date
            LANGUAGE plpgsql
            IMMUTABLE
            STRICT
            PARALLEL SAFE
            SET search_path = pg_catalog
            AS $function$
            BEGIN
                raw_value := btrim(raw_value);
                IF raw_value !~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                   OR raw_value < '0001-01-01' THEN
                    RETURN NULL;
                END IF;
                BEGIN
                    RETURN raw_value::date;
                EXCEPTION
                    WHEN datetime_field_overflow OR invalid_datetime_format THEN
                        RETURN NULL;
                END;
            END;
            $function$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                payload jsonb,
                field_key text
            )
            RETURNS text
            LANGUAGE sql
            IMMUTABLE
            STRICT
            PARALLEL SAFE
            SET search_path = pg_catalog
            AS $function$
                SELECT CASE jsonb_typeof(payload -> field_key)
                    WHEN 'string' THEN NULLIF(btrim(payload ->> field_key), '')
                    WHEN 'number' THEN NULLIF(btrim(payload ->> field_key), '')
                    WHEN 'boolean' THEN NULLIF(btrim(payload ->> field_key), '')
                    ELSE NULL
                END
            $function$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ANALYSIS_SCHEMA}.try_vector_1024_v1(raw_value text)
            RETURNS vector({VECTOR_DIMENSIONS})
            LANGUAGE plpgsql
            IMMUTABLE
            STRICT
            PARALLEL SAFE
            SET search_path = pg_catalog, public
            AS $function$
            BEGIN
                BEGIN
                    RETURN raw_value::vector({VECTOR_DIMENSIONS});
                EXCEPTION
                    WHEN OTHERS THEN
                        RETURN NULL;
                END;
            END;
            $function$
            """
        )
    )
    for signature in (
        "try_date_v1(text)",
        "jsonb_scalar_text_v1(jsonb, text)",
        "try_vector_1024_v1(text)",
    ):
        op.execute(
            sa.text(
                f"REVOKE ALL ON FUNCTION {ANALYSIS_SCHEMA}.{signature} FROM PUBLIC"
            )
        )


def _create_scoped_issue_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ANALYSIS_SCHEMA}.scoped_issue_records_v1()
            RETURNS TABLE (
                issue_id text,
                stable_issue_id text,
                dataset_key text,
                module_key text,
                revision_no integer,
                legacy_issue_number text,
                department text,
                major_category text,
                middle_category text,
                region_zone text,
                occurrence_stage text,
                occurrence_type text,
                oem_disclosure_status text,
                vehicle_model text,
                occurrence_date date,
                received_date date,
                issue_type text,
                cause_type text,
                supplier text,
                part_number text,
                process_name text,
                symptom text,
                cause text,
                countermeasure text,
                countermeasure_type text,
                action text,
                severity_grade text,
                confirmation_content text,
                check_plan text,
                applied text,
                reflection_result text,
                master_status text,
                search_text text,
                created_at timestamp without time zone,
                updated_at timestamp without time zone
            )
            LANGUAGE sql
            STABLE
            PARALLEL SAFE
            SECURITY DEFINER
            SET search_path = pg_catalog, public, {ANALYSIS_SCHEMA}
            AS $function$
                SELECT
                    records.id::text,
                    COALESCE(records.stable_record_id, records.id)::text,
                    records.dataset_key::text,
                    records.module_key::text,
                    revisions.revision_no,
                    NULLIF(btrim(records.legacy_issue_number), ''),
                    NULLIF(btrim(records.department), ''),
                    NULLIF(btrim(records.major_category), ''),
                    NULLIF(btrim(records.middle_category), ''),
                    NULLIF(btrim(records.region_zone), ''),
                    NULLIF(btrim(records.occurrence_stage), ''),
                    NULLIF(btrim(records.occurrence_type), ''),
                    NULLIF(btrim(records.oem_disclosure_status), ''),
                    NULLIF(btrim(records.vehicle_model), ''),
                    {ANALYSIS_SCHEMA}.try_date_v1(
                        records.occurrence_date::text
                    ),
                    {ANALYSIS_SCHEMA}.try_date_v1(
                        records.received_date::text
                    ),
                    NULLIF(btrim(records.issue_type), ''),
                    NULLIF(btrim(records.cause_type), ''),
                    NULLIF(btrim(records.supplier), ''),
                    NULLIF(btrim(records.part_number), ''),
                    NULLIF(btrim(records.process_name), ''),
                    NULLIF(btrim(records.symptom), ''),
                    NULLIF(btrim(records.cause), ''),
                    NULLIF(btrim(records.countermeasure), ''),
                    NULLIF(btrim(records.countermeasure_type), ''),
                    NULLIF(btrim(records.action), ''),
                    NULLIF(btrim(records.severity_grade), ''),
                    NULLIF(btrim(records.confirmation_content), ''),
                    NULLIF(btrim(records.check_plan), ''),
                    NULLIF(btrim(records.applied), ''),
                    NULLIF(btrim(records.reflection_result), ''),
                    NULLIF(btrim(records.evidence_legacy_issue), ''),
                    NULLIF(btrim(records.search_text), ''),
                    records.created_at,
                    records.updated_at
                FROM public.legacy_issue_records AS records
                JOIN public.legacy_issue_data_revisions AS revisions
                  ON revisions.id = records.revision_id
                 AND revisions.workspace_id = records.workspace_id
                WHERE records.workspace_id =
                          NULLIF(
                              current_setting(
                                  'ai_do.legacy_issue_workspace_id',
                                  true
                              ),
                              ''
                          )
                  AND records.module_key = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_module_keys',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
                  AND records.revision_id = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_revision_ids',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
                  AND (
                      records.retrieval_partition_id IS NULL
                      OR records.retrieval_partition_id::text = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_partition_ids',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
                  )
            $function$
            """
        )
    )


def _create_scoped_checklist_functions() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ANALYSIS_SCHEMA}.scoped_vehicle_checklists_v1()
            RETURNS TABLE (
                checklist_id text,
                vehicle_model text,
                vehicle_code text,
                module_key text,
                checklist_status text,
                source_revision_no integer,
                item_count integer,
                completed_at timestamp without time zone,
                created_at timestamp without time zone,
                updated_at timestamp without time zone
            )
            LANGUAGE sql
            STABLE
            PARALLEL SAFE
            SECURITY DEFINER
            SET search_path = pg_catalog, public, {ANALYSIS_SCHEMA}
            AS $function$
                SELECT
                    checklists.id::text,
                    COALESCE(
                        NULLIF(btrim(vehicles.vehicle_name), ''),
                        vehicles.vehicle_code
                    )::text,
                    vehicles.vehicle_code::text,
                    checklists.module_key::text,
                    checklists.status::text,
                    checklists.source_master_revision_no,
                    checklists.row_count,
                    checklists.completed_at,
                    checklists.created_at,
                    checklists.updated_at
                FROM public.legacy_issue_vehicle_module_checklists AS checklists
                JOIN public.legacy_issue_vehicle_models AS vehicles
                  ON vehicles.id = checklists.vehicle_model_id
                 AND vehicles.workspace_id = checklists.workspace_id
                WHERE checklists.workspace_id =
                          NULLIF(
                              current_setting(
                                  'ai_do.legacy_issue_workspace_id',
                                  true
                              ),
                              ''
                          )
                  AND checklists.id = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_checklist_ids',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
                  AND checklists.module_key = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_module_keys',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
            $function$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {ANALYSIS_SCHEMA}.scoped_vehicle_checklist_items_v1()
            RETURNS TABLE (
                checklist_item_id text,
                checklist_id text,
                source_issue_id text,
                stable_issue_id text,
                vehicle_model text,
                vehicle_code text,
                module_key text,
                checklist_status text,
                source_revision_no integer,
                legacy_issue_number text,
                major_category text,
                middle_category text,
                region_zone text,
                occurrence_stage text,
                occurrence_type text,
                occurrence_date date,
                issue_type text,
                cause_type text,
                supplier text,
                part_number text,
                process_name text,
                symptom text,
                cause text,
                countermeasure text,
                severity_grade text,
                applied text,
                reflection_result text,
                search_text text,
                created_at timestamp without time zone,
                updated_at timestamp without time zone
            )
            LANGUAGE sql
            STABLE
            PARALLEL SAFE
            SECURITY DEFINER
            SET search_path = pg_catalog, public, {ANALYSIS_SCHEMA}
            AS $function$
                SELECT
                    items.id::text,
                    checklists.id::text,
                    items.source_record_id::text,
                    COALESCE(
                        items.source_stable_record_id,
                        items.source_record_id
                    )::text,
                    COALESCE(
                        NULLIF(btrim(vehicles.vehicle_name), ''),
                        vehicles.vehicle_code
                    )::text,
                    vehicles.vehicle_code::text,
                    checklists.module_key::text,
                    checklists.status::text,
                    checklists.source_master_revision_no,
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'legacy_issue_number'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'major_category'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'middle_category'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'region_zone'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'occurrence_stage'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'occurrence_type'
                    ),
                    {ANALYSIS_SCHEMA}.try_date_v1(
                        {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                            items.field_values,
                            'occurrence_date'
                        )
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'issue_type'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'cause_type'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'supplier'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'part_number'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'process_name'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'symptom'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'cause'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'countermeasure'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'severity_grade'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'applied'
                    ),
                    {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                        items.field_values,
                        'reflection_result'
                    ),
                    NULLIF(
                        concat_ws(
                            ' ',
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'legacy_issue_number'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'major_category'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'middle_category'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'region_zone'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'occurrence_stage'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'occurrence_type'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'issue_type'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'cause_type'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'supplier'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'part_number'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'process_name'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'symptom'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'cause'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'countermeasure'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'severity_grade'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'applied'
                            ),
                            {ANALYSIS_SCHEMA}.jsonb_scalar_text_v1(
                                items.field_values,
                                'reflection_result'
                            )
                        ),
                        ''
                    ),
                    items.created_at,
                    items.updated_at
                FROM public.legacy_issue_vehicle_module_checklist_records AS items
                JOIN public.legacy_issue_vehicle_module_checklists AS checklists
                  ON checklists.id = items.checklist_id
                 AND checklists.workspace_id = items.workspace_id
                JOIN public.legacy_issue_vehicle_models AS vehicles
                  ON vehicles.id = checklists.vehicle_model_id
                 AND vehicles.workspace_id = checklists.workspace_id
                WHERE items.workspace_id =
                          NULLIF(
                              current_setting(
                                  'ai_do.legacy_issue_workspace_id',
                                  true
                              ),
                              ''
                          )
                  AND checklists.id = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_checklist_ids',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
                  AND checklists.module_key = ANY(
                          COALESCE(
                              string_to_array(
                                  NULLIF(
                                      current_setting(
                                          'ai_do.legacy_issue_module_keys',
                                          true
                                      ),
                                      ''
                                  ),
                                  ','
                              ),
                              ARRAY[]::text[]
                          )
                      )
            $function$
            """
        )
    )


def _create_security_barrier_views() -> None:
    views = (
        ("issue_records_v1", "scoped_issue_records_v1"),
        ("vehicle_checklists_v1", "scoped_vehicle_checklists_v1"),
        (
            "vehicle_checklist_items_v1",
            "scoped_vehicle_checklist_items_v1",
        ),
    )
    for view_name, function_name in views:
        op.execute(
            sa.text(
                f"""
                CREATE VIEW {ANALYSIS_SCHEMA}.{view_name}
                WITH (security_barrier = true, security_invoker = true)
                AS
                SELECT *
                FROM {ANALYSIS_SCHEMA}.{function_name}()
                """
            )
        )
        op.execute(
            sa.text(
                f"REVOKE ALL ON TABLE {ANALYSIS_SCHEMA}.{view_name} FROM PUBLIC"
            )
        )
    for function_name in (
        "scoped_issue_records_v1()",
        "scoped_vehicle_checklists_v1()",
        "scoped_vehicle_checklist_items_v1()",
    ):
        op.execute(
            sa.text(
                f"REVOKE ALL ON FUNCTION {ANALYSIS_SCHEMA}.{function_name} FROM PUBLIC"
            )
        )


def _create_vector_table() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TABLE {ANALYSIS_SCHEMA}.{VECTOR_TABLE} (
                id bigserial PRIMARY KEY,
                text varchar NOT NULL,
                metadata_ jsonb,
                node_id varchar,
                embedding vector({VECTOR_DIMENSIONS}),
                text_search_tsv tsvector
                    GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED
            )
            """
        )
    )


def _backfill_legacy_evidence_nodes() -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO {ANALYSIS_SCHEMA}.{VECTOR_TABLE} (
                text,
                metadata_,
                node_id,
                embedding
            )
            SELECT
                chunks.search_text,
                jsonb_build_object(
                    'workspace_id', chunks.workspace_id,
                    'partition_id', COALESCE(
                        chunks.retrieval_partition_id,
                        records.retrieval_partition_id,
                        revisions.retrieval_partition_id
                    ),
                    'module_key', records.module_key,
                    'revision_id', COALESCE(
                        chunks.revision_id,
                        records.revision_id
                    ),
                    'source_kind', 'legacy_issue_record',
                    'source_id', records.id,
                    'content_hash', encode(
                        sha256(convert_to(chunks.search_text, 'UTF8')),
                        'hex'
                    ),
                    'generation', {GENERATION_KEY}::integer
                ),
                concat(
                    'legacy_issue_record:',
                    records.id,
                    ':',
                    left(chunks.id, 16),
                    ':',
                    'g',
                    {GENERATION_KEY}
                ),
                {ANALYSIS_SCHEMA}.try_vector_1024_v1(
                    chunks.embedding_vector
                )
            FROM public.legacy_issue_ai_chunks AS chunks
            JOIN public.legacy_issue_records AS records
              ON records.id = chunks.record_id
             AND records.workspace_id = chunks.workspace_id
            LEFT JOIN public.legacy_issue_data_revisions AS revisions
              ON revisions.id = COALESCE(
                     chunks.revision_id,
                     records.revision_id
                 )
             AND revisions.workspace_id = chunks.workspace_id
            WHERE chunks.embedding_status = 'embedded'
              AND chunks.embedding_dimensions = {VECTOR_DIMENSIONS}
              AND chunks.embedding_vector IS NOT NULL
              AND NULLIF(btrim(chunks.search_text), '') IS NOT NULL
              AND COALESCE(
                      chunks.retrieval_partition_id,
                      records.retrieval_partition_id,
                      revisions.retrieval_partition_id
                  ) IS NOT NULL
              AND COALESCE(
                      chunks.revision_id,
                      records.revision_id
                  ) IS NOT NULL
              AND records.module_key IS NOT NULL
              AND {ANALYSIS_SCHEMA}.try_vector_1024_v1(
                      chunks.embedding_vector
                  ) IS NOT NULL
            """
        )
    )


def _backfill_analysis_metadata_nodes() -> None:
    op.execute(
        sa.text(
            f"""
            WITH scoped_revisions AS (
                SELECT DISTINCT
                    records.workspace_id,
                    COALESCE(
                        records.retrieval_partition_id,
                        revisions.retrieval_partition_id
                    ) AS partition_id,
                    records.module_key,
                    records.revision_id
                FROM public.legacy_issue_records AS records
                JOIN public.legacy_issue_data_revisions AS revisions
                  ON revisions.id = records.revision_id
                 AND revisions.workspace_id = records.workspace_id
                WHERE records.module_key IS NOT NULL
                  AND records.revision_id IS NOT NULL
                  AND COALESCE(
                          records.retrieval_partition_id,
                          revisions.retrieval_partition_id
                      ) IS NOT NULL
            ),
            metadata_documents(source_id, document_text) AS (
                VALUES
                    (
                        'view.issue_records_v1',
                        '과거차 문제점 1건당 1행. 차종, 권역, 모듈, 발생일, '
                        '유형, 원인, 협력사, 부품, 심각도, 대책, 적용 여부를 '
                        '집계하거나 상세 조회한다.'
                    ),
                    (
                        'view.vehicle_checklists_v1',
                        '차량과 모듈별 체크리스트 문서 1개당 1행. 문서 상태와 '
                        '항목 수, 원본 리비전, 완료일을 집계한다.'
                    ),
                    (
                        'view.vehicle_checklist_items_v1',
                        '차량 체크리스트 항목 1개당 1행. 원본 과거차 문제점과 '
                        '안정 식별자로 연결하여 반영 범위와 누락을 분석한다.'
                    )
            )
            INSERT INTO {ANALYSIS_SCHEMA}.{VECTOR_TABLE} (
                text,
                metadata_,
                node_id,
                embedding
            )
            SELECT
                documents.document_text,
                jsonb_build_object(
                    'workspace_id', scopes.workspace_id,
                    'partition_id', scopes.partition_id,
                    'module_key', scopes.module_key,
                    'revision_id', scopes.revision_id,
                    'source_kind', 'analysis_metadata',
                    'source_id', documents.source_id,
                    'content_hash', encode(
                        sha256(
                            convert_to(documents.document_text, 'UTF8')
                        ),
                        'hex'
                    ),
                    'generation', {GENERATION_KEY}::integer
                ),
                concat(
                    'analysis_metadata:',
                    documents.source_id,
                    ':',
                    left(
                        md5(
                            concat_ws(
                                ':',
                                scopes.workspace_id,
                                scopes.partition_id,
                                scopes.module_key,
                                scopes.revision_id
                            )
                        ),
                        16
                    ),
                    ':',
                    'g',
                    {GENERATION_KEY}
                ),
                NULL
            FROM scoped_revisions AS scopes
            CROSS JOIN metadata_documents AS documents
            """
        )
    )


def _create_vector_indexes() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX uq_data_analysis_nodes_v1_node_id
            ON {ANALYSIS_SCHEMA}.{VECTOR_TABLE} (node_id)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX analysis_nodes_v1_idx
            ON {ANALYSIS_SCHEMA}.{VECTOR_TABLE}
            USING gin (text_search_tsv)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX analysis_nodes_v1_idx_1
            ON {ANALYSIS_SCHEMA}.{VECTOR_TABLE}
            ((metadata_ ->> 'ref_doc_id'))
            """
        )
    )
    for metadata_key in (
        "workspace_id",
        "partition_id",
        "module_key",
        "revision_id",
        "source_kind",
        "source_id",
        "content_hash",
    ):
        op.execute(
            sa.text(
                f"""
                CREATE INDEX analysis_nodes_v1_idx_{metadata_key}_text
                ON {ANALYSIS_SCHEMA}.{VECTOR_TABLE}
                ((metadata_ ->> '{metadata_key}'))
                """
            )
        )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX analysis_nodes_v1_idx_generation_integer
            ON {ANALYSIS_SCHEMA}.{VECTOR_TABLE}
            (((metadata_ ->> 'generation')::integer))
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX data_analysis_nodes_v1_embedding_idx
            ON {ANALYSIS_SCHEMA}.{VECTOR_TABLE}
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """
        )
    )


def _seed_index_generations() -> None:
    for source_namespace, source_kind, embedding_model_expression in (
        (
            "legacy_issues",
            "legacy_issue_record",
            """
            (
                SELECT max(chunks.embedding_model)
                FROM public.legacy_issue_ai_chunks AS chunks
                WHERE chunks.workspace_id = workspaces.id
                  AND chunks.embedding_status = 'embedded'
                  AND chunks.embedding_dimensions = 1024
            )
            """,
        ),
        ("legacy_issue_analysis_metadata", "analysis_metadata", "NULL"),
    ):
        op.execute(
            sa.text(
                f"""
                INSERT INTO public.ai_index_generations (
                    id,
                    workspace_id,
                    app_id,
                    generation_key,
                    status,
                    backend,
                    source_namespace,
                    schema_version,
                    embedding_provider,
                    embedding_model,
                    embedding_dimensions,
                    source_count,
                    document_count,
                    chunk_count,
                    corpus_sha256,
                    validation_status,
                    validation_json,
                    created_by_user_id,
                    validated_at,
                    cutover_at,
                    retired_at,
                    created_at,
                    updated_at
                )
                SELECT
                    gen_random_uuid()::text,
                    workspaces.id,
                    '{APP_ID}',
                    '{GENERATION_KEY}',
                    'active',
                    '{VECTOR_BACKEND}',
                    '{source_namespace}',
                    1,
                    'inference-gateway-embedding',
                    {embedding_model_expression},
                    {VECTOR_DIMENSIONS},
                    (
                        SELECT count(
                                   DISTINCT nodes.metadata_ ->> 'source_id'
                               )::integer
                        FROM {ANALYSIS_SCHEMA}.{VECTOR_TABLE} AS nodes
                        WHERE nodes.metadata_ ->> 'workspace_id' =
                                  workspaces.id
                          AND nodes.metadata_ ->> 'source_kind' =
                                  '{source_kind}'
                          AND (nodes.metadata_ ->> 'generation')::integer =
                                  {GENERATION_KEY}
                    ),
                    (
                        SELECT count(*)::integer
                        FROM {ANALYSIS_SCHEMA}.{VECTOR_TABLE} AS nodes
                        WHERE nodes.metadata_ ->> 'workspace_id' =
                                  workspaces.id
                          AND nodes.metadata_ ->> 'source_kind' =
                                  '{source_kind}'
                          AND (nodes.metadata_ ->> 'generation')::integer =
                                  {GENERATION_KEY}
                    ),
                    (
                        SELECT count(*)::integer
                        FROM {ANALYSIS_SCHEMA}.{VECTOR_TABLE} AS nodes
                        WHERE nodes.metadata_ ->> 'workspace_id' =
                                  workspaces.id
                          AND nodes.metadata_ ->> 'source_kind' =
                                  '{source_kind}'
                          AND (nodes.metadata_ ->> 'generation')::integer =
                                  {GENERATION_KEY}
                    ),
                    (
                        SELECT encode(
                                   sha256(
                                       convert_to(
                                           COALESCE(
                                               string_agg(
                                                   nodes.metadata_
                                                       ->> 'content_hash',
                                                   ''
                                                   ORDER BY nodes.node_id
                                               ),
                                               ''
                                           ),
                                           'UTF8'
                                       )
                                   ),
                                   'hex'
                               )
                        FROM {ANALYSIS_SCHEMA}.{VECTOR_TABLE} AS nodes
                        WHERE nodes.metadata_ ->> 'workspace_id' =
                                  workspaces.id
                          AND nodes.metadata_ ->> 'source_kind' =
                                  '{source_kind}'
                          AND (nodes.metadata_ ->> 'generation')::integer =
                                  {GENERATION_KEY}
                    ),
                    'passed',
                    jsonb_build_object(
                        'bootstrap_revision', '{MIGRATION_REVISION}',
                        'source_kind', '{source_kind}',
                        'generation', {GENERATION_KEY},
                        'backfill_mode',
                        CASE
                            WHEN '{source_kind}' = 'legacy_issue_record'
                                THEN 'compatible_existing_embeddings'
                            ELSE 'fts_metadata_bootstrap'
                        END
                    ),
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                FROM public.workspaces AS workspaces
                ON CONFLICT (
                    workspace_id,
                    app_id,
                    backend,
                    source_namespace,
                    generation_key
                ) DO NOTHING
                """
            )
        )


def _ensure_analysis_reader_role() -> None:
    op.execute(
        sa.text(
            f"""
            DO $block$
            DECLARE
                current_role_can_manage_roles boolean;
                reader_is_safe boolean;
            BEGIN
                SELECT roles.rolsuper OR roles.rolcreaterole
                  INTO current_role_can_manage_roles
                  FROM pg_catalog.pg_roles AS roles
                 WHERE roles.rolname = current_user;

                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = '{ANALYSIS_READER_ROLE}'
                ) THEN
                    IF NOT COALESCE(current_role_can_manage_roles, false) THEN
                        RAISE EXCEPTION
                            'database role {ANALYSIS_READER_ROLE} must be '
                            'pre-provisioned before this migration'
                            USING ERRCODE = '42501',
                                  HINT =
                                      'Create a NOLOGIN, NOINHERIT, '
                                      'NOSUPERUSER, NOCREATEROLE, '
                                      'NOCREATEDB, NOREPLICATION, '
                                      'NOBYPASSRLS role and grant membership '
                                      'to the application migration role.';
                    END IF;
                    EXECUTE
                        'CREATE ROLE {ANALYSIS_READER_ROLE} '
                        'NOLOGIN NOINHERIT NOSUPERUSER NOCREATEROLE '
                        'NOCREATEDB NOREPLICATION NOBYPASSRLS';
                    RAISE NOTICE
                        'created least-privilege database role '
                        '{ANALYSIS_READER_ROLE}';
                ELSE
                    RAISE NOTICE
                        'using pre-provisioned database role '
                        '{ANALYSIS_READER_ROLE}';
                END IF;

                SELECT NOT roles.rolcanlogin
                           AND NOT roles.rolinherit
                           AND NOT roles.rolsuper
                           AND NOT roles.rolcreaterole
                           AND NOT roles.rolcreatedb
                           AND NOT roles.rolreplication
                           AND NOT roles.rolbypassrls
                  INTO reader_is_safe
                  FROM pg_catalog.pg_roles AS roles
                 WHERE roles.rolname = '{ANALYSIS_READER_ROLE}';

                IF NOT COALESCE(reader_is_safe, false) THEN
                    RAISE EXCEPTION
                        'database role {ANALYSIS_READER_ROLE} does not satisfy '
                        'the least-privilege contract'
                        USING ERRCODE = '42501';
                END IF;

                IF NOT pg_has_role(
                    current_user,
                    '{ANALYSIS_READER_ROLE}',
                    'MEMBER'
                ) THEN
                    IF NOT COALESCE(current_role_can_manage_roles, false) THEN
                        RAISE EXCEPTION
                            'application migration role must be a member of '
                            '{ANALYSIS_READER_ROLE}'
                            USING ERRCODE = '42501';
                    END IF;
                    EXECUTE format(
                        'GRANT {ANALYSIS_READER_ROLE} TO %I',
                        current_user
                    );
                    RAISE NOTICE
                        'granted {ANALYSIS_READER_ROLE} membership to %',
                        current_user;
                END IF;
            END;
            $block$
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON SCHEMA {ANALYSIS_SCHEMA} FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"REVOKE CREATE ON SCHEMA {ANALYSIS_SCHEMA} "
            f"FROM {ANALYSIS_READER_ROLE}"
        )
    )
    base_tables = (
        "legacy_issue_records",
        "legacy_issue_data_revisions",
        "legacy_issue_vehicle_models",
        "legacy_issue_vehicle_module_checklists",
        "legacy_issue_vehicle_module_checklist_records",
        "legacy_issue_ai_chunks",
    )
    op.execute(
        sa.text(
            "REVOKE ALL ON TABLE "
            + ", ".join(f"public.{table_name}" for table_name in base_tables)
            + f" FROM {ANALYSIS_READER_ROLE}"
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON TABLE {ANALYSIS_SCHEMA}.{VECTOR_TABLE} "
            f"FROM {ANALYSIS_READER_ROLE}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT USAGE ON SCHEMA {ANALYSIS_SCHEMA} "
            f"TO {ANALYSIS_READER_ROLE}"
        )
    )
    for function_name in (
        "scoped_issue_records_v1()",
        "scoped_vehicle_checklists_v1()",
        "scoped_vehicle_checklist_items_v1()",
    ):
        op.execute(
            sa.text(
                f"GRANT EXECUTE ON FUNCTION "
                f"{ANALYSIS_SCHEMA}.{function_name} "
                f"TO {ANALYSIS_READER_ROLE}"
            )
        )
    for view_name in (
        "issue_records_v1",
        "vehicle_checklists_v1",
        "vehicle_checklist_items_v1",
    ):
        op.execute(
            sa.text(
                f"GRANT SELECT ON TABLE {ANALYSIS_SCHEMA}.{view_name} "
                f"TO {ANALYSIS_READER_ROLE}"
            )
        )


def upgrade() -> None:
    _require_postgresql()
    _create_schema_and_conversion_functions()
    _create_scoped_issue_function()
    _create_scoped_checklist_functions()
    _create_security_barrier_views()
    _create_vector_table()
    _backfill_legacy_evidence_nodes()
    _backfill_analysis_metadata_nodes()
    _create_vector_indexes()
    _seed_index_generations()
    _ensure_analysis_reader_role()


def downgrade() -> None:
    _require_postgresql()
    op.execute(
        sa.text(
            f"""
            DELETE FROM public.ai_index_generations
            WHERE app_id = '{APP_ID}'
              AND backend = '{VECTOR_BACKEND}'
              AND generation_key = '{GENERATION_KEY}'
              AND validation_json ->> 'bootstrap_revision' =
                    '{MIGRATION_REVISION}'
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON SCHEMA {ANALYSIS_SCHEMA} "
            f"FROM {ANALYSIS_READER_ROLE}"
        )
    )
    op.execute(sa.text(f"DROP SCHEMA {ANALYSIS_SCHEMA} CASCADE"))
    # Roles are cluster-wide. The migration deliberately leaves a pre-provisioned
    # reader role and application membership intact on downgrade.
