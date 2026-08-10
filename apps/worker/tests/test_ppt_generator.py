from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import re
import threading
from types import SimpleNamespace

import pytest

from open_alm_worker.tasks import ppt_generator


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def test_chat_edit_error_result_hides_exception_details() -> None:
    result = ppt_generator._chat_edit_error_result(
        {"message": "수정", "answer": "provider timeout: secret-token"}
    )

    assert result["status"] == "error"
    assert result["intent"] == "chat"
    assert "secret-token" not in result["answer"]
    assert "provider timeout" not in result["answer"]


def test_find_browser_delegates_to_canonical(monkeypatch) -> None:
    # 워커 _find_browser 는 크로스플랫폼 정본(html_to_pptx._find_browser)에 위임한다.
    # (브라우저 경로/명령 상수·탐색 로직은 정본 한 곳에만 둬 워커·API 중복을 없앴다. 실제
    #  env override/PATH 탐색 로직은 api 쪽 test_html_to_pptx_find_browser_* 가 커버한다.)
    from open_alm_api.domains.ppt_generator.design import html_to_pptx

    monkeypatch.setattr(html_to_pptx, "_find_browser", lambda: "/usr/bin/google-chrome")

    assert ppt_generator._find_browser() == "/usr/bin/google-chrome"


def test_finalize_persists_generic_error_and_marks_celery_task_failed(monkeypatch) -> None:
    job = SimpleNamespace(
        id="job-finalize",
        family="corporate-house",
        slides_spec={"slides": [{"layout": "house-report", "data": {}}]},
        message="완료",
        error=None,
        pptx_key=None,
    )

    class FakeSession:
        def get(self, _model, job_id):
            return job if job_id == job.id else None

    @contextmanager
    def fake_scope():
        yield FakeSession()

    def fake_set(_session, target, **fields):
        for key, value in fields.items():
            setattr(target, key, value)

    monkeypatch.setattr(ppt_generator, "_db_session_scope", fake_scope)
    monkeypatch.setattr(ppt_generator, "_set", fake_set)
    monkeypatch.setattr(
        ppt_generator,
        "resolve_family",
        lambda family: (family, {"design": "house"}),
    )
    monkeypatch.setattr(
        ppt_generator,
        "_build_pptx_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("browser secret")),
    )

    result = ppt_generator.finalize.apply(args=[job.id], throw=False)

    assert result.failed()
    assert job.message == "변환 실패"
    assert job.error == "PPT 변환 중 오류가 발생했습니다."
    assert "browser secret" not in job.error


def test_claude_research_stops_parallel_calls_after_first_authentication_failure(
    monkeypatch,
) -> None:
    @contextmanager
    def fake_scope():
        yield object()

    class FakeExecution:
        def sanitized_text(self, *, fallback: str) -> str:
            return fallback

        def record_error(self, _error) -> None:
            return None

        def record_success(self, *, metadata) -> None:  # noqa: ARG002
            return None

    calls = 0
    calls_lock = threading.Lock()

    def reject_credential(**_kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        raise ppt_generator.AnthropicWebResearchAuthenticationError(
            "Anthropic research authentication failed"
        )

    monkeypatch.setattr(ppt_generator, "_db_session_scope", fake_scope)
    monkeypatch.setattr(
        ppt_generator,
        "resolve_llm_workload_route",
        lambda *_args, **_kwargs: SimpleNamespace(
            endpoint_url="https://api.anthropic.com",
            api_key=SimpleNamespace(get_secret_value=lambda: "invalid"),
            model_key="claude-sonnet-4-6",
            max_output_tokens=65_536,
        ),
    )
    monkeypatch.setattr(
        ppt_generator,
        "begin_external_capability",
        lambda *_args, **_kwargs: FakeExecution(),
    )
    monkeypatch.setattr(ppt_generator, "run_anthropic_web_research", reject_credential)

    auth_gate = ppt_generator._PptResearchAuthGate()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(
            executor.map(
                lambda index: ppt_generator._claude_research(
                    f"topic-{index}", auth_gate=auth_gate
                ),
                range(5),
            )
        )

    assert calls == 1
    assert results == [("", [])] * 5


def test_claude_research_checks_missing_credential_once_per_job(monkeypatch) -> None:
    @contextmanager
    def fake_scope():
        yield object()

    route_calls = 0
    calls_lock = threading.Lock()

    def missing_credential(*_args, **_kwargs):
        nonlocal route_calls
        with calls_lock:
            route_calls += 1
        return SimpleNamespace(
            endpoint_url="https://api.anthropic.com",
            api_key=None,
            model_key="claude-sonnet-4-6",
        )

    monkeypatch.setattr(ppt_generator, "_db_session_scope", fake_scope)
    monkeypatch.setattr(ppt_generator, "resolve_llm_workload_route", missing_credential)
    monkeypatch.setattr(
        ppt_generator,
        "begin_external_capability",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider gateway must not run without a credential")
        ),
    )

    auth_gate = ppt_generator._PptResearchAuthGate()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(
            executor.map(
                lambda index: ppt_generator._claude_research(
                    f"topic-{index}", auth_gate=auth_gate
                ),
                range(5),
            )
        )

    assert route_calls == 1
    assert results == [("", [])] * 5


def test_claude_research_threads_security_session_to_external_gateway(monkeypatch) -> None:
    security_db = object()
    captured: dict[str, object] = {}

    @contextmanager
    def fake_scope():
        yield security_db

    class FakeExecution:
        def sanitized_text(self, *, fallback: str) -> str:
            return fallback

        def record_success(self, *, metadata) -> None:  # noqa: ARG002
            return None

    monkeypatch.setattr(ppt_generator, "_db_session_scope", fake_scope)
    monkeypatch.setattr(
        ppt_generator,
        "resolve_llm_workload_route",
        lambda *_args, **_kwargs: SimpleNamespace(
            endpoint_url="https://api.anthropic.com",
            api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
            model_key="claude-sonnet-4-6",
            max_output_tokens=65_536,
        ),
    )

    def fake_begin(*_args, **kwargs):
        captured.update(kwargs)
        return FakeExecution()

    monkeypatch.setattr(ppt_generator, "begin_external_capability", fake_begin)
    monkeypatch.setattr(
        ppt_generator,
        "run_anthropic_web_research",
        lambda **_kwargs: SimpleNamespace(text="research", sources=[]),
    )

    result = ppt_generator._claude_research("topic")

    assert result == ("research", [])
    assert captured["db"] is security_db


def test_claude_research_releases_probe_after_unexpected_route_exception(monkeypatch) -> None:
    @contextmanager
    def fake_scope():
        yield object()

    class BrokenRoute:
        @property
        def endpoint_url(self):
            raise RuntimeError("route property failed")

    monkeypatch.setattr(ppt_generator, "_db_session_scope", fake_scope)
    monkeypatch.setattr(
        ppt_generator,
        "resolve_llm_workload_route",
        lambda *_args, **_kwargs: BrokenRoute(),
    )

    auth_gate = ppt_generator._PptResearchAuthGate()
    with pytest.raises(RuntimeError, match="route property failed"):
        ppt_generator._claude_research("topic", auth_gate=auth_gate)

    assert auth_gate._state == "ready"


def test_corporate_meeting_spec_keeps_missing_meeting_date_blank(monkeypatch) -> None:
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_meeting_fill_messages",
        lambda *_args, **_kwargs: [{"role": "user", "content": "prompt"}],
    )
    monkeypatch.setattr(ppt_generator, "_transcribe_audio_uploads", lambda *_args: "")
    monkeypatch.setattr(ppt_generator, "_job_author_name", lambda *_args: "")
    monkeypatch.setattr(
        ppt_generator,
        "_call_freeform_llm",
        lambda *_args, **_kwargs: (
            '{"title":"품질 회의","date":"","body":["결정 사항을 정리한다."]}'
        ),
    )
    job = SimpleNamespace(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        content="회의 메모",
        params={},
    )

    spec, slide_count = ppt_generator._generate_corporate_meeting_spec(
        _FakeSession(), job, "corporate-meeting", {}
    )

    match = re.search(r">회의일</td><td[^>]*>(.*?)</td>", spec["html"])

    assert slide_count == 1
    assert match is not None
    assert match.group(1) == ""


def test_corporate_meeting_spec_uses_fixed_author_label_not_personal_name(monkeypatch) -> None:
    # 표지 작성자는 개인 이름 대신 소속 고정 라벨(params["author_name"])로 통일한다.
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_meeting_fill_messages",
        lambda *_args, **_kwargs: [{"role": "user", "content": "prompt"}],
    )
    monkeypatch.setattr(ppt_generator, "_transcribe_audio_uploads", lambda *_args: "")
    # 개인 이름 조회는 폴백일 뿐 — 고정 라벨이 있으면 호출 결과가 표지에 노출되면 안 된다.
    monkeypatch.setattr(ppt_generator, "_job_author_name", lambda *_args: "주승근 책임")
    # 회귀: Qwen 이 노트에서 작성자(개인명)를 추출해 반환하는 정상 경로에서도 고정 라벨이
    # 우선해야 한다(예전엔 author 가 채워지면 개인명이 그대로 표지에 노출됐다).
    monkeypatch.setattr(
        ppt_generator,
        "_call_freeform_llm",
        lambda *_args,
        **_kwargs: '{"title":"품질 회의","author":"이몽룡 부장","body":["결정 사항"]}',
    )
    job = SimpleNamespace(
        id="job-1",
        workspace_id="workspace-1",
        user_id="user-1",
        content="회의 메모",
        params={"author_name": "기술연구소"},
    )

    spec, _ = ppt_generator._generate_corporate_meeting_spec(
        _FakeSession(), job, "corporate-meeting", {"author_name": "기술연구소"}
    )

    assert "기술연구소" in spec["html"]
    assert "주승근" not in spec["html"]
    assert "이몽룡" not in spec["html"]  # LLM 이 추출한 개인명도 고정 라벨로 대체돼야 한다


def test_apply_slot_images_leaves_slot_empty_when_no_attachment_match(monkeypatch) -> None:
    # 첨부 자료에 매칭되는 이미지가 없으면 슬롯은 비워 둔다(가상 생성 없음).
    monkeypatch.setattr(ppt_generator, "_resolve_slot_image_uris", lambda *_args: [None])
    slot: dict = {}
    job = SimpleNamespace(params={"topic": "제품 교육"})

    ppt_generator._apply_slot_images(job, [slot], [""])

    assert slot == {}


def test_apply_slot_images_uses_attachment_image_when_matched(monkeypatch) -> None:
    # 첨부 자료에서 추출/매칭된 이미지가 있으면 그 data URI 를 슬롯에 넣는다.
    monkeypatch.setattr(
        ppt_generator, "_resolve_slot_image_uris", lambda *_args: ["data:image/jpeg;base64,AAAA"]
    )
    slot: dict = {}
    job = SimpleNamespace(params={"topic": "제품 교육"})

    ppt_generator._apply_slot_images(job, [slot], [""])

    assert slot["photo_src"] == "data:image/jpeg;base64,AAAA"


def test_house_spec_uses_local_design_when_registered_route_is_local(monkeypatch) -> None:
    # 보안 회귀: 관리자 경로가 local이면 본문(첨부 추출 텍스트 포함)을 외부로 보내지 않는다.
    monkeypatch.setattr(ppt_generator, "_research_block", lambda *_a, **_k: "")
    monkeypatch.setattr(
        ppt_generator,
        "resolve_llm_workload_route",
        lambda *_a, **_k: SimpleNamespace(route="local"),
    )
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_messages",
        lambda *_a, **_k: [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
        ],
    )

    def _no_external(*_a, **_k):
        raise AssertionError("house 생성은 외부 Claude(_call_claude_design)를 호출하면 안 된다")

    monkeypatch.setattr(ppt_generator, "_call_claude_design", _no_external)

    qwen_calls = {"n": 0}

    def _fake_llm(*_a, **_k):
        qwen_calls["n"] += 1
        return "[]"

    monkeypatch.setattr(ppt_generator, "_call_llm", _fake_llm)
    monkeypatch.setattr(
        ppt_generator.parsing,
        "parse_slides_json",
        lambda *_a, **_k: [{"type": "cover", "data": {}}],
    )

    job = SimpleNamespace(
        id="job-house",
        workspace_id="ws",
        user_id="u",
        content="기밀 첨부 추출 텍스트",
        n_slides=3,
        params={},
    )

    spec, total = ppt_generator._generate_house_spec(_FakeSession(), job, "corporate-house", {})

    assert qwen_calls["n"] == 1  # 내부 Qwen 만 호출
    # _generate_house_spec 는 항상 a4 표지를 앞에 붙이므로 총 장수 = 표지(1) + 본문(1) = 2.
    assert total == 2
    assert spec["family"] == "corporate-house"
    assert spec["slides"][0]["layout"] == "a4-cover"


def test_enrich_house_passes_scalar_snapshot_to_research_threads(monkeypatch) -> None:
    # 회귀(Codex 후속): 병렬 섹션 검색은 ThreadPoolExecutor 로 도는데, 그 직전 _set 커밋으로
    # 만료된 PptJob 을 스레드에서 직접 참조하면 여러 스레드가 공유 Session 에서 동시에 lazy
    # load 하게 된다(Session 은 thread-safe 아님 → concurrent operations 오류/상태 오염).
    # _enrich_house_with_research 는 스칼라 스냅샷(_JobResearchRef)만 떠서 넘겨야 한다.
    monkeypatch.setattr(ppt_generator, "_collect_house_sections", lambda *_a, **_k: [])
    monkeypatch.setattr(
        ppt_generator,
        "_house_section_queries",
        lambda *_a, **_k: [("섹션A", "질의A"), ("섹션B", "질의B")],
    )
    monkeypatch.setattr(
        ppt_generator,
        "resolve_family",
        lambda *_a, **_k: ("corporate-house", {"design": "house"}),
    )
    monkeypatch.setattr(ppt_generator, "_set", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.prompts, "build_house_enrich_messages", lambda *_a, **_k: [])
    monkeypatch.setattr(ppt_generator, "_call_llm", lambda *_a, **_k: "[]")
    monkeypatch.setattr(
        ppt_generator.parsing,
        "parse_slides_json",
        lambda *_a, **_k: [{"type": "cover", "data": {}}],
    )

    received_jobs: list[object] = []

    def _fake_research(
        topic, *, model=None, extra_context="", job=None, auth_gate=None
    ):  # noqa: ARG001
        received_jobs.append(job)
        return f"결과:{topic}", []

    monkeypatch.setattr(ppt_generator, "_claude_research", _fake_research)

    job = SimpleNamespace(
        id="job-enrich",
        workspace_id="ws-1",
        user_id="user-1",
        family="corporate-house",
        params={"language": "Korean"},
    )

    out = ppt_generator._enrich_house_with_research(
        _FakeSession(), job, [{"type": "section", "data": {}}]
    )

    assert out == [{"type": "cover", "data": {}}]  # 보강 결과 반환
    assert len(received_jobs) == 2  # 두 섹션 모두 병렬 검색
    for ref in received_jobs:
        # 스레드로 넘어간 건 라이브 PptJob 이 아니라 스칼라 스냅샷이어야 한다.
        assert isinstance(ref, ppt_generator._JobResearchRef)
        assert ref is not job
        assert ref.id == "job-enrich"
        assert ref.workspace_id == "ws-1"
        assert ref.user_id == "user-1"
        assert ref.family == "corporate-house"


class _CancelGuardSession:
    """_set 의 취소 가드 검증용 세션 — refresh 시 최신 status 를 주입한다."""

    def __init__(self, refresh_status: str) -> None:
        self._refresh_status = refresh_status
        self.commits = 0
        self.rollbacks = 0

    def refresh(self, job, attribute_names=None) -> None:  # noqa: ARG002
        # 다른 커넥션(API)에서 커밋된 최신 status 를 다시 읽어온 상황을 흉내낸다.
        job.status = self._refresh_status

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _mk_job() -> SimpleNamespace:
    return SimpleNamespace(
        id="job-cancel",
        status="running",
        params={},
        message=None,
        error=None,
        updated_at=None,
    )


def test_set_discards_running_transition_when_cancelled() -> None:
    # 리뷰 지적: 취소 직후에도 워커의 첫 _set(status="running") 이 cancelled 를 덮어쓰면 안 된다.
    job = _mk_job()
    session = _CancelGuardSession(refresh_status="cancelled")

    ppt_generator._set(session, job, status="running", message="LLM 요청 중...")

    assert job.status == "cancelled"  # 덮어쓰이지 않음
    assert job.message is None
    assert session.commits == 0
    assert session.rollbacks == 1


def test_set_discards_error_and_message_when_cancelled() -> None:
    # 예외 경로의 _set(status="error") 및 message/error-만 갱신도 cancelled row 를 건드리면 안 된다.
    job = _mk_job()
    session = _CancelGuardSession(refresh_status="cancelled")

    ppt_generator._set(session, job, status="error", error="boom", message="실패")

    assert job.status == "cancelled"
    assert job.error is None  # updated_at/message/error 모두 보존
    assert job.updated_at is None
    assert session.commits == 0
    assert session.rollbacks == 1


def test_set_applies_updates_when_not_cancelled() -> None:
    # 취소되지 않았으면(긴 LLM 단계 이후 완료 checkpoint 포함) 정상적으로 갱신·커밋한다.
    job = _mk_job()
    session = _CancelGuardSession(refresh_status="running")

    ppt_generator._set(session, job, status="completed", message="완료")

    assert job.status == "completed"
    assert job.message == "완료"
    assert job.updated_at is not None
    assert session.commits == 1
    assert session.rollbacks == 0


def test_seminar_trip_merged_into_last_page_when_room() -> None:
    # 출장 일정: 마지막 report 페이지에 여유 있으면 그 페이지에 합쳐 빈 페이지를 없앤다.
    report_pages = [
        {
            "sections": [{"points": ["a"]}],
            "conclusion": ["c"],
            "meta": {"purpose": "p"},
            "page_role": "single",
        }
    ]
    trip = {
        "pattern": "trip_schedule",
        "days": [
            {"date": "5/27", "rows": [{"group": "이동", "content": ["x"], "attendees": "홍길동"}]}
        ],
    }
    merged = ppt_generator._maybe_merge_trip_into_report(report_pages, trip)

    assert merged is True
    assert report_pages[-1]["trip"] is trip


def test_seminar_trip_not_merged_when_page_full() -> None:
    big_rows = [{"points": ["a", "b", "c", "d"]} for _ in range(4)]  # 가중치 ~16
    report_pages = [{"sections": big_rows, "conclusion": ["c"], "page_role": "last"}]
    trip = {"days": [{"date": "1", "rows": [{"group": "g", "content": ["x"], "attendees": "m"}]}]}

    assert ppt_generator._maybe_merge_trip_into_report(report_pages, trip) is False
    assert "trip" not in report_pages[-1]


def test_seminar_schedule_ole_icon_injected_into_first_section(monkeypatch) -> None:
    # 도형/화살표 시트 이미지가 있으면 첫 본문 페이지 첫 섹션 비고에 똑딱이(ole_src) 항목이 붙는다.
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")
    job = SimpleNamespace(
        id="job-sched",
        workspace_id="ws-1",
        params={"schedule_images": [{"key": "ws/job/sched-images/0.png", "text": "표"}]},
    )
    report_pages = [{"pattern": "seminar_report", "sections": [{"no": "1", "topic": "행사"}]}]

    ppt_generator._inject_seminar_ole_icon(_FakeSession(), job, report_pages)

    items = report_pages[0]["sections"][0]["remark"]["items"]
    assert any(it.get("ole_src", "").startswith("data:image/png;base64,") for it in items)
    assert any(it.get("caption") == "첨부 일정표" for it in items)


def test_seminar_schedule_ole_icon_wins_over_stale_fold_trip(monkeypatch) -> None:
    # 이전 실행의 fold_trip 이 남아 있어도 schedule_images 가 있으면 OLE 슬롯은 첨부 일정표 몫이다.
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")
    job = SimpleNamespace(
        id="job-sched-stale",
        workspace_id="ws-1",
        params={
            "schedule_images": [{"key": "ws/job/sched-images/0.png"}],
            "fold_trip": {"days": [{"date": "old", "rows": [{"content": ["old"]}]}]},
        },
    )
    report_pages = [{"pattern": "seminar_report", "sections": [{"no": "1", "topic": "행사"}]}]

    ok = ppt_generator._inject_seminar_ole_icon(_FakeSession(), job, report_pages)

    items = report_pages[0]["sections"][0]["remark"]["items"]
    assert ok is True
    assert any(it.get("caption") == "첨부 일정표" for it in items)
    assert all(it.get("caption") != "출장 일정" for it in items)


def test_seminar_schedule_ole_icon_participates_in_pagination(monkeypatch) -> None:
    # 회귀(Codex): 일정표 아이콘을 pagination 뒤에 붙이면, 비고칸이 이미 사진/메모로 찬 행에서
    # 표 높이 계산보다 실제 행이 커져 첫 본문 페이지가 겹칠 수 있다. 생성 흐름은 아이콘을 원본
    # slide 에 먼저 심고 paginate 해야 한다.
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_fill_messages",
        lambda *_a, **_k: [{"role": "user", "content": "report"}],
    )
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_trip_messages",
        lambda *_a, **_k: [{"role": "user", "content": "trip"}],
    )
    monkeypatch.setattr(ppt_generator, "_inject_seminar_photos", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")

    replies = iter(
        [
            (
                '{"pattern":"seminar_report","title":"세미나 보고","meta":{},'
                '"sections":['
                '{"no":"1","topic":"현장","points":["내용"],'
                '"remark":{"items":['
                '{"label":"A","photo":true},{"label":"B","photo":true},'
                '{"label":"C","photo":true},{"label":"D","photo":true},'
                '{"caption":"1234567890123","photo":false}'
                "]}},"
                '{"no":"2","topic":"후속","points":["12345678901234567890123456789012345"],'
                '"remark":{"items":[{"caption":"메모","photo":false}]}}'
                "],"
                '"conclusion":["확인"]}'
            ),
            '{"pattern":"trip_schedule","title":"출장 일정","days":[]}',
        ]
    )
    monkeypatch.setattr(ppt_generator, "_call_freeform_llm", lambda *_a, **_k: next(replies))
    job = SimpleNamespace(
        id="job-sched-page",
        workspace_id="ws-1",
        user_id="u",
        content="세미나 참석함",
        family="corporate-seminar",
        params={"schedule_images": [{"key": "sched.png"}]},
    )

    spec, slide_count = ppt_generator._generate_corporate_seminar_spec(
        _FakeSession(), job, "corporate-seminar", {}
    )

    joined = " ".join(s.get("inner_html", "") for s in spec["body"])
    assert len(spec["body"]) == 2
    assert slide_count == 3  # 표지 1 + 본문 2
    assert "첨부 일정표" in joined


def test_seminar_pagination_moves_conclusion_to_tail_when_single_page_overflows() -> None:
    # 회귀: 정보헤더가 있는 첫 본문 페이지에 결론이 같이 못 들어가면, 본문은 first 로 남기고
    # 결론 전용 last 페이지를 추가해야 한다.
    slide = {
        "pattern": "seminar_report",
        "title": "세미나 보고",
        "meta": {"purpose": "검토"},
        "sections": [
            {
                "no": "1",
                "topic": "긴 본문",
                "points": ["매우 긴 내용 " * 60],
                "remark": {"items": [{"caption": "메모 " * 20, "photo": False}]},
            }
        ],
        "conclusion": ["후속 조치 필요"],
    }

    pages = ppt_generator._paginate_seminar_report(slide)

    assert len(pages) == 2
    assert pages[0]["page_role"] == "first"
    assert pages[0]["meta"] == {"purpose": "검토"}
    assert "conclusion" not in pages[0]
    assert pages[1]["page_role"] == "last"
    assert pages[1]["conclusion"] == ["후속 조치 필요"]


def test_seminar_fold_trip_injects_ole_icon(monkeypatch) -> None:
    # 페이지를 못 채워 접은 출장 일정(fold_trip)이 있으면 '출장 일정' 똑딱이 아이콘이 붙는다.
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")
    job = SimpleNamespace(
        id="job-fold",
        workspace_id="ws-1",
        params={"fold_trip": {"days": [{"date": "1", "rows": [{"content": ["x"]}]}]}},
    )
    report_pages = [{"pattern": "seminar_report", "sections": [{"no": "1", "topic": "행사"}]}]

    ok = ppt_generator._inject_seminar_ole_icon(_FakeSession(), job, report_pages)

    assert ok is True  # 성공 시 True — 호출부는 이 값이 True 일 때만 접는다.
    items = report_pages[0]["sections"][0]["remark"]["items"]
    assert any(it.get("caption") == "출장 일정" for it in items)


def test_seminar_fold_trip_commit_failure_keeps_trip_as_page_without_ghost_ole(
    monkeypatch,
) -> None:
    # 회귀: fold_trip 커밋이 실패하면 출장 일정은 접지 않고 별도 페이지로 남아야 하며,
    # 커밋되지 않은 OLE 아이콘도 미리보기 본문에 남기면 안 된다.
    class CommitFailSession:
        def __init__(self) -> None:
            self.rollbacks = 0

        def commit(self) -> None:
            raise RuntimeError("db down")

        def rollback(self) -> None:
            self.rollbacks += 1

    monkeypatch.setattr(ppt_generator, "_set", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "flag_modified", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "_inject_seminar_photos", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "_maybe_merge_trip_into_report", lambda *_a, **_k: False)
    monkeypatch.setattr(ppt_generator, "_build_seminar_ole_pptx", lambda *_a, **_k: b"PPTX")
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_fill_messages",
        lambda *_a, **_k: [{"role": "user", "content": "report"}],
    )
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_trip_messages",
        lambda *_a, **_k: [{"role": "user", "content": "trip"}],
    )
    replies = iter(
        [
            (
                '{"pattern":"seminar_report","title":"세미나 보고","meta":{},'
                '"sections":[{"no":"1","topic":"본문","points":["내용"]}],'
                '"conclusion":["확인"]}'
            ),
            (
                '{"pattern":"trip_schedule","title":"출장 일정",'
                '"days":[{"date":"1","rows":[{"group":"이동","content":["출발"],"attendees":"홍길동"}]}]}'
            ),
        ]
    )
    monkeypatch.setattr(ppt_generator, "_call_freeform_llm", lambda *_a, **_k: next(replies))
    session = CommitFailSession()
    job = SimpleNamespace(
        id="job-fold-fail",
        workspace_id="ws-1",
        user_id="u",
        content="세미나 참석함",
        family="corporate-seminar",
        params={},
    )

    spec, _ = ppt_generator._generate_corporate_seminar_spec(session, job, "corporate-seminar", {})

    joined = " ".join(s.get("inner_html", "") for s in spec["body"])
    assert job.params == {}
    assert session.rollbacks == 1
    assert "참석 인원" in joined
    assert "data:image/png;base64" not in joined


def test_seminar_stale_fold_trip_removed_when_current_run_does_not_fold(monkeypatch) -> None:
    # 이전 실행에서 params 에 남은 fold_trip 은 이번 실행이 접지 않기로 하면 제거한다.
    monkeypatch.setattr(ppt_generator, "_set", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "flag_modified", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "_inject_seminar_photos", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_fill_messages",
        lambda *_a, **_k: [{"role": "user", "content": "report"}],
    )
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_trip_messages",
        lambda *_a, **_k: [{"role": "user", "content": "trip"}],
    )
    replies = iter(
        [
            (
                '{"pattern":"seminar_report","title":"세미나 보고","meta":{},'
                '"sections":[{"no":"1","topic":"본문","points":["내용"]}],'
                '"conclusion":["확인"]}'
            ),
            '{"pattern":"trip_schedule","title":"출장 일정","days":[]}',
        ]
    )
    monkeypatch.setattr(ppt_generator, "_call_freeform_llm", lambda *_a, **_k: next(replies))
    session = _FakeSession()
    job = SimpleNamespace(
        id="job-stale-fold",
        workspace_id="ws-1",
        user_id="u",
        content="세미나 참석함",
        family="corporate-seminar",
        params={"fold_trip": {"days": [{"date": "old", "rows": [{"content": ["old"]}]}]}},
    )

    ppt_generator._generate_corporate_seminar_spec(session, job, "corporate-seminar", {})

    assert "fold_trip" not in job.params
    assert session.commits == 1


def test_seminar_schedule_images_remove_stale_fold_before_icon(monkeypatch) -> None:
    # schedule_images 가 있는 재생성에서는 남아 있던 fold_trip 을 먼저 제거하고 첨부 일정표 아이콘을 붙인다.
    monkeypatch.setattr(ppt_generator, "_set", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "flag_modified", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "_inject_seminar_photos", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_fill_messages",
        lambda *_a, **_k: [{"role": "user", "content": "report"}],
    )
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_trip_messages",
        lambda *_a, **_k: [{"role": "user", "content": "trip"}],
    )
    replies = iter(
        [
            (
                '{"pattern":"seminar_report","title":"세미나 보고","meta":{},'
                '"sections":[{"no":"1","topic":"본문","points":["내용"]}],'
                '"conclusion":["확인"]}'
            ),
            '{"pattern":"trip_schedule","title":"출장 일정","days":[]}',
        ]
    )
    monkeypatch.setattr(ppt_generator, "_call_freeform_llm", lambda *_a, **_k: next(replies))
    session = _FakeSession()
    job = SimpleNamespace(
        id="job-sched-stale-fold",
        workspace_id="ws-1",
        user_id="u",
        content="세미나 참석함",
        family="corporate-seminar",
        params={
            "schedule_images": [{"key": "sched.png"}],
            "fold_trip": {"days": [{"date": "old", "rows": [{"content": ["old"]}]}]},
        },
    )

    spec, _ = ppt_generator._generate_corporate_seminar_spec(session, job, "corporate-seminar", {})

    joined = " ".join(s.get("inner_html", "") for s in spec["body"])
    assert "fold_trip" not in job.params
    assert session.commits == 1
    assert "첨부 일정표" in joined
    assert "출장 일정" not in joined


def test_seminar_ole_icon_returns_false_when_icon_save_fails(monkeypatch) -> None:
    # 회귀(Codex): 아이콘 저장이 실패하면 False 를 반환해 호출부가 접기를 취소하고 출장 일정을
    # 별도 페이지로 남기게 한다(아이콘이 없으면 finalize 가 OLE 를 못 넣어 일정이 유실됨).
    def _boom(*_a, **_k):
        raise RuntimeError("minio down")

    monkeypatch.setattr(ppt_generator, "_put_object", _boom)
    monkeypatch.setattr(ppt_generator.ole, "make_ole_icon_png", lambda *_a, **_k: b"ICONBYTES")
    job = SimpleNamespace(
        id="job-fold",
        workspace_id="ws-1",
        params={"fold_trip": {"days": [{"date": "1", "rows": [{"content": ["x"]}]}]}},
    )
    report_pages = [{"pattern": "seminar_report", "sections": [{"no": "1", "topic": "행사"}]}]

    ok = ppt_generator._inject_seminar_ole_icon(_FakeSession(), job, report_pages)

    assert ok is False
    assert "remark" not in report_pages[0]["sections"][0]  # 실패 시 비고 미변경


def test_seminar_schedule_ole_icon_noop_without_schedule_images(monkeypatch) -> None:
    monkeypatch.setattr(ppt_generator, "_put_object", lambda *_a, **_k: None)
    job = SimpleNamespace(id="job-sched", workspace_id="ws-1", params={})
    report_pages = [{"sections": [{"no": "1", "topic": "행사"}]}]

    ppt_generator._inject_seminar_ole_icon(_FakeSession(), job, report_pages)

    assert "remark" not in report_pages[0]["sections"][0]


def test_seminar_spec_omits_empty_trip_schedule_page(monkeypatch) -> None:
    # 회귀(Codex): 자료에 일정 정보가 없으면 프롬프트가 days=[] 를 반환한다(없는 일정 창작 금지).
    # 그 빈 출장 일정을 별도 페이지로 렌더하면 헤더만 있는 빈 슬라이드가 생기므로, 추가하지 않는다.
    monkeypatch.setattr(ppt_generator, "_research_block", lambda *_a, **_k: "")
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_fill_messages",
        lambda *_a, **_k: [{"role": "user", "content": "x"}],
    )
    monkeypatch.setattr(
        ppt_generator.prompts,
        "build_corporate_seminar_trip_messages",
        lambda *_a, **_k: [{"role": "user", "content": "x"}],
    )
    monkeypatch.setattr(ppt_generator, "_inject_seminar_photos", lambda *_a, **_k: None)
    replies = iter(
        [
            '{"pattern":"seminar_report","title":"세미나 보고","meta":{},'
            '"sections":[{"no":"1","topic":"발표 내용","points":["내용 A","내용 B"]}],'
            '"conclusion":["유익했음"]}',
            '{"pattern":"trip_schedule","title":"출장 일정","days":[]}',
        ]
    )
    monkeypatch.setattr(ppt_generator, "_call_freeform_llm", lambda *_a, **_k: next(replies))
    job = SimpleNamespace(
        id="job-sem",
        workspace_id="ws-1",
        user_id="u",
        content="세미나 참석함",
        family="corporate-seminar",
        params={},
    )

    spec, _ = ppt_generator._generate_corporate_seminar_spec(_FakeSession(), job, "corporate-seminar", {})

    joined = " ".join(s.get("inner_html", "") for s in spec["body"])
    # '참석 인원'은 출장 일정 표에만 있는 헤더(본문 표엔 없음) → 빈 출장 페이지가 붙었는지 판별.
    assert "참석 인원" not in joined  # 빈 출장 일정 페이지가 붙지 않는다
    assert "발표 내용" in joined  # 본문(주요 내용)은 정상 렌더


def test_build_schedule_ole_pptx_builds_deck(monkeypatch) -> None:
    # schedule_images 바이트로 이미지 1장당 슬라이드 1장인 .pptx 를 만든다.
    import io as _io

    from PIL import Image
    from pptx import Presentation

    png = _io.BytesIO()
    Image.new("RGB", (120, 80), (200, 200, 200)).save(png, format="PNG")
    monkeypatch.setattr(ppt_generator.ppt_service, "fetch_object_bytes", lambda _k: png.getvalue())
    job = SimpleNamespace(
        id="job-sched",
        workspace_id="ws-1",
        params={"schedule_images": [{"key": "a.png"}, {"key": "b.png"}]},
    )

    data = ppt_generator._build_schedule_ole_pptx(job)

    assert data
    prs = Presentation(_io.BytesIO(data))
    assert len(prs.slides) == 2


def test_build_schedule_ole_pptx_none_without_images(monkeypatch) -> None:
    monkeypatch.setattr(ppt_generator.ppt_service, "fetch_object_bytes", lambda _k: None)
    job = SimpleNamespace(
        id="job-sched", workspace_id="ws-1", params={"schedule_images": [{"key": "x"}]}
    )
    assert ppt_generator._build_schedule_ole_pptx(job) is None


def test_maybe_embed_ole_schedule_images_win_over_stale_fold_trip(monkeypatch) -> None:
    # cleanup commit 이 실패해 fold_trip 이 DB 에 남아도 finalize 는 schedule_images 를 우선해야 한다.
    calls: list[dict] = []

    monkeypatch.setattr(ppt_generator, "_build_schedule_ole_pptx", lambda _job: b"SCHEDULE")
    monkeypatch.setattr(ppt_generator, "_build_seminar_ole_pptx", lambda _job: b"TRIP")
    monkeypatch.setattr(
        ppt_generator.ppt_service,
        "fetch_object_bytes",
        lambda key: b"ICON" if key.endswith("/embed/icon.png") else None,
    )

    def fake_inject(pptx_bytes, embed_bytes, icon_bytes, *, slide_index, name):
        calls.append(
            {
                "pptx_bytes": pptx_bytes,
                "embed_bytes": embed_bytes,
                "icon_bytes": icon_bytes,
                "slide_index": slide_index,
                "name": name,
            }
        )
        return b"EMBEDDED"

    monkeypatch.setattr(ppt_generator.ole, "inject_ole_into_pptx", fake_inject)
    job = SimpleNamespace(
        id="job-sched-finalize",
        workspace_id="ws-1",
        family="corporate-seminar",
        params={
            "schedule_images": [{"key": "sched.png"}],
            "fold_trip": {"days": [{"date": "old", "rows": [{"content": ["old"]}]}]},
        },
    )

    result = ppt_generator._maybe_embed_ole(job, b"PPTX")

    assert result == b"EMBEDDED"
    assert calls == [
        {
            "pptx_bytes": b"PPTX",
            "embed_bytes": b"SCHEDULE",
            "icon_bytes": b"ICON",
            "slide_index": 1,
            "name": "첨부 일정표",
        }
    ]
