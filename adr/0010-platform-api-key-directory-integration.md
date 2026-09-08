# ADR 0010: 범위 제한 플랫폼 API 키와 디렉터리 연계

- Status: Accepted
- Date: 2026-08-26

## Context

회사별 Open Work Hub 구축에서는 인사·조직 시스템 등 내부 서비스가 조직 계층과 임직원
프로필을 읽어야 한다. 사용자 access token을 자동화에 재사용하면 사람의 세션과 시스템 주체가
혼합되고, platform admin token을 제공하면 필요 이상의 쓰기 권한이 노출된다.

연계 consumer는 최소 권한 키, 명확한 projection, 감사 가능한 수명주기가 필요하다. 운영자는
현재 키를 승인된 시스템에 다시 설치할 수 있도록 관리자 재표시도 요구한다. 이 요구는 평문을
저장하지 않는 인증 설계와 함께 다뤄야 한다.

## Decision

### 사용자 인증과 별도인 opaque credential을 사용한다

`owh_pk_` opaque bearer token을 플랫폼 API 키로 사용한다. 외부 integration route만 이 credential을
인정하며 사용자/session dependency와 상호 교환하지 않는다. 조직·임직원 read scope를
`organization:read`, `people:read`로 분리하고 발급 가능한 scope는 코드 registry로 제한한다.

### 인증 hash와 재표시 암호문을 함께 저장한다

인증은 token의 SHA-256 hash를 constant-time 비교하는 방식으로 수행한다. 관리자 재표시 요구를
위해 원문은 별도 전용 root에서 purpose-derived key로 암호화해 저장한다. root는
`OPEN_WORK_HUB_PLATFORM_API_KEY_ENCRYPTION_KEY`로만 공급하고 DB에는 두지 않는다.

목록에는 짧은 prefix만 표시한다. 발급·재표시 응답은 cache되지 않으며 모든 재표시는 감사한다.
폐기하면 암호문을 삭제하고 status와 폐기자를 기록한다. hash는 폐기된 credential의 식별과
감사 보존을 위해 유지한다.

### 외부 계약은 명시적인 읽기 projection이다

외부 API는 admin/user schema를 그대로 노출하지 않고 허용 필드만 가진 응답 DTO를 사용한다.
현재 상태 기반 page 조회만 제공하며 snapshot, delta, tombstone과 write-back은 제공하지 않는다.
Scope 요구사항은 route의 OpenAPI extension에서 선언하고 관리자 문서 화면도 그 schema에서
operation 목록을 파생한다.

조직 정보는 회사 전역 metadata다. [ADR 0012](0012-company-app-access-without-workspaces.md)에 따라
회사는 배포·DB 경계로 구분하며 외부 projection에 별도 tenant ID를 추가하지 않는다.
디렉터리 조회 scope가 제품 권한을 부여하지 않는다. 현재 조직 그룹의 구성과 앱·자원 권한은
[Organization](../docs/domains/organization/README.md)과
[App Platform](../docs/domains/app-platform/README.md)이 소유한다.

## Consequences

- 자동화 credential이 사람의 세션과 분리되고 consumer별 최소 read scope를 적용할 수 있다.
- DB만 유출되면 hash에서 원문을 복원할 수 없지만, DB와 encryption root를 함께 획득한 공격자는
  활성 키를 복호화할 수 있다. 따라서 root 접근과 재표시 권한을 강하게 통제하고 감사해야 한다.
- Root 회전은 기존 인증을 중단하지 않지만 기존 키의 재표시를 중단한다. 새 키 발급, consumer
  전환, 이전 키 폐기 순서의 운영 절차가 필요하다.
- 현재 상태 paging은 대규모 동기화 중 변경에 대해 일관된 snapshot을 보장하지 않는다. consumer는
  주기적인 전체 재조정을 지원해야 한다.
- 새 scope나 write operation은 registry 추가만으로 끝나지 않으며 전용 DTO, 권한·감사·OpenAPI,
  negative test와 위협 모델 검토가 필요하다.

## Rejected Alternatives

- **관리자 사용자 token 재사용**: 시스템 주체 식별과 최소 권한, 독립 폐기가 불가능하다.
- **API 키 평문 저장**: DB 단독 유출 시 즉시 credential 유출로 이어진다.
- **재표시 불가능한 hash-only 키**: 더 단순하고 강한 모델이지만 승인된 관리자 재설치 요구를
  충족하지 못한다. 향후 요구가 사라지면 암호문 저장을 제거하는 방향을 우선 검토한다.
- **admin user schema 그대로 외부 공개**: 내부 필드가 우발적으로 추가 노출될 수 있어 별도
  projection DTO를 선택한다.

## Non-Goals

- 외부 시스템의 사용자·조직 쓰기 또는 provisioning
- SCIM, webhook, delta feed와 tombstone
- customer-defined scope, OAuth client credential, IP allowlist와 rate limiting
- 디렉터리 연계 credential을 통한 제품 권한·업무 역할 자동 부여

## Related Decisions

- [ADR 0012: 회사·그룹·앱별 권한](0012-company-app-access-without-workspaces.md)
