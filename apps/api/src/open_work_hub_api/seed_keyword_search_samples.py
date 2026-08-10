from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import (
    ensure_dev_login_seed_data,
    ensure_workspace_default_pms_space,
)
from open_work_hub_api.domains.auth.models import Team, User, Workspace
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocTarget, NativeDocPage
from open_work_hub_api.domains.meeting.models import Meeting, MeetingAttendee, MeetingRecording
from open_work_hub_api.domains.planner.models import PlannerEvent
from open_work_hub_api.domains.pms.models import Task, TaskComment, TaskList
from open_work_hub_api.domains.retrieval.partitioning import assign_default_partition
from open_work_hub_api.domains.search.service import refresh_workspace_keyword_index


WORKSPACE_KEY = "general"
ADMIN_EMAIL = "admin@open-work-hub.local"
SAMPLE_TASK_LIST_KEY = "SEARCH"
SAMPLE_PREFIX = "[검색검증]"
SOURCE_REF_PREFIX = "keyword-search-e2e"

TOPICS = [
    ("예산 리스크", "공급사 단가 변경과 환율 변동으로 예산 리스크가 증가했습니다."),
    ("고객 이탈", "고객 이탈 징후가 반복되어 계정 담당자 후속 조치가 필요합니다."),
    ("납기 지연", "부품 승인 지연으로 납기 지연 가능성이 높아졌습니다."),
    ("배터리 발열", "배터리 발열 태스크가 재현되어 QA 재검증을 요청합니다."),
    ("런칭 체크리스트", "런칭 체크리스트의 보안 승인과 공지 문안이 남아 있습니다."),
    ("온보딩", "신규 파트너 온보딩 자료와 교육 일정이 업데이트되었습니다."),
    ("품질 감사", "품질 감사에서 발견된 문서 누락 항목을 보완해야 합니다."),
    ("재고 부족", "주요 SKU 재고 부족으로 긴급 발주와 대체품 검토가 필요합니다."),
    ("계약 갱신", "계약 갱신 조건과 서비스 수준 합의서를 법무 검토 중입니다."),
    ("데이터 마이그레이션", "데이터 마이그레이션 리허설에서 매핑 오류가 확인되었습니다."),
]


def main() -> None:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
        workspace = _one(db, select(Workspace).where(Workspace.key == WORKSPACE_KEY))
        admin = _one(db, select(User).where(User.email == ADMIN_EMAIL))
        task_list = _get_or_create_sample_task_list(db, workspace, admin)

        _clear_previous_samples(db, workspace)
        created = {
            "docs": _seed_docs(db, workspace, admin, task_list),
            "meetings": _seed_meetings(db, workspace, admin, admin),
            "tasks": _seed_tasks(db, workspace, task_list, admin, admin),
            "events": _seed_events(db, workspace, admin),
        }
        db.flush()
        refresh_workspace_keyword_index(db, workspace=workspace)
        db.commit()

    print(
        "Seeded keyword search samples: "
        + ", ".join(f"{kind}={count}" for kind, count in created.items())
    )
    print(f"Workspace: {WORKSPACE_KEY}")
    print("Suggested queries: 예산 리스크, 고객 이탈, 납기 지연, 배터리 발열, 런칭 체크리스트")


def _get_or_create_sample_task_list(db: Session, workspace: Workspace, admin: User) -> TaskList:
    team = ensure_workspace_default_pms_space(db, workspace)
    task_list = db.scalar(
        select(TaskList).where(
            TaskList.team_id == team.id,
            TaskList.key == SAMPLE_TASK_LIST_KEY,
        )
    )
    if task_list is not None:
        return task_list
    task_list = TaskList(
        id=new_id(),
        key=SAMPLE_TASK_LIST_KEY,
        name="Search Sample List",
        description="Sample PMS list for keyword search verification.",
        status="active",
        team_id=team.id,
        created_by_id=admin.id,
    )
    db.add(task_list)
    db.flush()
    return task_list


def _clear_previous_samples(db: Session, workspace: Workspace) -> None:
    for doc in db.scalars(
        select(NativeDoc).where(
            NativeDoc.workspace_id == workspace.id,
            NativeDoc.source_ref.like(f"{SOURCE_REF_PREFIX}:%"),
        )
    ).all():
        db.delete(doc)

    for meeting in db.scalars(
        select(Meeting).where(
            Meeting.workspace_id == workspace.id,
            Meeting.title.like(f"{SAMPLE_PREFIX}%"),
        )
    ).all():
        db.delete(meeting)

    list_ids = [
        item.id
        for item in db.scalars(
            select(TaskList)
            .join(Team, TaskList.team_id == Team.id)
            .where(Team.workspace_id == workspace.id)
        ).all()
    ]
    if list_ids:
        for task in db.scalars(
            select(Task).where(
                Task.list_id.in_(list_ids),
                Task.title.like(f"{SAMPLE_PREFIX}%"),
            )
        ).all():
            db.delete(task)

    for event in db.scalars(
        select(PlannerEvent).where(
            PlannerEvent.workspace_id == workspace.id,
            PlannerEvent.title.like(f"{SAMPLE_PREFIX}%"),
        )
    ).all():
        db.delete(event)
    db.flush()


def _seed_docs(db: Session, workspace: Workspace, owner: User, task_list: TaskList) -> int:
    for index in range(36):
        topic, sentence = TOPICS[index % len(TOPICS)]
        title = f"{SAMPLE_PREFIX} {topic} 운영 문서 {index + 1:02d}"
        doc = NativeDoc(
            id=new_id(),
            workspace_id=workspace.id,
            owner_id=owner.id,
            title=title,
            source_app="docs",
            source_kind="manual",
            source_ref=f"{SOURCE_REF_PREFIX}:doc:{index + 1:02d}",
            generation_kind="human",
        )
        assign_default_partition(
            db,
            target=doc,
            source_namespace="docs",
            candidate_scope_kind="workspace",
            workspace_id=workspace.id,
        )
        db.add(doc)
        db.add(
            NativeDocPage(
                id=new_id(),
                doc_id=doc.id,
                parent_id=None,
                title=f"{topic} 상세 분석",
                sort_order=0,
                created_by_id=owner.id,
                content_blocks=[
                    _heading(f"{topic} 현황"),
                    _paragraph(sentence),
                    _paragraph(
                        f"{topic} 관련 담당자는 매일 오전 스탠드업에서 상태를 공유하고, "
                        "차단 요인은 PMS 태스크와 회의록에 연결합니다."
                    ),
                    _paragraph(
                        "검색 검증용 데이터로 문서 제목, 본문, 대상 facet 확인에 사용합니다."
                    ),
                ],
            )
        )
        db.add(
            NativeDocTarget(
                id=new_id(),
                doc_id=doc.id,
                target_app="pms",
                target_type="list",
                target_id=task_list.id,
                is_primary=True,
                sort_order=index,
            )
        )
    return 36


def _seed_meetings(db: Session, workspace: Workspace, organizer: User, attendee: User) -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    for index in range(24):
        topic, sentence = TOPICS[index % len(TOPICS)]
        start_at = now + timedelta(days=index - 4, hours=9 + (index % 5))
        meeting = Meeting(
            id=new_id(),
            workspace_id=workspace.id,
            organizer_id=organizer.id if index % 2 == 0 else attendee.id,
            title=f"{SAMPLE_PREFIX} {topic} 주간 싱크 {index + 1:02d}",
            agenda=f"{topic} 진행 상황, 리스크, 담당자 후속 조치를 점검합니다.",
            start_at=start_at,
            end_at=start_at + timedelta(minutes=45),
            status="completed" if index % 3 else "scheduled",
        )
        assign_default_partition(
            db,
            target=meeting,
            source_namespace="meeting",
            candidate_scope_kind="workspace",
            workspace_id=workspace.id,
        )
        db.add(meeting)
        db.flush()
        db.add(
            MeetingAttendee(
                id=new_id(),
                meeting_id=meeting.id,
                user_id=attendee.id if meeting.organizer_id == organizer.id else organizer.id,
                role="required",
                response="accepted",
            )
        )
        db.add(
            MeetingRecording(
                id=new_id(),
                meeting_id=meeting.id,
                storage_key=f"keyword-search-e2e/recordings/{meeting.id}.webm",
                duration_sec=1800 + index,
                file_size=1024 + index,
                idempotency_key=f"keyword-search-e2e-{index + 1:02d}",
                uploaded_by_id=meeting.organizer_id,
                transcription_status="completed",
                progress_pct=100,
                transcript_text=(
                    f"{sentence} 참석자는 {topic} 우선순위를 재정렬하고 "
                    "다음 회의 전까지 차단 태스크를 업데이트하기로 했습니다."
                ),
                summary_text=f"{topic} 회의 요약: 핵심 리스크와 실행 항목을 확정했습니다.",
                transcribe_started_at=start_at,
                transcribe_completed_at=start_at + timedelta(minutes=30),
            )
        )
    return 24


def _seed_tasks(
    db: Session,
    workspace: Workspace,
    task_list: TaskList,
    reporter: User,
    assignee: User,
) -> int:
    max_number = (
        db.scalar(select(func.max(Task.task_number)).where(Task.list_id == task_list.id)) or 0
    )
    statuses = ["todo", "in_progress", "done", "canceled"]
    priorities = ["low", "medium", "high", "urgent"]
    today = date.today()
    for index in range(48):
        topic, sentence = TOPICS[index % len(TOPICS)]
        task = Task(
            id=new_id(),
            list_id=task_list.id,
            task_number=max_number + index + 1,
            title=f"{SAMPLE_PREFIX} {topic} 실행 과제 {index + 1:02d}",
            description=(
                f"{sentence} 담당자는 원인, 영향도, 완료 기준을 정리해야 합니다. "
                f"{topic} 검색에서 상태 facet과 담당자 정보가 함께 보여야 합니다."
            ),
            description_blocks=[_paragraph(sentence)],
            status=statuses[index % len(statuses)],
            priority=priorities[index % len(priorities)],
            assignee_id=assignee.id if index % 4 != 0 else None,
            reporter_id=reporter.id,
            start_date=today + timedelta(days=index % 10),
            due_date=today + timedelta(days=3 + index % 21),
            board_position=index,
            archived=False,
        )
        assign_default_partition(
            db,
            target=task,
            source_namespace="pms",
            candidate_scope_kind="workspace",
            workspace_id=workspace.id,
        )
        db.add(task)
        db.flush()
        db.add(
            TaskComment(
                id=new_id(),
                task_id=task.id,
                author_id=assignee.id,
                body=f"{topic} 후속 확인: 고객 영향도와 릴리스 차단 여부를 업데이트했습니다.",
                body_blocks=[_paragraph(f"{topic} 코멘트 검색 검증")],
            )
        )
    return 48


def _seed_events(db: Session, workspace: Workspace, owner: User) -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    for index in range(30):
        topic, sentence = TOPICS[index % len(TOPICS)]
        start_at = now + timedelta(days=index - 3, hours=10 + (index % 4))
        event = PlannerEvent(
            id=new_id(),
            workspace_id=workspace.id,
            owner_id=owner.id,
            title=f"{SAMPLE_PREFIX} {topic} 일정 {index + 1:02d}",
            description=f"{sentence} 캘린더 검색에서 start_date와 visibility facet을 확인합니다.",
            location="Open Work Hub HQ 5F" if index % 2 == 0 else "Remote",
            visibility="public" if index % 3 == 0 else "private",
            all_day=index % 7 == 0,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
        )
        assign_default_partition(
            db,
            target=event,
            source_namespace="planner",
            candidate_scope_kind="personal",
            user_id=owner.id,
        )
        db.add(event)
    return 30


def _heading(text: str) -> dict:
    return {"type": "heading", "props": {"level": 2}, "content": [{"type": "text", "text": text}]}


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _one(db: Session, statement):
    value = db.scalar(statement)
    if value is None:
        raise RuntimeError(f"Missing required seed dependency for statement: {statement}")
    return value


if __name__ == "__main__":
    main()
