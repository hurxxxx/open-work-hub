from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import Base and all model modules so Base.metadata is fully populated.
from open_alm_api.core.db import Base
from open_alm_api.core.model_registry import import_all_models
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.ai import approvals as ai_approvals  # noqa: F401
from open_alm_api.domains.ai import models as ai_models  # noqa: F401
from open_alm_api.domains.ai.runtime import models as ai_runtime_models  # noqa: F401
from open_alm_api.domains.auth import models as auth_models  # noqa: F401
from open_alm_api.domains.conversations import models as conversations_models  # noqa: F401
from open_alm_api.domains.dataviz import models as dataviz_models  # noqa: F401
from open_alm_api.domains.dataviz import sys_perf_models as dataviz_sys_perf_models  # noqa: F401
from open_alm_api.domains.diagrams import models as diagrams_models  # noqa: F401
from open_alm_api.domains.lawsearch import models as lawsearch_models  # noqa: F401
from open_alm_api.domains.dm import models as dm_models  # noqa: F401
from open_alm_api.domains.docs import models as docs_models  # noqa: F401
from open_alm_api.domains.files import models as files_models  # noqa: F401
from open_alm_api.domains.images import models as images_models  # noqa: F401
from open_alm_api.domains.legacy_issues import models as legacy_issues_models  # noqa: F401
from open_alm_api.domains.mail import models as mail_models  # noqa: F401
from open_alm_api.domains.meal_invoice_ocr import models as meal_invoice_ocr_models  # noqa: F401
from open_alm_api.domains.media import models as media_models  # noqa: F401
from open_alm_api.domains.meeting import models as meeting_models  # noqa: F401
from open_alm_api.domains.mcloudoc import models as mcloudoc_models  # noqa: F401
from open_alm_api.domains.news import models as news_models  # noqa: F401
from open_alm_api.domains.notifications import models as notifications_models  # noqa: F401
from open_alm_api.domains.patent_automation import models as patent_automation_models  # noqa: F401
from open_alm_api.domains.personal_widgets import models as personal_widgets_models  # noqa: F401
from open_alm_api.domains.planner import models as planner_models  # noqa: F401
from open_alm_api.domains.pms import models as pms_models  # noqa: F401
from open_alm_api.domains.qna import models as qna_models  # noqa: F401
from open_alm_api.domains.rag import models as rag_models  # noqa: F401
from open_alm_api.domains.retrieval import models as retrieval_models  # noqa: F401
from open_alm_api.domains.release_notes import models as release_notes_models  # noqa: F401
from open_alm_api.domains.recording import models as recording_models  # noqa: F401
from open_alm_api.domains.search import models as search_models  # noqa: F401
from open_alm_api.domains.spec_compare import models as spec_compare_models  # noqa: F401
from open_alm_api.domains.video_chat import models as video_chat_models  # noqa: F401
from open_alm_api.domains.whiteboard import models as whiteboard_models  # noqa: F401

import_all_models()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the DSN from app settings unless an override was passed in
# programmatically (e.g. tests). Allows operators to run alembic without
# duplicating the connection string in alembic.ini.
if not config.get_main_option("sqlalchemy.url", "").startswith(
    ("postgresql://", "postgresql+psycopg://")
):
    config.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)

target_metadata = Base.metadata

_MANUALLY_MANAGED_INDEXES = {
    "ix_audit_logs_action_created",
    "ix_audit_logs_actor_created",
    "ix_audit_logs_created_at",
}


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    del compare_to
    if type_ == "index" and name in _MANUALLY_MANAGED_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
