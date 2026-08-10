from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from dev_accounts import dev_login

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.docs import access_grants
from open_alm_api.domains.docs.access_grants import (
    bump_doc_grant_expiry_for_meeting,
    revoke_doc_grants_for_meeting_attendee,
)
from open_alm_api.domains.docs.models import DocMeetingAccess, NativeDoc
from open_alm_api.domains.meeting.models import Meeting


def test_revoke_doc_grants_for_meeting_attendee_updates_active_grants_and_enqueues(
    client: TestClient,
    monkeypatch,
) -> None:
    context = _create_docs_meeting_access_context(client)
    enqueued_doc_ids: list[str] = []
    monkeypatch.setattr(
        access_grants,
        "enqueue_doc_search_index_by_id",
        lambda db, *, doc_id, operation: enqueued_doc_ids.append(doc_id),
    )

    with get_session_factory()() as db:
        count = revoke_doc_grants_for_meeting_attendee(
            db,
            meeting_id=context["meeting_id"],
            user_id=context["recipient_id"],
            revoked_by_user_id=context["owner_id"],
            reason="attendee_removed",
        )
        db.commit()

        revoked_grants = list(
            db.scalars(
                select(DocMeetingAccess).where(
                    DocMeetingAccess.granted_by_meeting_id == context["meeting_id"],
                    DocMeetingAccess.user_id == context["recipient_id"],
                )
            )
        )

    assert count == 2
    assert sorted(enqueued_doc_ids) == sorted(context["doc_ids"])
    assert all(grant.revoked_at is not None for grant in revoked_grants)
    assert {grant.revoke_reason for grant in revoked_grants} == {"attendee_removed"}


def test_bump_doc_grant_expiry_for_meeting_ignores_revoked_grants(
    client: TestClient,
    monkeypatch,
) -> None:
    context = _create_docs_meeting_access_context(client, include_revoked=True)
    enqueued_doc_ids: list[str] = []
    monkeypatch.setattr(
        access_grants,
        "enqueue_doc_search_index_by_id",
        lambda db, *, doc_id, operation: enqueued_doc_ids.append(doc_id),
    )
    new_end_at = datetime(2026, 5, 20, 9, 0, tzinfo=UTC).replace(tzinfo=None)

    with get_session_factory()() as db:
        count = bump_doc_grant_expiry_for_meeting(
            db,
            meeting_id=context["meeting_id"],
            new_end_at=new_end_at,
        )
        db.commit()

        grants = list(
            db.scalars(
                select(DocMeetingAccess).where(
                    DocMeetingAccess.granted_by_meeting_id == context["meeting_id"],
                )
            )
        )

    active_grants = [grant for grant in grants if grant.revoked_at is None]
    revoked_grants = [grant for grant in grants if grant.revoked_at is not None]
    assert count == 2
    assert sorted(enqueued_doc_ids) == sorted(context["doc_ids"])
    assert {grant.expires_at for grant in active_grants} == {new_end_at + timedelta(days=7)}
    assert {grant.expires_at for grant in revoked_grants} == {None}


def _create_docs_meeting_access_context(
    client: TestClient,
    *,
    include_revoked: bool = False,
) -> dict[str, object]:
    dev_login(client, "delivery-hub-admin")
    dev_login(client, "delivery-hub-member")

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        owner = db.scalar(select(User).where(User.email == "delivery-hub-admin@open-alm.local"))
        recipient = db.scalar(select(User).where(User.email == "delivery-hub-member@open-alm.local"))
        assert workspace is not None
        assert owner is not None
        assert recipient is not None

        meeting = Meeting(
            id=new_id(),
            workspace_id=workspace.id,
            organizer_id=owner.id,
            title="Docs access grant refactor",
            agenda="",
            start_at=datetime(2026, 5, 20, 1, 0),
            end_at=datetime(2026, 5, 20, 2, 0),
        )
        docs = [
            NativeDoc(
                id=new_id(),
                workspace_id=workspace.id,
                owner_id=owner.id,
                title=f"Grant doc {index}",
                source_kind="grant_refactor",
            )
            for index in range(2)
        ]
        grants = [
            DocMeetingAccess(
                id=new_id(),
                doc_id=doc.id,
                user_id=recipient.id,
                granted_by_user_id=owner.id,
                granted_by_meeting_id=meeting.id,
                access_level="read",
                reason="meeting_attendee",
            )
            for doc in docs
        ]
        if include_revoked:
            revoked_doc = NativeDoc(
                id=new_id(),
                workspace_id=workspace.id,
                owner_id=owner.id,
                title="Revoked grant doc",
                source_kind="grant_refactor",
            )
            docs.append(revoked_doc)
            grants.append(
                DocMeetingAccess(
                    id=new_id(),
                    doc_id=revoked_doc.id,
                    user_id=recipient.id,
                    granted_by_user_id=owner.id,
                    granted_by_meeting_id=meeting.id,
                    access_level="read",
                    reason="meeting_attendee",
                    revoked_at=datetime(2026, 5, 20, 3, 0),
                    revoked_by_user_id=owner.id,
                    revoke_reason="already_revoked",
                )
            )

        db.add_all([meeting, *docs, *grants])
        db.commit()
        return {
            "meeting_id": meeting.id,
            "owner_id": owner.id,
            "recipient_id": recipient.id,
            "doc_ids": [doc.id for doc in docs[:2]],
        }
