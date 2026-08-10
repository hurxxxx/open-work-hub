from __future__ import annotations

from collections.abc import Iterator

from alembic import command
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import OrgUnit, User, Workspace
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRevisionOverviewHistory,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition


pytestmark = pytest.mark.migration

BASE_REVISION = "e4a7c9d2f6b1"
ATTACHMENT_REVISION = "f6c8a0b2d4e7"
ATTACHMENT_TABLE = "legacy_issue_revision_meeting_attachments"
CLEANUP_TABLE = "legacy_issue_revision_meeting_attachment_cleanups"
DATASET_KEY = "legacy_issue.common-master.aircon"


@pytest.fixture
def revision_meeting_attachment_migration_config(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
) -> Iterator[object]:
    monkeypatch.setenv("AI_DO_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("AI_DO_LLM_HEALTHCHECK_ON_STARTUP", "0")

    from ai_do_api.core.db import _alembic_config
    from ai_do_api.core.settings import get_settings

    get_settings.cache_clear()
    engine = create_engine(postgres_dsn)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueRevisionOverviewHistory.__table__,
        ],
    )
    engine.dispose()

    try:
        config = _alembic_config()
        command.stamp(config, BASE_REVISION)
        yield config
    finally:
        get_settings.cache_clear()


def test_revision_meeting_attachment_migration_backfills_and_is_reversible(
    revision_meeting_attachment_migration_config,
    postgres_dsn: str,
) -> None:
    engine = create_engine(postgres_dsn)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO workspaces (
                        id, key, name, description, active, created_at, updated_at
                    ) VALUES (
                        'meeting-attachment-workspace',
                        'meeting-attachment-workspace',
                        'Meeting Attachment Workspace',
                        '',
                        true,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login_id, email, full_name, password_hash,
                        auth_provider, status, login_blocked, is_admin,
                        must_change_password, theme_preference, locale, time_zone,
                        date_format, app_bar_layout, created_at
                    ) VALUES (
                        'meeting-attachment-user',
                        'meeting-attachment-user',
                        'meeting-attachment-user@ai-do.local',
                        'Meeting Attachment User',
                        'hash',
                        'local',
                        'active',
                        false,
                        false,
                        false,
                        'system',
                        'ko-KR',
                        'Asia/Seoul',
                        'korean',
                        '{}',
                        CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO legacy_issue_data_revisions (
                        id, workspace_id, dataset_key, revision_no, status, note,
                        created_at, updated_at, published_at
                    ) VALUES
                    (
                        'meeting-revision-active',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        1,
                        'published',
                        'Active imported row',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-hidden',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        2,
                        'published',
                        'Hidden imported row',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-system',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        3,
                        'published',
                        'Needs system row',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-unlinked-hidden',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        4,
                        'published',
                        'Unlinked hidden source row',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-aggregate',
                        'meeting-attachment-workspace',
                        'legacy_issue.common-master',
                        1,
                        'published',
                        'Aggregate revision',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-internal',
                        'meeting-attachment-workspace',
                        'legacy_issue.checklist-source.abc123',
                        1,
                        'published',
                        'Internal revision',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-number-fallback',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        5,
                        'published',
                        'Number fallback revision',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-revision-number-owner',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        10,
                        'published',
                        'Renumbered overview owner',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"dataset_key": DATASET_KEY},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO legacy_issue_revision_overview_history (
                        id, workspace_id, dataset_key, linked_revision_id, origin,
                        revision_no, revision_label, sort_order, deleted_at,
                        created_at, updated_at
                    ) VALUES
                    (
                        'meeting-history-active',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        NULL,
                        'imported',
                        1,
                        '1',
                        0,
                        NULL,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-history-hidden',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        'meeting-revision-hidden',
                        'imported',
                        2,
                        '2',
                        1,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-history-unlinked-hidden',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        NULL,
                        'imported',
                        4,
                        '4',
                        2,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    ),
                    (
                        'meeting-history-occupied-number',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        'meeting-revision-number-owner',
                        'manual',
                        5,
                        '5',
                        3,
                        NULL,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"dataset_key": DATASET_KEY},
            )

        assert {ATTACHMENT_TABLE, CLEANUP_TABLE}.isdisjoint(inspect(engine).get_table_names())
        command.upgrade(
            revision_meeting_attachment_migration_config,
            ATTACHMENT_REVISION,
        )

        inspector = inspect(engine)
        assert {ATTACHMENT_TABLE, CLEANUP_TABLE}.issubset(inspector.get_table_names())
        assert {column["name"] for column in inspector.get_columns(ATTACHMENT_TABLE)} == {
            "id",
            "workspace_id",
            "dataset_key",
            "overview_history_id",
            "filename",
            "content_type",
            "size_bytes",
            "description",
            "storage_key",
            "uploaded_by_id",
            "client_request_id",
            "created_at",
            "updated_at",
        }
        assert {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(ATTACHMENT_TABLE)
        } == {
            ("storage_key",),
            (
                "workspace_id",
                "dataset_key",
                "overview_history_id",
                "uploaded_by_id",
                "client_request_id",
            ),
        }
        assert {
            constraint["name"] for constraint in inspector.get_check_constraints(ATTACHMENT_TABLE)
        } == {
            "ck_legacy_issue_revision_meeting_attachments_size",
            "ck_li_revision_meeting_attachment_request_length",
        }
        overview_fk = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys(ATTACHMENT_TABLE)
            if foreign_key["constrained_columns"] == ["overview_history_id"]
        )
        assert overview_fk["options"].get("ondelete") == "RESTRICT"
        assert {column["name"] for column in inspector.get_columns(CLEANUP_TABLE)} == {
            "id",
            "workspace_id",
            "storage_key",
            "attempt_count",
            "last_error",
            "last_attempted_at",
            "created_at",
        }

        with engine.begin() as connection:
            active_link = connection.scalar(
                text(
                    "SELECT linked_revision_id "
                    "FROM legacy_issue_revision_overview_history "
                    "WHERE id = 'meeting-history-active'"
                )
            )
            hidden_link = connection.scalar(
                text(
                    "SELECT linked_revision_id "
                    "FROM legacy_issue_revision_overview_history "
                    "WHERE id = 'meeting-history-hidden'"
                )
            )
            system_row = connection.execute(
                text(
                    "SELECT id, origin, revision_no, revision_label, summary, deleted_at "
                    "FROM legacy_issue_revision_overview_history "
                    "WHERE linked_revision_id = 'meeting-revision-system'"
                )
            ).one()
            hidden_replacement_count = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM legacy_issue_revision_overview_history "
                    "WHERE linked_revision_id = 'meeting-revision-hidden' "
                    "AND deleted_at IS NULL"
                )
            )
            unlinked_hidden_system_count = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM legacy_issue_revision_overview_history "
                    "WHERE linked_revision_id = 'meeting-revision-unlinked-hidden' "
                    "AND origin = 'system' AND deleted_at IS NULL"
                )
            )
            out_of_scope_history_count = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM legacy_issue_revision_overview_history "
                    "WHERE dataset_key IN ("
                    "'legacy_issue.common-master', "
                    "'legacy_issue.checklist-source.abc123'"
                    ")"
                )
            )
            number_fallback = connection.execute(
                text(
                    "SELECT revision_no, revision_label "
                    "FROM legacy_issue_revision_overview_history "
                    "WHERE linked_revision_id = 'meeting-revision-number-fallback'"
                )
            ).one()
            connection.execute(
                text(
                    f"""
                    INSERT INTO {ATTACHMENT_TABLE} (
                        id, workspace_id, dataset_key, overview_history_id,
                        filename, content_type, size_bytes, description,
                        storage_key, uploaded_by_id, client_request_id,
                        created_at, updated_at
                    ) VALUES (
                        'meeting-attachment-1',
                        'meeting-attachment-workspace',
                        :dataset_key,
                        :history_id,
                        'minutes.pdf',
                        'application/pdf',
                        10,
                        'decision record',
                        'legacy-issues/revision-meeting-attachments/object-1',
                        'meeting-attachment-user',
                        'request-1',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"dataset_key": DATASET_KEY, "history_id": system_row.id},
            )

        assert active_link == "meeting-revision-active"
        assert hidden_link == "meeting-revision-hidden"
        assert hidden_replacement_count == 0
        assert unlinked_hidden_system_count == 1
        assert out_of_scope_history_count == 0
        assert number_fallback.revision_no is None
        assert number_fallback.revision_label == "5"
        assert system_row.origin == "system"
        assert system_row.revision_no == 3
        assert system_row.revision_label == "3"
        assert system_row.summary == "Needs system row"
        assert system_row.deleted_at is None

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f"""
                        INSERT INTO {ATTACHMENT_TABLE} (
                            id, workspace_id, dataset_key, overview_history_id,
                            filename, content_type, size_bytes, storage_key,
                            uploaded_by_id, client_request_id, created_at, updated_at
                        ) VALUES (
                            'meeting-attachment-conflict',
                            'meeting-attachment-workspace',
                            :dataset_key,
                            :history_id,
                            'retry.pdf',
                            'application/pdf',
                            10,
                            'legacy-issues/revision-meeting-attachments/object-2',
                            'meeting-attachment-user',
                            'request-1',
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {"dataset_key": DATASET_KEY, "history_id": system_row.id},
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM legacy_issue_revision_overview_history WHERE id = :history_id"
                    ),
                    {"history_id": system_row.id},
                )

        command.downgrade(
            revision_meeting_attachment_migration_config,
            BASE_REVISION,
        )
        assert {ATTACHMENT_TABLE, CLEANUP_TABLE}.isdisjoint(inspect(engine).get_table_names())
    finally:
        engine.dispose()
