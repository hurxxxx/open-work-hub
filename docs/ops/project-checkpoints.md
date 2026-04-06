# Project Checkpoints

이 문서는 큰 작업의 중간 스냅샷을 짧게 남긴다.

## Entries

### 2026-04-06

date:
2026-04-06

workstream:
AIDOO PMS MVP

scenario_id:
pms

completed:
- `Wiki` 제품 표면과 레거시 경로 처리를 제거하고 `PMS`만 남김
- PMS용 백엔드 도메인 추가
  - `projects`
  - `project_members`
  - `milestones`
  - `issues`
  - `issue_comments`
  - `issue_activity_logs`
  - `schedule_dependencies`
- PMS REST API 추가
  - 프로젝트, 멤버, 마일스톤, 이슈, 댓글, 활동 로그, 의존성, 대시보드
- `/pms`를 실제 작업면으로 교체
  - 대시보드
  - 프로젝트 생성
  - 보드/리스트
  - 이슈 상세 drawer
  - 모바일 상세 패널
  - 마일스톤/멤버/최근 활동 패널
- PMS 구현 계획 문서 추가: `docs/planning/pms-implementation-plan.md`
- 검증 완료
  - `pnpm exec nx test api`
  - `pnpm exec nx test web`
  - `pnpm exec nx build web`

open_risks:
- PMS 화면은 기능은 동작하지만 현재 카드 비중이 높아 실사용 PM 툴 밀도와는 거리가 있다
- 간트/타임라인 UI는 아직 없다
- 프로젝트 멤버 추가는 API까지 있고 웹 관리 UI는 읽기 중심이다
- PMS 하네스 문서는 정리됐지만, 실제 제품의 비-AI CRUD 방향과 완전히 맞추는 추가 정합화는 더 필요하다

next_action:
- PMS를 카드형 포털 UI에서 dense한 프로젝트 관리 툴 UI로 재구성
- 보드/리스트/이슈 상세를 더 전면에 두고 대시보드는 축소
