# ADR 0007: 회사 tenant와 workspace 범위 계층

- Status: Accepted
- Date: 2026-07-20

## Context

Open ALM는 같은 회사의 여러 부서가 각자 workspace를 만들고, 회사 전체에서 사용하는 앱과
workspace별 협업 앱을 함께 제공한다. 현재 배포 전략은 동일 코드베이스를 계열사 또는 고객사별
데이터베이스와 설정으로 분리하는 방식이다.

이 구조에서는 workspace 자체를 최상위 tenant로 볼지, 회사를 최상위 tenant로 두고 workspace를
그 하위 작업 영역으로 볼지 명확히 해야 한다. 이 결정이 없으면 URL의 workspace slug, 앱
availability, 데이터 소유권, 실행 principal과 접근 권한이 하나의 scope 개념으로 혼용될 수 있다.

## Decision

### 회사가 최상위 tenant다

현재 Open ALM 배포 하나와 그 데이터베이스·설정 묶음은 회사 tenant 하나를 나타낸다. 회사 tenant는
현재 별도 DB row가 아닌 배포 경계로 암묵적으로 식별한다. 따라서 모든 canonical URL에 회사
slug를 넣거나 모든 테이블에 `company_id`를 추가하지 않는다.

활성 인증 사용자는 이 회사 tenant에 속한다. tenant 수준의 system role과 platform admin 권한이
전역 관리 작업을 통제한다.

### Workspace는 tenant 아래의 협업 범위다

Workspace는 부서·팀·프로젝트의 협업, 접근 제어와 데이터 격리를 위한 하위 범위이며 별도
tenant가 아니다. Workspace 앱의 canonical route는 `/w/:workspaceSlug/...`를 유지하고, global
앱의 canonical route에는 workspace slug를 넣지 않는다.

Workspace slug는 대상 workspace를 찾고 화면 맥락을 복원하는 locator다. slug의 존재 자체는
권한 증거가 아니며, API는 membership, RBAC, resource ACL과 app entitlement를 서버에서 다시
검사한다. 반대로 global route는 workspace 선택이 필요 없다는 뜻이지 공개 접근을 뜻하지 않는다.

### 서로 다른 scope 계약을 분리한다

다음 차원은 서로 대체하지 않는다.

| 차원                | 계약                                          |
| ------------------- | --------------------------------------------- |
| Tenant boundary     | 회사 배포 경계                                |
| App availability    | `platform` 또는 `workspace`                   |
| Resource ownership  | `company`, `personal`, `workspace`, `hybrid`  |
| Route context       | global 또는 workspace                         |
| Execution principal | 요청 시점의 personal 또는 workspace principal |

`platform` availability는 회사 tenant 전체에서 앱을 사용할 수 있다는 뜻이며, 데이터가 company
소유라는 뜻은 아니다. 예를 들어 platform 앱도 personal resource를 다룰 수 있다. `hybrid`는 여러
소유 범위를 조합한다는 표시이며 저장 데이터의 독립적인 소유자가 아니다. Execution principal도
resource ownership과 동일시하지 않는다.

Platform 앱은 global bootstrap과 platform visibility를 사용하고 UI, API, AI tool과 worker의
실행 시점에 동일한 hard gate를 적용한다. Workspace 앱은 workspace bootstrap과 entitlement를
사용한다.

### 회사 resource와 교차 workspace 조회

Company resource는 인증된 tenant 사용자에게 제공하며, 별도 resource ACL이 없는 읽기는 활성
tenant 사용자에게 허용하는 것을 기본으로 한다. 변경 작업은 별도 정책이 없다면 platform admin을
기본 권한으로 한다.

여러 workspace의 데이터를 집계하는 기능은 원본 workspace 식별자를 보존한다. 결과를 반환하거나
원본으로 이동할 때 현재 사용자의 workspace membership, source entitlement와 resource ACL을 다시
검사한다.

Launcher category, 정렬과 개인 pin은 표시 구성일 뿐 접근 권한을 부여하지 않는다. 사용자·조직·팀
단위의 앱 또는 category audience targeting은 이 결정에 포함하지 않으며 별도 계약으로 다룬다.

## Consequences

- 회사 공용 Q&A, 뉴스·리포트와 platform AI 도구는 workspace를 먼저 선택하지 않고도 제공할 수
  있다.
- Workspace slug 유무만으로 앱 availability나 데이터 권한을 판단할 수 없으며 모든 실행 면에서
  server-side gate가 필요하다.
- 앱 설계와 검토에서 availability, resource ownership, route context와 principal을 각각 명시해야
  한다.
- 현재의 암묵적 tenant 식별은 배포·데이터베이스가 회사별로 분리돼 있다는 전제에서만 안전하다.

## Non-Goals

- 하나의 데이터베이스에서 여러 회사 tenant를 운영하는 shared-database multi-tenancy
- 모든 기존 앱을 global 앱으로 전환하는 작업
- 사용자·조직·팀별 앱 또는 launcher category audience targeting
- Workspace 생성·수명주기와 조직 구조 정책의 확정

향후 shared-database multi-tenancy가 필요해지면 명시적인 tenant identifier, 격리 정책과 migration을
새 ADR로 결정한다. 현재의 암묵적 tenant 모델을 shared database에 그대로 사용하지 않는다.

## Related Decisions

- [ADR 0002: MCP Capability Platform](0002-mcp-capability-platform.md)
- [ADR 0003: Company-Scoped Global Apps](0003-company-scoped-global-apps.md)
- [ADR 0006: Platform and Personal Global Apps](0006-platform-personal-global-apps.md)

ADR 0003과 ADR 0006의 global app 계약은 이 tenant 계층 위에서 유지되며 이 ADR이 두 결정을
대체하지 않는다.
