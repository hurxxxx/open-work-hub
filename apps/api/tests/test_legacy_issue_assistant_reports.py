from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from dev_accounts import auth_headers, create_workspace_user_session, dev_login

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.ai_artifacts.contracts import (
    AiArtifactCreate,
    AiArtifactQueryCreate,
    AiArtifactSourceCreate,
)
from open_alm_api.domains.ai_artifacts.models import AiArtifact
from open_alm_api.domains.ai_artifacts.repository import AiArtifactRepository
from open_alm_api.domains.auth.models import AuditLog, User, Workspace
from open_alm_api.domains.conversations.models import Conversation, ConversationTurn
from open_alm_api.domains.legacy_issues.app_catalog import (
    LEGACY_ISSUES_WORKSPACE_APP,
)


REPORT_TITLE = "과거차 문제점 근거 기반 보고서"


def test_report_management_navigation_uses_canonical_route() -> None:
    report_nav = next(
        item
        for item in LEGACY_ISSUES_WORKSPACE_APP.nav_items
        if item.id == "legacy-issues-assistant-history"
    )

    assert report_nav.title == "보고서 관리"
    assert report_nav.path_suffix == "/reports"


def _report_artifacts(
    report_id: str,
    *,
    content: str,
    document_status: str = "closed",
) -> list[dict[str, str]]:
    return [
        {
            "id": report_id,
            "type": "document",
            "title": REPORT_TITLE,
            "language": "markdown",
            "content": content,
            "status": document_status,
        },
        {
            "id": f"{report_id}-analysis",
            "type": "legacy-issue-analysis",
            "title": "과거차 문제점 정형 분석",
            "content": '{"version": 1}',
            "status": "closed",
        },
    ]


def _add_conversation_turns(
    *,
    conversation_id: str,
    workspace_id: str,
    user_id: str,
    title: str,
    question: str,
    assistant_meta: dict,
    created_at: datetime,
    deleted_at: datetime | None = None,
    scope_ref: str = "legacy_issues",
    scope_resource_id: str = "workspace",
    include_question_snapshot: bool = True,
) -> None:
    with get_session_factory()() as db:
        assistant_turn_id = f"{conversation_id}-assistant"
        conversation = Conversation(
            id=conversation_id,
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            scope_ref=scope_ref,
            scope_resource_id=scope_resource_id,
            created_at=created_at,
            updated_at=created_at,
            deleted_at=deleted_at,
        )
        db.add(conversation)
        db.add_all(
            [
                ConversationTurn(
                    id=f"{conversation_id}-user",
                    conversation_id=conversation_id,
                    seq=1,
                    role="user",
                    content=question,
                    created_at=created_at,
                ),
                ConversationTurn(
                    id=assistant_turn_id,
                    conversation_id=conversation_id,
                    seq=2,
                    role="assistant",
                    content="보고서를 생성했습니다.",
                    meta=assistant_meta,
                    created_at=created_at + timedelta(seconds=1),
                ),
            ]
        )
        db.flush()
        is_completed_report = (
            assistant_meta.get("policy") == "scope_direct_response"
            and assistant_meta.get("decision_reason") == "scope_direct_response"
            and assistant_meta.get("finish_reason") == "stop"
            and assistant_meta.get("response_status") == "done"
        )
        if is_completed_report:
            for artifact in assistant_meta.get("artifacts") or []:
                if (
                    artifact.get("type") != "document"
                    or artifact.get("status") != "closed"
                    or not artifact.get("content")
                ):
                    continue
                report_id = str(artifact["id"])
                sequence = int(
                    hashlib.sha256(report_id.encode("utf-8")).hexdigest()[:8],
                    16,
                )
                db.add(
                    AiArtifact(
                        id=report_id,
                        artifact_number=f"AIR-20260725-{sequence:010d}",
                        workspace_id=workspace_id,
                        owner_user_id=user_id,
                        graph_run_id=None,
                        conversation_id=conversation_id,
                        conversation_turn_id=assistant_turn_id,
                        app_id="legacy-issues",
                        artifact_type="report",
                        title=artifact["title"],
                        content_type="text/markdown",
                        content_text=artifact["content"],
                        payload_json=(
                            {
                                "schema_version": 1,
                                "request": {
                                    "kind": "user_question",
                                    "text": question,
                                },
                            }
                            if include_question_snapshot
                            else None
                        ),
                        schema_version=1,
                        content_sha256="a" * 64,
                        content_size_bytes=len(
                            str(artifact["content"]).encode("utf-8")
                        ),
                        visibility="private",
                        status="completed",
                        completed_at=created_at + timedelta(seconds=1),
                        created_at=created_at + timedelta(seconds=1),
                    )
                )
        db.commit()


def _successful_report_meta(report_id: str, *, content: str) -> dict:
    return {
        "policy": "scope_direct_response",
        "decision_reason": "scope_direct_response",
        "finish_reason": "stop",
        "response_status": "done",
        "artifacts": _report_artifacts(report_id, content=content),
    }


def _add_standalone_report(
    *,
    workspace_id: str,
    owner_user_id: str,
    question: str,
    title: str = REPORT_TITLE,
) -> tuple[str, str, str]:
    with get_session_factory()() as db:
        artifact = AiArtifactRepository(db).create_completed(
            AiArtifactCreate(
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
                app_id="legacy-issues",
                artifact_type="report",
                title=title,
                content_text="# 독립 보고서\n\n저장된 결과를 기반으로 작성했습니다.",
                payload={
                    "request": {
                        "kind": "user_question",
                        "text": question,
                    }
                },
            ),
            queries=(
                AiArtifactQueryCreate(
                    query_kind="sql",
                    title="차종별 발생 건수",
                    family_id="issues.by_vehicle",
                    query_spec={"group_by": ["vehicle_model"]},
                    statement_text=(
                        "SELECT vehicle_model, COUNT(*) AS issue_count "
                        "FROM legacy_issue_records "
                        "WHERE vehicle_model = :vehicle_model GROUP BY vehicle_model"
                    ),
                    typed_params={
                        "vehicle_model": {
                            "type": "string",
                            "value": "EV-A",
                        }
                    },
                    execution_status="completed",
                    result_schema=[
                        {"key": "vehicle_model", "label": "차종", "type": "text"},
                        {"key": "issue_count", "label": "발생 건수", "type": "number"},
                    ],
                    result_rows=[
                        {"vehicle_model": "EV-A", "issue_count": 7},
                        {"vehicle_model": "EV-B", "issue_count": 4},
                    ],
                    row_count=3,
                    duration_ms=18,
                    truncated=True,
                    payload_bytes=96,
                    exactness="exact",
                ),
            ),
            sources=(
                AiArtifactSourceCreate(
                    source_kind="vehicle_checklist",
                    source_ref="checklist:ev-a",
                    title="EV-A 차종별 체크리스트",
                    locator={"datasetKey": "vehicle-module-checklist"},
                    metadata={"matchMethod": "semantic"},
                    grid_columns=[
                        {"key": "module", "label": "모듈"},
                        {"key": "result", "label": "결과"},
                    ],
                    grid_rows=[{"module": "배터리", "result": "점검 필요"}],
                    row_count=1,
                ),
                AiArtifactSourceCreate(
                    source_kind="sql_query",
                    source_ref="query:legacy-synthetic-projection",
                    title="이전 호환 SQL 투영",
                    grid_rows=[{"vehicle_model": "EV-A", "issue_count": 7}],
                    row_count=1,
                ),
            ),
        )
        query_id = artifact.queries[0].id
        db.commit()
        return artifact.id, artifact.artifact_number, query_id


def test_list_assistant_reports_returns_only_current_users_successful_report_artifacts(
    client: TestClient,
) -> None:
    current = dev_login(client, "administrator")
    workspace_slug = current["user"]["workspaces"][0]["slug"]
    other_user = create_workspace_user_session(
        client,
        workspace_key=workspace_slug,
        login_id="legacyreportpeer",
        email="legacy-report-peer@open-alm.local",
        full_name="Legacy Report Peer",
    )
    created_at = datetime(2026, 7, 25, 10, 0, 0)
    long_report = "# 보고서\n\n" + "모터 과열 원인 분석 " * 30

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        current_user = db.get(User, current["user"]["id"])
        peer_user = db.get(User, other_user["user"]["id"])
        assert workspace is not None
        assert current_user is not None
        assert peer_user is not None
        workspace_id = workspace.id
        current_user_id = current_user.id
        peer_user_id = peer_user.id

    _add_conversation_turns(
        conversation_id="report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="모터 과열 보고서",
        question="모터 과열 문제를 경영진 보고서로 작성해줘",
        assistant_meta=_successful_report_meta("report-artifact", content=long_report),
        created_at=created_at,
        include_question_snapshot=False,
    )
    _add_conversation_turns(
        conversation_id="peer-report-conv",
        workspace_id=workspace_id,
        user_id=peer_user_id,
        title="다른 사용자의 보고서",
        question="다른 사용자의 질문",
        assistant_meta=_successful_report_meta("peer-report-artifact", content="비공개"),
        created_at=created_at + timedelta(minutes=1),
    )
    _add_conversation_turns(
        conversation_id="ordinary-doc-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="일반 문서",
        question="일반 분석 문서를 작성해줘",
        assistant_meta={
            **_successful_report_meta("ordinary-document", content="일반 문서"),
            "decision_reason": "policy_local_only",
        },
        created_at=created_at + timedelta(minutes=2),
    )
    _add_conversation_turns(
        conversation_id="cancelled-report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="취소된 보고서",
        question="취소된 보고서 질문",
        assistant_meta={
            **_successful_report_meta("cancelled-report", content="부분 보고서"),
            "finish_reason": "cancelled",
            "response_status": "cancelled",
        },
        created_at=created_at + timedelta(minutes=3),
    )
    _add_conversation_turns(
        conversation_id="deleted-report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="삭제된 보고서",
        question="삭제된 보고서 질문",
        assistant_meta=_successful_report_meta("deleted-report", content="삭제됨"),
        created_at=created_at + timedelta(minutes=4),
        deleted_at=created_at + timedelta(minutes=5),
    )
    _add_conversation_turns(
        conversation_id="wrong-scope-report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="다른 범위 보고서",
        question="다른 범위 질문",
        assistant_meta=_successful_report_meta("wrong-scope-report", content="다른 범위"),
        created_at=created_at + timedelta(minutes=6),
        scope_ref="meeting",
        scope_resource_id="meeting-1",
    )
    open_report_meta = _successful_report_meta("open-report", content="작성 중")
    open_report_meta["artifacts"][0]["status"] = "open"
    _add_conversation_turns(
        conversation_id="open-report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="작성 중인 보고서",
        question="작성 중인 보고서 질문",
        assistant_meta=open_report_meta,
        created_at=created_at + timedelta(minutes=7),
    )
    report_without_analysis = _successful_report_meta(
        "report-without-analysis",
        content="의미검색 근거 기반 보고서",
    )
    report_without_analysis["artifacts"] = report_without_analysis["artifacts"][:1]
    _add_conversation_turns(
        conversation_id="no-analysis-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="의미검색 보고서",
        question="의미검색 결과를 보고서로 만들어줘",
        assistant_meta=report_without_analysis,
        created_at=created_at + timedelta(minutes=8),
    )
    wrong_title_meta = _successful_report_meta("wrong-title-report", content="다른 제목")
    wrong_title_meta["artifacts"][0]["title"] = "일반 분석 문서"
    _add_conversation_turns(
        conversation_id="wrong-title-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="다른 제목 보고서",
        question="다른 제목 보고서 질문",
        assistant_meta=wrong_title_meta,
        created_at=created_at + timedelta(minutes=9),
    )

    response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/legacy-issues/assistant/reports",
        headers=auth_headers(current["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 5
    assert payload["limit"] == 30
    assert payload["offset"] == 0
    assert [item["report_id"] for item in payload["items"]] == [
        "wrong-title-report",
        "report-without-analysis",
        "wrong-scope-report",
        "deleted-report",
        "report-artifact",
    ]
    assert payload["items"][1] == {
        "report_id": "report-without-analysis",
        "conversation_id": "no-analysis-conv",
        "turn_id": "no-analysis-conv-assistant",
        "conversation_title": "의미검색 보고서",
        "question": "의미검색 결과를 보고서로 만들어줘",
        "title": REPORT_TITLE,
        "preview": "의미검색 근거 기반 보고서",
        "created_at": "2026-07-25T10:08:01",
    }
    assert payload["items"][0]["title"] == "일반 분석 문서"
    assert "\n" not in payload["items"][4]["preview"]
    assert payload["items"][4]["preview"].startswith("# 보고서 모터 과열 원인 분석")
    assert len(payload["items"][4]["preview"]) == 220
    assert payload["items"][4]["preview"].endswith("...")


def test_list_assistant_reports_paginates_artifacts_in_stable_newest_first_order(
    client: TestClient,
) -> None:
    current = dev_login(client, "administrator")
    workspace_slug = current["user"]["workspaces"][0]["slug"]

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        current_user = db.get(User, current["user"]["id"])
        assert workspace is not None
        assert current_user is not None
        workspace_id = workspace.id
        current_user_id = current_user.id

    created_at = datetime(2026, 7, 25, 11, 0, 0)
    _add_conversation_turns(
        conversation_id="older-report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="이전 보고서",
        question="이전 보고서를 작성해줘",
        assistant_meta=_successful_report_meta("older-report", content="이전 내용"),
        created_at=created_at,
    )
    newest_meta = _successful_report_meta("newer-report-a", content="최신 내용 A")
    newest_meta["artifacts"].insert(
        1,
        {
            "id": "newer-report-b",
            "type": "document",
            "title": REPORT_TITLE,
            "language": "markdown",
            "content": "최신 내용 B",
            "status": "closed",
        },
    )
    _add_conversation_turns(
        conversation_id="newer-report-conv",
        workspace_id=workspace_id,
        user_id=current_user_id,
        title="최신 보고서",
        question="최신 보고서를 작성해줘",
        assistant_meta=newest_meta,
        created_at=created_at + timedelta(minutes=1),
    )

    response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/legacy-issues/assistant/reports",
        params={"limit": 2, "offset": 1},
        headers=auth_headers(current["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [item["report_id"] for item in payload["items"]] == [
        "newer-report-b",
        "older-report",
    ]


def test_report_management_preserves_snapshots_and_enforces_share_acl(
    client: TestClient,
) -> None:
    owner_session = dev_login(client, "administrator")
    workspace_slug = owner_session["user"]["workspaces"][0]["slug"]
    peer_session = create_workspace_user_session(
        client,
        workspace_key=workspace_slug,
        login_id="reportmanagementpeer",
        email="report-management-peer@open-alm.local",
        full_name="Report Management Peer",
    )
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        workspace_id = workspace.id
        other_workspace = db.scalar(
            select(Workspace).where(Workspace.id != workspace_id).limit(1)
        )
        assert other_workspace is not None
        other_workspace_id = other_workspace.id

    question = "EV-A와 EV-B의 문제 발생 건수를 비교해줘"
    report_id, report_number, query_id = _add_standalone_report(
        workspace_id=workspace_id,
        owner_user_id=owner_session["user"]["id"],
        question=question,
    )
    _add_standalone_report(
        workspace_id=workspace_id,
        owner_user_id=peer_session["user"]["id"],
        question="다른 사용자의 비공개 질문",
    )
    _, cross_workspace_report_number, _ = _add_standalone_report(
        workspace_id=other_workspace_id,
        owner_user_id=owner_session["user"]["id"],
        question="다른 워크스페이스 질문",
    )
    _add_conversation_turns(
        conversation_id="peer-lineage-conv",
        workspace_id=workspace_id,
        user_id=peer_session["user"]["id"],
        title="공유 계보 보고서",
        question="원본 대화 계보를 포함한 보고서를 작성해줘",
        assistant_meta=_successful_report_meta(
            "peer-lineage-report",
            content="공유 계보 내용",
        ),
        created_at=datetime(2026, 7, 25, 12, 0, 0),
    )
    with get_session_factory()() as db:
        peer_lineage_report = db.get(AiArtifact, "peer-lineage-report")
        assert peer_lineage_report is not None
        peer_lineage_report_number = peer_lineage_report.artifact_number
    base_url = f"/api/v1/workspaces/{workspace_slug}/legacy-issues/reports"
    owner_headers = auth_headers(owner_session["token"])
    peer_headers = auth_headers(peer_session["token"])

    mine = client.get(base_url, headers=owner_headers)
    assert mine.status_code == 200, mine.text
    mine_payload = mine.json()
    assert mine_payload["total"] == 1
    assert mine_payload["items"][0] == {
        "report_id": report_id,
        "report_number": report_number,
        "title": REPORT_TITLE,
        "question": question,
        "preview": "# 독립 보고서 저장된 결과를 기반으로 작성했습니다.",
        "completed_at": mine_payload["items"][0]["completed_at"],
        "owner_user_id": owner_session["user"]["id"],
        "owner_name": owner_session["user"]["display_name"],
        "visibility": "private",
        "query_count": 1,
        "source_count": 1,
    }
    assert client.get(
        base_url,
        params={"view": "shared"},
        headers=peer_headers,
    ).json()["total"] == 0
    assert (
        client.get(f"{base_url}/{report_number}", headers=peer_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"{base_url}/{cross_workspace_report_number}",
            headers=owner_headers,
        ).status_code
        == 404
    )

    shared = client.put(
        f"{base_url}/{report_number}/workspace-share",
        headers=owner_headers,
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["visibility"] == "workspace"
    assert shared.json()["report_number"] == report_number
    repeated_share = client.put(
        f"{base_url}/{report_number}/workspace-share",
        headers=owner_headers,
    )
    assert repeated_share.status_code == 200, repeated_share.text

    shared_list = client.get(
        base_url,
        params={"view": "shared"},
        headers=peer_headers,
    )
    assert shared_list.status_code == 200, shared_list.text
    assert shared_list.json()["total"] == 1
    assert shared_list.json()["items"][0]["report_number"] == report_number
    detail = client.get(f"{base_url}/{report_number}", headers=peer_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["question"] == question
    assert detail.json()["conversation_id"] is None
    assert detail.json()["query_count"] == 1
    assert detail.json()["source_count"] == 1

    queries = client.get(
        f"{base_url}/{report_number}/queries",
        headers=peer_headers,
    )
    assert queries.status_code == 200, queries.text
    query = queries.json()["items"][0]
    assert query["id"] == query_id
    assert query["family_id"] == "issues.by_vehicle"
    assert query["typed_params"]["vehicle_model"]["value"] == "EV-A"
    assert query["row_count"] == 3
    assert query["truncated"] is True
    assert "result_rows" not in query
    assert "result_schema" not in query

    rows = client.get(
        f"{base_url}/{report_number}/queries/{query_id}/rows",
        params={"limit": 1, "offset": 1},
        headers=peer_headers,
    )
    assert rows.status_code == 200, rows.text
    assert rows.json() == {
        "query_id": query_id,
        "columns": [
            {"key": "vehicle_model", "label": "차종", "type": "text"},
            {"key": "issue_count", "label": "발생 건수", "type": "number"},
        ],
        "rows": [{"vehicle_model": "EV-B", "issue_count": 4}],
        "row_count": 3,
        "captured_row_count": 2,
        "truncated": True,
        "limit": 1,
        "offset": 1,
        "total": 2,
    }
    sources = client.get(
        f"{base_url}/{report_number}/sources",
        headers=peer_headers,
    )
    assert sources.status_code == 200, sources.text
    assert len(sources.json()["items"]) == 1
    assert sources.json()["items"][0]["source_kind"] == "vehicle_checklist"
    assert all(
        source["source_kind"] != "sql_query"
        for source in sources.json()["items"]
    )

    assert (
        client.put(
            f"{base_url}/{report_number}/workspace-share",
            headers=peer_headers,
        ).status_code
        == 404
    )
    owner_lineage = client.get(
        f"{base_url}/{peer_lineage_report_number}",
        headers=peer_headers,
    )
    assert owner_lineage.status_code == 200, owner_lineage.text
    assert owner_lineage.json()["conversation_id"] == "peer-lineage-conv"
    assert owner_lineage.json()["conversation_turn_id"] == (
        "peer-lineage-conv-assistant"
    )
    peer_share = client.put(
        f"{base_url}/{peer_lineage_report_number}/workspace-share",
        headers=peer_headers,
    )
    assert peer_share.status_code == 200, peer_share.text
    shared_lineage = client.get(
        f"{base_url}/{peer_lineage_report_number}",
        headers=owner_headers,
    )
    assert shared_lineage.status_code == 200, shared_lineage.text
    assert shared_lineage.json()["conversation_id"] is None
    assert shared_lineage.json()["conversation_turn_id"] is None

    unshared = client.delete(
        f"{base_url}/{report_number}/workspace-share",
        headers=owner_headers,
    )
    assert unshared.status_code == 200, unshared.text
    assert unshared.json()["visibility"] == "private"
    assert (
        client.get(f"{base_url}/{report_number}", headers=peer_headers).status_code
        == 404
    )

    with get_session_factory()() as db:
        actions = list(
            db.scalars(
                select(AuditLog.action)
                .where(AuditLog.entity_id == report_id)
                .order_by(AuditLog.created_at)
            )
        )
    assert actions == [
        "legacy_issues.report.share",
        "legacy_issues.report.unshare",
    ]
