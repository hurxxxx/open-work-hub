from __future__ import annotations

from fastapi.testclient import TestClient

from test_meeting import _auth_headers, _bootstrap_admin_session


def test_release_note_current_dismiss_and_history(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    headers = _auth_headers(session["token"])

    july_20_body_fragments = [
        "여러 상태 필터",
        "오름차순과 내림차순",
        "작업공간별로 유지",
        "완료일",
        "여러 작업공간의 담당 태스크",
        "리스트 순서와 폴더 배치",
        "첨부파일·파일명",
        "차종은 관리자가 영구 삭제",
        "아이두 챗봇",
        "AI 분석은 계속",
        "고정 개인 도구",
        "전사 공용 앱",
        "오늘 일정 위젯",
        "공동 청구 금액",
        "식당 전표 재판독",
        "PPT 생성 결과 변환",
        "새로고침",
        "접근 가능한 첫 번째 스페이스의 개요",
        "활성 리스트를 함께 확인",
        "사용자 지정 순서를 기본",
        "보관 중에는 읽기 전용",
        "필요할 때 복원",
    ]
    expected_notes = [
        (
            "2026-07-23-02",
            [
                "행 높이 자동 맞춤",
                "설정은 표별로 유지",
                "열교환기와 쿨링모듈의 아이콘",
                "아직 리비전이 없는 모듈",
                "최초 데이터를 입력",
                "새로고침",
            ],
        ),
        (
            "2026-07-23-01",
            [
                "점검방안·적용유무·반영/검토결과",
                "모듈별 직접 수정 권한자",
                "기존 데이터와 첨부파일",
                "데이터 열의 순서와 표시/숨김",
                "모든 사용자의 공유 설정",
                "열교환기",
                "키워드·의미·하이브리드 검색",
                "표가 포함되거나 스캔된 PDF",
                "전사 공용 앱",
                "유사한 OCR 표기",
                "불필요한 합계금액",
                "원문에 없는 목적이나 결론",
                "사용하지 않는 회의",
                "이미지 생성 제공자·모델",
                "로그인 차단",
                "새로고침",
            ],
        ),
        (
            "2026-07-21-01",
            [
                "워크스페이스 검색",
                "식당 명세서 OCR",
                "초안을 저장하고 편집을 종료",
                "전사 공용 화면",
                "ERP 인사 원본 스냅샷",
                "가로 스크롤바",
                "복지몰 바로가기",
            ],
        ),
        ("2026-07-20-01", july_20_body_fragments),
        (
            "2026-07-07-ui-ux",
            [
                "상위 태스크",
                "과거차 문제점",
                "PPT 생성",
                "업무 사이트",
                "두원공조 그룹웨어",
                "읽기 전용",
                "검색 버튼",
                "자동 작업 화면",
            ],
        ),
        (
            "2026-07-01-ui-ux",
            [
                "우측 dock",
                "PMS 위젯",
            ],
        ),
        (
            "2026-06-24-ui-ux",
            [
                "앱 런처",
                "AI 도구",
                "다크 모드",
            ],
        ),
        (
            "2026-06-17-01",
            [
                "AI 추천",
                "산업 리포트",
            ],
        ),
        (
            "2026-06-15-prod",
            [
                "첨부파일 다운로드가 되지 않던 현상",
            ],
        ),
    ]

    for release_key, body_fragments in expected_notes:
        current = client.get("/api/v1/release-notes/current", headers=headers)
        assert current.status_code == 200, current.text
        current_item = current.json()["item"]
        assert current_item is not None
        assert current_item["release_key"] == release_key
        assert current_item["dismissed_at"] is None
        assert "localhost" not in current_item["body"]
        for fragment in body_fragments:
            assert fragment in current_item["body"]

        dismissed = client.post(
            f"/api/v1/release-notes/{current_item['id']}/dismiss",
            headers=headers,
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["dismissed_at"] is not None

    after_dismiss_all = client.get("/api/v1/release-notes/current", headers=headers)
    assert after_dismiss_all.status_code == 200, after_dismiss_all.text
    assert after_dismiss_all.json()["item"] is None

    history = client.get("/api/v1/release-notes", headers=headers)
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert "2026-07-16-01" not in {item["release_key"] for item in items}
    assert "2026-07-07-02-ui-ux" not in {item["release_key"] for item in items}
    assert [item["release_key"] for item in items[: len(expected_notes)]] == [
        release_key for release_key, _ in expected_notes
    ]
    for item in items[: len(expected_notes)]:
        assert item["dismissed_at"] is not None
