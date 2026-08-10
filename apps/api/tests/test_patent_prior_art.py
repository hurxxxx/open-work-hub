from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from io import BytesIO
import json
import sys
from types import SimpleNamespace
import zipfile

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.core.worker_queue_contract import (
    LEGACY_PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_RUN_JOB_TASK_NAME,
)
from open_alm_api.domains.auth.models import (
    User,
    Workspace,
    WorkspaceAppEntitlement,
    WorkspaceUserBinding,
)
from open_alm_api.domains.patent_prior_art import (
    PATENT_PRIOR_ART_APP_ID,
    pipeline,
    router,
    service,
)
from open_alm_api.domains.patent_prior_art.artifacts import (
    PatentPriorArtArtifactStore,
    StoredArtifact,
    input_storage_key,
    job_storage_prefix,
    report_markdown_storage_key,
    result_json_storage_key,
)
from open_alm_api.domains.patent_prior_art.models import (
    PatentPriorArtArtifact,
    PatentPriorArtCandidate,
    PatentPriorArtExecutedQuery,
    PatentPriorArtJob,
)
from open_alm_api.domains.patent_prior_art.dispatch import PatentPriorArtJobDispatcher
from open_alm_api.domains.patent_prior_art.planning import (
    build_display_query,
    compile_provider_queries,
)
from open_alm_api.domains.patent_prior_art.queue_cutover import (
    PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER,
    PatentPriorArtQueueCutoverError,
    reconcile_patent_prior_art_queue_cutover,
    rollback_patent_prior_art_queue_cutover,
)
from open_alm_api.domains.patent_prior_art.schemas import (
    PatentPriorArtCandidateOut,
    PatentPriorArtExecutedQueryOut,
    PatentPriorArtFileParseResponse,
    PatentPriorArtJobCreateRequest,
    PatentPriorArtQueryPreviewRequest,
    PatentPriorArtQueryPreviewResponse,
    PatentPriorArtSearchPlanDraft,
    PatentPriorArtSearchValues,
)


class FakeArtifactStore:
    def __init__(self) -> None:
        self.inputs: dict[str, dict[str, object]] = {}
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []
        self.fail_cleanup = False

    def put_input_payload(
        self,
        *,
        workspace_id: str,
        job_id: str,
        payload: dict[str, object],
    ) -> str:
        key = input_storage_key(workspace_id, job_id)
        self.inputs[key] = payload
        self.objects[key] = b"stored input"
        return key

    def read_input_payload(self, storage_key: str) -> dict[str, object]:
        return self.inputs[storage_key]

    def put_result_artifacts(
        self,
        *,
        workspace_id: str,
        job_id: str,
        execution_id: str,
        result_json: str,
        report_markdown: str,
    ) -> tuple[StoredArtifact, StoredArtifact]:
        result_key = result_json_storage_key(workspace_id, job_id, execution_id)
        report_key = report_markdown_storage_key(workspace_id, job_id, execution_id)
        result_bytes = result_json.encode()
        report_bytes = report_markdown.encode()
        self.objects[result_key] = result_bytes
        self.objects[report_key] = report_bytes
        return (
            StoredArtifact(
                kind="result_json",
                filename="prior-art-result.json",
                mime_type="application/json; charset=utf-8",
                size_bytes=len(result_bytes),
                storage_key=result_key,
            ),
            StoredArtifact(
                kind="report_markdown",
                filename="prior-art-report.md",
                mime_type="text/markdown; charset=utf-8",
                size_bytes=len(report_bytes),
                storage_key=report_key,
            ),
        )

    def read_artifact(self, storage_key: str, *, expected_size: int) -> bytes:
        content = self.objects[storage_key]
        assert len(content) == expected_size
        return content

    def remove_objects(self, storage_keys) -> None:
        if self.fail_cleanup:
            raise RuntimeError("object storage unavailable")
        for storage_key in storage_keys:
            self.removed.append(storage_key)
            self.objects.pop(storage_key, None)
            self.inputs.pop(storage_key, None)

    def remove_job_objects(
        self,
        *,
        workspace_id: str,
        job_id: str,
        recorded_storage_keys=(),
    ) -> None:
        if self.fail_cleanup:
            raise RuntimeError("object storage unavailable")
        prefix = f"{job_storage_prefix(workspace_id, job_id)}/"
        keys = [
            input_storage_key(workspace_id, job_id),
            *recorded_storage_keys,
            *(key for key in self.objects if key.startswith(prefix)),
        ]
        self.remove_objects(keys)

    def remove_stale_execution_objects(
        self,
        *,
        workspace_id: str,
        job_id: str,
        keep_execution_id: str,
    ) -> None:
        if self.fail_cleanup:
            raise RuntimeError("object storage unavailable")
        executions_prefix = f"{job_storage_prefix(workspace_id, job_id)}/executions/"
        keep_prefix = f"{executions_prefix}{keep_execution_id}/"
        self.remove_objects(
            key
            for key in list(self.objects)
            if key.startswith(executions_prefix) and not key.startswith(keep_prefix)
        )


class FakeDispatcher:
    def __init__(self) -> None:
        self.job_ids: list[str] = []
        self.task_ids: list[str] = []
        self.fail = False
        self.on_dispatch: Callable[[str, str], None] | None = None

    def dispatch(self, job_id: str, *, task_id: str) -> None:
        self.job_ids.append(job_id)
        self.task_ids.append(task_id)
        if self.on_dispatch is not None:
            self.on_dispatch(job_id, task_id)
        if self.fail:
            raise RuntimeError("broker unavailable")


class FakeQueueBroker:
    def __init__(
        self,
        *,
        legacy_messages: int = 0,
        new_messages: int = 0,
        marker_exists: bool = False,
    ) -> None:
        self.queues = {
            LEGACY_PATENT_PRIOR_ART_QUEUE: legacy_messages,
            PATENT_PRIOR_ART_QUEUE: new_messages,
        }
        self.marker_exists = marker_exists

    @property
    def legacy_messages(self) -> int:
        return self.queues[LEGACY_PATENT_PRIOR_ART_QUEUE]

    def delete(self, *names: str) -> int:
        removed = 0
        for name in names:
            if name == PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER:
                removed += int(self.marker_exists)
                self.marker_exists = False
                continue
            removed += int(self.queues[name] > 0)
            self.queues[name] = 0
        return removed

    def exists(self, name: str) -> int:
        assert name == PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER
        return int(self.marker_exists)

    def llen(self, name: str) -> int:
        return self.queues[name]

    def set(self, name: str, value: str) -> bool:
        assert name == PATENT_PRIOR_ART_QUEUE_CUTOVER_MARKER
        assert value == "completed"
        self.marker_exists = True
        return True

    def type(self, name: str) -> str:
        return "list" if self.queues[name] else "none"


class FakeQueueTaskPublisher:
    def __init__(self, broker: FakeQueueBroker) -> None:
        self.broker = broker
        self.task_ids: list[str] = []
        self.queues: list[str] = []

    def send_task(
        self,
        name: str,
        *,
        args: list[str],
        queue: str,
        task_id: str,
    ) -> object:
        assert name == PATENT_PRIOR_ART_RUN_JOB_TASK_NAME
        assert len(args) == 1
        self.task_ids.append(task_id)
        self.queues.append(queue)
        self.broker.queues[queue] += 1
        return object()


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            WorkspaceUserBinding.__table__,
            WorkspaceAppEntitlement.__table__,
            PatentPriorArtJob.__table__,
            PatentPriorArtCandidate.__table__,
            PatentPriorArtExecutedQuery.__table__,
            PatentPriorArtArtifact.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FakeArtifactStore, FakeDispatcher]:
    store = FakeArtifactStore()
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(
        service,
        "patent_prior_art_artifact_store",
        lambda: store,
    )
    monkeypatch.setattr(
        service,
        "patent_prior_art_job_dispatcher",
        lambda: dispatcher,
    )
    return store, dispatcher


def _scope(identifier: str) -> SimpleNamespace:
    return SimpleNamespace(id=identifier)


def _search_values(
    values: list[str] | None = None,
    *,
    source: str = "user",
) -> PatentPriorArtSearchValues:
    return PatentPriorArtSearchValues(values=values or [], source=source)


def _request(
    *,
    category_ids: list[str] | None = None,
    jurisdictions: list[str] | None = None,
    technology_summary: str = "",
    idempotency_key: str = "request-0001",
) -> PatentPriorArtJobCreateRequest:
    return PatentPriorArtJobCreateRequest(
        title="  선행기술 조사  ",
        idempotency_key=idempotency_key,
        invention_text="차량 열관리 장치의 제어 방법에 관한 충분히 긴 발명 설명입니다.",
        technology_summary=technology_summary,
        jurisdictions=jurisdictions or ["KR"],
        search_plan=PatentPriorArtSearchPlanDraft(
            category_ids=_search_values(category_ids or ["vehicle"]),
            keywords_ko=_search_values(["열관리"], source="input_derived"),
            keywords_en=_search_values(["thermal management"], source="input_derived"),
            ipc_codes=_search_values(["B60H"], source="input_derived"),
            cpc_codes=_search_values(),
            applicants=_search_values(),
            excluded_terms=_search_values(),
            display_query="B60H AND 열관리",
        ),
    )


_V1_COMPAT_QUERY = (
    '"열 관리" OR H01L1/00 OR H01L2/00 OR H01L3/00 OR H01L4/00 OR '
    "H01L5/00 OR H01L6/00 OR H01L7/00 OR H01L8/00 OR H01L9/00"
)
_V1_COMPAT_DISPLAY_QUERY = f"{_V1_COMPAT_QUERY}\n{_V1_COMPAT_QUERY}"


def _v1_compatibility_request(*, idempotency_key: str) -> PatentPriorArtJobCreateRequest:
    codes = [f"H01L{index}/00" for index in range(1, 10)]
    return PatentPriorArtJobCreateRequest(
        title="",
        idempotency_key=idempotency_key,
        invention_text="차량의 열을 효율적으로 관리하는 제어 장치에 관한 충분히 긴 발명 설명입니다.",
        technology_summary="차량 열 관리 제어",
        jurisdictions=["KR", "US"],
        search_plan=PatentPriorArtSearchPlanDraft(
            category_ids=_search_values([]),
            keywords_ko=_search_values(["열 관리"]),
            keywords_en=_search_values([]),
            ipc_codes=_search_values([]),
            cpc_codes=_search_values(codes),
            applicants=_search_values(["회사"]),
            excluded_terms=_search_values([]),
            display_query="caller supplied display is not authoritative",
        ),
    )


def _v1_fingerprint(request: PatentPriorArtJobCreateRequest) -> str:
    fingerprint_plan = request.search_plan.model_copy(
        update={"display_query": _V1_COMPAT_DISPLAY_QUERY}
    )
    fingerprint_request = request.model_copy(
        update={
            "jurisdictions": ["KR", "US"],
            "search_plan": fingerprint_plan,
        }
    )
    return service._request_fingerprint(fingerprint_request)


def _add_job(
    db: Session,
    *,
    job_id: str,
    workspace_id: str = "workspace-1",
    owner_id: str = "user-1",
    status: str = "queued",
    stage: str = "queued",
    task_id: str | None = None,
) -> PatentPriorArtJob:
    row = PatentPriorArtJob(
        id=job_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        title="조사",
        idempotency_key=f"request-{job_id}",
        request_fingerprint=f"fingerprint-{job_id}",
        status=status,
        stage=stage,
        progress_percent=0 if status == "queued" else 20,
        jurisdictions=["KR"],
        search_plan=_request().search_plan.model_dump(mode="json"),
        input_storage_key=input_storage_key(workspace_id, job_id),
        celery_task_id=task_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _execution_id(row: PatentPriorArtJob) -> str:
    assert row.execution_id
    return row.execution_id


def _empty_pipeline_result(label: str) -> SimpleNamespace:
    return SimpleNamespace(
        result_json=json.dumps({"execution": label}),
        report_markdown=f"# {label}",
        candidates=[],
        executed_queries=[],
    )


def _report_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "report_type": "patent_prior_art_research",
        "title": "선행기술 조사",
        "scope": {
            "jurisdictions": ["KR"],
            "category_ids": ["vehicle"],
            "invention_text": "센서 기반 열관리 제어 장치",
            "invention_text_truncated": False,
            "technology_summary": "열관리 제어 기술",
        },
        "search_plan": _request().search_plan.model_dump(mode="json"),
        "executed_queries": [],
        "selection": {"candidate_count": 0, "ranking_profile": {}},
        "candidates": [],
    }


def _succeed_report_job(db: Session, *, job_id: str = "job-1") -> PatentPriorArtJob:
    row = _add_job(db, job_id=job_id)
    claimed = service.claim_job(db, job_id=row.id)
    assert claimed is not None
    service.persist_result(
        db,
        claimed,
        execution_id=_execution_id(claimed),
        result=SimpleNamespace(
            result_json=json.dumps(_report_payload(), ensure_ascii=False),
            report_markdown="# 기존 Markdown",
            candidates=[],
            executed_queries=[],
        ),
    )
    db.refresh(claimed)
    return claimed


def _grant_job_execution_access(db: Session) -> tuple[Workspace, User]:
    workspace = Workspace(
        id="workspace-1",
        key="workspace-1",
        name="Workspace 1",
        active=True,
    )
    user = User(
        id="user-1",
        login_id="user-1",
        email="user-1@example.test",
        full_name="User 1",
        password_hash="not-used",
        status="active",
        login_blocked=False,
    )
    db.add_all(
        [
            workspace,
            user,
            WorkspaceUserBinding(
                id="binding-1",
                workspace_id=workspace.id,
                user_id=user.id,
                role="member",
            ),
            WorkspaceAppEntitlement(
                id="entitlement-1",
                workspace_id=workspace.id,
                app_id=PATENT_PRIOR_ART_APP_ID,
                visibility_override=True,
            ),
        ]
    )
    db.commit()
    return workspace, user


def test_create_job_stores_reviewed_summary_and_canonical_category_first_plan(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, dispatcher = adapters
    request = _request(category_ids=["vehicle"])
    observed_reservation: dict[str, object] = {}

    def observe_committed_reservation(job_id: str, task_id: str) -> None:
        db.expire_all()
        reserved = db.get(PatentPriorArtJob, job_id)
        assert reserved is not None
        observed_reservation.update(
            task_id=reserved.celery_task_id,
            published_at=reserved.dispatch_published_at,
            attempts=reserved.dispatch_attempts,
        )
        assert reserved.celery_task_id == task_id

    dispatcher.on_dispatch = observe_committed_reservation
    preview_response = PatentPriorArtQueryPreviewResponse(
        technology_summary="  검토 완료된 차량 열관리 기술 요약  ",
        plan=request.search_plan,
        source_queries=[],
    )
    monkeypatch.setattr(
        pipeline,
        "preview_patent_prior_art_search",
        lambda *_args, **_kwargs: preview_response,
    )
    preview = service.preview_query(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=PatentPriorArtQueryPreviewRequest(
            invention_text=request.invention_text,
            category_ids=["vehicle"],
            jurisdictions=["KR"],
        ),
    )
    edited_plan = preview.plan.model_copy(
        update={
            "keywords_ko": _search_values(
                ["편집된 열관리 제어"],
                source="user",
            ),
            "display_query": "미리보기의 오래된 표시 검색식",
        }
    )

    output = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=request.model_copy(
            update={
                "technology_summary": preview.technology_summary,
                "search_plan": edited_plan,
            }
        ),
    )

    row = db.get(PatentPriorArtJob, output.id)
    assert row is not None
    assert row.search_plan["category_ids"] == {
        "values": ["vehicle"],
        "source": "user",
    }
    assert "invention_text" not in PatentPriorArtJob.__table__.columns
    stored_input = service.load_job_input(row)
    assert stored_input.invention_text.startswith("차량")
    assert stored_input.technology_summary == "검토 완료된 차량 열관리 기술 요약"
    compiled = compile_provider_queries(
        stored_input.search_plan,
        stored_input.jurisdictions,
    )
    canonical_display_query = build_display_query(compiled)
    assert compiled[0].purpose == "category_anchor"
    assert compiled[0].source_id == "category-vehicle-kr"
    assert stored_input.search_plan.display_query == canonical_display_query
    assert row.search_plan["display_query"] == canonical_display_query
    assert "미리보기의 오래된 표시 검색식" not in canonical_display_query
    assert dispatcher.job_ids == [row.id]
    assert dispatcher.task_ids == [row.celery_task_id]
    assert observed_reservation == {
        "attempts": 1,
        "published_at": None,
        "task_id": row.celery_task_id,
    }
    assert row.dispatch_attempts == 1
    assert row.dispatch_published_at is not None
    assert output.stage == "queued"
    assert output.status_message is None


def test_create_job_rejects_empty_compiled_plan_before_side_effects(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, dispatcher = adapters
    request = _request()
    empty_values = _search_values([], source="user")
    empty_plan = request.search_plan.model_copy(
        update={
            "category_ids": empty_values,
            "keywords_ko": empty_values,
            "keywords_en": empty_values,
            "ipc_codes": empty_values,
            "cpc_codes": empty_values,
            "applicants": empty_values,
            "excluded_terms": empty_values,
            "display_query": "사용자가 입력한 문자열은 검색 계획이 아닙니다",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        service.create_job(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            request=request.model_copy(update={"search_plan": empty_plan}),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail.code == "patent_prior_art.invalid_scope"
    assert store.inputs == {}
    assert dispatcher.job_ids == []
    assert db.scalars(select(PatentPriorArtJob)).all() == []


def test_create_job_reuses_matching_idempotency_key_and_rejects_mismatch(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, dispatcher = adapters
    request = _request(idempotency_key="stable-request-1")

    first = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=request,
    )
    second = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=request,
    )

    assert second.id == first.id
    assert dispatcher.job_ids == [first.id]
    assert len(store.inputs) == 1
    assert len(db.scalars(select(PatentPriorArtJob)).all()) == 1

    with pytest.raises(HTTPException) as conflict:
        service.create_job(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            request=request.model_copy(update={"title": "different request"}),
        )
    assert conflict.value.status_code == 409
    assert conflict.value.detail.code == "patent_prior_art.invalid_scope"


def test_create_job_reuses_pre_upgrade_v1_fingerprint(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, dispatcher = adapters
    request = _v1_compatibility_request(idempotency_key="stable-request-pre-upgrade")
    existing = _add_job(db, job_id="pre-upgrade")
    existing.idempotency_key = request.idempotency_key
    existing.request_fingerprint = _v1_fingerprint(request)
    db.add(existing)
    db.commit()

    output = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=request,
    )

    assert output.id == existing.id
    assert store.inputs == {}
    assert dispatcher.job_ids == []


def test_create_job_stores_v1_fingerprint_with_current_presentation_fields(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    request = _v1_compatibility_request(idempotency_key="stable-request-rollback")
    output = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=request,
    )

    row = db.get(PatentPriorArtJob, output.id)
    assert row is not None
    compiled = compile_provider_queries(
        PatentPriorArtSearchPlanDraft.model_validate(row.search_plan),
        row.jurisdictions,
    )
    assert row.request_fingerprint == _v1_fingerprint(request)
    assert row.request_fingerprint == (
        "9972ac7520faa5618b26ad8e730edce3446b421d7910afd8776701a446f6e8c7"
    )
    assert row.title == request.technology_summary
    assert row.search_plan["display_query"] == build_display_query(compiled)
    assert row.search_plan["display_query"] != _V1_COMPAT_DISPLAY_QUERY
    assert dispatcher.job_ids == [output.id]


def test_failed_or_ambiguous_publication_is_durably_republished_with_fresh_fence(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    dispatcher.fail = True
    output = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=_request(idempotency_key="stable-request-2"),
    )
    row = db.get(PatentPriorArtJob, output.id)
    assert row is not None
    first_task_id = row.celery_task_id
    assert first_task_id
    assert row.status == "queued"
    assert row.failure_code is None
    assert row.dispatch_published_at is None
    assert row.dispatch_attempts == 1

    republish_at = service._utcnow()
    row.updated_at = republish_at - service._DISPATCH_RESERVATION_GRACE - timedelta(seconds=1)
    db.add(row)
    db.commit()
    dispatcher.fail = False

    assert service.republish_pending_jobs(db, now=republish_at) == 1
    db.refresh(row)
    second_task_id = row.celery_task_id
    assert second_task_id and second_task_id != first_task_id
    assert dispatcher.task_ids == [first_task_id, second_task_id]
    assert row.dispatch_attempts == 2
    assert row.dispatch_published_at is not None
    assert service.claim_job(db, job_id=row.id, task_id=first_task_id) is None
    assert service.claim_job(db, job_id=row.id, task_id=second_task_id) is not None


def test_republisher_excludes_recent_confirmed_and_nonqueued_jobs(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    republish_at = service._utcnow()
    old = republish_at - service._DISPATCH_RESERVATION_GRACE - timedelta(seconds=1)
    due = _add_job(db, job_id="due", task_id="due-task")
    recent = _add_job(db, job_id="recent", task_id="recent-task")
    confirmed = _add_job(db, job_id="confirmed", task_id="confirmed-task")
    running = _add_job(
        db,
        job_id="running",
        task_id="running-task",
        status="running",
        stage="searching",
    )
    cancelled = _add_job(
        db,
        job_id="cancelled",
        status="cancelled",
        stage="cancelled",
    )
    due.updated_at = old
    confirmed.updated_at = old
    confirmed.dispatch_published_at = old
    running.updated_at = old
    cancelled.updated_at = old
    db.add_all([due, recent, confirmed, running, cancelled])
    db.commit()

    assert service.republish_pending_jobs(db, now=republish_at) == 1
    assert dispatcher.job_ids == [due.id]


def test_republisher_preserves_confirmed_job_waiting_behind_long_running_job(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    now = service._utcnow()
    running = _add_job(db, job_id="running", task_id="running-task")
    claimed = service.claim_job(db, job_id=running.id, task_id="running-task")
    assert claimed is not None
    waiting = _add_job(db, job_id="waiting", task_id="waiting-task")
    waiting.dispatch_published_at = now - timedelta(minutes=16)
    waiting.updated_at = waiting.dispatch_published_at
    db.add(waiting)
    db.commit()

    assert service.republish_pending_jobs(db, now=now) == 0
    db.refresh(waiting)
    assert waiting.celery_task_id == "waiting-task"
    assert waiting.dispatch_published_at == now - timedelta(minutes=16)
    assert dispatcher.task_ids == []


def test_cancel_between_dispatch_reservation_and_send_leaves_delivery_unclaimable(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters

    def cancel_reserved_job(job_id: str, _task_id: str) -> None:
        service.cancel_job(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            job_id=job_id,
        )

    dispatcher.on_dispatch = cancel_reserved_job
    output = service.create_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=_request(idempotency_key="stable-request-3"),
    )
    row = db.get(PatentPriorArtJob, output.id)
    assert row is not None
    published_task_id = dispatcher.task_ids[0]
    assert row.status == "cancelled"
    assert row.celery_task_id is None
    assert row.dispatch_published_at is None
    assert service.claim_job(db, job_id=row.id, task_id=published_task_id) is None


def test_private_job_reads_are_scoped_to_both_workspace_and_owner(
    db: Session,
) -> None:
    _add_job(db, job_id="job-1")
    _add_job(db, job_id="job-2", owner_id="user-2")
    _add_job(db, job_id="job-3", workspace_id="workspace-2")

    visible = service.list_jobs(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        limit=30,
    )
    assert [item.id for item in visible.items] == ["job-1"]
    assert visible.total == 1

    for workspace_id, owner_id in (
        ("workspace-2", "user-1"),
        ("workspace-1", "user-2"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.get_job(
                db,
                workspace=_scope(workspace_id),
                user=_scope(owner_id),
                job_id="job-1",
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail.code == "patent_prior_art.not_found"


def test_cancel_is_atomic_idempotent_and_blocks_worker_claim(db: Session) -> None:
    _add_job(db, job_id="job-1", task_id="task-1")

    first = service.cancel_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id="job-1",
    )
    second = service.cancel_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id="job-1",
    )

    assert first.status == second.status == "cancelled"
    assert first.stage == second.stage == "cancelled"
    assert service.claim_job(db, job_id="job-1", task_id="task-1") is None


def test_claim_rejects_foreign_and_live_duplicate_deliveries(
    db: Session,
) -> None:
    _add_job(db, job_id="job-1", task_id="task-a")

    assert service.claim_job(db, job_id="job-1", task_id="task-b") is None
    claimed = service.claim_job(db, job_id="job-1", task_id="task-a")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.celery_task_id == "task-a"
    first_execution_id = _execution_id(claimed)
    assert claimed.execution_attempts == 1
    assert claimed.execution_lease_expires_at is not None

    # A redelivery cannot rotate the fence while the original execution still
    # owns a live DB lease. Recovery must first make a fresh queued delivery.
    assert service.claim_job(db, job_id="job-1", task_id="task-a") is None
    assert not service.is_cancelled(
        db,
        job_id="job-1",
        execution_id=first_execution_id,
    )
    assert service.claim_job(db, job_id="job-1", task_id="task-b") is None


def test_claim_requires_precommitted_dispatch_fence(
    db: Session,
) -> None:
    _add_job(db, job_id="job-1")

    assert service.claim_job(db, job_id="job-1", task_id="task-unreserved") is None
    row = db.get(PatentPriorArtJob, "job-1")
    assert row is not None
    row.celery_task_id = "task-current"
    db.commit()
    claimed = service.claim_job(db, job_id="job-1", task_id="task-current")

    assert claimed is not None
    assert claimed.celery_task_id == "task-current"
    assert claimed.execution_id is not None
    assert service.claim_job(db, job_id="job-1", task_id="task-stale") is None


def test_can_execute_job_revalidates_access_and_app_entitlement(
    db: Session,
) -> None:
    workspace, user = _grant_job_execution_access(db)
    row = _add_job(db, job_id="job-1", task_id="task-a")
    claimed = service.claim_job(db, job_id=row.id, task_id="task-a")
    assert claimed is not None
    execution_id = _execution_id(claimed)
    entitlement = db.scalar(
        select(WorkspaceAppEntitlement).where(
            WorkspaceAppEntitlement.workspace_id == workspace.id,
            WorkspaceAppEntitlement.app_id == PATENT_PRIOR_ART_APP_ID,
        )
    )
    assert entitlement is not None
    assert service.can_execute_job(db, claimed, execution_id=execution_id)

    entitlement.visibility_override = False
    db.commit()
    assert not service.can_execute_job(db, claimed, execution_id=execution_id)

    entitlement.visibility_override = True
    user.login_blocked = True
    db.commit()
    assert not service.can_execute_job(db, claimed, execution_id=execution_id)

    user.login_blocked = False
    user.status = "inactive"
    db.commit()
    assert not service.can_execute_job(db, claimed, execution_id=execution_id)

    user.status = "active"
    workspace.active = False
    db.commit()
    assert not service.can_execute_job(db, claimed, execution_id=execution_id)

    workspace.active = True
    user.is_admin = True
    binding = db.scalar(
        select(WorkspaceUserBinding).where(
            WorkspaceUserBinding.workspace_id == workspace.id,
            WorkspaceUserBinding.user_id == user.id,
        )
    )
    assert binding is not None
    db.delete(binding)
    db.commit()
    assert not service.can_execute_job(db, claimed, execution_id=execution_id)


def test_live_same_task_redelivery_cannot_steal_execution_fence(
    db: Session,
) -> None:
    _grant_job_execution_access(db)
    row = _add_job(db, job_id="job-1", task_id="task-a")
    first = service.claim_job(db, job_id=row.id, task_id="task-a")
    assert first is not None
    first_execution_id = _execution_id(first)

    assert service.claim_job(db, job_id=row.id, task_id="task-a") is None
    assert service.can_execute_job(
        db,
        first,
        execution_id=first_execution_id,
    )


def test_lease_recovery_issues_fresh_task_fence_and_isolates_result_objects(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, dispatcher = adapters
    row = _add_job(db, job_id="job-1", task_id="task-a")
    first = service.claim_job(db, job_id=row.id, task_id="task-a")
    assert first is not None
    first_execution_id = _execution_id(first)
    crashed_result_key = result_json_storage_key(
        "workspace-1",
        row.id,
        first_execution_id,
    )
    crashed_report_key = report_markdown_storage_key(
        "workspace-1",
        row.id,
        first_execution_id,
    )
    store.objects[crashed_result_key] = b"orphaned result"
    store.objects[crashed_report_key] = b"orphaned report"

    recovery_time = service._utcnow()
    first.execution_lease_expires_at = recovery_time - timedelta(seconds=1)
    db.add(first)
    db.commit()
    assert service.recover_expired_jobs(db, now=recovery_time) == (1, 0)
    assert service.republish_pending_jobs(db, now=recovery_time) == 1
    db.refresh(row)
    second_task_id = row.celery_task_id
    assert second_task_id is not None
    assert second_task_id != "task-a"
    assert dispatcher.task_ids == [second_task_id]

    second = service.claim_job(db, job_id=row.id, task_id=second_task_id)
    assert second is not None
    second_execution_id = _execution_id(second)
    assert second_execution_id != first_execution_id
    assert service.is_cancelled(
        db,
        job_id=row.id,
        execution_id=first_execution_id,
    )
    assert not service.update_stage(
        db,
        first,
        execution_id=first_execution_id,
        stage="ranking",
        progress_percent=50,
    )
    assert not service.mark_failed(
        db,
        first,
        execution_id=first_execution_id,
        failure_code="pipeline_failed",
    )

    service.persist_result(
        db,
        second,
        execution_id=second_execution_id,
        result=_empty_pipeline_result("winner"),
    )
    winner_result_key = result_json_storage_key(
        "workspace-1",
        row.id,
        second_execution_id,
    )
    winner_report_key = report_markdown_storage_key(
        "workspace-1",
        row.id,
        second_execution_id,
    )

    with pytest.raises(service.PatentPriorArtPersistenceCancelled):
        service.persist_result(
            db,
            first,
            execution_id=first_execution_id,
            result=_empty_pipeline_result("stale"),
        )

    assert winner_result_key in store.objects
    assert winner_report_key in store.objects
    assert crashed_result_key not in store.objects
    assert crashed_report_key not in store.objects
    assert crashed_result_key in store.removed
    assert crashed_report_key in store.removed
    assert (
        result_json_storage_key(
            "workspace-1",
            row.id,
            first_execution_id,
        )
        not in store.objects
    )
    assert set(db.scalars(select(PatentPriorArtArtifact.execution_id)).all()) == {
        second_execution_id
    }


def test_queue_cutover_fences_active_jobs_empties_legacy_queue_and_republishes(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    queued = _add_job(db, job_id="queued", task_id="old-queued-task")
    running = _add_job(db, job_id="running", task_id="old-running-task")
    claimed = service.claim_job(db, job_id=running.id, task_id="old-running-task")
    assert claimed is not None
    old_execution_id = _execution_id(claimed)
    broker = FakeQueueBroker(legacy_messages=2)
    cutover_time = service._utcnow()
    queued.dispatch_published_at = cutover_time - timedelta(minutes=5)
    db.add(queued)
    db.commit()

    result = reconcile_patent_prior_art_queue_cutover(
        db,
        broker,
        now=cutover_time,
    )

    assert result.cutover_performed is True
    assert result.legacy_messages_removed == 2
    assert result.jobs_fenced == 2
    assert result.jobs_published == 2
    assert result.final_legacy_queue_length == 0
    assert broker.marker_exists is True
    assert broker.legacy_messages == 0
    assert len(dispatcher.task_ids) == 2

    for row in (queued, running):
        db.refresh(row)
        assert row.status == "queued"
        assert row.stage == "queued"
        assert row.execution_id is None
        assert row.execution_lease_expires_at is None
        assert row.next_attempt_at is None
        assert row.celery_task_id in dispatcher.task_ids
        assert row.celery_task_id not in {"old-queued-task", "old-running-task"}
        assert row.dispatch_published_at is not None

    assert (
        service.update_stage(
            db,
            claimed,
            execution_id=old_execution_id,
            stage="reporting",
            progress_percent=80,
        )
        is False
    )

    second_result = reconcile_patent_prior_art_queue_cutover(
        db,
        broker,
        now=cutover_time,
    )
    assert second_result.cutover_performed is False
    assert second_result.jobs_fenced == 0
    assert second_result.jobs_published == 0
    assert len(dispatcher.task_ids) == 2


def test_queue_cutover_fails_closed_when_active_jobs_are_not_fully_published(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    _add_job(db, job_id="queued", task_id="old-task")
    dispatcher.fail = True
    broker = FakeQueueBroker(legacy_messages=1)

    with pytest.raises(
        PatentPriorArtQueueCutoverError,
        match="active_jobs_not_fully_republished",
    ):
        reconcile_patent_prior_art_queue_cutover(db, broker)

    assert broker.legacy_messages == 0
    assert broker.marker_exists is False


def test_queue_rollback_fences_active_jobs_and_republishes_to_legacy_queue(
    db: Session,
) -> None:
    queued = _add_job(db, job_id="queued", task_id="new-queued-task")
    running = _add_job(db, job_id="running", task_id="new-running-task")
    claimed = service.claim_job(db, job_id=running.id, task_id="new-running-task")
    assert claimed is not None
    old_execution_id = _execution_id(claimed)
    broker = FakeQueueBroker(
        legacy_messages=1,
        new_messages=2,
        marker_exists=True,
    )
    publisher = FakeQueueTaskPublisher(broker)
    dispatcher = PatentPriorArtJobDispatcher(
        publisher=publisher,
        queue=LEGACY_PATENT_PRIOR_ART_QUEUE,
    )

    result = rollback_patent_prior_art_queue_cutover(
        db,
        broker,
        dispatcher=dispatcher,
        now=service._utcnow(),
    )

    assert result.new_messages_removed == 2
    assert result.legacy_messages_removed == 1
    assert result.jobs_fenced == 2
    assert result.jobs_published == 2
    assert result.final_new_queue_length == 0
    assert result.final_legacy_queue_length == 2
    assert broker.marker_exists is False
    assert broker.queues[PATENT_PRIOR_ART_QUEUE] == 0
    assert broker.queues[LEGACY_PATENT_PRIOR_ART_QUEUE] == 2
    assert publisher.queues == [
        LEGACY_PATENT_PRIOR_ART_QUEUE,
        LEGACY_PATENT_PRIOR_ART_QUEUE,
    ]

    for row in (queued, running):
        db.refresh(row)
        assert row.status == "queued"
        assert row.stage == "queued"
        assert row.execution_id is None
        assert row.execution_lease_expires_at is None
        assert row.celery_task_id in publisher.task_ids
        assert row.dispatch_published_at is not None

    assert (
        service.update_stage(
            db,
            claimed,
            execution_id=old_execution_id,
            stage="reporting",
            progress_percent=80,
        )
        is False
    )


def test_transient_failure_waits_in_db_and_is_published_only_when_due(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, dispatcher = adapters
    row = _add_job(db, job_id="job-1", task_id="task-a")
    claimed = service.claim_job(db, job_id=row.id, task_id="task-a")
    assert claimed is not None
    first_execution_id = _execution_id(claimed)
    restart_time = service._utcnow()

    assert service.schedule_automatic_restart(
        db,
        claimed,
        execution_id=first_execution_id,
        now=restart_time,
    )
    db.refresh(claimed)
    assert claimed.status == "queued"
    assert claimed.stage == "retry_waiting"
    assert claimed.execution_id is None
    assert claimed.execution_lease_expires_at is None
    assert claimed.automatic_restart_count == 1
    assert claimed.next_attempt_at == restart_time + service._AUTOMATIC_RESTART_DELAY
    projected = service.get_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    assert projected.stage == "retry_waiting"
    assert projected.failure_code is None
    assert projected.execution_attempts == 1
    assert projected.automatic_restart_count == 1
    assert projected.next_attempt_at == claimed.next_attempt_at
    assert projected.can_cancel is True
    assert (
        service.update_stage(
            db,
            claimed,
            execution_id=first_execution_id,
            stage="searching",
            progress_percent=20,
        )
        is False
    )

    assert (
        service.republish_pending_jobs(
            db,
            now=claimed.next_attempt_at - timedelta(microseconds=1),
        )
        == 0
    )
    assert service.republish_pending_jobs(db, now=claimed.next_attempt_at) == 1
    db.refresh(claimed)
    assert claimed.stage == "queued"
    assert claimed.next_attempt_at is None
    assert claimed.celery_task_id is not None
    assert claimed.celery_task_id != "task-a"
    assert dispatcher.task_ids == [claimed.celery_task_id]


def test_expired_execution_recovers_once_then_terminalizes_as_worker_lost(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, _dispatcher = adapters
    row = _add_job(db, job_id="job-1", task_id="task-a")
    first = service.claim_job(db, job_id=row.id, task_id="task-a")
    assert first is not None
    first_execution_id = _execution_id(first)
    recovery_time = service._utcnow()
    first.execution_lease_expires_at = recovery_time - timedelta(seconds=1)
    db.commit()

    assert service.recover_jobs(db, now=recovery_time) == {
        "restarted": 1,
        "failed": 0,
        "published": 1,
    }
    db.refresh(row)
    recovered_task_id = row.celery_task_id
    assert recovered_task_id is not None
    assert recovered_task_id != "task-a"
    assert (
        service.mark_failed(
            db,
            first,
            execution_id=first_execution_id,
            failure_code="pipeline_failed",
        )
        is False
    )

    second = service.claim_job(db, job_id=row.id, task_id=recovered_task_id)
    assert second is not None
    second_execution_id = _execution_id(second)
    assert second.execution_attempts == 2
    second_recovery_time = recovery_time + timedelta(minutes=4)
    second.execution_lease_expires_at = second_recovery_time - timedelta(seconds=1)
    db.commit()

    assert service.recover_jobs(db, now=second_recovery_time) == {
        "restarted": 0,
        "failed": 1,
        "published": 0,
    }
    db.refresh(row)
    assert row.status == "failed"
    assert row.stage == "failed"
    assert row.failure_code == "worker_lost"
    assert row.execution_id is None
    assert row.execution_lease_expires_at is None
    assert row.next_attempt_at is None
    with pytest.raises(service.PatentPriorArtPersistenceCancelled):
        service.persist_result(
            db,
            second,
            execution_id=second_execution_id,
            result=_empty_pipeline_result("late"),
        )


def test_execution_lease_heartbeat_is_fenced_by_execution_id(db: Session) -> None:
    row = _add_job(db, job_id="job-1", task_id="task-a")
    claimed = service.claim_job(db, job_id=row.id, task_id="task-a")
    assert claimed is not None
    execution_id = _execution_id(claimed)
    heartbeat_time = service._utcnow()

    assert service.renew_execution_lease(
        db,
        job_id=row.id,
        execution_id=execution_id,
        now=heartbeat_time,
    )
    db.refresh(claimed)
    assert claimed.execution_lease_expires_at == heartbeat_time + service._EXECUTION_LEASE_DURATION
    assert not service.renew_execution_lease(
        db,
        job_id=row.id,
        execution_id="stale-execution",
        now=heartbeat_time,
    )


def test_recovery_finds_prelease_running_job_from_old_revision(db: Session) -> None:
    recovery_time = service._utcnow()
    row = _add_job(
        db,
        job_id="legacy-running",
        status="running",
        stage="searching",
        task_id="legacy-task",
    )
    row.execution_id = "legacy-execution"
    row.execution_lease_expires_at = None
    row.updated_at = recovery_time - service._EXECUTION_LEASE_DURATION - timedelta(seconds=1)
    db.commit()

    assert service.recover_expired_jobs(db, now=recovery_time) == (1, 0)
    db.refresh(row)
    assert row.status == "queued"
    assert row.stage == "retry_waiting"
    assert row.execution_id is None
    assert row.next_attempt_at == recovery_time
    assert row.automatic_restart_count == 1


def test_stage_and_failure_transitions_expose_codes_not_raw_messages(
    db: Session,
) -> None:
    row = _add_job(db, job_id="job-1")
    claimed = service.claim_job(db, job_id=row.id)
    assert claimed is not None
    execution_id = _execution_id(claimed)

    assert service.update_stage(
        db,
        claimed,
        execution_id=execution_id,
        stage="ranking",
        progress_percent=45,
    )
    assert service.mark_failed(
        db,
        claimed,
        execution_id=execution_id,
        failure_code="Raw database timeout from host 10.0.0.1",
    )

    db.refresh(claimed)
    assert claimed.status == "failed"
    assert claimed.stage == "failed"
    assert claimed.failure_code == "pipeline_failed"
    output = service.get_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    assert output.stage == "failed"
    assert output.status_message is None
    assert output.failure_code == "pipeline_failed"
    assert output.execution_attempts == 1
    assert output.automatic_restart_count == 0


def test_persist_result_keeps_job_local_projection_without_numeric_score(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, _ = adapters
    row = _add_job(db, job_id="job-1")
    claimed = service.claim_job(db, job_id=row.id)
    assert claimed is not None
    execution_id = _execution_id(claimed)
    result = SimpleNamespace(
        result_json='{"candidate_count":1}',
        report_markdown="# 선행기술 조사\n\n중립 보고서",
        candidates=[
            PatentPriorArtCandidateOut(
                rank=1,
                publication_number="KR2024000001A",
                title="열관리 제어 장치",
                assignees=["Applicant A"],
                jurisdiction="KR",
                classification_codes=["B60H"],
                relevance_band="high",
                match_reasons=["구성요소 일치"],
                external_url="https://example.test/patent/1",
            )
        ],
        executed_queries=[
            PatentPriorArtExecutedQueryOut(
                source_id="kipris",
                source_label="KIPRIS",
                jurisdiction="KR",
                query_text="B60H AND 열관리",
                result_count=1,
                status="succeeded",
            ),
            PatentPriorArtExecutedQueryOut(
                source_id="kipris-wo",
                source_label="KIPRIS",
                jurisdiction="WO",
                query_text="B60H AND thermal management",
                result_count=None,
                status="failed",
                failure_code="provider_unavailable",
            ),
        ],
    )

    service.persist_result(
        db,
        claimed,
        execution_id=execution_id,
        result=result,
    )

    db.refresh(claimed)
    assert claimed.status == "succeeded"
    assert claimed.stage == "completed"
    assert "score" not in PatentPriorArtCandidate.__table__.columns
    assert db.scalar(select(PatentPriorArtCandidate.job_id)) == row.id
    assert db.scalar(select(PatentPriorArtExecutedQuery.job_id)) == row.id
    assert set(db.scalars(select(PatentPriorArtArtifact.kind)).all()) == {
        "result_json",
        "report_markdown",
    }

    output = service.get_result(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    assert output.candidate_count == 1
    assert output.partial is True
    assert output.candidates[0].publication_number == "KR2024000001A"
    assert output.executed_queries[0].status == "succeeded"
    assert output.executed_queries[1].status == "failed"
    assert output.executed_queries[1].failure_code == "provider_unavailable"
    assert output.report_markdown == "# 선행기술 조사\n\n중립 보고서"
    assert store.objects[result_json_storage_key("workspace-1", row.id, execution_id)] == (
        b'{"candidate_count":1}'
    )

    failed_query = db.scalar(
        select(PatentPriorArtExecutedQuery).where(
            PatentPriorArtExecutedQuery.job_id == row.id,
            PatentPriorArtExecutedQuery.status == "failed",
        )
    )
    assert failed_query is not None
    failed_query.failure_code = "private provider request URL"
    db.commit()
    redacted = service.get_result(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    assert redacted.partial is True
    assert redacted.executed_queries[1].failure_code is None


def test_persist_result_compensates_objects_when_projection_fails(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, _ = adapters
    row = _add_job(db, job_id="job-1")
    claimed = service.claim_job(db, job_id=row.id)
    assert claimed is not None
    execution_id = _execution_id(claimed)
    invalid_result = SimpleNamespace(
        result_json="{}",
        report_markdown="# report",
        candidates=[{"rank": 1}],
        executed_queries=[],
    )

    with pytest.raises(ValueError):
        service.persist_result(
            db,
            claimed,
            execution_id=execution_id,
            result=invalid_result,
        )

    db.refresh(claimed)
    assert claimed.status == "running"
    result_key = result_json_storage_key("workspace-1", row.id, execution_id)
    report_key = report_markdown_storage_key("workspace-1", row.id, execution_id)
    assert result_key in store.removed
    assert report_key in store.removed
    assert result_key not in store.objects
    assert report_key not in store.objects


def test_artifact_store_compensates_json_when_markdown_upload_fails() -> None:
    class FailingSecondPutClient:
        def __init__(self) -> None:
            self.put_count = 0
            self.removed: list[str] = []

        def put_object(self, _bucket, _key, _data, **_kwargs):
            self.put_count += 1
            if self.put_count == 2:
                raise RuntimeError("second upload failed")

        def remove_object(self, _bucket: str, key: str) -> None:
            self.removed.append(key)

    client = FailingSecondPutClient()
    store = PatentPriorArtArtifactStore(
        bucket_name="test-bucket",
        client=client,  # type: ignore[arg-type]
        ensure_bucket_exists=lambda: None,
    )

    with pytest.raises(RuntimeError, match="second upload failed"):
        store.put_result_artifacts(
            workspace_id="workspace-1",
            job_id="job-1",
            execution_id="execution-1",
            result_json="{}",
            report_markdown="# report",
        )

    assert client.removed == [result_json_storage_key("workspace-1", "job-1", "execution-1")]


def test_artifact_store_deletes_every_execution_under_bounded_job_prefix() -> None:
    class PrefixCleanupClient:
        def __init__(self) -> None:
            self.names = [
                result_json_storage_key("workspace-1", "job-1", "execution-1"),
                report_markdown_storage_key(
                    "workspace-1",
                    "job-1",
                    "crashed-execution",
                ),
            ]
            self.removed: list[str] = []
            self.list_call: tuple[str, str, bool] | None = None

        def list_objects(self, bucket, *, prefix, recursive):
            self.list_call = (bucket, prefix, recursive)
            return [SimpleNamespace(object_name=name) for name in self.names]

        def remove_object(self, _bucket: str, key: str) -> None:
            self.removed.append(key)

    client = PrefixCleanupClient()
    store = PatentPriorArtArtifactStore(
        bucket_name="test-bucket",
        client=client,  # type: ignore[arg-type]
        ensure_bucket_exists=lambda: None,
    )

    store.remove_job_objects(workspace_id="workspace-1", job_id="job-1")

    prefix = f"{job_storage_prefix('workspace-1', 'job-1')}/"
    assert client.list_call == ("test-bucket", prefix, True)
    assert set(client.removed) == {
        input_storage_key("workspace-1", "job-1"),
        *client.names,
    }


def test_artifact_store_removes_only_stale_execution_objects() -> None:
    current_result = result_json_storage_key(
        "workspace-1",
        "job-1",
        "current-execution",
    )
    stale_report = report_markdown_storage_key(
        "workspace-1",
        "job-1",
        "crashed-execution",
    )

    class ExecutionCleanupClient:
        def __init__(self, names: list[str]) -> None:
            self.names = names
            self.removed: list[str] = []
            self.list_prefix = ""

        def list_objects(self, _bucket, *, prefix, recursive):
            assert recursive is True
            self.list_prefix = prefix
            return [SimpleNamespace(object_name=name) for name in self.names]

        def remove_object(self, _bucket: str, key: str) -> None:
            self.removed.append(key)

    client = ExecutionCleanupClient([current_result, stale_report])
    store = PatentPriorArtArtifactStore(
        bucket_name="test-bucket",
        client=client,  # type: ignore[arg-type]
        ensure_bucket_exists=lambda: None,
    )

    store.remove_stale_execution_objects(
        workspace_id="workspace-1",
        job_id="job-1",
        keep_execution_id="current-execution",
    )

    assert client.list_prefix == (f"{job_storage_prefix('workspace-1', 'job-1')}/executions/")
    assert client.removed == [stale_report]

    client.names = ["patent-prior-art/workspace-1/other-job/executions/escaped/report.md"]
    with pytest.raises(ValueError, match="escaped"):
        store.remove_stale_execution_objects(
            workspace_id="workspace-1",
            job_id="job-1",
            keep_execution_id="current-execution",
        )


def test_artifact_download_is_owner_scoped_and_uses_safe_attachment_headers(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, _ = adapters
    row = _add_job(
        db,
        job_id="job-1",
        status="succeeded",
        stage="completed",
    )
    key = report_markdown_storage_key("workspace-1", row.id, "execution-1")
    store.objects[key] = b"# report"
    artifact = PatentPriorArtArtifact(
        id="artifact-1",
        workspace_id="workspace-1",
        job_id=row.id,
        execution_id="execution-1",
        kind="report_markdown",
        filename="prior-art report.md",
        mime_type="text/markdown; charset=utf-8",
        size_bytes=len(b"# report"),
        storage_key=key,
    )
    db.add(artifact)
    db.commit()

    with pytest.raises(HTTPException) as cross_owner:
        service.get_artifact(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-2"),
            job_id=row.id,
            artifact_id=artifact.id,
        )
    assert cross_owner.value.status_code == 404

    response = service.get_artifact(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
        artifact_id=artifact.id,
    )
    assert response.body == b"# report"
    assert response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''prior-art%20report.md"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


def test_report_export_is_owner_scoped_on_demand_and_uses_safe_headers(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    _store, _dispatcher = adapters
    row = _succeed_report_job(db)
    artifact_count = len(
        db.scalars(
            select(PatentPriorArtArtifact).where(PatentPriorArtArtifact.job_id == row.id)
        ).all()
    )

    with pytest.raises(HTTPException) as cross_owner:
        service.get_report(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-2"),
            job_id=row.id,
            report_format="html",
        )
    assert cross_owner.value.status_code == 404

    response = service.get_report(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
        report_format="html",
    )

    assert response.body.startswith(b"<!doctype html>")
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''patent-prior-art-detailed-job-1.html"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert (
        len(
            db.scalars(
                select(PatentPriorArtArtifact).where(PatentPriorArtArtifact.job_id == row.id)
            ).all()
        )
        == artifact_count
    )


def test_report_export_rejects_unready_or_invalid_job_local_result(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
) -> None:
    store, _dispatcher = adapters
    queued = _add_job(db, job_id="queued-job")
    with pytest.raises(HTTPException) as unready:
        service.get_report(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            job_id=queued.id,
            report_format="pdf",
        )
    assert unready.value.detail.code == "patent_prior_art.not_ready"

    succeeded = _succeed_report_job(db, job_id="succeeded-job")
    artifact = db.scalar(
        select(PatentPriorArtArtifact).where(
            PatentPriorArtArtifact.job_id == succeeded.id,
            PatentPriorArtArtifact.kind == "result_json",
        )
    )
    assert artifact is not None
    store.objects[artifact.storage_key] = b"not-json"
    artifact.size_bytes = len(b"not-json")
    db.commit()

    with pytest.raises(HTTPException) as invalid:
        service.get_report(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            job_id=succeeded.id,
            report_format="docx",
        )
    assert invalid.value.detail.code == "patent_prior_art.not_ready"


@pytest.mark.parametrize(
    ("initial_status", "initial_stage"),
    [
        ("running", "searching"),
        ("succeeded", "completed"),
        ("failed", "failed"),
    ],
)
def test_delete_normalizes_and_retains_tombstone_until_cleanup_succeeds(
    db: Session,
    adapters: tuple[FakeArtifactStore, FakeDispatcher],
    initial_status: str,
    initial_stage: str,
) -> None:
    store, _ = adapters
    row = _add_job(
        db,
        job_id="job-1",
        status=initial_status,
        stage=initial_stage,
        task_id="task-before-delete",
    )
    row.execution_id = "execution-before-delete"
    row.failure_code = "pipeline_failed"
    db.commit()
    store.objects[row.input_storage_key] = b"input"
    crash_result_key = result_json_storage_key(
        "workspace-1",
        row.id,
        "unrecorded-execution",
    )
    crash_report_key = report_markdown_storage_key(
        "workspace-1",
        row.id,
        "unrecorded-execution",
    )
    store.objects[crash_result_key] = b"orphaned result"
    store.objects[crash_report_key] = b"orphaned report"
    store.fail_cleanup = True

    first = service.delete_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    retained = db.get(PatentPriorArtJob, row.id)
    assert first.deleted is False
    assert retained is not None
    assert retained.deletion_requested_at is not None
    assert retained.cleanup_failure_code == "storage_cleanup_failed"
    assert retained.status == "cancelled"
    assert retained.stage == "cleanup_pending"
    assert retained.failure_code is None
    assert retained.celery_task_id is None
    assert retained.execution_id is None
    visible = service.get_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    assert visible.stage == "cleanup_pending"
    assert (
        service.list_jobs(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            limit=30,
        )
        .items[0]
        .id
        == row.id
    )
    with pytest.raises(HTTPException) as result_exc:
        service.get_result(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            job_id=row.id,
        )
    assert result_exc.value.detail.code == "patent_prior_art.not_found"

    store.fail_cleanup = False
    second = service.delete_job(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        job_id=row.id,
    )
    assert second.deleted is True
    assert db.get(PatentPriorArtJob, row.id) is None
    assert crash_result_key not in store.objects
    assert crash_report_key not in store.objects


def test_parse_file_rejects_spoofed_or_mismatched_uploads(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common = {
        "workspace": _scope("workspace-1"),
        "user": _scope("user-1"),
    }
    invalid = (
        ("empty.pdf", "application/pdf", b""),
        ("notes.txt", "text/plain", b"plain text"),
        ("spoofed.pdf", "application/pdf", b"not a pdf"),
        ("wrong.pdf", "application/zip", b"%PDF-1.7\n"),
    )
    for filename, mime_type, content in invalid:
        with pytest.raises(HTTPException) as exc_info:
            service.parse_file(
                db,
                filename=filename,
                mime_type=mime_type,
                content=content,
                **common,
            )
        assert exc_info.value.status_code in {413, 422}

    captured: dict[str, object] = {}

    def fake_extract_document(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(normalized_text="[p.1] 차량 열관리 발명 설명")

    monkeypatch.setattr(service, "extract_document", fake_extract_document)
    parsed = service.parse_file(
        db,
        filename="invention.pdf",
        mime_type="application/pdf",
        content=b"%PDF-1.7\nbody",
        **common,
    )
    assert parsed.extracted_text == "[p.1] 차량 열관리 발명 설명"
    assert captured["mime_type"] == "application/pdf"


def test_office_upload_requires_extension_specific_package_marker(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("word/document.xml", "<document />")

    monkeypatch.setattr(
        service,
        "extract_document",
        lambda **_kwargs: SimpleNamespace(normalized_text="문서에서 추출된 발명 설명"),
    )
    parsed = service.parse_file(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        filename="invention.docx",
        mime_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        content=archive_bytes.getvalue(),
    )
    assert parsed.mime_type.endswith("wordprocessingml.document")

    with pytest.raises(HTTPException) as mismatch:
        service.parse_file(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            filename="invention.xlsx",
            mime_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            content=archive_bytes.getvalue(),
        )
    assert mismatch.value.detail.code == "patent_prior_art.invalid_file_type"


def test_pptx_upload_is_accepted_and_reaches_bounded_extraction(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation />")

    monkeypatch.setattr(
        service,
        "extract_document",
        lambda **_kwargs: SimpleNamespace(normalized_text="발표자료에서 추출된 발명 설명"),
    )
    parsed = service.parse_file(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        filename="invention.pptx",
        mime_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        content=archive_bytes.getvalue(),
    )

    assert parsed.mime_type.endswith("presentationml.presentation")
    assert parsed.extracted_text == "발표자료에서 추출된 발명 설명"


def test_pptx_upload_requires_presentation_package_marker(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("word/document.xml", "<document />")

    monkeypatch.setattr(
        service,
        "extract_document",
        lambda **_kwargs: pytest.fail("mislabelled package must not reach extraction"),
    )
    with pytest.raises(HTTPException) as exc_info:
        service.parse_file(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            filename="invention.pptx",
            mime_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            content=archive_bytes.getvalue(),
        )

    assert exc_info.value.detail.code == "patent_prior_art.invalid_file_type"


def test_config_reports_visual_extraction_disabled() -> None:
    # Visual/OCR extraction is not part of this delivery: the parse-file contract
    # accepts only `file` (no per-call `visual` input), so the retained contract
    # response field is always reported False.
    assert service.config().visual_extraction_available is False


def test_parse_file_counts_embedded_media_objects(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation />")
        archive.writestr("ppt/media/image1.png", b"\x89PNG\r\n")
        archive.writestr("ppt/media/image2.png", b"\x89PNG\r\n")

    monkeypatch.setattr(
        service,
        "extract_document",
        lambda **_kwargs: SimpleNamespace(normalized_text="짧은 텍스트 상자 본문"),
    )

    parsed = service.parse_file(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        filename="invention.pptx",
        mime_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        content=archive_bytes.getvalue(),
    )

    assert parsed.extracted_text == "짧은 텍스트 상자 본문"
    assert parsed.embedded_object_count == 2


def test_office_archive_limits_bound_entries_members_expansion_and_encryption() -> None:
    def info(
        name: str,
        *,
        compressed: int,
        uncompressed: int,
        encrypted: bool = False,
    ) -> zipfile.ZipInfo:
        item = zipfile.ZipInfo(name)
        item.compress_size = compressed
        item.file_size = uncompressed
        item.flag_bits = 0x1 if encrypted else 0
        return item

    safe = [info("word/document.xml", compressed=1_000, uncompressed=10_000)]
    assert not service._office_archive_exceeds_limits(safe)
    assert service._office_archive_exceeds_limits(
        [info("word/document.xml", compressed=1_000, uncompressed=10_000, encrypted=True)]
    )
    assert service._office_archive_exceeds_limits(
        [info(f"word/item-{index}.xml", compressed=1, uncompressed=1) for index in range(1001)]
    )
    assert service._office_archive_exceeds_limits(
        [info("word/document.xml", compressed=1_000_000, uncompressed=(25 * 1024 * 1024) + 1)]
    )
    assert service._office_archive_exceeds_limits(
        [
            info(f"word/item-{index}.xml", compressed=1024 * 1024, uncompressed=24 * 1024 * 1024)
            for index in range(6)
        ]
    )
    assert service._office_archive_exceeds_limits(
        [info("word/document.xml", compressed=1, uncompressed=1_000)]
    )


def test_office_upload_rejects_high_expansion_archive_before_extraction(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(
        archive_bytes,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("word/document.xml", b"0" * (1024 * 1024))

    monkeypatch.setattr(
        service,
        "extract_document",
        lambda **_kwargs: pytest.fail("unsafe package must not reach extraction"),
    )
    with pytest.raises(HTTPException) as exc_info:
        service.parse_file(
            db,
            workspace=_scope("workspace-1"),
            user=_scope("user-1"),
            filename="invention.docx",
            mime_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            content=archive_bytes.getvalue(),
        )
    assert exc_info.value.detail.code == "patent_prior_art.invalid_file_type"


def test_router_upload_reader_counts_chunks_even_without_trusted_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ChunkUpload:
        def __init__(self) -> None:
            self.chunks = iter((b"123", b"45", b""))

        async def read(self, _size: int) -> bytes:
            return next(self.chunks)

    monkeypatch.setattr(router, "_MAX_UPLOAD_BYTES", 4)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router._read_upload(ChunkUpload()))  # type: ignore[arg-type]
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail.code == "patent_prior_art.request_too_large"


def test_json_body_cap_accepts_advertised_korean_limit_and_rejects_cap_plus_one() -> None:
    maximum_request = _request().model_copy(update={"invention_text": "가" * 200_000})
    encoded = json.dumps(
        maximum_request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(encoded) > 512 * 1024
    assert len(encoded) < router._MAX_JSON_BODY_BYTES

    assert (
        router._content_length_is_invalid_or_exceeds(str(len(encoded)), router._MAX_JSON_BODY_BYTES)
        is False
    )
    assert (
        router._content_length_is_invalid_or_exceeds(
            str(router._MAX_JSON_BODY_BYTES + 1), router._MAX_JSON_BODY_BYTES
        )
        is True
    )


def test_parse_route_offloads_document_extraction_from_event_loop(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Upload:
        filename = "invention.pdf"
        content_type = "application/pdf"

        def __init__(self) -> None:
            self.chunks = iter((b"%PDF-1.7\n", b""))
            self.closed = False

        async def read(self, _size: int) -> bytes:
            return next(self.chunks)

        async def close(self) -> None:
            self.closed = True

    expected = PatentPriorArtFileParseResponse(
        filename="invention.pdf",
        mime_type="application/pdf",
        extracted_text="발명 설명",
        character_count=5,
    )
    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_run_in_threadpool(function, *args, **kwargs):
        calls.append((function, args, kwargs))
        return expected

    monkeypatch.setattr(router, "run_in_threadpool", fake_run_in_threadpool)
    upload = Upload()
    result = asyncio.run(
        router.parse_file(
            file=upload,  # type: ignore[arg-type]
            db=db,
            current_user=_scope("user-1"),  # type: ignore[arg-type]
            workspace=_scope("workspace-1"),  # type: ignore[arg-type]
        )
    )

    assert result is expected
    assert calls[0][0] is service.parse_file
    assert calls[0][2]["content"] == b"%PDF-1.7\n"
    assert upload.closed is True


def test_preview_passes_vehicle_category_as_plain_planning_context(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_preview(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setitem(
        sys.modules,
        "open_alm_api.domains.patent_prior_art.pipeline",
        SimpleNamespace(preview_patent_prior_art_search=fake_preview),
    )
    request = PatentPriorArtQueryPreviewRequest(
        invention_text="차량 열관리 장치에 대한 충분히 긴 선행기술 조사 입력 설명입니다.",
        category_ids=["vehicle"],
        jurisdictions=["kr"],
    )

    output = service.preview_query(
        db,
        workspace=_scope("workspace-1"),
        user=_scope("user-1"),
        request=request,
    )

    assert isinstance(output, SimpleNamespace)
    assert captured["category_ids"] == ["vehicle"]
    assert captured["jurisdictions"] == ["KR"]
    assert captured["explicit_applicants"] == ()
