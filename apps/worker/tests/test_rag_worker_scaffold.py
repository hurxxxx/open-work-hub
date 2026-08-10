# ruff: noqa: E402

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
import importlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_alm_api.core.db import Base  # noqa: E402
from open_alm_api.core.telemetry import (
    bootstrap_telemetry,
    get_tracer_provider,
    start_as_current_span,
)  # noqa: E402
from open_alm_api.domains.auth.models import (  # noqa: E402
    PlatformAppVisibility,
    Team,
    User,
    Workspace,
)
from open_alm_api.domains.qna.constants import QNA_DOCUMENT_RESOURCE_TYPE  # noqa: E402
from open_alm_api.domains.docs.models import (  # noqa: E402
    DocMeetingAccess,
    NativeDoc,
    NativeDocTarget,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from open_alm_api.domains.files import search_hooks as file_search_hooks  # noqa: E402
from open_alm_api.domains.files import storage_adapter as file_storage  # noqa: E402
from open_alm_api.domains.files.models import (  # noqa: E402
    FileManagerFile,
    FileManagerFileSourceMetadata,
)
from open_alm_api.domains.meeting.models import (  # noqa: E402
    Meeting,
    MeetingAttendee,
    MeetingDocLink,
    MeetingRecording,
    MeetingTaskLink,
)
from open_alm_api.domains.pms.models import (  # noqa: E402
    Folder,
    Label,
    Milestone,
    Task,
    TaskAssignee,
    TaskComment,
    TaskFollower,
    TaskLabel,
    TaskList,
    TaskUserAccess,
)
from open_alm_api.domains.planner.models import PlannerEvent  # noqa: E402
from open_alm_api.domains.rag.contracts import (  # noqa: E402
    RagJobStatus,
    RagProjection,
    RagSyncLane,
    RagSyncOperation,
)
from open_alm_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE  # noqa: E402
from open_alm_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE  # noqa: E402
from open_alm_api.domains.rag.pms_projection import PMS_TASK_RESOURCE_TYPE  # noqa: E402
from open_alm_api.domains.rag.providers import (  # noqa: E402
    RagProviderConfigurationError,
    RagProviderTransientError,
)
from open_alm_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob  # noqa: E402
from open_alm_api.domains.rag.outbox import (  # noqa: E402
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)
from open_alm_api.domains.retrieval.models import (  # noqa: E402
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_alm_api.domains.retrieval.projection_fencing import (  # noqa: E402
    ProjectionEventRef,
    record_projection_event,
)
from open_alm_api.domains.retrieval.partition_adapter_registry import (  # noqa: E402
    RetrievalProjectionBinding,
    register_retrieval_partition_adapter,
    reset_retrieval_partition_adapters,
)
from open_alm_api.domains.rag.source_adapter_registry import (  # noqa: E402
    RagResourceAdapter,
    RagVisibilityScopeAdapter,
    register_rag_resource_adapter,
    register_rag_visibility_scope_adapter,
    reset_rag_source_adapters,
)
from open_alm_api.domains.source_access.registry import (  # noqa: E402
    register_source_access_adapter,
    reset_source_access_adapters,
)
from open_alm_api.domains.source_access.resource_types import (  # noqa: E402
    FILE_MANAGER_FILE_RESOURCE_TYPE,
    PLANNER_EVENT_RESOURCE_TYPE,
)
from open_alm_api.domains.search.models import SearchIndexJob  # noqa: E402
from open_alm_api.domains.pms.rag_sync import (  # noqa: E402
    PMS_LABEL_RECOMPUTE_SCOPE,
    PMS_MEETING_VISIBILITY_SCOPE,
)
from open_alm_worker.queue_contract import (  # noqa: E402
    DEFAULT_QUEUE,
    ERP_HR_SNAPSHOT_QUEUE,
    ERP_HR_SNAPSHOT_TASK_NAME,
    HR_MASTER_QUEUE,
    HR_MASTER_TASK_NAME,
    IMAGE_GENERATION_QUEUE,
    IMAGE_GENERATION_TASK_NAME,
    LEGACY_ISSUE_EXCEL_EXPORT_QUEUE,
    LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME,
    LEGACY_PATENT_PRIOR_ART_QUEUE,
    LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS,
    NEWS_COLLECT_QUEUE,
    PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_RECOVER_TASK_NAME,
    PATENT_PRIOR_ART_REPUBLISH_TASK_NAME,
    PATENT_PRIOR_ART_RUN_JOB_TASK_NAME,
    QNA_BOARD_SYNC_QUEUE,
    WORKER_BOOTSTRAP_GROUPS,
    WORKER_QUEUE_GROUPS,
    WORKER_QUEUE_NAMES,
    assert_worker_queue_access,
    celery_task_routes,
    celery_worker_group_concurrency,
    celery_worker_queue_argument,
    worker_bootstrap_group_requires_llm_routing,
)


def _worker_db_path(tmp_path: Path) -> Path:
    return tmp_path / "worker-rag.sqlite3"


def _worker_dsn(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _init_worker_db(
    db_path: Path,
    *,
    create_routing_tables: bool,
    seed_provider_rows: bool,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        if create_routing_tables:
            connection.execute(
                """
                CREATE TABLE ai_model_provider_configs (
                    provider_id TEXT PRIMARY KEY
                )
                """
            )
            connection.execute("CREATE TABLE ai_model_catalog_entries (id TEXT PRIMARY KEY)")
            connection.execute(
                "CREATE TABLE ai_model_route_overrides (workload_id TEXT PRIMARY KEY)"
            )
            connection.execute(
                "CREATE TABLE image_model_provider_configs (provider_id TEXT PRIMARY KEY)"
            )
            connection.execute("CREATE TABLE image_model_profiles (profile_id TEXT PRIMARY KEY)")
        if seed_provider_rows:
            connection.executemany(
                "INSERT INTO ai_model_provider_configs (provider_id) VALUES (?)",
                [(provider_id,) for provider_id in ("anthropic", "gemini", "local", "openai")],
            )
        connection.commit()
    finally:
        connection.close()


def _reload_worker_module(module_name: str):
    for cached_name in list(sys.modules):
        if cached_name == "open_alm_worker" or cached_name.startswith("open_alm_worker."):
            sys.modules.pop(cached_name, None)
    return importlib.import_module(module_name)


@pytest.fixture(autouse=True)
def _default_worker_rag_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "0")
    monkeypatch.setenv("OPEN_ALM_RAG_VECTOR_INDEX_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_RAG_EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_RAG_RERANK_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_RAG_OCR_PROVIDER", "fake")
    reset_rag_source_adapters()
    reset_source_access_adapters()
    reset_retrieval_partition_adapters()
    register_rag_resource_adapter(
        RagResourceAdapter(
            resource_type="doc",
            app_id="tests",
            partition_adapter_id="doc",
            load_projection=lambda db, resource_id, rag_service: None,
        )
    )
    test_adapter = _WorkerTestSourceAccessAdapter()
    register_retrieval_partition_adapter(test_adapter)
    register_source_access_adapter(test_adapter)
    try:
        yield
    finally:
        reset_rag_source_adapters()
        reset_source_access_adapters()
        reset_retrieval_partition_adapters()


class _WorkerTestSourceAccessAdapter:
    adapter_id = "doc"
    partition_adapter_id = "doc"
    source_namespace = "doc"
    resource_types = ("doc",)
    allowed_candidate_scopes = ("workspace",)
    allowed_transitions = ()
    transition_mode = "generic"
    keyword_acl_entity_types = ()

    def bind_resource_partition(
        self,
        db,
        *,
        resource_type: str,
        resource_id: str,
    ) -> RetrievalProjectionBinding:
        del db
        return RetrievalProjectionBinding(
            resource_type=resource_type,
            resource_id=resource_id,
            partition_id="11111111-1111-1111-1111-111111111111",
        )

    def can_read_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
        del policy, resource_type, resource_id
        return True

    def can_read_rag_resource(
        self,
        policy,
        *,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        del policy, resource_type, resource_id
        return True

    def has_accessible_source(self, policy, *, resource_type: str) -> bool:
        del policy, resource_type
        return True

    def keyword_acl_branches(self, policy):
        del policy
        return []


def test_worker_queue_contract_drives_dev_and_prod_worker_surfaces() -> None:
    route_queues = {route["queue"] for route in celery_task_routes().values()}
    assert set(WORKER_QUEUE_NAMES) == {"celery", *route_queues}
    assert celery_task_routes()[IMAGE_GENERATION_TASK_NAME]["queue"] == IMAGE_GENERATION_QUEUE
    assert set().union(*WORKER_QUEUE_GROUPS.values()) == set(WORKER_QUEUE_NAMES)
    assert WORKER_QUEUE_GROUPS["default"] == (
        DEFAULT_QUEUE,
        NEWS_COLLECT_QUEUE,
        QNA_BOARD_SYNC_QUEUE,
    )
    assert IMAGE_GENERATION_QUEUE in WORKER_QUEUE_GROUPS["long"]
    assert LEGACY_ISSUE_EXCEL_EXPORT_QUEUE in WORKER_QUEUE_GROUPS["long"]
    assert WORKER_QUEUE_GROUPS["patent"] == (PATENT_PRIOR_ART_QUEUE,)
    assert PATENT_PRIOR_ART_QUEUE not in WORKER_QUEUE_GROUPS["long"]
    assert PATENT_PRIOR_ART_QUEUE not in celery_worker_queue_argument().split(",")
    assert LEGACY_PATENT_PRIOR_ART_QUEUE not in WORKER_QUEUE_NAMES
    assert PATENT_PRIOR_ART_QUEUE != LEGACY_PATENT_PRIOR_ART_QUEUE
    assert (
        celery_task_routes()[PATENT_PRIOR_ART_RUN_JOB_TASK_NAME]["queue"] == PATENT_PRIOR_ART_QUEUE
    )
    assert celery_task_routes()[PATENT_PRIOR_ART_REPUBLISH_TASK_NAME]["queue"] == DEFAULT_QUEUE
    assert (
        celery_task_routes()[PATENT_PRIOR_ART_RECOVER_TASK_NAME]["queue"]
        == PATENT_PRIOR_ART_QUEUE
    )
    assert celery_worker_group_concurrency("patent") == 1
    assert (
        celery_task_routes()[LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME]["queue"]
        == LEGACY_ISSUE_EXCEL_EXPORT_QUEUE
    )
    # PPT 생성 큐는 전용 워커만 소비하도록 long 에서 분리한다(원격 long 워커의 큐 가로채기 방지).
    # 큐 이름도 과거 "ppt_generate" 에서 분리 — 옛 설정 워커가 재접속 시 재구독하지 못하게 한다.
    assert WORKER_QUEUE_GROUPS["ppt"] == ("ppt_generate_dedicated",)
    assert "ppt_generate_dedicated" not in WORKER_QUEUE_GROUPS["long"]
    assert "ppt_generate" not in WORKER_QUEUE_NAMES
    assert celery_worker_group_concurrency("realtime") > celery_worker_group_concurrency("long")
    assert set(WORKER_BOOTSTRAP_GROUPS) == {
        "all",
        "default",
        "realtime",
        "long",
        "ppt",
        "patent",
        "ai_graph",
        "beat",
    }
    assert LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS == (
        "all",
        "long",
        "ppt",
        "patent",
        "ai_graph",
    )
    assert worker_bootstrap_group_requires_llm_routing("all")
    assert worker_bootstrap_group_requires_llm_routing("long")
    assert worker_bootstrap_group_requires_llm_routing("ppt")
    assert worker_bootstrap_group_requires_llm_routing("patent")
    assert worker_bootstrap_group_requires_llm_routing("ai_graph")
    assert not worker_bootstrap_group_requires_llm_routing("default")
    assert not worker_bootstrap_group_requires_llm_routing("realtime")
    assert not worker_bootstrap_group_requires_llm_routing("beat")

    project = json.loads((WORKSPACE_ROOT / "apps/worker/project.json").read_text())
    worker_command = project["targets"]["dev"]["options"]["commands"][0]
    assert "open_alm_worker.queue_contract --celery-queues" in worker_command
    assert celery_worker_queue_argument() not in worker_command

    default_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker.service.template"
    ).read_text()
    realtime_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker-realtime.service.template"
    ).read_text()
    long_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker-long.service.template"
    ).read_text()
    ai_graph_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker-ai-graph.service.template"
    ).read_text()
    ppt_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker-ppt.service.template"
    ).read_text()
    patent_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker-patent.service.template"
    ).read_text()
    beat_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-prod-worker-beat.service.template"
    ).read_text()
    prod_systemd_script = (WORKSPACE_ROOT / "scripts/prod-systemd.sh").read_text()
    assert "__OPEN_ALM_WORKER_DEFAULT_QUEUE_NAMES__" in default_template
    assert "__OPEN_ALM_WORKER_REALTIME_QUEUE_NAMES__" in realtime_template
    assert "__OPEN_ALM_WORKER_LONG_QUEUE_NAMES__" in long_template
    assert "__OPEN_ALM_WORKER_AI_GRAPH_QUEUE_NAMES__" in ai_graph_template
    assert "__OPEN_ALM_WORKER_PPT_QUEUE_NAMES__" in ppt_template
    assert "__OPEN_ALM_WORKER_PATENT_QUEUE_NAMES__" in patent_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=default" in default_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=realtime" in realtime_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=long" in long_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ai_graph" in ai_graph_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ppt" in ppt_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=patent" in patent_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=beat" in beat_template
    assert "TimeoutStopSec=3900" in default_template
    assert "TimeoutStopSec=3900" in realtime_template
    assert "TimeoutStopSec=3900" in long_template
    assert "TimeoutStopSec=3900" in ppt_template
    assert "TimeoutStopSec=3900" in patent_template
    assert "--hostname=open-alm-prod-worker-patent@" in patent_template
    assert "--concurrency __OPEN_ALM_WORKER_PATENT_CONCURRENCY__" in patent_template
    assert (
        "ExecStartPre=__OPEN_ALM_ROOT__/apps/worker/.venv/bin/python -m open_alm_worker.ppt_browser_smoke"
        in ppt_template
    )
    assert "KillMode=mixed" in default_template
    assert "KillMode=mixed" in realtime_template
    assert "KillMode=mixed" in long_template
    assert "KillMode=mixed" in ai_graph_template
    assert "KillMode=mixed" in ppt_template
    assert "KillMode=mixed" in patent_template
    assert "celery_worker_queue_argument" in prod_systemd_script
    assert "open-alm-prod-worker-realtime.service" in prod_systemd_script
    assert "open-alm-prod-worker-long.service" in prod_systemd_script
    assert "open-alm-prod-worker-ai-graph.service" in prod_systemd_script
    assert "open-alm-prod-worker-ppt.service" in prod_systemd_script
    assert "open-alm-prod-worker-patent.service" in prod_systemd_script

    dev_default_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-dev-worker.service.template"
    ).read_text()
    dev_realtime_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-dev-worker-realtime.service.template"
    ).read_text()
    dev_ppt_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-dev-worker-ppt.service.template"
    ).read_text()
    dev_patent_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-dev-worker-patent.service.template"
    ).read_text()
    dev_ai_graph_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-dev-worker-ai-graph.service.template"
    ).read_text()
    dev_beat_template = (
        WORKSPACE_ROOT / "ops/systemd/user/open-alm-dev-worker-beat.service.template"
    ).read_text()
    assert "__OPEN_ALM_WORKER_DEFAULT_QUEUE_NAMES__" in dev_default_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=default" in dev_default_template
    assert "__OPEN_ALM_WORKER_REALTIME_QUEUE_NAMES__" in dev_realtime_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=realtime" in dev_realtime_template
    assert "__OPEN_ALM_WORKER_PPT_QUEUE_NAMES__" in dev_ppt_template
    assert "__OPEN_ALM_WORKER_PATENT_QUEUE_NAMES__" in dev_patent_template
    assert "__OPEN_ALM_WORKER_AI_GRAPH_QUEUE_NAMES__" in dev_ai_graph_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ai_graph" in dev_ai_graph_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ppt" in dev_ppt_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=patent" in dev_patent_template
    assert "--hostname=open-alm-dev-worker-ppt@" in dev_ppt_template
    assert "--hostname=open-alm-dev-worker-patent@" in dev_patent_template
    assert "--concurrency __OPEN_ALM_WORKER_PATENT_CONCURRENCY__" in dev_patent_template
    assert "python -m open_alm_worker.ppt_browser_smoke" in dev_ppt_template
    assert "KillMode=mixed" in dev_ppt_template
    assert "KillMode=mixed" in dev_patent_template
    assert "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=beat" in dev_beat_template
    assert "celerybeat-schedule.db" in dev_beat_template
    dev_systemd_script = (WORKSPACE_ROOT / "scripts/dev-systemd.sh").read_text()
    assert "open-alm-dev-worker.service" in dev_systemd_script
    assert "open-alm-dev-worker-realtime.service" in dev_systemd_script
    assert "open-alm-dev-worker-ai-graph.service" in dev_systemd_script
    assert "open-alm-dev-worker-ppt.service" in dev_systemd_script
    assert "open-alm-dev-worker-patent.service" in dev_systemd_script
    assert "open-alm-dev-worker-beat.service" in dev_systemd_script
    assert "__OPEN_ALM_WORKER_DEFAULT_QUEUE_NAMES__" in dev_systemd_script
    assert "__OPEN_ALM_WORKER_REALTIME_QUEUE_NAMES__" in dev_systemd_script
    assert "__OPEN_ALM_WORKER_AI_GRAPH_QUEUE_NAMES__" in dev_systemd_script
    assert "__OPEN_ALM_WORKER_PPT_QUEUE_NAMES__" in dev_systemd_script
    assert "__OPEN_ALM_WORKER_PATENT_QUEUE_NAMES__" in dev_systemd_script


def test_server_managed_patent_queue_rejects_general_or_unmanaged_workers() -> None:
    managed_dev_root = Path("/projects/open-alm/dev")

    with pytest.raises(RuntimeError, match="dedicated patent worker"):
        assert_worker_queue_access(
            queue_group="long",
            requested_queues=PATENT_PRIOR_ART_QUEUE,
            env_profile="dev",
            root=managed_dev_root,
        )
    with pytest.raises(RuntimeError, match="managed dev/prod server checkout"):
        assert_worker_queue_access(
            queue_group="patent",
            requested_queues=PATENT_PRIOR_ART_QUEUE,
            env_profile="local",
            root=WORKSPACE_ROOT,
        )

    assert_worker_queue_access(
        queue_group="patent",
        requested_queues=PATENT_PRIOR_ART_QUEUE,
        env_profile="dev",
        root=managed_dev_root,
    )
    assert_worker_queue_access(
        queue_group="long",
        requested_queues=celery_worker_queue_argument("long"),
        env_profile="local",
        root=WORKSPACE_ROOT,
    )


def test_celery_routes_rag_tasks_to_dedicated_queues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))

    celery_module = _reload_worker_module("open_alm_worker.celery_app")
    routes = celery_module.celery_app.conf.task_routes

    assert routes == celery_task_routes()
    assert routes["rag.sync_resource"]["queue"] == "rag_sync_realtime"
    assert routes["rag.sync_backfill_resource"]["queue"] == "rag_sync_backfill"
    assert routes["rag.recompute_visibility"]["queue"] == "rag_visibility_recompute"
    assert routes["rag.republish_pending_jobs"]["queue"] == "celery"
    assert routes["search.republish_pending_index_jobs"]["queue"] == "celery"
    assert routes["documents.sync"]["queue"] == DEFAULT_QUEUE
    assert routes["ocr.normalize"]["queue"] == DEFAULT_QUEUE
    assert routes["drafts.export"]["queue"] == DEFAULT_QUEUE
    assert routes["media.cleanup_orphans"]["queue"] == DEFAULT_QUEUE
    assert routes["meeting.cleanup_stale_staging"]["queue"] == DEFAULT_QUEUE
    assert routes["legacy_issues.excel_export.generate"]["queue"] == (
        LEGACY_ISSUE_EXCEL_EXPORT_QUEUE
    )
    assert routes["legacy_issues.excel_export.republish"]["queue"] == DEFAULT_QUEUE
    assert routes["legacy_issues.excel_export.cleanup"]["queue"] == DEFAULT_QUEUE
    assert (
        routes["legacy_issue_attachment.cleanup_vehicle_module_checklist_objects"]["queue"]
        == DEFAULT_QUEUE
    )
    assert (
        routes["legacy_issue_attachment.reconcile_vehicle_module_checklist_orphans"]["queue"]
        == DEFAULT_QUEUE
    )
    assert routes["mail.sync_job"]["queue"] == "mail_sync"
    assert routes["mail.sync_account"]["queue"] == "mail_sync"
    assert routes["mail.dispatch_due_sync_jobs"]["queue"] == "celery"
    assert routes[ERP_HR_SNAPSHOT_TASK_NAME]["queue"] == ERP_HR_SNAPSHOT_QUEUE
    assert routes[HR_MASTER_TASK_NAME]["queue"] == HR_MASTER_QUEUE
    beat = celery_module.celery_app.conf.beat_schedule
    for entry in beat.values():
        task_name = entry["task"]
        assert entry["options"]["queue"] == routes[task_name]["queue"]
    assert beat["republish-pending-rag-jobs"]["task"] == "rag.republish_pending_jobs"
    patent_recovery_available = (
        importlib.util.find_spec("open_alm_worker.tasks.apps.patent_prior_art.task") is not None
    )
    assert ("recover-patent-prior-art-jobs" in beat) is patent_recovery_available
    if patent_recovery_available:
        assert beat["recover-patent-prior-art-jobs"]["task"] == (PATENT_PRIOR_ART_RECOVER_TASK_NAME)
        assert (
            beat["recover-patent-prior-art-jobs"]["options"]["queue"]
            == PATENT_PRIOR_ART_QUEUE
        )
    assert beat["republish-pending-legacy-issue-excel-exports"]["task"] == (
        "legacy_issues.excel_export.republish"
    )
    assert beat["cleanup-expired-legacy-issue-excel-exports"]["task"] == (
        "legacy_issues.excel_export.cleanup"
    )
    cleanup_beat = beat["cleanup-legacy-issue-vehicle-module-checklist-attachment-objects"]
    assert (
        cleanup_beat["task"] == "legacy_issue_attachment.cleanup_vehicle_module_checklist_objects"
    )
    assert cleanup_beat["schedule"] == 300.0
    reconcile_beat = beat["reconcile-legacy-issue-vehicle-module-checklist-attachment-orphans"]
    assert (
        reconcile_beat["task"]
        == "legacy_issue_attachment.reconcile_vehicle_module_checklist_orphans"
    )
    assert reconcile_beat["schedule"] == 3600.0
    assert (
        beat["republish-pending-search-index-jobs"]["task"] == "search.republish_pending_index_jobs"
    )
    assert beat["collect-news-every-two-hours"]["task"] == "news.collect_all"
    assert beat["collect-news-every-two-hours"]["schedule"]._orig_hour == "*/2"
    assert beat["collect-industry-report-daily"]["task"] == "industry_report.collect_all"
    assert beat["collect-industry-report-daily"]["schedule"]._orig_hour == 7
    assert beat["collect-industry-report-daily"]["schedule"]._orig_minute == 0
    erp_hr_beat = beat["capture-erp-hr-snapshot-daily"]
    assert erp_hr_beat["task"] == ERP_HR_SNAPSHOT_TASK_NAME
    assert erp_hr_beat["schedule"]._orig_hour == 3
    assert erp_hr_beat["schedule"]._orig_minute == 20
    master_beat = beat["build-integrated-hr-master-daily"]
    assert master_beat["task"] == HR_MASTER_TASK_NAME
    assert master_beat["schedule"]._orig_hour == 3
    assert master_beat["schedule"]._orig_minute == 30


def test_rag_republisher_publishes_due_pending_jobs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                RagSyncJob(
                    id="sync-realtime-due",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-realtime",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.REALTIME.value,
                    status=RagJobStatus.PENDING.value,
                    attempts=0,
                ),
                RagSyncJob(
                    id="sync-backfill-future",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-backfill",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.BACKFILL.value,
                    status=RagJobStatus.PENDING.value,
                    attempts=0,
                    next_retry_at=now + timedelta(minutes=5),
                ),
                RagSyncJob(
                    id="sync-realtime-stale-processing",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-stale-processing",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.REALTIME.value,
                    status=RagJobStatus.PROCESSING.value,
                    attempts=1,
                    updated_at=now - timedelta(hours=1),
                ),
                RagSyncJob(
                    id="sync-realtime-fresh-processing",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-fresh-processing",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.REALTIME.value,
                    status=RagJobStatus.PROCESSING.value,
                    attempts=1,
                    updated_at=now,
                ),
                RagVisibilityRecomputeJob(
                    id="visibility-due",
                    workspace_id="ws-1",
                    scope_type="workspace_membership",
                    scope_id="binding-1",
                    status=RagJobStatus.PENDING.value,
                    attempts=0,
                ),
                RagVisibilityRecomputeJob(
                    id="visibility-stale-processing",
                    workspace_id="ws-1",
                    scope_type="workspace_membership",
                    scope_id="binding-stale",
                    status=RagJobStatus.PROCESSING.value,
                    attempts=1,
                    updated_at=now - timedelta(hours=1),
                ),
                RagVisibilityRecomputeJob(
                    id="visibility-fresh-processing",
                    workspace_id="ws-1",
                    scope_type="workspace_membership",
                    scope_id="binding-fresh",
                    status=RagJobStatus.PROCESSING.value,
                    attempts=1,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

    published: list[tuple[str, list[str], str]] = []

    class _FakeSignature:
        def __init__(self, task_name: str, args: list[str]) -> None:
            self.task_name = task_name
            self.args = args

        def apply_async(self, *, queue: str, retry: bool) -> None:
            assert retry is False
            published.append((self.task_name, self.args, queue))

    class _FakeCeleryApp:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            assert immutable is True
            return _FakeSignature(task_name, args)

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(tasks_module, "celery_app", _FakeCeleryApp())

    assert tasks_module.republish_pending_rag_jobs.run(limit=10) == 4
    assert published == [
        (
            "rag.sync_resource",
            ["sync-realtime-stale-processing"],
            "rag_sync_realtime",
        ),
        ("rag.sync_resource", ["sync-realtime-due"], "rag_sync_realtime"),
        (
            "rag.recompute_visibility",
            ["visibility-stale-processing"],
            "rag_visibility_recompute",
        ),
        (
            "rag.recompute_visibility",
            ["visibility-due"],
            "rag_visibility_recompute",
        ),
    ]


def test_sync_resource_worker_span_inherits_outbox_trace_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    bootstrap_telemetry(service_name="open-alm-worker-test")
    exporter = InMemorySpanExporter()
    provider = get_tracer_provider()
    assert provider is not None
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with start_as_current_span(
        tracer_name="tests.worker",
        span_name="tests.rag_parent",
    ) as parent_span:
        parent_span_id = parent_span.get_span_context().span_id
        with Session(engine) as session:
            with session.begin():
                session.add(
                    Workspace(
                        id="ws-1",
                        key="ws-1",
                        name="Workspace 1",
                        description="",
                        active=True,
                    )
                )
                job = enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-1",
                )
                job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "disabled"
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert "tests.rag_parent" in spans
    assert "rag.sync_resource" in spans
    child_span = spans["rag.sync_resource"]
    assert child_span.parent is not None
    assert child_span.parent.span_id == parent_span_id
    assert child_span.context.trace_id == spans["tests.rag_parent"].context.trace_id

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1


def test_platform_disabled_qna_rag_job_stays_pending_before_provider_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            PlatformAppVisibility.__table__,
            RagSyncJob.__table__,
        ],
    )
    with Session(engine) as session:
        session.add_all(
            [
                PlatformAppVisibility(
                    id="qna-platform-visibility",
                    app_id="qa-assistant",
                    visible=False,
                ),
                RagSyncJob(
                    id="qna-platform-disabled-job",
                    scope_kind="company",
                    workspace_id=None,
                    resource_type=QNA_DOCUMENT_RESOURCE_TYPE,
                    resource_id="qna-1",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.REALTIME.value,
                    status=RagJobStatus.PENDING.value,
                    attempts=0,
                ),
            ]
        )
        session.commit()

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    original_process_sync_job = tasks_module._process_sync_job

    def fail_provider_io(*_args, **_kwargs):
        raise AssertionError("disabled Q&A RAG job must not reach provider I/O")

    monkeypatch.setattr(tasks_module, "_process_sync_job", fail_provider_io)

    assert tasks_module.sync_resource.run("qna-platform-disabled-job") == "platform-disabled"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, "qna-platform-disabled-job")
        assert stored is not None
        assert stored.status == RagJobStatus.PENDING.value
        assert stored.attempts == 0

    monkeypatch.setattr(tasks_module, "_process_sync_job", original_process_sync_job)
    visibility_checks = iter((True, False))
    monkeypatch.setattr(
        tasks_module,
        "is_platform_app_enabled",
        lambda session, app_id: next(visibility_checks),
    )

    assert tasks_module.sync_resource.run("qna-platform-disabled-job") == "platform-disabled"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, "qna-platform-disabled-job")
        assert stored is not None
        assert stored.status == RagJobStatus.PENDING.value
        assert stored.attempts == 0
        assert stored.last_error == "platform_app_disabled:qa-assistant"


def test_sync_resource_worker_marks_legacy_unsupported_resource_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = RagSyncJob(
                id="sync-unsupported-resource",
                workspace_id="ws-1",
                resource_type="missing_resource",
                resource_id="resource-1",
                operation=RagSyncOperation.UPSERT.value,
                lane=RagSyncLane.REALTIME.value,
                status=RagJobStatus.PENDING.value,
                attempts=0,
            )
            session.add(job)
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.sync_resource.run(job_id) == "unsupported_resource_type"

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.attempts == 1
        assert stored.last_error == "unsupported resource_type: missing_resource"


def test_recompute_visibility_worker_marks_terminal_statuses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            disabled_job = RagVisibilityRecomputeJob(
                id="visibility-disabled-unsupported-scope",
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-1",
                status=RagJobStatus.PENDING.value,
                attempts=0,
            )
            session.add(disabled_job)
            disabled_job_id = disabled_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(disabled_job_id) == "disabled"

    with Session(engine) as session:
        stored = session.get(RagVisibilityRecomputeJob, disabled_job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.last_error is None

    with Session(engine) as session:
        with session.begin():
            enabled_job = RagVisibilityRecomputeJob(
                id="visibility-enabled-unsupported-scope",
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-2",
                status=RagJobStatus.PENDING.value,
                attempts=0,
            )
            session.add(enabled_job)
            enabled_job_id = enabled_job.id

    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(enabled_job_id) == "unsupported_scope_type"

    with Session(engine) as session:
        stored = session.get(RagVisibilityRecomputeJob, enabled_job_id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.attempts == 1
        assert stored.last_error == "unsupported scope_type: workspace_membership"


def test_sync_resource_worker_ignores_already_closed_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocTarget.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-doc-owner@open-alm.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.sync_resource.run(job_id) == "succeeded"
    assert tasks_module.sync_resource.run(job_id) == "ignored"

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_loads_projection_through_registered_resource_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    calls: list[tuple[str, str]] = []
    reset_rag_source_adapters()
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                load_projection=lambda db, resource_id, rag_service: calls.append(
                    (resource_id, str(rag_service))
                )
                or None,
            )
        )

        projection = tasks_module._load_projection_for_job(
            object(),
            SimpleNamespace(resource_type="plugin_resource", resource_id="external:record:1"),
            rag_service="rag-service",
        )

        assert projection is None
        assert calls == [("external:record:1", "rag-service")]
    finally:
        reset_rag_source_adapters()


def test_rag_worker_routes_files_only_to_the_active_partitioned_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    settings = SimpleNamespace(files_retrieval_enabled=True)
    pair = SimpleNamespace(qdrant_physical_name="files-v1-release")
    expected_providers = object()
    expected_service = object()
    calls: list[tuple[object, object]] = []
    monkeypatch.setattr(tasks_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks_module, "provider_bundle", lambda: expected_providers)
    monkeypatch.setattr(
        tasks_module,
        "resolve_active_partitioned_generation_pair",
        lambda db, *, settings: calls.append((db, settings)) or pair,
    )
    monkeypatch.setattr(
        tasks_module,
        "build_partitioned_rag_projection_service",
        lambda resolved_settings, *, collection, providers: (
            expected_service
            if (
                resolved_settings is settings
                and collection == pair.qdrant_physical_name
                and providers is expected_providers
            )
            else None
        ),
    )
    monkeypatch.setattr(
        tasks_module,
        "_rag_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("Files must not use the legacy vector collection")
        ),
    )
    db = object()

    runtime = tasks_module._rag_runtime_for_job(
        db,
        SimpleNamespace(
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            retrieval_partition_id="partition-1",
            projection_event_sequence=1,
            projection_version=1,
            desired_state="active",
        ),
    )

    assert runtime.service is expected_service
    assert runtime.collection == pair.qdrant_physical_name
    assert calls == [(db, settings)]


def test_rag_worker_keeps_non_file_jobs_on_the_legacy_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    expected_service = object()
    monkeypatch.setattr(tasks_module, "_rag_service", lambda: expected_service)
    monkeypatch.setattr(tasks_module, "collection_name", lambda: "legacy-collection")
    monkeypatch.setattr(
        tasks_module,
        "resolve_active_partitioned_generation_pair",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy sources must not resolve the Files generation")
        ),
    )

    runtime = tasks_module._rag_runtime_for_job(
        object(),
        SimpleNamespace(resource_type=NATIVE_DOC_RESOURCE_TYPE),
    )

    assert runtime.service is expected_service
    assert runtime.collection == "legacy-collection"


def test_rag_worker_fails_closed_when_files_operator_gate_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "get_settings",
        lambda: SimpleNamespace(files_retrieval_enabled=False),
    )

    with pytest.raises(
        tasks_module.PartitionedRetrievalRuntimeUnavailable,
        match="operator_gate_disabled",
    ):
        tasks_module._rag_runtime_for_job(
            object(),
            SimpleNamespace(resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE),
        )


def test_rag_worker_pauses_files_job_without_consuming_retry_budget_when_gate_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RetrievalPartition.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            RagSyncJob.__table__,
        ],
    )
    with Session(engine) as session:
        session.add_all(
            [
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                ),
                RetrievalPartition(
                    id="d2a7f7b8-450a-48ae-863f-8b81ff2c0eb7",
                    source_namespace="files",
                    managed_workspace_id="ws-1",
                    candidate_scope_kind="workspace",
                    candidate_workspace_id="ws-1",
                    is_default_ingest=False,
                ),
            ]
        )
        session.flush()
        event = record_projection_event(
            session,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-paused",
            retrieval_partition_id="d2a7f7b8-450a-48ae-863f-8b81ff2c0eb7",
            change_kind="content",
            desired_state="active",
            diagnostic_workspace_id="ws-1",
        )
        session.add(
            RagSyncJob(
                id="rag-files-gate-paused",
                scope_kind="workspace",
                workspace_id="ws-1",
                lane="realtime",
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                operation="upsert",
                retrieval_partition_id=event.retrieval_partition_id,
                projection_event_sequence=event.event_sequence,
                projection_version=event.projection_version,
                desired_state=event.desired_state,
                trace_context={},
                status="pending",
                attempts=3,
            )
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_FILES_RETRIEVAL_ENABLED", "0")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("operator pause must not schedule a Celery retry"),
    )

    result = tasks_module.sync_resource.run("rag-files-gate-paused")

    assert result == "operator_gate_paused"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, "rag-files-gate-paused")
        assert stored is not None
        assert stored.status == "pending"
        assert stored.attempts == 3
        assert stored.next_retry_at is not None
        assert stored.last_error == "operator_gate_disabled"


def test_rag_worker_rejects_unfenced_file_job_before_backend_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "get_settings",
        lambda: SimpleNamespace(files_retrieval_enabled=True),
    )
    monkeypatch.setattr(
        tasks_module,
        "resolve_active_partitioned_generation_pair",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unfenced Files jobs must be rejected before backend resolution")
        ),
    )

    with pytest.raises(
        tasks_module.PartitionedRetrievalRuntimeUnavailable,
        match="unfenced_file_job",
    ):
        tasks_module._rag_runtime_for_job(
            object(),
            SimpleNamespace(
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                retrieval_partition_id=None,
                projection_event_sequence=None,
                projection_version=None,
                desired_state=None,
            ),
        )


def test_sync_resource_worker_rejects_mismatched_projection_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")

    class _FakeRagService:
        def sync_projection(self, projection, *, collection):
            del projection, collection
            raise AssertionError("sync should not run")

        def delete_projection(self, **kwargs):
            del kwargs
            raise AssertionError("delete should not run")

    reset_rag_source_adapters()
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                load_projection=lambda db, resource_id, rag_service: RagProjection(
                    workspace_id="ws-other",
                    resource_type="plugin_resource",
                    resource_id=resource_id,
                    source_kind="plugin",
                    title="Wrong workspace",
                ),
            )
        )
        monkeypatch.setattr(tasks_module, "_rag_service", lambda: _FakeRagService())
        monkeypatch.setattr(tasks_module, "collection_name", lambda: "test")
        job = SimpleNamespace(
            id="job-identity-mismatch",
            scope_kind="workspace",
            workspace_id="ws-1",
            resource_type="plugin_resource",
            resource_id="external:record:1",
            operation=RagSyncOperation.UPSERT.value,
        )

        with pytest.raises(tasks_module.RagProjectionIdentityError):
            tasks_module._process_sync_job(object(), job)
        assert tasks_module._is_non_retryable_rag_error(
            tasks_module.RagProjectionIdentityError("bad identity")
        )
    finally:
        reset_rag_source_adapters()


def test_sync_resource_worker_enriches_versioned_projection_with_job_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    partition_id = "11111111-1111-1111-1111-111111111111"
    source_projection = RagProjection(
        workspace_id="ws-1",
        resource_type="plugin_resource",
        resource_id="resource-1",
        source_kind="plugin",
        title="Versioned projection",
    )
    captured: list[RagProjection] = []

    class _FakeRagService:
        def sync_projection(self, projection, *, collection):
            assert collection == "test"
            captured.append(projection)
            return SimpleNamespace(chunk_count=1)

    reset_rag_source_adapters()
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                load_projection=lambda db, resource_id, rag_service: source_projection,
            )
        )
        monkeypatch.setattr(tasks_module, "_rag_service", lambda: _FakeRagService())
        monkeypatch.setattr(tasks_module, "collection_name", lambda: "test")
        monkeypatch.setattr(
            tasks_module,
            "_lock_projection_head_for_vector_mutation",
            lambda session, job: None,
        )
        job = SimpleNamespace(
            id="job-versioned-projection",
            scope_kind="workspace",
            workspace_id="ws-1",
            resource_type="plugin_resource",
            resource_id="resource-1",
            operation=RagSyncOperation.UPSERT.value,
            retrieval_partition_id=partition_id,
            projection_version=7,
        )

        assert tasks_module._process_sync_job(object(), job) == "succeeded"
        assert captured[0].retrieval_partition_id == partition_id
        assert captured[0].projection_version == 7
        assert source_projection.retrieval_partition_id is None
        assert source_projection.projection_version is None
    finally:
        reset_rag_source_adapters()


def test_sync_resource_commits_prepared_projection_before_vector_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    calls: list[str] = []
    projection = RagProjection(
        workspace_id="ws-1",
        resource_type="plugin_resource",
        resource_id="resource-1",
        source_kind="plugin",
        title="Prepared projection",
    )

    class _Session:
        def commit(self) -> None:
            calls.append("commit")

    class _FakeRagService:
        def sync_projection(self, candidate, *, collection):
            assert candidate is projection
            assert collection == "test"
            calls.append("vector")
            return SimpleNamespace(chunk_count=1)

    reset_rag_source_adapters()
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                load_projection=lambda db, resource_id, rag_service: projection,
                on_projection_prepared=lambda db, resource_id: calls.append("prepared"),
                on_projection_synced=lambda db, resource_id, chunk_count: calls.append("synced"),
            )
        )
        monkeypatch.setattr(tasks_module, "_rag_service", lambda: _FakeRagService())
        monkeypatch.setattr(tasks_module, "collection_name", lambda: "test")
        job = SimpleNamespace(
            id="job-prepared",
            scope_kind="workspace",
            workspace_id="ws-1",
            resource_type="plugin_resource",
            resource_id="resource-1",
            operation=RagSyncOperation.UPSERT.value,
        )

        assert tasks_module._process_sync_job(_Session(), job) == "succeeded"
        assert calls == ["prepared", "commit", "vector", "synced"]
    finally:
        reset_rag_source_adapters()


def test_sync_resource_stops_before_embedding_when_prepared_event_advances_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    calls: list[str] = []
    partition_id = "7eb7f076-a8a8-40f1-8153-4f692124bc4e"
    projection = RagProjection(
        workspace_id="ws-1",
        resource_type="plugin_resource",
        resource_id="resource-1",
        source_kind="plugin",
        title="Prepared projection",
    )
    projection_event = ProjectionEventRef(
        event_sequence=1,
        resource_type="plugin_resource",
        resource_id="resource-1",
        projection_version=1,
        retrieval_partition_id=partition_id,
        change_kind="content",
        desired_state="active",
        content_checksum=None,
        visibility_checksum=None,
        diagnostic_workspace_id="ws-1",
    )

    class _Session:
        def commit(self) -> None:
            calls.append("commit")

    class _FakeRagService:
        def sync_projection(self, candidate, *, collection):
            del candidate, collection
            raise AssertionError("superseded projection must not be embedded or written")

    reset_rag_source_adapters()
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                load_projection=lambda db, resource_id, rag_service: projection,
                on_projection_prepared_event=lambda db, resource_id, event: calls.append(
                    "prepared"
                ),
            )
        )
        monkeypatch.setattr(tasks_module, "_rag_service", lambda: _FakeRagService())
        monkeypatch.setattr(tasks_module, "collection_name", lambda: "test")
        monkeypatch.setattr(
            tasks_module,
            "_projection_event_ref_for_job",
            lambda session, job: projection_event,
        )
        monkeypatch.setattr(
            tasks_module,
            "_initial_projection_fence_stale_reason",
            lambda session, job: "head_mismatch:projection_version",
        )
        job = SimpleNamespace(
            id="job-prepared-superseded",
            scope_kind="workspace",
            workspace_id="ws-1",
            resource_type="plugin_resource",
            resource_id="resource-1",
            operation=RagSyncOperation.UPSERT.value,
            retrieval_partition_id=partition_id,
            projection_version=1,
        )

        with pytest.raises(tasks_module.RagProjectionSuperseded):
            tasks_module._process_sync_job(_Session(), job)
        assert calls == ["prepared", "commit"]
    finally:
        reset_rag_source_adapters()


def test_recompute_visibility_worker_queues_through_registered_scope_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    enqueued: list[dict[str, object]] = []
    reset_rag_source_adapters()
    try:
        register_rag_visibility_scope_adapter(
            RagVisibilityScopeAdapter(
                scope_type="plugin_scope",
                resource_type="plugin_resource",
                operation=RagSyncOperation.UPSERT.value,
                resource_ids=lambda db, job: ["plugin-1", "plugin-2"],
            )
        )
        monkeypatch.setattr(
            tasks_module,
            "_enqueue_resource_sync_jobs",
            lambda session, **kwargs: enqueued.append(kwargs),
        )
        session = SimpleNamespace(commit=lambda: None)
        job = SimpleNamespace(
            workspace_id="ws-1",
            scope_type="plugin_scope",
            scope_id="scope-1",
            cursor=None,
        )

        result = tasks_module._process_visibility_job(session, job)

        assert result == ("queued", None)
        assert enqueued == [
            {
                "workspace_id": "ws-1",
                "resource_type": "plugin_resource",
                "resource_ids": ["plugin-1", "plugin-2"],
                "operation": RagSyncOperation.UPSERT,
                "lane": RagSyncLane.BACKFILL,
            }
        ]
    finally:
        reset_rag_source_adapters()


def test_recompute_visibility_worker_ignores_already_closed_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = RagVisibilityRecomputeJob(
                id="visibility-closed-unsupported-scope",
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-1",
                status=RagJobStatus.PENDING.value,
                attempts=0,
            )
            session.add(job)
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(job_id) == "disabled"
    assert tasks_module.recompute_visibility.run(job_id) == "ignored"

    with Session(engine) as session:
        stored = session.get(RagVisibilityRecomputeJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1


def test_recompute_visibility_worker_queues_docs_sync_jobs_for_meeting_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            Meeting.__table__,
            MeetingDocLink.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        login_id="user-1",
                        email="worker-doc-owner@open-alm.local",
                        full_name="Worker Doc Owner",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        login_id="user-2",
                        email="worker-attendee@open-alm.local",
                        full_name="Worker Attendee",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Meeting Linked Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                Meeting(
                    id="meeting-1",
                    workspace_id="ws-1",
                    organizer_id="user-1",
                    notes_doc_id=None,
                    notes_page_id=None,
                    title="Worker Meeting",
                    agenda="",
                    start_at=datetime(2026, 4, 22, 0, 0, 0),
                    end_at=datetime(2026, 4, 22, 1, 0, 0),
                    status="scheduled",
                )
            )
            session.add(
                MeetingDocLink(
                    id="meeting-doc-1",
                    meeting_id="meeting-1",
                    doc_id="doc-1",
                    added_by_id="user-1",
                )
            )
            session.add(
                DocMeetingAccess(
                    id="grant-1",
                    doc_id="doc-1",
                    user_id="user-2",
                    access_level="read",
                    granted_by_meeting_id="meeting-1",
                    granted_by_user_id="user-1",
                    reason="meeting_attendee",
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="meeting",
                scope_id="meeting-1",
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        stored_visibility_job = session.get(RagVisibilityRecomputeJob, visibility_job_id)
        assert stored_visibility_job is not None
        assert stored_visibility_job.status == "succeeded"
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == NATIVE_DOC_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "doc-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1
        assert queued_jobs[0].lane == "backfill"


def test_recompute_visibility_worker_uses_cursor_doc_ids_when_meeting_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            Meeting.__table__,
            MeetingDocLink.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-doc-owner@open-alm.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Deleted Meeting Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="meeting",
                scope_id="meeting-deleted",
                cursor={"doc_ids": ["doc-1"]},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == NATIVE_DOC_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "doc-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1


def test_recompute_visibility_worker_queues_pms_visibility_updates_for_meeting_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Task.__table__,
            Meeting.__table__,
            MeetingTaskLink.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
            TaskUserAccess.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        login_id="user-1",
                        email="worker-owner@open-alm.local",
                        full_name="Worker Owner",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        login_id="user-2",
                        email="worker-reader@open-alm.local",
                        full_name="Worker Reader",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Team 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="LIST1",
                    name="List 1",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    created_by_id="user-1",
                )
            )
            session.add(
                Task(
                    id="issue-1",
                    list_id="list-1",
                    task_number=1,
                    title="Meeting linked issue",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            session.add(
                Task(
                    id="issue-2",
                    list_id="list-1",
                    task_number=2,
                    title="Meeting linked issue outside cursor",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            session.add(
                Meeting(
                    id="meeting-1",
                    workspace_id="ws-1",
                    organizer_id="user-1",
                    notes_doc_id=None,
                    notes_page_id=None,
                    title="Worker Meeting",
                    agenda="",
                    start_at=datetime(2026, 4, 22, 0, 0, 0),
                    end_at=datetime(2026, 4, 22, 1, 0, 0),
                    status="scheduled",
                )
            )
            session.add(
                MeetingTaskLink(
                    id="meeting-task-1",
                    meeting_id="meeting-1",
                    task_id="issue-1",
                    added_by_id="user-1",
                )
            )
            session.add(
                MeetingTaskLink(
                    id="meeting-task-2",
                    meeting_id="meeting-1",
                    task_id="issue-2",
                    added_by_id="user-1",
                )
            )
            session.add(
                TaskUserAccess(
                    id="grant-1",
                    task_id="issue-1",
                    user_id="user-2",
                    access_level="read",
                    granted_by_meeting_id="meeting-1",
                    granted_by_user_id="user-1",
                    reason="meeting_attendee",
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type=PMS_MEETING_VISIBILITY_SCOPE,
                scope_id="meeting-1",
                cursor={"task_ids": ["issue-1"], "operation": "visibility_update"},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == PMS_TASK_RESOURCE_TYPE,
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert {job.resource_id for job in queued_jobs} == {"issue-1", "issue-2"}
        assert {job.lane for job in queued_jobs} == {"backfill"}


def test_recompute_visibility_worker_uses_cursor_issue_ids_when_pms_meeting_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Task.__table__,
            Meeting.__table__,
            MeetingTaskLink.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
            TaskUserAccess.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-owner@open-alm.local",
                    full_name="Worker Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Team 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="LIST1",
                    name="List 1",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    created_by_id="user-1",
                )
            )
            session.add(
                Task(
                    id="issue-1",
                    list_id="list-1",
                    task_number=1,
                    title="Deleted meeting issue",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type=PMS_MEETING_VISIBILITY_SCOPE,
                scope_id="meeting-deleted",
                cursor={"task_ids": ["issue-1"], "operation": "visibility_update"},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == PMS_TASK_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "issue-1",
                    RagSyncJob.operation == RagSyncOperation.VISIBILITY_UPDATE.value,
                )
            )
        )
        assert len(queued_jobs) == 1


def test_recompute_visibility_worker_uses_cursor_issue_ids_for_deleted_pms_label_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Task.__table__,
            Label.__table__,
            TaskLabel.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-owner@open-alm.local",
                    full_name="Worker Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Team 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="LIST1",
                    name="List 1",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    created_by_id="user-1",
                )
            )
            session.add(
                Task(
                    id="issue-1",
                    list_id="list-1",
                    task_number=1,
                    title="Deleted label issue",
                    description="",
                    status="backlog",
                    priority="medium",
                    reporter_id="user-1",
                    assignee_id=None,
                    archived=False,
                )
            )
            visibility_job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type=PMS_LABEL_RECOMPUTE_SCOPE,
                scope_id="label-deleted",
                cursor={"task_ids": ["issue-1"], "operation": "upsert"},
            )
            visibility_job_id = visibility_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.recompute_visibility.run(visibility_job_id) == "queued"

    with Session(engine) as session:
        queued_jobs = list(
            session.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_type == PMS_TASK_RESOURCE_TYPE,
                    RagSyncJob.resource_id == "issue-1",
                    RagSyncJob.operation == RagSyncOperation.UPSERT.value,
                )
            )
        )
        assert len(queued_jobs) == 1


def test_sync_resource_worker_upserts_docs_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocTarget.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-doc-owner@open-alm.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module.provider_bundle()
    collection = tasks_module.collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="doc-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "doc-1"
    assert snapshot.resource_type == NATIVE_DOC_RESOURCE_TYPE
    assert "worker sync content" in snapshot.text_content

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_processes_files_upsert_and_delete_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-files-test")
    monkeypatch.setattr(file_search_hooks, "FILES_RETRIEVAL_ACTIVE", True)

    class StoredObject:
        def stream(self, _chunk_size: int):
            yield "히터 시스템 정상 작동 전압은 9V에서 16V입니다.".encode()

        def close(self) -> None:
            return None

        def release_conn(self) -> None:
            return None

    monkeypatch.setattr(file_storage, "open_file_object", lambda _storage_key: StoredObject())

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            RagSyncJob.__table__,
            SearchIndexJob.__table__,
        ],
    )
    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-file-owner@open-alm.local",
                    full_name="Worker File Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                FileManagerFile(
                    id="file-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    filename="heater.txt",
                    content_type="text/plain",
                    size_bytes=64,
                    storage_key="files/ws-1/file-1/heater.txt",
                    visibility="private",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id="file-1",
            )
            upsert_job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    bundle = tasks_module.provider_bundle()
    collection = tasks_module.collection_name()
    monkeypatch.setattr(
        tasks_module,
        "_rag_runtime_for_job",
        lambda session, job: tasks_module._RagProjectionRuntime(
            service=tasks_module._rag_service(),
            collection=collection,
        ),
    )
    assert tasks_module.sync_resource.run(upsert_job_id) == "succeeded"
    snapshot = bundle.vector_index.snapshot_projection(
        collection=collection,
        chunk_id="file-1:document:0",
    )
    assert snapshot is not None
    assert snapshot.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
    assert "정상 작동 전압" in snapshot.text_content

    with Session(engine) as session:
        file = session.get(FileManagerFile, "file-1")
        search_job = session.scalar(
            select(SearchIndexJob).where(SearchIndexJob.entity_id == "file-1")
        )
        assert file is not None and file.extraction_status == "ready"
        assert search_job is not None and search_job.operation == "upsert"
        with session.begin_nested():
            file.deleted_at = datetime.now(UTC).replace(tzinfo=None)
            delete_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id="file-1",
                operation=RagSyncOperation.DELETE,
            )
            delete_job_id = delete_job.id
        session.commit()

    assert tasks_module.sync_resource.run(delete_job_id) == "deleted"
    assert (
        bundle.vector_index.snapshot_projection(
            collection=collection,
            chunk_id="file-1:document:0",
        )
        is None
    )
    with Session(engine) as session:
        file = session.get(FileManagerFile, "file-1")
        search_jobs = list(
            session.scalars(select(SearchIndexJob).where(SearchIndexJob.entity_id == "file-1"))
        )
        assert file is not None and file.extraction_text is None
        # The source delete event owns the fenced keyword delete. Completing the
        # vector delete must not create an unfenced duplicate search job.
        assert len(search_jobs) == 1
        assert search_jobs[0].operation == "upsert"


def test_files_keyword_job_survives_vector_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-files-failure")
    monkeypatch.setattr(file_search_hooks, "FILES_RETRIEVAL_ACTIVE", True)

    class StoredObject:
        def stream(self, _chunk_size: int):
            yield "임베딩 장애 중에도 키워드 색인은 생성됩니다.".encode()

        def close(self) -> None:
            return None

        def release_conn(self) -> None:
            return None

    class FailingRagService:
        def sync_projection(self, projection, *, collection):
            del projection, collection
            raise RagProviderTransientError("embedding provider unavailable")

    monkeypatch.setattr(file_storage, "open_file_object", lambda _storage_key: StoredObject())
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            RagSyncJob.__table__,
            SearchIndexJob.__table__,
        ],
    )
    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-file-failure@open-alm.local",
                    full_name="Worker File Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                FileManagerFile(
                    id="file-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    filename="provider-failure.txt",
                    content_type="text/plain",
                    size_bytes=64,
                    storage_key="files/ws-1/file-1/provider-failure.txt",
                    visibility="workspace",
                )
            )

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_rag_runtime_for_job",
        lambda session, current_job: tasks_module._RagProjectionRuntime(
            service=FailingRagService(),
            collection="test",
        ),
    )
    job = SimpleNamespace(
        id="job-file-provider-failure",
        scope_kind="workspace",
        workspace_id="ws-1",
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-1",
        operation=RagSyncOperation.UPSERT.value,
    )

    with Session(engine) as session:
        with pytest.raises(RagProviderTransientError, match="provider unavailable"):
            tasks_module._process_sync_job(session, job)

    with Session(engine) as session:
        file = session.get(FileManagerFile, "file-1")
        search_job = session.scalar(
            select(SearchIndexJob).where(SearchIndexJob.entity_id == "file-1")
        )
        assert file is not None and file.extraction_status == "ready"
        assert "키워드 색인" in (file.extraction_text or "")
        assert search_job is not None and search_job.operation == "upsert"


def test_sync_resource_worker_deletes_docs_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocTarget.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-doc-owner@open-alm.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            upsert_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            upsert_job_id = upsert_job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    assert tasks_module.sync_resource.run(upsert_job_id) == "succeeded"

    with Session(engine) as session:
        with session.begin():
            delete_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
                operation=RagSyncOperation.DELETE,
            )
            delete_job_id = delete_job.id

    result = tasks_module.sync_resource.run(delete_job_id)

    assert result == "deleted"
    bundle = tasks_module.provider_bundle()
    collection = tasks_module.collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="doc-1:0")
    assert snapshot is None

    with Session(engine) as session:
        stored = session.get(RagSyncJob, delete_job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_deletes_personal_planner_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            PlannerEvent.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    login_id="user-1",
                    email="worker-planner-owner@open-alm.local",
                    full_name="Worker Planner Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                PlannerEvent(
                    id="event-1",
                    legacy_workspace_id="ws-1",
                    owner_id="user-1",
                    title="Planner Sync Event",
                    description="Discuss roadmap",
                    location="Pangyo",
                    legacy_visibility="public",
                    all_day=False,
                    start_at=datetime(2026, 5, 20, 1, 0, 0),
                    end_at=datetime(2026, 5, 20, 2, 0, 0),
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=PLANNER_EVENT_RESOURCE_TYPE,
                resource_id="event-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "deleted_missing_projection"
    bundle = tasks_module.provider_bundle()
    collection = tasks_module.collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="event-1:0")
    assert snapshot is None

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_upserts_meeting_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Meeting.__table__,
            MeetingAttendee.__table__,
            MeetingTaskLink.__table__,
            MeetingDocLink.__table__,
            MeetingRecording.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        login_id="user-1",
                        email="worker-meeting-organizer@open-alm.local",
                        full_name="Worker Meeting Organizer",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        login_id="user-2",
                        email="worker-meeting-attendee@open-alm.local",
                        full_name="Worker Meeting Attendee",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                Meeting(
                    id="meeting-1",
                    workspace_id="ws-1",
                    organizer_id="user-1",
                    title="Worker Meeting Sync",
                    agenda="Discuss launch blockers",
                    start_at=datetime(2026, 5, 20, 1, 0, 0),
                    end_at=datetime(2026, 5, 20, 2, 0, 0),
                    status="scheduled",
                )
            )
            session.add(
                MeetingAttendee(
                    id="attendee-1",
                    meeting_id="meeting-1",
                    user_id="user-2",
                    role="required",
                    response="accepted",
                )
            )
            session.add(
                MeetingRecording(
                    id="recording-1",
                    meeting_id="meeting-1",
                    storage_key="meeting/meeting-1/recording-1.webm",
                    file_size=100,
                    mime_type="audio/webm",
                    idempotency_key="meeting-rag-recording",
                    uploaded_by_id="user-1",
                    source="manual_upload",
                    transcription_status="done",
                    progress_pct=100,
                    transcript_text="Budget risk was reviewed and owners were assigned.",
                    summary_text="Owners assigned and budget risk reviewed.",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=MEETING_RESOURCE_TYPE,
                resource_id="meeting-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module.provider_bundle()
    collection = tasks_module.collection_name()
    snapshot = bundle.vector_index.snapshot_projection(
        collection=collection, chunk_id="meeting-1:0"
    )
    assert snapshot is not None
    assert snapshot.resource_id == "meeting-1"
    assert snapshot.resource_type == MEETING_RESOURCE_TYPE
    assert snapshot.source_kind == "meeting"
    assert "meeting_organizer:user-1" in snapshot.visibility_refs
    assert "meeting_attendee:user-2" in snapshot.visibility_refs
    assert "budget risk reviewed" in snapshot.text_content.lower()

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_upserts_pms_issue_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            Milestone.__table__,
            Label.__table__,
            Task.__table__,
            TaskAssignee.__table__,
            TaskFollower.__table__,
            TaskLabel.__table__,
            TaskComment.__table__,
            TaskUserAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add_all(
                [
                    User(
                        id="user-1",
                        login_id="user-1",
                        email="worker-pms-reporter@open-alm.local",
                        full_name="Worker PMS Reporter",
                        password_hash="hash",
                        status="active",
                    ),
                    User(
                        id="user-2",
                        login_id="user-2",
                        email="worker-pms-grantee@open-alm.local",
                        full_name="Worker PMS Grantee",
                        password_hash="hash",
                        status="active",
                    ),
                ]
            )
            session.add(
                Team(
                    id="team-1",
                    workspace_id="ws-1",
                    key="TEAM1",
                    name="Worker PMS Team",
                    description="",
                    active=True,
                    trashed_at=None,
                )
            )
            session.add(
                TaskList(
                    id="list-1",
                    key="PMS1",
                    name="Worker PMS List",
                    description="",
                    status="active",
                    archived=False,
                    team_id="team-1",
                    folder_id=None,
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            session.add(
                Task(
                    id="issue-1",
                    list_id="list-1",
                    task_number=1,
                    title="Worker PMS Issue",
                    description="Issue projection body",
                    description_blocks=[{"type": "paragraph", "text": "Issue projection blocks"}],
                    status="backlog",
                    priority="high",
                    assignee_id=None,
                    reporter_id="user-1",
                    parent_id=None,
                    milestone_id=None,
                    start_date=None,
                    due_date=None,
                    board_position=1,
                    recurrence_rule=None,
                    archived=False,
                )
            )
            session.add(
                TaskComment(
                    id="comment-1",
                    task_id="issue-1",
                    author_id="user-1",
                    body="Need a follow-up",
                    body_blocks=None,
                )
            )
            session.add(
                TaskUserAccess(
                    id="grant-1",
                    task_id="issue-1",
                    user_id="user-2",
                    access_level="read",
                    granted_by_meeting_id="meeting-1",
                    granted_by_user_id="user-1",
                    reason="meeting_attendee",
                    expires_at=None,
                    revoked_at=None,
                    revoked_by_user_id=None,
                    revoke_reason=None,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=PMS_TASK_RESOURCE_TYPE,
                resource_id="issue-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module.provider_bundle()
    collection = tasks_module.collection_name()
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="issue-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "issue-1"
    assert snapshot.resource_type == PMS_TASK_RESOURCE_TYPE
    assert snapshot.source_kind == "pms_task"
    assert snapshot.metadata["team_id"] == "team-1"
    assert "task_grant:user-2" in snapshot.visibility_refs
    assert "Need a follow-up" in snapshot.text_content

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_provider_bundle_uses_qdrant_vector_index_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_VECTOR_INDEX_PROVIDER", "qdrant")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_URL", "http://qdrant.test:6333")
    monkeypatch.setenv("OPEN_ALM_RAG_QDRANT_API_KEY", "secret")

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    tasks_module.provider_bundle.cache_clear()
    provider_factory = importlib.import_module("open_alm_api.domains.rag.provider_factory")

    created: dict[str, str | None] = {}

    class StubQdrantVectorIndexClient:
        def __init__(self, *, url: str | None = None, api_key: str | None = None) -> None:
            created["url"] = url
            created["api_key"] = api_key

    monkeypatch.setattr(
        provider_factory,
        "QdrantVectorIndexClient",
        StubQdrantVectorIndexClient,
    )

    bundle = tasks_module.provider_bundle()

    assert isinstance(bundle.vector_index, StubQdrantVectorIndexClient)
    assert created == {
        "url": "http://qdrant.test:6333",
        "api_key": "secret",
    }


def test_collection_name_matches_model_scoped_runtime_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_EMBEDDING_PROVIDER", "local_sentence_transformers")
    monkeypatch.setenv(
        "OPEN_ALM_RAG_EMBEDDING_MODEL",
        "dragonkue/snowflake-arctic-embed-l-v2.0-ko",
    )

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")

    collection = tasks_module.collection_name()

    assert collection == "open-alm-dev-rag-dragonkue-snowflake-arctic-embed-l-v2-0-ko"


def test_sync_resource_worker_schedules_retry_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RetryScheduled(Exception):
        pass

    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-retry",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    retry_calls: list[int] = []

    def fake_retry(*, exc, countdown, **_kwargs):
        assert isinstance(exc, RuntimeError)
        retry_calls.append(countdown)
        raise RetryScheduled()

    monkeypatch.setattr(tasks_module.sync_resource, "retry", fake_retry)

    with pytest.raises(RetryScheduled):
        tasks_module.sync_resource.run(job_id)

    assert retry_calls == [7]
    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "pending"
        assert stored.attempts == 1
        assert stored.next_retry_at is not None
        assert stored.last_error == "boom"


def test_sync_resource_worker_merges_retry_when_duplicate_pending_job_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    class _FakeSignature:
        def apply_async(self, *, queue: str, retry: bool) -> None:
            del queue, retry

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            del task_name, args, immutable
            return _FakeSignature()

    monkeypatch.setattr(
        "open_alm_api.domains.rag.outbox.get_celery_client",
        lambda: _FakeCeleryClient(),
    )

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            original_job_id = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-retry-merge",
            ).id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    merged_pending_id: str | None = None

    def _inject_duplicate_pending(_session, job):
        nonlocal merged_pending_id
        with Session(engine) as competing_session:
            with competing_session.begin():
                merged_pending_id = enqueue_rag_sync_job(
                    competing_session,
                    workspace_id=job.workspace_id,
                    resource_type=job.resource_type,
                    resource_id=job.resource_id,
                    operation=RagSyncOperation(job.operation),
                    lane=RagSyncLane(job.lane),
                    content_checksum=job.content_checksum,
                    visibility_checksum=job.visibility_checksum,
                    trace_context=job.trace_context,
                ).id
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks_module, "_process_sync_job", _inject_duplicate_pending)
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("merged retry must not schedule a Celery retry"),
    )

    result = tasks_module.sync_resource.run(original_job_id)

    assert result == "retry_merged"
    assert merged_pending_id is not None
    with Session(engine) as session:
        original = session.get(RagSyncJob, original_job_id)
        merged = session.get(RagSyncJob, merged_pending_id)
        assert original is not None
        assert merged is not None
        assert original.status == "cancelled"
        assert original.next_retry_at is None
        assert original.last_error == f"merged_retry_into:{merged_pending_id}: boom"
        assert merged.status == "pending"


def test_recompute_visibility_worker_merges_retry_when_duplicate_pending_job_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            original_job = RagVisibilityRecomputeJob(
                id="visibility-retry-original",
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-1",
                cursor={"doc_ids": ["doc-original"]},
                status=RagJobStatus.PENDING.value,
                attempts=0,
            )
            session.add(original_job)

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    merged_pending_id = "visibility-retry-merged"

    def _inject_duplicate_pending(_session, job):
        with Session(engine) as competing_session:
            with competing_session.begin():
                competing_session.add(
                    RagVisibilityRecomputeJob(
                        id=merged_pending_id,
                        workspace_id=job.workspace_id,
                        scope_type=job.scope_type,
                        scope_id=job.scope_id,
                        cursor={"doc_ids": ["doc-pending"]},
                        status=RagJobStatus.PENDING.value,
                        attempts=0,
                    )
                )
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks_module, "_process_visibility_job", _inject_duplicate_pending)
    monkeypatch.setattr(
        tasks_module.recompute_visibility,
        "retry",
        lambda **_kwargs: pytest.fail("merged retry must not schedule a Celery retry"),
    )

    result = tasks_module.recompute_visibility.run("visibility-retry-original")

    assert result == "retry_merged"
    with Session(engine) as session:
        original = session.get(RagVisibilityRecomputeJob, "visibility-retry-original")
        merged = session.get(RagVisibilityRecomputeJob, merged_pending_id)
        assert original is not None
        assert merged is not None
        assert original.status == "cancelled"
        assert original.next_retry_at is None
        assert original.last_error == f"merged_retry_into:{merged_pending_id}: boom"
        assert merged.status == "pending"
        assert merged.cursor == {"doc_ids": ["doc-original", "doc-pending"]}


def test_sync_resource_worker_cancels_superseded_processing_job_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                RagSyncJob(
                    id="rag-stale-processing",
                    workspace_id="ws-1",
                    lane=RagSyncLane.REALTIME.value,
                    resource_type="doc",
                    resource_id="doc-superseded",
                    operation=RagSyncOperation.UPSERT.value,
                    trace_context={},
                    status=RagJobStatus.PROCESSING.value,
                    attempts=1,
                    created_at=now - timedelta(hours=2),
                    updated_at=now - timedelta(hours=2),
                ),
                RagSyncJob(
                    id="rag-newer-pending",
                    workspace_id="ws-1",
                    lane=RagSyncLane.REALTIME.value,
                    resource_type="doc",
                    resource_id="doc-superseded",
                    operation=RagSyncOperation.DELETE.value,
                    trace_context={},
                    status=RagJobStatus.PENDING.value,
                    attempts=0,
                    created_at=now - timedelta(minutes=1),
                    updated_at=now - timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: pytest.fail("superseded RAG job must not mutate the vector index"),
    )

    result = tasks_module.sync_resource.run("rag-stale-processing")

    assert result == "superseded"
    with Session(engine) as session:
        stale = session.get(RagSyncJob, "rag-stale-processing")
        pending = session.get(RagSyncJob, "rag-newer-pending")
        assert stale is not None
        assert pending is not None
        assert stale.status == RagJobStatus.CANCELLED.value
        assert stale.last_error == "superseded_by:rag-newer-pending:before_mutation"
        assert pending.status == RagJobStatus.PENDING.value


def test_sync_resource_worker_rejects_stale_projection_head_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RetrievalPartition.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            RagSyncJob.__table__,
        ],
    )
    partition_id = "11111111-1111-1111-1111-111111111111"
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add(
            RetrievalPartition(
                id=partition_id,
                source_namespace="docs",
                managed_workspace_id="ws-1",
                candidate_scope_kind="workspace",
                candidate_workspace_id="ws-1",
                state="active",
                metadata_version=1,
                is_default_ingest=True,
            )
        )
        session.add(
            RetrievalProjectionEvent(
                event_sequence=1,
                resource_type="doc",
                resource_id="stale-versioned-doc",
                projection_version=1,
                retrieval_partition_id=partition_id,
                change_kind="content",
                desired_state="active",
                content_checksum="content-v1",
                created_at=now - timedelta(minutes=2),
            )
        )
        session.add(
            RetrievalProjectionHead(
                resource_type="doc",
                resource_id="stale-versioned-doc",
                projection_version=2,
                retrieval_partition_id=partition_id,
                desired_state="deleted",
                updated_at=now - timedelta(minutes=1),
            )
        )
        session.add(
            RagSyncJob(
                id="rag-stale-versioned",
                workspace_id="ws-1",
                lane=RagSyncLane.REALTIME.value,
                resource_type="doc",
                resource_id="stale-versioned-doc",
                operation=RagSyncOperation.UPSERT.value,
                retrieval_partition_id=partition_id,
                projection_event_sequence=1,
                projection_version=1,
                desired_state="active",
                content_checksum="content-v1",
                trace_context={},
                status=RagJobStatus.PENDING.value,
                attempts=0,
                created_at=now - timedelta(minutes=2),
                updated_at=now - timedelta(minutes=2),
            )
        )
        session.commit()

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: pytest.fail(
            "stale projection job must not compute embeddings or mutate vectors"
        ),
    )

    result = tasks_module.sync_resource.run("rag-stale-versioned")

    assert result == "superseded"
    with Session(engine) as session:
        stale = session.get(RagSyncJob, "rag-stale-versioned")
        assert stale is not None
        assert stale.status == RagJobStatus.CANCELLED.value
        assert stale.last_error == (
            "superseded_by_projection_head:initial:head_mismatch:projection_version,desired_state"
        )


def test_sync_resource_worker_uses_retry_after_for_transient_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RetryScheduled(Exception):
        pass

    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_RETRY_BACKOFF_SECONDS", "7")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-rate-limit",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(
            RagProviderTransientError("slow down", retry_after_seconds=19)
        ),
    )

    retry_calls: list[int] = []

    def fake_retry(*, exc, countdown, **_kwargs):
        assert isinstance(exc, RagProviderTransientError)
        retry_calls.append(countdown)
        raise RetryScheduled()

    monkeypatch.setattr(tasks_module.sync_resource, "retry", fake_retry)

    with pytest.raises(RetryScheduled):
        tasks_module.sync_resource.run(job_id)

    assert retry_calls == [19]


def test_sync_resource_worker_cancels_non_retryable_provider_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-bad-config",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(
            RagProviderConfigurationError("bad qdrant schema")
        ),
    )
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("non-retryable provider errors must not schedule retry"),
    )

    result = tasks_module.sync_resource.run(job_id)

    assert result == "non_retryable_error"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.last_error == "non_retryable: bad qdrant schema"


def test_sync_resource_worker_dead_letters_poison_message_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "1")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-dead",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, _job: (_ for _ in ()).throw(RuntimeError("poison")),
    )
    monkeypatch.setattr(
        tasks_module.sync_resource,
        "retry",
        lambda **_kwargs: pytest.fail("dead-letter path must not schedule retry"),
    )

    result = tasks_module.sync_resource.run(job_id)

    assert result == "dead_letter"
    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.attempts == 1
        assert stored.next_retry_at is None
        assert stored.last_error == "dead_letter: poison"


def test_sync_backfill_worker_drains_chunked_batch_with_throttle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_routing_tables=True,
        seed_provider_rows=True,
    )
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_BACKFILL_BATCH_SIZE", "2")
    monkeypatch.setenv("OPEN_ALM_RAG_BACKFILL_THROTTLE_MS", "50")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            backfill_ids = [
                enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id=f"doc-backfill-{index}",
                    lane=RagSyncLane.BACKFILL,
                ).id
                for index in range(1, 4)
            ]
            realtime_id = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-realtime",
                lane=RagSyncLane.REALTIME,
            ).id

    tasks_module = _reload_worker_module("open_alm_worker.tasks.rag_sync")
    processed: list[str] = []
    sleeps: list[float] = []
    monkeypatch.setattr(
        tasks_module,
        "_process_sync_job",
        lambda _session, job: processed.append(job.id) or "succeeded",
    )
    monkeypatch.setattr(tasks_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = tasks_module.sync_backfill_resource.run(backfill_ids[0])

    assert result == "succeeded"
    assert processed == backfill_ids[:2]
    assert sleeps == [0.05]

    with Session(engine) as session:
        first = session.get(RagSyncJob, backfill_ids[0])
        second = session.get(RagSyncJob, backfill_ids[1])
        third = session.get(RagSyncJob, backfill_ids[2])
        realtime = session.get(RagSyncJob, realtime_id)
        assert first is not None and first.status == "succeeded"
        assert second is not None and second.status == "succeeded"
        assert third is not None and third.status == "pending"
        assert realtime is not None and realtime.status == "pending"
