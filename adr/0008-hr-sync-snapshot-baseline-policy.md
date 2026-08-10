# ADR 0008: HR 동기화 불변 스냅샷과 적용 기준선

- Status: Accepted
- Date: 2026-07-21

## Context

외부 HR 연동은 그룹웨어 사용자·조직 projection과 ERP 인사 원본 수집을 포함한다. 현재 상태만
남기면 어느 실행이 어떤 원본을 읽었는지, source별로 무엇을 baseline으로 삼았는지, 실패한 실행
뒤 어떤 기준으로 변경을 판정했는지 재현할 수 없다. 그룹웨어 원천의 부분 조회를 정상 퇴직으로
오인하면 많은 계정을 즉시 정지할 수도 있다. 반대로 검토하지 않은 ERP 데이터를 기존 사용자나
조직에 바로 적용하면 서로 다른 identity·조직 코드 체계를 잘못 병합할 수 있다.

검토한 대안은 다음과 같다.

- Open ALM의 현재 `users`와 `org_units`만 최신 원천과 비교한다. 저장량은 작지만 원본과 판정 근거를
  재현하지 못한다.
- 변경 event만 저장한다. 변경 조회는 쉽지만 diff 구현 오류나 source schema 변화가 있으면 원본
  기준으로 재계산할 수 없다.
- 매 실행의 원본 snapshot을 불변으로 보존하고, 마지막으로 성공 적용한 snapshot과의 diff를
  별도 change event로 저장한다. 저장량과 개인정보 관리 비용은 늘지만 판정과 재처리를 재현할 수
  있다.

또한 재입사자를 원천 행의 `user_num`, 로그인 ID, 이름·이메일 또는 사번 중 무엇으로 연결할지,
실패·거부 run을 다음 비교 기준으로 사용할지, 각 source가 snapshot만 보존할지 업무 projection까지
적용할지를 명시적인 결정이 필요하다.

## Decision

### 모든 실행의 원본을 불변 snapshot으로 보존한다

원천 조회 전에 durable HR sync run을 만들고, 조회에 성공한 run은 source scope가 계약한 모든
사용자·조직 또는 사용자 원본 행과 값을 정규화 전에 정확히 저장한다. 중복·무효 행도 raw
snapshot에서 제거하지 않고 validation 결과로 구분한다. 원천 접속이 실패해 snapshot을 만들 수
없는 실행도 aggregate run metadata와 안전한 오류 분류를 남긴다.

Raw snapshot과 row-level change event는 365일 보존한다. 현재 baseline snapshot은 365일이
지나도 다음 succeeded baseline이 대체할 때까지 보호한다. Run 상태, baseline 관계, 집계 count,
checksum과 validation/application 결과 같은 aggregate metadata는 자동 만료 없이 장기 보존한다.
보존 후보와 baseline 보호는 `(source_system, scope_key)`별로 계산하며 한 source의 cleanup이 다른
source 또는 scope의 snapshot을 제거하지 않는다.

### Source별 적용 모드를 분리한다

각 source scope는 `snapshot_only` 또는 `projection_apply` 적용 모드를 명시한다. 그룹웨어 domain 1은
검증된 사용자·조직 snapshot을 기존 `users`, `org_units`와 세션에 반영하는
`projection_apply`다. ERP `dbo.UV_H_EMPLOYEE_LIST_DWC`는 승인된 23개 컬럼을 보존·검증하는
`snapshot_only`다.

ERP `succeeded`는 snapshot이 수집·수락됐다는 뜻일 뿐 사용자·조직 또는 인사 master에 적용됐다는
뜻이 아니다. ERP run은 `users`, `org_units`, 인증 세션과 별도 master를 생성·갱신·병합하지 않는다.
ERP와 그룹웨어의 사람 identity, 필드별 정본, 부서 코드 매핑과 충돌 승인 정책은 후속 ADR로
결정한다.

### 마지막 succeeded snapshot만 baseline으로 사용한다

Candidate는 동일한 `(source_system, scope_key)`의 가장 최근 `succeeded` snapshot과만 비교한다.
다른 source나 scope의 snapshot을 baseline으로 섞지 않는다. 수집 중, 적용 중, 거부 또는 실패한
run은 baseline이 아니다. 최초 `projection_apply` run에는 이전 부재를 판정할 근거가 없으므로
현재 유효 행을 initial import하고 퇴직을 추론하지 않는다. 최초 `snapshot_only` run은 원본을
수락할 뿐 업무 projection을 만들지 않는다.

필수 조회 누락, 부분·빈 결과, 알 수 없는 schema, 원천 행 identity·활성 로그인 중복 또는 완전성
검증 실패가 있으면 run 전체를 reject한다. Rejected run은 사용자·조직·세션을 일부라도 변경하지
않고 같은 source scope의 baseline을 유지한다. `projection_apply` source에서 사번이 비어 있거나
중복되어 특정 계정 연결만 모호하면 해당 행을 identity conflict로 차단하되, 완전성이 확인된
나머지 행은 적용한다. ERP `snapshot_only`는 `EMP_NO` 누락·중복을 snapshot 완전성 오류로 보고
run을 거부한다.

### 완전한 최신 snapshot에서의 부재를 퇴직으로 판정한다

`projection_apply`인 그룹웨어에서 검증을 통과한 완전한 candidate에 직전 baseline의 사용자가
없으면 해당 사용자를 퇴직으로 판정한다. 퇴직은 Open ALM 계정을 삭제하지 않고 `suspended`로
바꾸며 모든 활성 세션을 폐기한다.
사용자 UUID, 권한·membership, 사용자 소유 데이터와 관리자가 설정한 `login_blocked` 값은
보존한다.

조직도 완전한 snapshot에서 사라지면 삭제하지 않고 비활성화한다.

### 사번으로 계정 생명주기를 연결한다

그룹웨어 원천 행의 주소는 사용자 `(source_system, domain_num, user_num)`, 조직
`(source_system, domain_num, org_code)`로 보존한다. 퇴직·재입사를 거쳐 같은 사람의 Open ALM
계정을 연결하는 기준은 원천 `EMP_NO` 사번이다.

같은 사번의 재입사는 `user_num`이나 로그인 ID가 바뀌어도 기존 내부 사용자 UUID를 다시
활성화한다. 퇴직 때 폐기한 세션은 복구하지 않으며 사용자는 다시 인증해야 한다. 기존
`login_blocked`도 자동 해제하지 않는다.

새 사번은 새 계정을 만들고 기존 계정과 자동 병합하거나 권한·데이터를 이전하지 않는다. 사번이
누락·중복되거나 새 사번의 로그인 ID가 기존 계정과 충돌하는 등 identity가 모호하면 conflict로
기록하고 자동 반영하지 않는다. 이름, 이메일이나 로그인 ID의 유사성만으로 계정을 병합하지 않는다.
이 계정 생명주기 규칙은 ERP `snapshot_only` 행을 Open ALM 계정에 연결하는 규칙이 아니다.

## Consequences

### Positive

- 모든 퇴직·입사·재입사 판정의 before/after 원본과 적용 결과를 재현할 수 있다.
- 실패·부분 조회가 정상 baseline을 오염시키거나 대량 계정 정지를 유발하지 않는다.
- 같은 사번의 재입사는 기존 UUID와 업무 데이터를 유지하면서 폐기된 세션은 되살리지 않는다.
- Raw snapshot에서 validation과 diff를 다시 실행할 수 있다.
- ERP 원본을 기존 계정과 성급하게 병합하지 않고 후속 master 결정을 위한 재현 가능한 입력으로
  보존할 수 있다.

### Negative

- 매일 사용자·조직 개인정보를 복제하므로 저장 공간, platform-admin 접근 통제, 감사와 365일
  retention 작업이 필요하다.
- Source query/schema를 versioning하고 complete snapshot 여부를 검증해야 한다.
- 사번 품질이 낮거나 새 사번이 기존 로그인 ID와 충돌하면 자동 적용 대신 운영 확인이 필요하다.
- Snapshot 저장과 업무 적용을 분리하면서도 적용 transaction과 동시 실행을 제어해야 한다.
- Source별 baseline과 retention을 격리하고 `succeeded`의 의미를 적용 모드와 함께 조회해야 한다.

## Non-Goals

- 상태 코드별 인사 업무 명칭, row-count 허용 수치와 운영 승인 UI의 세부 구현을 이 ADR에서
  고정하지 않는다.
- HR 동기화가 workspace membership, system role이나 앱 entitlement를 자동 부여·회수하도록
  확장하지 않는다.
- 이름, 이메일 또는 유사도 기반의 자동 사용자 병합을 도입하지 않는다.
- ERP와 그룹웨어를 결합한 인사 master schema, 필드별 정본, 조직 매핑 또는 자동 병합 정책을
  이 결정에서 확정하지 않는다.

## Follow-up

- 상세 run state, validation, diff, 계정·세션과 retention 계약은
  [HR 동기화 계약](../docs/domains/hr/README.md)을 구현 정본으로 유지한다.
- 그룹웨어 View와 source-specific 완전성·컬럼 계약은
  [그룹웨어 인터페이스](../interfaces/groupware/auth-http-database.md)에 기록한다.
- ERP 승인 View, SQL 인증 환경변수 이름과 23개 컬럼의 snapshot-only 계약은
  [ERP 인사 사용자 DB View](../interfaces/erp/employee-database.md)에 기록한다.
- ERP·그룹웨어 통합 인사 master의 identity, source 우선순위, 조직과 충돌 처리 기준은
  후속 [ADR 0011](0011-unified-hr-master.md)에서 결정한다.
