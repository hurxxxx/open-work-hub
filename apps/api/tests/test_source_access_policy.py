from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from dev_accounts import dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.pms.space_models import Team, TeamMember
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.models import (
    DocMeetingAccess,
    NativeDoc,
    NativeDocTarget,
    NativeDocUserShare,
)
from open_work_hub_api.domains.meeting.models import Meeting, MeetingAttendee
from open_work_hub_api.domains.pms.models import Task, TaskUserAccess, TaskList
from open_work_hub_api.domains.source_access import SourceAclPolicy
from open_work_hub_api.domains.source_access.resource_types import (
    MEETING_RESOURCE_TYPE,
    NATIVE_DOC_RESOURCE_TYPE,
    PLANNER_EVENT_RESOURCE_TYPE,
    PMS_TASK_RESOURCE_TYPE,
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _user(db, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _new_space(db) -> Team:
    team = Team(id=new_id(), key=new_id(), name="Source ACL space")
    db.add(team)
    db.flush()
    return team


def _ensure_team_member(db, *, team: Team, user: User) -> None:
    existing = db.scalar(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
    )
    if existing is None:
        db.add(TeamMember(id=new_id(), team_id=team.id, user_id=user.id, role="member"))


def test_source_acl_policy_blocks_inactive_resources(client: TestClient) -> None:
    dev_login(client, "delivery-hub-admin")
    dev_login(client, "delivery-hub-member")

    with get_session_factory()() as db:
        admin = _user(db, "delivery-hub-admin@open-work-hub.local")
        member = _user(db, "delivery-hub-member@open-work-hub.local")
        team = _new_space(
            db,
        )
        _ensure_team_member(db, team=team, user=member)

        trashed_doc = NativeDoc(
            id=new_id(),
            owner_id=member.id,
            title="Stale doc",
            source_kind="manual",
            trashed_at=_utcnow(),
        )
        task_list = TaskList(
            id=new_id(),
            key=f"SRC{new_id()[:6]}",
            name="Source ACL",
            team_id=team.id,
            created_by_id=admin.id,
        )
        archived_issue = Task(
            id=new_id(),
            list_id=task_list.id,
            task_number=1,
            title="Archived issue",
            reporter_id=admin.id,
            archived=True,
        )
        meeting = Meeting(
            id=new_id(),
            organizer_id=admin.id,
            title="Accessible meeting",
            agenda="",
            start_at=_utcnow(),
            end_at=_utcnow() + timedelta(hours=1),
        )
        meeting.attendees.append(MeetingAttendee(id=new_id(), user_id=member.id))
        db.add_all([trashed_doc, task_list, archived_issue, meeting])
        db.commit()

        policy = SourceAclPolicy.for_user(db, user=member)

        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, trashed_doc.id) is False
        assert policy.can_read_resource(PMS_TASK_RESOURCE_TYPE, archived_issue.id) is False
        assert policy.can_read_resource(MEETING_RESOURCE_TYPE, meeting.id) is True


def test_source_acl_policy_matches_searchable_resource_matrix(client: TestClient) -> None:
    dev_login(client, "delivery-hub-admin")
    dev_login(client, "delivery-hub-member")

    with get_session_factory()() as db:
        admin = _user(db, "delivery-hub-admin@open-work-hub.local")
        member = _user(db, "delivery-hub-member@open-work-hub.local")
        team = _new_space(
            db,
        )
        _ensure_team_member(db, team=team, user=member)

        owned_doc = NativeDoc(
            id=new_id(),
            owner_id=member.id,
            title="Owned doc",
            source_kind="owned_policy",
        )
        shared_doc = NativeDoc(
            id=new_id(),
            owner_id=admin.id,
            title="Shared doc",
            source_kind="shared_policy",
        )
        shared_doc.user_shares.append(
            NativeDocUserShare(
                id=new_id(),
                user_id=member.id,
                created_by_id=admin.id,
                access_level="read",
            )
        )
        meeting_granted_doc = NativeDoc(
            id=new_id(),
            owner_id=admin.id,
            title="Meeting grant doc",
            source_kind="meeting_grant_policy",
        )
        meeting_granted_doc.meeting_access_grants.append(
            DocMeetingAccess(
                id=new_id(),
                user_id=member.id,
                granted_by_user_id=admin.id,
                access_level="read",
            )
        )
        company_doc = NativeDoc(
            id=new_id(),
            owner_id=admin.id,
            title="Company doc",
            source_kind="company_policy",
        )
        company_doc.ownership_kind = "company"
        company_doc.company_visible = True
        team_doc = NativeDoc(
            id=new_id(),
            owner_id=admin.id,
            title="Team doc",
            source_kind="team_policy",
        )
        team_doc.targets.append(
            NativeDocTarget(
                id=new_id(),
                target_app="pms",
                target_type="space",
                target_id=team.id,
            )
        )
        private_doc = NativeDoc(
            id=new_id(),
            owner_id=admin.id,
            title="Private doc",
            source_kind="private_policy",
        )
        personal_shared_doc = NativeDoc(
            id=new_id(),
            owner_id=admin.id,
            title="Personal shared doc",
            source_kind="personal_policy",
            rag_scope="personal",
        )
        personal_shared_doc.user_shares.append(
            NativeDocUserShare(
                id=new_id(),
                user_id=member.id,
                created_by_id=admin.id,
                access_level="read",
            )
        )

        private_team = Team(
            id=new_id(),
            key=f"src-{new_id()[:6]}",
            name="Private Source ACL Team",
        )
        db.add(private_team)
        db.flush()
        team_list = TaskList(
            id=new_id(),
            key=f"SRC{new_id()[:6]}",
            name="Team list",
            team_id=team.id,
            created_by_id=admin.id,
        )
        private_list = TaskList(
            id=new_id(),
            key=f"PRV{new_id()[:6]}",
            name="Private list",
            team_id=private_team.id,
            created_by_id=admin.id,
        )
        team_issue = Task(
            id=new_id(),
            list_id=team_list.id,
            task_number=1,
            title="Team issue",
            reporter_id=admin.id,
        )
        granted_issue = Task(
            id=new_id(),
            list_id=private_list.id,
            task_number=1,
            title="Granted issue",
            reporter_id=admin.id,
        )
        granted_issue.user_access_grants.append(
            TaskUserAccess(
                id=new_id(),
                user_id=member.id,
                granted_by_user_id=admin.id,
                access_level="read",
            )
        )
        private_issue = Task(
            id=new_id(),
            list_id=private_list.id,
            task_number=2,
            title="Private issue",
            reporter_id=admin.id,
        )

        attendee_meeting = Meeting(
            id=new_id(),
            organizer_id=admin.id,
            title="Attendee meeting",
            agenda="",
            start_at=_utcnow(),
            end_at=_utcnow() + timedelta(hours=1),
        )
        attendee_meeting.attendees.append(MeetingAttendee(id=new_id(), user_id=member.id))
        private_meeting = Meeting(
            id=new_id(),
            organizer_id=admin.id,
            title="Private meeting",
            agenda="",
            start_at=_utcnow(),
            end_at=_utcnow() + timedelta(hours=1),
        )
        db.add_all(
            [
                owned_doc,
                shared_doc,
                meeting_granted_doc,
                company_doc,
                team_doc,
                private_doc,
                personal_shared_doc,
                private_team,
                team_list,
                private_list,
                team_issue,
                granted_issue,
                private_issue,
                attendee_meeting,
                private_meeting,
            ]
        )
        db.commit()

        policy = SourceAclPolicy.for_user(db, user=member)
        acl_filter = policy.build_keyword_acl_filter()
        space_acl_ids = [
            value
            for branch in acl_filter.branches
            if branch.entity_type == "doc"
            for clause in branch.clauses
            if clause.field == "team_ids"
            for value in clause.values
        ]

        assert team.id in space_acl_ids
        assert private_team.id not in space_acl_ids

        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, owned_doc.id) is True
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, shared_doc.id) is True
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, meeting_granted_doc.id) is True
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, company_doc.id) is True
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, team_doc.id) is True
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, private_doc.id) is False
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, personal_shared_doc.id) is True
        assert (
            policy.can_read_rag_resource(NATIVE_DOC_RESOURCE_TYPE, personal_shared_doc.id) is False
        )
        assert policy.can_read_resource(PMS_TASK_RESOURCE_TYPE, team_issue.id) is True
        assert policy.can_read_resource(PMS_TASK_RESOURCE_TYPE, granted_issue.id) is True
        assert policy.can_read_resource(PMS_TASK_RESOURCE_TYPE, private_issue.id) is False
        assert policy.can_read_resource(MEETING_RESOURCE_TYPE, attendee_meeting.id) is True
        assert policy.can_read_resource(MEETING_RESOURCE_TYPE, private_meeting.id) is False
        assert policy.can_read_resource(PLANNER_EVENT_RESOURCE_TYPE, "personal-event") is False
        assert policy.can_read_rag_resource(MEETING_RESOURCE_TYPE, attendee_meeting.id) is True
        assert policy.can_read_rag_resource(MEETING_RESOURCE_TYPE, private_meeting.id) is False
        assert policy.can_read_rag_resource(PMS_TASK_RESOURCE_TYPE, team_issue.id) is True
        assert policy.can_read_rag_resource(PMS_TASK_RESOURCE_TYPE, private_issue.id) is False
        assert policy.can_read_rag_resource(PLANNER_EVENT_RESOURCE_TYPE, "personal-event") is False
        source_kinds = set(policy.visible_native_doc_source_kinds())
        assert {
            "owned_policy",
            "shared_policy",
            "meeting_grant_policy",
            "company_policy",
            "team_policy",
            "personal_policy",
        }.issubset(source_kinds)
        assert "private_policy" not in source_kinds
        rag_source_kinds = set(policy.visible_rag_native_doc_source_kinds())
        assert "personal_policy" not in rag_source_kinds


def test_pms_reporter_requires_explicit_space_membership(
    client: TestClient,
) -> None:
    dev_login(client, "delivery-hub-admin")

    with get_session_factory()() as db:
        reporter = User(
            id=new_id(),
            login_id="pms-source-reporter",
            email="pms-source-reporter@open-work-hub.local",
            full_name="PMS Source Reporter",
            password_hash="hash",
            status="active",
        )
        private_team = Team(
            id=new_id(),
            key=f"pms-src-{new_id()[:6]}",
            name="PMS Source Private Team",
        )
        db.add_all([reporter, private_team])
        db.flush()
        private_list = TaskList(
            id=new_id(),
            key=f"PSA{new_id()[:6]}",
            name="PMS source private list",
            team_id=private_team.id,
            created_by_id=reporter.id,
        )
        private_issue = Task(
            id=new_id(),
            list_id=private_list.id,
            task_number=1,
            title="Task reporter should not see without space membership",
            reporter_id=reporter.id,
        )
        db.add_all(
            [
                reporter,
                private_team,
                private_list,
                private_issue,
            ]
        )
        db.commit()

        policy = SourceAclPolicy.for_user(db, user=reporter)
        assert policy.can_read_resource(PMS_TASK_RESOURCE_TYPE, private_issue.id) is False
        assert policy.can_read_rag_resource(PMS_TASK_RESOURCE_TYPE, private_issue.id) is False

        db.add(
            TeamMember(
                id=new_id(),
                team_id=private_team.id,
                user_id=reporter.id,
                role="member",
            )
        )
        db.commit()

        policy = SourceAclPolicy.for_user(db, user=reporter)
        assert policy.can_read_resource(PMS_TASK_RESOURCE_TYPE, private_issue.id) is True
        assert policy.can_read_rag_resource(PMS_TASK_RESOURCE_TYPE, private_issue.id) is True
