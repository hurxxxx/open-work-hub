# PMS 안정화 + IA 재설계 현황

## 구현 완료

### Stage 1 안정화
- [x] `viewer` 쓰기 차단
  - 이슈 수정/삭제
  - 코멘트 작성
  - 의존성 추가
  - 첨부 업로드/삭제
  - 체크리스트 생성/수정/삭제/정렬
  - 시간기록 생성/수정/삭제
  - 다중 담당자 변경
- [x] 폴더 CRUD 권한 하드닝
  - Space owner/admin 또는 global admin만 생성/수정/삭제 가능
- [x] Docs 미디어 sync 시그니처 수정
  - project docs create/update/delete 경로 정상화
- [x] nullable issue 필드 explicit `null` clear 지원
  - `assignee_id`
  - `milestone_id`
  - `start_date`
  - `due_date`
  - `recurrence_rule`
  - `parent_id`
- [x] 다중 담당자 API에 프로젝트 멤버십 검증 추가
- [x] 커스텀 상태 slug 불변 처리
  - 생성 시에만 slug 생성
  - 이름 변경 시 기존 이슈 status 값 유지
- [x] 설정 패널에 멤버 역할 변경/멤버 제거 UI 연결

### Stage 2 IA 재설계
- [x] 사용자 라우팅을 `List` 중심으로 전환
  - 메인 경로: `/tool/pms-list-{id}`
  - 레거시 `/tool/pms-project-{id}` → 동일 ID list route redirect
- [x] `Team`을 PMS `Space`로 사용
  - 기본 `Team Space` 자동 보장
  - 기존 `team_id = null` 리스트는 기본 Space로 이관
- [x] 사이드바를 `Space > Folder > List + Docs` 구조로 전환
- [x] `Team Docs` 탭 제거
- [x] Space Docs 실구현
  - 경로: `/tool/pms-space-{space_id}-docs`
  - hierarchical page CRUD
  - 실제 BlockEditor 연결
- [x] list-named API alias 추가
  - `/api/v1/pms/lists`
  - `/api/v1/pms/lists/{id}/...`
  - `/api/v1/pms/spaces/{space_id}/lists`
- [x] 프론트 API 레이어를 `lists`/`space docs` 계약으로 전환

## 제거된 기능

- [x] Automations — 코드·DB 스키마·프론트 API 전체 제거 (불필요)
- [x] Goals / OKR — 코드·DB 스키마·프론트 API 전체 제거 (불필요)

## 호환용 유지

- [ ] 내부 저장 구조의 `pms_projects` 테이블 이름
  - 물리 테이블은 유지
  - 사용자 계약과 UI에서는 `List`로 노출
- [ ] legacy `/projects` API
  - 기존 클라이언트 호환용 alias로 유지
- [ ] project-scoped docs API
  - 기존 데이터 호환용으로 유지
  - 신규 PMS UI는 Space Docs 사용

## 후속 개선 후보

- [ ] issue payload의 `project_id` 등 내부 필드명을 `list_id` 계열로 정리
- [ ] Folder 생성/정렬/이동 UI 추가
- [ ] Space 권한을 프로젝트 fallback 없이 완전한 Space ACL로 정리
- [ ] Space Docs 페이지 이동/드래그 정렬 UX 개선

## 검증

- [x] `pnpm nx test web --skip-nx-cache`
- [x] `pnpm nx build web --skip-nx-cache`
- [x] `cd apps/api && uv run pytest tests/test_pms_issues.py -q`
- [x] `cd apps/api && uv run python -m py_compile ...`
