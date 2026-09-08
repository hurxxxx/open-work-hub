from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.models import AuthSession, utcnow_naive
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.community.models import (
    CommunityChannel,
    CommunityComment,
    CommunityPost,
)
from open_work_hub_api.domains.community.service import DEFAULT_CHANNEL_KEY, ensure_default_channels
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.pms.models import Attachment, Task, TaskList
from open_work_hub_api.domains.usage.models import UsageEvent, UsageExcludedUser
from open_work_hub_api.domains.usage.service import (
    USAGE_EVENT_APP_OPEN,
    USAGE_EVENT_CONTENT_VIEW,
    USAGE_EVENT_SEARCH_QUERY,
    record_usage_event,
)
from open_work_hub_api.domains.whiteboard.models import Whiteboard


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open Work Hub Admin",
            "email": "admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_usage_dashboard_aggregates_user_content_and_llm_usage(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    user_id = admin["user"]["id"]
    _seed_usage_rows(
        user_id=user_id,
    )

    response = client.get(
        "/api/v1/admin/usage/dashboard?days=30&limit=10",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    totals = payload["totals"]
    assert totals["active_user_count"] >= 1
    assert totals["docs_created_count"] == 1
    assert totals["whiteboards_created_count"] == 1
    assert totals["meetings_created_count"] == 1
    assert totals["pms_tasks_created_count"] == 1
    assert totals["app_open_count"] == 1
    assert totals["content_view_count"] == 3
    assert totals["search_query_count"] == 1
    assert totals["docs_view_count"] == 2
    assert totals["whiteboards_view_count"] == 1
    assert totals["llm_call_count"] == 1
    assert totals["llm_success_count"] == 1
    assert totals["llm_total_tokens"] == 15
    assert totals["today_visitor_count"] >= 1

    user_item = next(item for item in payload["users"] if item["user_id"] == user_id)
    assert user_item["docs_owned_count"] == 1
    assert user_item["whiteboards_owned_count"] == 1
    assert user_item["app_open_count"] == 1
    assert user_item["content_view_count"] == 3
    assert user_item["search_query_count"] == 1
    assert user_item["docs_view_count"] == 2
    assert user_item["llm_call_count"] == 1
    assert user_item["llm_total_tokens"] == 15
    assert user_item["activity_score"] >= 11
    assert payload["usage_by_app"][0]["key"] == "docs"
    assert payload["usage_by_route"][0]["key"] == "/apps/docs"
    assert payload["content_views_by_kind"][0]["key"] == "doc"
    assert payload["content_views_by_kind"][0]["count"] == 2
    assert payload["llm_by_task_kind"][0]["key"] == "chatbot"
    assert payload["llm_by_model"][0]["key"] == "local/test-model"
    assert len(payload["daily_trends"]) == 30
    assert payload["daily_trends"][-1]["visitor_count"] >= 1
    assert payload["daily_trends"][-1]["active_user_count"] >= 1
    assert len(payload["hourly_access"]) == 24
    assert "average_visitor_count" in payload["hourly_access"][-1]
    assert payload["token_rankings"][0]["user_id"] == user_id
    assert payload["token_rankings"][0]["llm_total_tokens"] == 15
    assert payload["pms_summary"]["project_count"] >= 1
    assert payload["pms_summary"]["stakeholder_count"] >= 1
    assert payload["pms_summary"]["attachment_count"] == 1
    assert payload["pms_summary"]["attachment_total_bytes"] == 2048
    assert "task_activity_count" in payload["pms_summary"]
    assert payload["ai_team_summary"]["connections"]
    assert payload["ai_team_summary"]["suggestion_count"] == 2
    assert payload["ai_team_summary"]["unanswered_suggestion_count"] == 1


def test_admin_usage_hourly_access_uses_kst_buckets(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    user_id = admin["user"]["id"]
    today_kst = utcnow_naive().replace(tzinfo=UTC).astimezone(ZoneInfo("Asia/Seoul")).date()
    target_date = today_kst - timedelta(days=1)
    occurred_at_utc = datetime.combine(
        target_date,
        time(hour=0, minute=30),
        tzinfo=UTC,
    ).replace(tzinfo=None)

    with get_session_factory()() as db:
        sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)).all()
        assert sessions
        for session in sessions:
            session.created_at = occurred_at_utc
            session.last_seen_at = occurred_at_utc
        db.commit()

    response = client.get(
        (
            "/api/v1/admin/usage/dashboard"
            f"?from_date={target_date.isoformat()}"
            f"&to_date={target_date.isoformat()}"
            "&limit=10"
        ),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    hourly_access = {item["hour"]: item for item in response.json()["hourly_access"]}
    assert hourly_access[9]["login_count"] == 1
    assert hourly_access[9]["visitor_count"] == 1
    assert hourly_access[0]["login_count"] == 0
    assert hourly_access[0]["visitor_count"] == 0


def test_admin_usage_dashboard_defaults_to_one_week(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    response = client.get(
        "/api/v1/admin/usage/dashboard",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["period_days"] == 7
    assert len(payload["daily_trends"]) == 7


def test_admin_usage_dashboard_date_range_uses_kst_day_boundaries(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    user_id = admin["user"]["id"]
    today_kst = utcnow_naive().replace(tzinfo=UTC).astimezone(ZoneInfo("Asia/Seoul")).date()
    target_date = today_kst - timedelta(days=1)
    start_utc = (
        datetime.combine(target_date, time.min, tzinfo=ZoneInfo("Asia/Seoul"))
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    end_utc = (
        datetime.combine(
            target_date + timedelta(days=1),
            time.min,
            tzinfo=ZoneInfo("Asia/Seoul"),
        )
        .astimezone(UTC)
        .replace(tzinfo=None)
    )

    with get_session_factory()() as db:
        for index, occurred_at in enumerate(
            [
                start_utc - timedelta(seconds=1),
                start_utc,
                end_utc - timedelta(seconds=1),
                end_utc,
            ]
        ):
            record_usage_event(
                db,
                actor_user_id=user_id,
                app_id="settings",
                event_type=USAGE_EVENT_APP_OPEN,
                route_path="/admin/usage",
                source=f"usage-range-boundary-{index}",
                occurred_at=occurred_at,
            )
        db.commit()

    response = client.get(
        (
            "/api/v1/admin/usage/dashboard"
            f"?from_date={target_date.isoformat()}"
            f"&to_date={target_date.isoformat()}"
            "&limit=10"
        ),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["period_days"] == 1
    assert payload["from_date"] == target_date.isoformat()
    assert payload["to_date"] == target_date.isoformat()
    assert payload["totals"]["app_open_count"] == 2
    assert len(payload["daily_trends"]) == 1
    assert payload["daily_trends"][0]["date"] == target_date.isoformat()
    assert payload["daily_trends"][0]["active_user_count"] == 1


def test_usage_event_endpoint_dedupes_repeated_events(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    user_id = admin["user"]["id"]

    payload = {
        "app_id": "community",
        "event_type": "app.open",
        "route_path": "/community",
        "source": "shell.nav.community",
        "metadata": {"has_app_route": False},
    }
    first_response = client.post(
        "/api/v1/usage/events",
        headers=_auth_headers(token),
        json=payload,
    )
    second_response = client.post(
        "/api/v1/usage/events",
        headers=_auth_headers(token),
        json=payload,
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    with get_session_factory()() as db:
        rows = db.query(UsageEvent).filter(UsageEvent.actor_user_id == user_id).all()
    assert len(rows) == 1
    assert rows[0].app_id == "community"
    assert rows[0].event_type == "app.open"
    assert rows[0].route_path == "/community"
    assert rows[0].count == 2


def test_admin_usage_excluded_users_are_persisted_and_omitted(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    admin_user_id = admin["user"]["id"]

    created_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "usage-excluded@example.com",
            "full_name": "Usage Excluded",
            "temporary_password": "supersecret123",
        },
    )
    assert created_response.status_code == 201, created_response.text
    excluded_user_id = created_response.json()["user"]["id"]

    replace_response = client.put(
        "/api/v1/admin/usage/excluded-users",
        headers=_auth_headers(token),
        json={"user_ids": [excluded_user_id]},
    )
    assert replace_response.status_code == 200, replace_response.text
    assert [item["user_id"] for item in replace_response.json()] == [excluded_user_id]

    list_response = client.get(
        "/api/v1/admin/usage/excluded-users",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    assert [item["user_id"] for item in list_response.json()] == [excluded_user_id]

    with get_session_factory()() as db:
        record_usage_event(
            db,
            actor_user_id=admin_user_id,
            app_id="settings",
            event_type=USAGE_EVENT_APP_OPEN,
            route_path="/admin/usage",
            source="usage-test.included",
        )
        record_usage_event(
            db,
            actor_user_id=excluded_user_id,
            app_id="settings",
            event_type=USAGE_EVENT_APP_OPEN,
            route_path="/admin/usage/excluded",
            source="usage-test.excluded",
        )
        db.commit()

    dashboard_response = client.get(
        "/api/v1/admin/usage/dashboard?days=30&limit=10",
        headers=_auth_headers(token),
    )
    assert dashboard_response.status_code == 200, dashboard_response.text
    payload = dashboard_response.json()
    assert payload["totals"]["app_open_count"] == 1
    assert {item["key"] for item in payload["usage_by_route"]} == {"/admin/usage"}
    assert excluded_user_id not in {item["user_id"] for item in payload["users"]}


def test_admin_usage_targets_limit_dashboard_scope_and_keep_exclusions(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    included_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "usage-target-included@example.com",
            "full_name": "Usage Target Included",
            "temporary_password": "supersecret123",
        },
    )
    excluded_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "usage-target-excluded@example.com",
            "full_name": "Usage Target Excluded",
            "temporary_password": "supersecret123",
        },
    )
    outside_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "usage-target-outside@example.com",
            "full_name": "Usage Target Outside",
            "temporary_password": "supersecret123",
        },
    )
    activity_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "usage-target-activity@example.com",
            "full_name": "Usage Target Activity",
            "temporary_password": "supersecret123",
        },
    )
    assert included_response.status_code == 201, included_response.text
    assert excluded_response.status_code == 201, excluded_response.text
    assert outside_response.status_code == 201, outside_response.text
    assert activity_response.status_code == 201, activity_response.text
    included_user_id = included_response.json()["user"]["id"]
    excluded_user_id = excluded_response.json()["user"]["id"]
    outside_user_id = outside_response.json()["user"]["id"]
    activity_user_id = activity_response.json()["user"]["id"]

    with get_session_factory()() as db:
        db.add(
            UsageExcludedUser(
                user_id=excluded_user_id,
                created_by_user_id=admin["user"]["id"],
            )
        )
        for user_id, route_path in [
            (included_user_id, "/usage-target/included"),
            (excluded_user_id, "/usage-target/excluded"),
            (outside_user_id, "/usage-target/outside"),
        ]:
            record_usage_event(
                db,
                actor_user_id=user_id,
                app_id="settings",
                event_type=USAGE_EVENT_APP_OPEN,
                route_path=route_path,
                source=f"usage-target.{user_id}",
            )
        task_list_id = new_id()
        db.add(
            TaskList(
                id=task_list_id,
                key=f"activity-{task_list_id[:8]}",
                name="Activity-only list",
                description="",
                created_by_id=activity_user_id,
            )
        )
        db.add(
            Task(
                id=new_id(),
                list_id=task_list_id,
                task_number=1,
                title="Activity-only task",
                description="",
                reporter_id=activity_user_id,
            )
        )
        db.commit()

    replace_response = client.put(
        "/api/v1/admin/usage/targets",
        headers=_auth_headers(token),
        json={"user_ids": [included_user_id, activity_user_id]},
    )
    assert replace_response.status_code == 200, replace_response.text
    target_payload = replace_response.json()
    assert {item["user_id"] for item in target_payload["users"]} == {
        included_user_id,
        activity_user_id,
    }
    assert target_payload["resolved_user_count"] == 2

    dashboard_response = client.get(
        "/api/v1/admin/usage/dashboard?days=30&limit=10",
        headers=_auth_headers(token),
    )
    assert dashboard_response.status_code == 200, dashboard_response.text
    payload = dashboard_response.json()
    assert payload["target_scope"]["configured"] is True
    assert payload["target_scope"]["user_count"] == 2
    assert payload["totals"]["user_count"] == 2
    assert payload["totals"]["app_open_count"] == 1
    assert payload["totals"]["active_user_count"] == 2
    assert {item["user_id"] for item in payload["users"]} == {
        included_user_id,
        activity_user_id,
    }
    assert {item["key"] for item in payload["usage_by_route"]} == {"/usage-target/included"}

    clear_response = client.put(
        "/api/v1/admin/usage/targets",
        headers=_auth_headers(token),
        json={"user_ids": []},
    )
    assert clear_response.status_code == 200, clear_response.text
    assert clear_response.json()["resolved_user_count"] == 0


def test_admin_audit_logs_supports_filters(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    user_id = admin["user"]["id"]

    with get_session_factory()() as db:
        for index in range(3):
            record_audit_log(
                db,
                actor_user_id=user_id,
                action="admin.test.filtered",
                entity_kind="test_entity",
                entity_id=f"usage-test-{index}",
                summary=f"Filtered usage audit event {index}",
                payload={"source": "test", "index": index},
            )
        db.commit()

    response = client.get(
        "/api/v1/admin/audit-logs?action=admin.test.filtered&q=usage-test&limit=2&offset=1",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert payload["next_offset"] is None
    assert len(payload["items"]) == 2
    assert [item["action"] for item in payload["items"]] == [
        "admin.test.filtered",
        "admin.test.filtered",
    ]
    assert payload["items"][0]["payload"]["source"] == "test"


def test_admin_audit_logs_ai_security_query_includes_external_calls(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    user_id = admin["user"]["id"]

    with get_session_factory()() as db:
        record_audit_log(
            db,
            actor_user_id=user_id,
            action="admin.ai_security.rule.create",
            entity_kind="ai_security_rule",
            entity_id="rule-1",
            summary="AI security rule created",
            payload={"source": "test"},
        )
        record_audit_log(
            db,
            actor_user_id=user_id,
            action="ai_external_call",
            entity_kind="ai_external_capability",
            entity_id="external-1",
            summary="source=web_search capability=web_search provider=anthropic status=blocked",
            payload={"status": "blocked", "policy_reason": "pii_detected"},
        )
        record_audit_log(
            db,
            actor_user_id=user_id,
            action="admin.unrelated",
            entity_kind="admin",
            entity_id="unrelated-1",
            summary="Unrelated event",
            payload={"source": "test"},
        )
        db.commit()

    response = client.get(
        "/api/v1/admin/audit-logs?q=ai_security&limit=20",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    actions = [item["action"] for item in response.json()["items"]]
    assert "admin.ai_security.rule.create" in actions
    assert "ai_external_call" in actions
    assert "admin.unrelated" not in actions

    explicit_filter_response = client.get(
        "/api/v1/admin/audit-logs?ai_security_only=true&limit=20",
        headers=_auth_headers(token),
    )

    assert explicit_filter_response.status_code == 200, explicit_filter_response.text
    explicit_actions = [item["action"] for item in explicit_filter_response.json()["items"]]
    assert "admin.ai_security.rule.create" in explicit_actions
    assert "ai_external_call" in explicit_actions
    assert "admin.unrelated" not in explicit_actions


def _seed_usage_rows(
    *,
    user_id: str,
) -> None:
    now = utcnow_naive()
    with get_session_factory()() as db:
        doc_id = new_id()
        task_list_id = new_id()
        task_id = new_id()
        db.add(
            NativeDoc(
                id=doc_id,
                owner_id=user_id,
                title="Usage document",
                doc_type="general",
                source_app="docs",
                source_kind="manual",
                generation_kind="human",
                rag_scope="official",
            )
        )
        db.add(
            Whiteboard(
                id=new_id(),
                owner_id=user_id,
                title="Usage whiteboard",
            )
        )
        db.add(
            Meeting(
                id=new_id(),
                organizer_id=user_id,
                title="Usage meeting",
                agenda="",
                start_at=now,
                end_at=now + timedelta(hours=1),
            )
        )
        db.add(
            TaskList(
                id=task_list_id,
                key=f"usage-{task_list_id[:8]}",
                name="Usage list",
                description="",
                created_by_id=user_id,
            )
        )
        db.add(
            Task(
                id=task_id,
                list_id=task_list_id,
                task_number=1,
                title="Usage task",
                description="",
                reporter_id=user_id,
            )
        )
        db.add(
            Attachment(
                id=new_id(),
                task_id=task_id,
                filename="usage.pdf",
                content_type="application/pdf",
                size_bytes=2048,
                storage_key=f"pms/{task_id}/usage.pdf",
                uploaded_by_id=user_id,
            )
        )
        ensure_default_channels(db)
        suggestions_channel = db.scalar(
            select(CommunityChannel).where(CommunityChannel.key == DEFAULT_CHANNEL_KEY)
        )
        assert suggestions_channel is not None
        answered_post_id = new_id()
        unanswered_post_id = new_id()
        db.add_all(
            [
                CommunityPost(
                    id=answered_post_id,
                    channel_id=suggestions_channel.id,
                    author_id=user_id,
                    title="Answered usage suggestion",
                    body="Please improve usage reports.",
                    created_at=now,
                    updated_at=now,
                ),
                CommunityPost(
                    id=unanswered_post_id,
                    channel_id=suggestions_channel.id,
                    author_id=user_id,
                    title="Unanswered usage suggestion",
                    body="Please add dashboard filters.",
                    created_at=now,
                    updated_at=now,
                ),
                CommunityComment(
                    id=new_id(),
                    post_id=answered_post_id,
                    author_id=user_id,
                    body="Acknowledged.",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        record_usage_event(
            db,
            actor_user_id=user_id,
            app_id="docs",
            event_type=USAGE_EVENT_APP_OPEN,
            route_path="/apps/docs",
            source="shell.nav.docs",
        )
        record_usage_event(
            db,
            actor_user_id=user_id,
            app_id="docs",
            event_type=USAGE_EVENT_CONTENT_VIEW,
            content_kind="doc",
            content_id=doc_id,
            content_title="Usage document",
            source="docs.item.view",
        )
        record_usage_event(
            db,
            actor_user_id=user_id,
            app_id="docs",
            event_type=USAGE_EVENT_CONTENT_VIEW,
            content_kind="doc",
            content_id=doc_id,
            content_title="Usage document",
            source="docs.item.view",
        )
        record_usage_event(
            db,
            actor_user_id=user_id,
            app_id="whiteboard",
            event_type=USAGE_EVENT_CONTENT_VIEW,
            content_kind="whiteboard",
            content_id="whiteboard-usage",
            content_title="Usage whiteboard",
            source="whiteboard.item.view",
        )
        record_usage_event(
            db,
            actor_user_id=user_id,
            app_id="docs",
            event_type=USAGE_EVENT_SEARCH_QUERY,
            content_kind="doc",
            source="docs.search",
            metadata={"query_hash": "usage-test", "query_length": 5},
        )
        record_audit_log(
            db,
            actor_user_id=user_id,
            action="llm_call",
            entity_kind="llm_task",
            entity_id="usage-run",
            summary="llm_call source=test pool=local task_kind=chatbot status=ok",
            payload={
                "actor_user_id": user_id,
                "task_kind": "chatbot",
                "model": "local/test-model",
                "status": "ok",
                "latency_ms": 120,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )
        db.commit()
