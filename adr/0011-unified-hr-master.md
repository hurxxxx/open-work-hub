# ADR 0011: 사번 기반 통합 인사 마스터

- Status: Accepted
- Date: 2026-07-29

## Context

그룹웨어 domain 1은 사용자·조직 snapshot을 `users`, `org_units`와 세션에 적용하고,
ERP `dbo.UV_H_EMPLOYEE_LIST_DWC`는 원본 snapshot만 보존한다. ADR 0008은 두 원천의
사람 identity, 필드별 정본, 조직 매핑과 rollback이 결정되기 전까지 자동 병합을
금지했다.

두 원천에는 ERP에만 있는 현장 인원과 그룹웨어에만 있는 해외·사업장 계정이 모두
존재한다. 같은 사람인데 사번이 다른 사례는 원천을 정비하거나, 플랫폼 관리자가 ERP
인력과 그룹웨어 사용자를 각각 직접 선택해 통합본 안에서만 수동 연결한다. 이름·이메일을
이용한 자동 추정 병합은 동명이인이나 공용 값 때문에 identity 근거로 사용할 수 없다.

ERP에는 독립 조직 View가 없고 직원 View의 `DEPT_CD`, `DEPT_NM`만 있으므로 ERP
조직은 이 두 컬럼을 그룹화한 평면 부서로만 구성할 수 있다.

## Decision

### 원본과 통합 projection을 분리한다

그룹웨어와 ERP의 불변 raw snapshot을 계속 source별 baseline으로 관리한다. 별도의
통합 master run이 같은 KST 날짜의 최신 `succeeded` 그룹웨어·ERP run 하나씩을
정확한 run ID와 hash로 참조해 완전한 통합 projection을 만든다.

통합 master는 실행별 불변 person, external person, group, conflict row로 저장한다. 최신
`succeeded` master run만 현재 조회본이 되며 실패·거부·누락 run은 기존 현재
조회본을 바꾸지 않는다. 동일 source pair, master schema version, 단조 증가하는
identity resolution revision의 성공 결과는 하나만 허용한다. 정렬된 활성 수동 링크와
인력 구분 수동 지정 집합의 hash를 checksum과 provenance에 포함하되, 관리 변경 후 과거
상태를 잘못 재사용하지 않도록 hash가 아니라 revision을 idempotency fence로 사용한다.

ERP source run은 계속 `snapshot_only`이고 그룹웨어는 계정 생명주기를 소유한다.
그러나 업무 앱은 raw snapshot이나 source 전용 table을 직접 읽지 않고 아래 HR
consumer view 계약 중 필요한 기준을 명시적으로 선택한다.

### 하나의 HR 경계에서 소비 기준을 명시한다

여기서 “통합본”은 모든 소비자가 같은 합집합 row를 읽거나 person 정보를 물리적인
단일 table에 넣는다는 뜻이 아니다. 정확한 source run으로 만든 불변 master version과
그 위의 versioned consumer view 계약을 한 HR 경계가 소유한다는 뜻이다.

| 기준 | 포함 범위 | canonical field와 현재 consumer |
| ---- | --------- | ------------------------------- |
| `erp` | 최신 `succeeded` master에서 ERP source row가 연결된 `matched`, `erp_only`, `identity_conflict` person만 포함한다. `groupware_only`와 격리 conflict row는 제외한다. | ERP view v2는 사번, 이름, 부서 코드·명, 직위, 직종, 생년월일, 입사일, 전화번호 9개 field를 materialize한다. 종합검진과 외부 HR 연계가 이 기준을 사용한다. |
| `groupware` | 검증을 통과해 그룹웨어 계정·조직 projection에 적용 가능한 사람과 조직만 포함한다. ERP-only 사람을 계정으로 만들지 않는다. | 로그인 ID, 계정 상태, 이메일, 그룹웨어 조직 경로와 계정 연결은 그룹웨어를 정본으로 사용한다. 기존 `users`, `org_units`, 세션과 사용자·권한 관리가 이 기준을 계속 사용한다. |
| `integrated` | 최신 `succeeded` master의 전체 person 합집합, 그룹웨어 안정 식별자로 보존한 해외/외부 인력, source-qualified group, reconciliation/conflict 정보를 포함한다. | ERP 연결 person의 이름·직위/직종·그룹은 ERP를, 로그인·계정 연결·그룹웨어 조직 경로는 그룹웨어를 사용한다. 향후 두 원천의 정합 상태가 필요한 앱만 이 기준을 명시적으로 선택한다. |

한 consumer가 요청 중 기준을 바꾸거나, 선택한 기준이 없을 때 다른 기준이나 raw
snapshot으로 조용히 fallback하지 않는다. 종합검진은 특히 raw ERP typed reader를
직접 호출하지 않고 master의 `erp` 기준 projection에서 ERP-connected people만 읽는다.
이 때문에 그룹웨어-only 계정이 검진 모집단에 섞이지 않고, 그룹웨어 사번 충돌이
있더라도 유일한 ERP person은 `identity_conflict` 상태와 함께 보존할 수 있다.

Master는 각 versioned view가 계약한 canonical field를 실행 시점에 함께 materialize한다.
ERP view v2의 계약은 위 9개 field로 제한하며 ERP의 나머지 14개 field가 필요해지면 consumer
view schema를 올리고 master materialization과 projection hash를 함께 migration한다. Master
run ID·schema version·checksum, 정확한 ERP/그룹웨어 run ID와 snapshot hash, row별 source
snapshot row ID와 reconciliation status가 provenance다.
Source snapshot row ID는 raw row를 영구 참조하는 외래키가 아니라 당시 입력을 식별하는
불변 값이다. 365일 retention으로 raw row가 삭제된 뒤에도 master의 canonical value와
provenance ID, 장기 보존 source run metadata/hash만으로 consumer view가 계속 동작해야
하며 raw snapshot을 다시 dereference하지 않는다.

### 사번만 사람 identity로 사용한다

사번은 앞뒤 공백을 제거하고 대문자로 바꾼 값으로 비교한다. 한 source snapshot
안에서 비어 있지 않고 유일한 사번만 사람 identity 후보가 된다.

- ERP와 그룹웨어에 유일한 동일 사번이 하나씩 있으면 `matched`다.
- 한쪽에만 유일한 사번이 있으면 `erp_only` 또는 `groupware_only`다.
- 그룹웨어 활성 사용자 중 빈 사번, `Z0000`, `Z00000`은 사번보다 안정적인
  `(domain_num, user_num)` source identity로 별도 external person에 보존하고
  `해외/외부`로 분류한다. 이 세 값은 이름이 ERP와 같아도 수동 매칭 후보가 아니다.
- 그 밖의 중복 그룹웨어 사번은 master person으로 만들지 않고 conflict row로 격리한다.
  같은 정규화 사번의 유일한 ERP row가 있으면 그 ERP
  person은 `identity_conflict`로 보존하되 어떤 그룹웨어 row도 연결하지 않는다.
- 이름, 이메일, 전화번호 또는 조직 유사성으로 자동 병합하거나 사번을 교정하지
  않는다.

서로 다른 실사번의 source-only 행은 별도 사람으로 남는다. 관리자는 현재 master의
`groupware_only` 사용자와 `erp_only` 인력을 양쪽 전체 목록에서 각각 검색·선택해 연결한다.
이름은 검색과 확인을 돕는 정보일 뿐 후보 제한이나 자동 identity 근거가 아니다. 이름이
다른 두 사람을 연결할 때는 확인 사유를 필수로 남긴다. 관리자가 그룹웨어 안정 식별자와
ERP 사번을 명시적으로 연결하면 다음 master에서 ERP 사번을 canonical person code로 사용하는
`matched/manual`이 된다. 생성·해제 actor와 시각을 감사하며 `users.employee_code`,
그룹웨어·ERP 원본 사번, 계정·권한은 변경하지 않는다. 빈 사번과 `Z0000`, `Z00000` external
person, 식별 conflict row는 수동 매핑 대상으로 제공하지 않는다.
양쪽에 서로 다른 관리자 지정 인력 구분이 활성화되어 있으면 어느 분류를 승계할지
불명확하므로 매핑을 거부하고 관리자가 먼저 분류를 정리하게 한다. 한쪽에만 지정이 있거나
양쪽 지정이 같으면 ERP 지정, 그룹웨어 지정 순으로 같은 유효 분류를 materialize한다.

`workforce_category`와 reconciliation은 분리한다. 자동 분류(`inferred`)는 자연 또는 수동
매칭을 `internal`, ERP-only를 `field`(현장직·ERP 전용), placeholder/빈 사번을 `external`,
groupware-only·identity conflict를 `unresolved`로 계산한다. 플랫폼 관리자는 기본 분류의
표시 이름과 설명을 수정하고 custom 분류를 추가·수정·보관할 수 있다. 또한 ERP 연결 사람은
ERP 사번, ERP가 없는 사람은 그룹웨어 안정 식별자를 기준으로 유효 분류(`effective`)를 직접
지정하거나 자동 분류로 되돌릴 수 있다. 수동 지정은 불변 이력과 활성·해제 revision을 보존하고
다음 master부터 자동 분류보다 우선한다. Conflict row에는 수동 분류를 지정하지 않는다.
분류 이름 변경은 표시 metadata 변경이며, 사람별 지정·초기화만 resolution revision과 새
master를 만든다.

### 필드별 정본과 그룹을 명시한다

ERP 연결이 있는 사람은 ERP의 이름, 직위·직종과 부서를 정본으로 사용한다.
그룹웨어 연결이 있으면 로그인 ID, 인증 계정 연결, 이메일과 그룹웨어 조직 경로를
사용한다. 그룹웨어 이메일이 비어 있을 때만 ERP 이메일을 fallback으로 사용한다.

ERP 그룹은 승인된 직원 View의 `DEPT_CD`, `DEPT_NM`을 `GROUP BY`한 평면 목록이다.
코드 또는 이름이 비어 있거나 한 정규화 코드가 여러 이름에 대응하면 ERP candidate를
거부한다. ERP 연결 사람은 ERP 부서를 통합 그룹으로 사용한다. ERP에 없는
그룹웨어-only 사람만 그룹웨어 primary 조직을 fallback 그룹으로 사용한다.
ERP 부서 코드와 그룹웨어 조직 코드를 자동 매핑하지 않으며 group identity에는
source system을 포함한다.

### 운영과 접근을 제한한다

통합 배치는 그룹웨어 03:10, ERP 03:20 이후 기본 03:30 KST에 독립 실행한다. 한쪽의
당일 성공 snapshot이 없으면 적용하지 않는다. 플랫폼 관리자는 기존 배치 작업
화면에서 수동 재실행할 수 있다.

`building` 또는 `failed` master 시도는 관리자 배치 상태에서 정상으로 표시하지 않는다.
Consumer head는 latest `succeeded` master인 last-known-good view이며, 종합검진은 현재 별도
age threshold로 이를 stale 처리하지 않는다. 새 source 수집이나 master build가 실패해도 직전
성공 head를 자동으로 unavailable로 바꾸지 않는다. 다만 호환되는 `hr-master-v5` 성공본이
없거나 ERP view schema, projection hash, 필수 field 또는 row count 검증이 실패하면 다른 기준
projection이나 raw source로 fallback하지 않고 fail-closed한다.

관리자용 통합 master 조회, 수동 매칭 생성·해제, 인력 구분 catalog와 사람별 지정 관리는
platform admin으로 제한한다. 승인된 외부 시스템은 [ADR 0012](0012-platform-api-keys-and-rest-integrations.md)의
공통 플랫폼 API 키와 `hr:read` scope를 사용해 별도 allowlist REST projection만 읽을 수 있다.
사용자 session token을 기계 연계에 재사용하거나 API key로 관리자 mutation을 호출하지 않는다.
두 조회 경계 모두 개인정보 값·사번·이름·검색어·자유 입력 사유를 감사 payload에 넣지 않는다.
수동 매칭과 사람별 분류 변경은 현재 master의 정확한 source pair를 하나의 단조 증가
resolution revision으로 재생성한다. Master row는 완료 후 365일 보존하며 현재 성공본은
다음 성공본이 생길 때까지 보호한다. 과거본 수동 활성화나 원천 인라인 수정은 제공하지 않는다.
관리자 화면의 재생성 대기는 별도 master 상태 조회로 요청 revision의 `succeeded` 또는
`failed`를 확인한다. 실패 또는 timeout에서는 폴링을 중지하고 직전 성공 head를 계속 표시한다.
수동 매핑된 person은 `identity_resolution_kind=manual` 필터로 별도 조회하고 상세에서 링크를
해제할 수 있다.

## Consequences

- ERP/GW 합집합을 한 화면에서 조회하면서도 로그인 계정이 없는 인원을 `users`로
  만들지 않는다.
- 잘못된 사번은 정상 인원의 반영을 막지 않지만 conflict로 명시적으로 드러난다.
- Source별 조직 체계는 보존되며 ERP 평면 부서에 존재하지 않는 계층을 추론하지
  않는다.
- 종합검진은 master의 ERP 기준 view로 전환하되 Open ALM 계정·권한은 그룹웨어 projection을
  유지한다.
- 관리자 매핑과 인력 구분은 integrated 정합 projection만 바꾸며 ERP 기준 view의 인원,
  9개 field와 projection hash를 바꾸지 않는다.
- 향후 consumer는 `erp`, `groupware`, `integrated` 중 업무 기준과 freshness/failure 정책을
  명시하고 전환 migration을 별도로 검증해야 한다.

## Related contracts

- [ADR 0008](0008-hr-sync-snapshot-baseline-policy.md)
- [HR 동기화 계약](../docs/domains/hr/README.md)
- [ERP 인사 사용자 DB View](../interfaces/erp/employee-database.md)
