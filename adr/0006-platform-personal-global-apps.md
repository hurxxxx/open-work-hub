# ADR 0006: Platform Availability and Personal Global Apps

- Status: Accepted
- Date: 2026-07-16

## Context

Open Work Hub의 앱 활성화와 데이터 소유권은 기존에 workspace 하나의 축으로 취급됐다. 그러나
Community는 회사 전체 리소스이고, Mail과 Planner는 사용자가 소유하는 개인화 도구다.
이 앱들을 선택된 workspace에 묶으면 workspace가 없는 사용자, 여러 workspace의 일정과
메일, 전역 DM·개인 위젯에서 인위적인 범위가 생긴다.

동시에 전역 앱도 관리자가 완전히 끌 수 있어야 하며, UI만 숨기는 것이 아니라 API, AI,
worker를 포함한 모든 실행 경계가 같은 결정을 따라야 한다.

## Decision

### 1. Availability와 resource ownership을 분리한다

- `availability_scope="workspace"` 앱은 workspace entitlement로 활성화한다.
- `availability_scope="platform"` 앱은 platform visibility로 활성화한다.
- Frontend `resourceScope`는 `workspace`, `company`, `personal`, `hybrid`로 데이터 소유권을
  별도로 선언한다.
- Community는 `platform + company`, Mail과 Planner는 `platform + personal`이다.

### 2. Global bootstrap을 별도 정본으로 둔다

- 인증된 전역 앱 셸은 `GET /api/v1/apps/bootstrap`을 사용한다.
- 응답은 활성 platform app, global launcher category, personal tools와
  `workspace_id=null`, `scope=personal` principal을 반환한다.
- workspace bootstrap과 workspace 앱 관리에는 platform app을 포함하지 않는다.
- platform app은 workspace가 없는 사용자도 사용할 수 있다.

### 3. 전역 비활성은 hard gate다

Platform visibility가 off이면 다음 경계를 모두 차단한다.

- App Bar와 global route
- REST API
- AI capability discovery와 execution
- background dispatch, claim, provider I/O

데이터는 삭제하지 않는다. 다시 활성화하면 기존 데이터가 그대로 보인다. 사용자별 앱 숨김
설정은 이번 계약에 포함하지 않는다.

### 4. Personal tools는 고정 런처다

- App Bar에 편집 불가능한 `개인 도구` 런처를 둔다.
- Mail과 Planner는 이 런처 안에서만 표시하며 DB category와 즐겨찾기 pin 대상에서 제외한다.
- 둘 다 비활성일 때 런처를 숨긴다.
- Community는 개인 도구가 아니며 일반 global category 편집 계약을 유지한다.

### 5. Personal data는 사용자 소유다

- Mail account가 사용자 소유의 정본이며 mailbox/message/draft/sync row는 account를 통해
  소유자를 판정한다. 동일 이메일 계정을 합치지 않고 모든 ID와 암호문을 보존한다.
- Planner event는 owner-only이며 workspace와 public visibility를 갖지 않는다.
- 교차 사용자 ID 접근은 존재 여부를 노출하지 않도록 404로 처리한다.
- Mail과 Planner의 canonical Web/API 경로는 `/mail`, `/planner`, `/api/v1/mail`,
  `/api/v1/planner`이며 workspace legacy route를 유지하지 않는다.

### 6. 여러 workspace의 shared source는 origin을 보존한다

- Calendar와 개인 위젯은 사용자가 접근할 수 있고 해당 source app이 활성화된 모든
  workspace의 Meeting/PMS 데이터를 합친다.
- 각 결과는 origin workspace ref를 포함하며 열기와 수정은 원본 workspace에서 수행한다.
- DM 사용자 검색은 workspace와 무관한 전사 사용자 디렉터리를 사용한다.
- 개인 Planner busy block은 회의 가용성에 반영하되 다른 사용자의 제목·장소는 숨긴다.

## Consequences

### Positive

- 개인 도구가 선택된 workspace와 무관하게 일관되게 동작한다.
- 회사 리소스, 개인 리소스, workspace 리소스의 소유권이 명확해진다.
- 관리자 off가 UI와 서버 실행에서 동일한 보안 경계가 된다.

### Negative

- 셸이 global bootstrap과 workspace bootstrap을 합성해야 한다.
- 전역 집계 응답은 origin workspace와 source entitlement를 함께 관리해야 한다.
- 기존 workspace 소유 컬럼과 route를 제거하는 데이터 마이그레이션이 필요하다.

## Related Decisions

- [ADR 0002](0002-mcp-capability-platform.md): AI capability discoverability와 execution gate
- [ADR 0005](0005-registered-llm-workload.md): Mail/Planner LLM workload 실행 계약
