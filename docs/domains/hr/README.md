# HR 동기화 계약

이 문서는 외부 인사 원천의 수집, 원본 보존, source별 projection 적용, 변경 판정과 계정
생명주기의 정본이다. 그룹웨어의 실제 View와 컬럼 매핑은
[그룹웨어 인증 HTTP/DB 연동 정보](../../../interfaces/groupware/auth-http-database.md),
ERP의 승인 View와 23개 컬럼 계약은
[ERP 인사 사용자 DB View](../../../interfaces/erp/employee-database.md),
스냅샷과 기준선 선택의 아키텍처 결정은
[ADR 0008](../../../adr/0008-hr-sync-snapshot-baseline-policy.md)을 따른다.

HR 동기화는 회사 tenant 전체의 관리 작업이다. 현재 회사 tenant는 배포와 데이터베이스
경계로 식별하므로 HR 실행·스냅샷에 `workspace_id`를 사용하지 않는다. 실행 이력과 원본
열람은 platform admin 권한으로 제한한다.

## Source 적용 모드

각 source scope는 수집 결과를 업무 projection에 적용하는지 명시해야 한다. 한 source의 모드를
다른 source에 암묵적으로 상속하지 않는다.

| Source scope                     | 모드               | 현재 동작                                                                                              |
| -------------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------ |
| Groupware domain 1               | `projection_apply` | 사용자·조직 snapshot을 검증한 뒤 `users`, `org_units`와 세션에 적용한다.                               |
| ERP `dbo.UV_H_EMPLOYEE_LIST_DWC` | `snapshot_only`    | 23개 사용자 컬럼과 평면 부서 원본을 snapshot으로 수집·검증하고 `users`, `org_units`에는 직접 적용하지 않는다. |

ERP와 그룹웨어 snapshot을 결합한 인사정보 master의 identity, 필드별 정본과 조직 규칙은
[ADR 0011](../../../adr/0011-unified-hr-master.md)을 따른다. 통합 master는 source run과
분리된 derived projection이며 기존 인증 사용자·조직 projection을 대체하지 않는다.
외부 시스템이 기준별 projection을 읽는 endpoint, API key, page와 field 계약은
[통합 인사 REST API](rest-api.md)를 따른다.

## Consumer 기준 projection

HR 데이터 consumer는 raw snapshot 저장 구조를 알지 않고 HR domain의 한 typed read 경계에서
업무 기준을 `erp`, `groupware`, `integrated` 중 하나로 선언한다. “통합 인사정보”는 모든
consumer가 물리적인 단일 table이나 같은 합집합 row를 읽는다는 뜻이 아니라, 정확한 source
version과 provenance를 공유하는 consumer view 계약의 모음이다. 선택한 기준의 schema·hash·row
검증이 실패할 때 다른 기준으로 자동 전환하지 않는다.

| 기준 | 포함 범위 | canonical field와 사용처 |
| ---- | --------- | ------------------------- |
| `erp` | 최신 성공 master person 중 ERP snapshot row가 연결된 `matched`, `erp_only`, `identity_conflict`만 포함한다. `groupware_only`와 격리 conflict row는 제외한다. | ERP view v2는 사번, 이름, 부서 코드·명, 직위, 직종, 생년월일, 입사일, 전화번호 9개 field를 반환한다. 종합검진 모집단과 외부 HR 연계가 사용한다. |
| `groupware` | 검증된 그룹웨어 사용자·조직 중 계정 identity를 안전하게 확정할 수 있는 row를 포함한다. ERP-only person을 포함하지 않는다. | 로그인 ID, 계정 상태, 이메일, 그룹웨어 조직 경로와 계정 연결을 정본으로 사용한다. 기존 `users`, `org_units`, 세션과 Open ALM 사용자·권한 관리가 계속 사용한다. HR sync는 system role이나 workspace/team membership을 부여하지 않는다. |
| `integrated` | 최신 성공 master의 전체 person, source-qualified group와 reconciliation/conflict 상태를 포함한다. | ERP 연결 person의 이름·직위/직종·그룹은 ERP, 로그인·계정 연결·그룹웨어 조직 경로는 그룹웨어가 정본이다. 두 원천의 합집합이나 정합 상태가 필요한 future app만 명시적으로 선택한다. |

HR typed read metadata는 선택한 기준에 필요한 master/source run ID, schema version,
checksum/hash와 수집 시각을 제공한다. 각 업무 API는 이 metadata 중 화면·감사·freshness에
필요한 항목만 노출하고, 내부 consumer는 전체 metadata를 결과 provenance와 계약 검증에 사용한다.

## 정본 용어

| 용어               | 의미                                                                          |
| ------------------ | ----------------------------------------------------------------------------- |
| sync run           | 한 source scope를 한 번 수집·검증·적용하려는 실행 시도                        |
| raw snapshot       | 한 run에서 원천이 반환한 모든 행과 값을 정규화 전에 그대로 보존한 불변 데이터 |
| candidate snapshot | 검증과 비교를 기다리는 현재 run의 raw snapshot                                |
| baseline snapshot  | 같은 source scope에서 가장 최근 `succeeded` run의 snapshot                    |
| change event       | candidate와 baseline의 결정론적 비교 결과                                     |
| application action | `projection_apply` source의 change event를 사용자·조직과 세션에 적용한 결과   |
| employee number    | 원천 `EMP_NO` 사번. 그룹웨어 계정 생명주기와 통합 master 사람 identity의 기준이다. |

Source scope는 `(source_system, scope_key)`로 구분하며 baseline, 동시 실행과 retention의 최소
격리 단위다. 그룹웨어 사용자와 조직의
원천 행 식별자는 각각 `(source_system, domain_num, user_num)`과
`(source_system, domain_num, org_code)`다. 원천 행 식별자는 snapshot 행의 출처를 찾는
주소이고, 사번은 그룹웨어 projection에서 퇴직·재입사 시 같은 Open ALM 계정을 연결하는 생명주기
식별 기준이다. ERP scope에서는 `EMP_NO`를 snapshot 완전성 identity로 검증한다. 통합 master는
앞뒤 공백 제거와 대문자 정규화 후 사번만으로 사람을 결합하지만, 이 결합은 Open ALM 계정 identity나
권한 이전을 의미하지 않는다.

## 실행과 상태

모든 실행은 원천 조회 전에 durable run metadata를 만든다. 원천 접속 자체가 실패해 raw
snapshot을 만들 수 없더라도 실패한 시도와 오류 분류는 run metadata에 남긴다. 오류에는
credential, 접속 문자열이나 원본 개인정보를 기록하지 않는다.

| 상태         | 계약                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------ |
| `pending`    | 실행 식별자, source scope, trigger와 시작 시각을 기록했다.                                       |
| `capturing`  | 원천 조회 결과를 raw snapshot으로 저장 중이다.                                                   |
| `validating` | raw snapshot, row count, schema version과 checksum을 보존하고 완전성을 검증 중이다.              |
| `applying`   | `projection_apply` source가 검증을 통과한 change event를 하나의 transaction으로 처리 중이다.     |
| `succeeded`  | 해당 source mode의 수집·검증과 필요한 적용이 완료되어 다음 run의 baseline이 될 수 있다.          |
| `rejected`   | snapshot이 누락·부분 조회·schema/identity 검증 실패로 거부되었다. 업무 데이터는 변경하지 않는다. |
| `failed`     | 수집 또는 적용 중 기술 오류가 발생했다. 업무 데이터와 baseline은 변경하지 않는다.                |

같은 source scope에서는 한 번에 하나의 run만 적용한다. 재시도와 중복 전달은 run 또는
idempotency identity로 식별하고 change event와 application action을 중복 생성하지 않는다.
Snapshot 저장 transaction과 업무 반영 transaction을 분리해 적용 실패 후에도 수집 증거를
보존하되, 업무 반영은 사용자·조직 변경과 세션 폐기를 포함해 원자적으로 commit한다.
`snapshot_only` source는 검증 후 `applying`이나 업무 반영 없이 `succeeded`가 될 수 있다. 이때
`succeeded`는 snapshot 수락을 의미하며 projection이나 master 반영을 의미하지 않는다.

## Raw snapshot 계약

- 원천 조회에 성공한 모든 run은 source scope가 계약한 사용자·조직 또는 사용자 원본 행을 누락
  없이 저장한다.
- 원문 컬럼명, null과 원문 값을 trimming, case folding, 기본값 대입 같은 정규화 전에 저장한다.
- 중복되거나 유효하지 않은 행도 raw snapshot에서는 제거하지 않는다. 별도 canonical projection과
  validation result가 문제를 표시한다.
- Snapshot에는 실행 식별자, source scope, versioned query/schema, 원천 행 종류, row ordinal과
  checksum을 함께 기록한다. Row ordinal은 수집 증거이며 identity 의미를 갖지 않는다.
- Raw snapshot과 이미 확정한 change event는 수정하지 않는다. 재처리는 새 run으로 수행한다.
- 원천 전체를 의미 없이 `SELECT *`로 확장하지 않는다. 명시적으로 versioning한 조회 projection이
  그 run에서 보존해야 할 정확한 원본 범위다.

## 검증과 baseline 선택

Candidate는 다음 조건을 모두 통과해야 baseline 비교와 source mode에 따른 수락·적용 대상이 된다.

- source scope가 계약한 모든 필수 entity 조회가 성공했다.
- query/schema version과 필수 컬럼이 인식 가능하다.
- 원천의 완전성 기준과 허용된 row-count 변화 범위를 통과했다.
- 필수 원천 행 identity가 존재하고 source scope 안에서 유일하다.
- `projection_apply` source는 활성 사용자 로그인 identity와 조직 참조가 일관된다.
- Snapshot checksum과 저장 row count가 실제 수집 결과와 일치한다.

누락, 부분 조회, 빈 결과, schema 불일치, 원천 행 identity·활성 로그인 중복 또는 급격한 누락이
있으면 run을 `rejected`로 끝낸다. 완전한 candidate 안에서 특정 사용자가 사라진 것은 부분 조회와
다르며 아래 퇴직 규칙을 적용한다. 사번이 비어 있거나 중복되어 자동 계정 연결만 모호한 행은
`identity_conflict`로 기록하고 해당 행의 생성·재활성화를 차단한다. 다른 확정적 행은 반영한다.
수동 실행의 `force` 의미는 source별로 다르다.

- 그룹웨어는 관리자가 원천 건수와 퇴직 후보를 확인한 뒤 수동 실행으로 대량 퇴직·조직 비활성
  guard만 명시적으로 우회할 수 있다. 빈/부분 snapshot과 source identity·활성 로그인 중복은
  우회하지 않는다.
- ERP는 수동 실행이 비활성 스케줄의 실행 gate만 우회한다. 빈 결과, schema 불일치, `EMP_NO`
  누락·중복과 대량감소 검증을 포함한 snapshot 완전성 guard는 수동 실행에서도 우회하지 않는다.

비교 기준은 같은 `(source_system, scope_key)`의 가장 최근 `succeeded` snapshot 하나뿐이다. 다른
source나 scope의 snapshot을 baseline으로 섞지 않는다. `pending`,
`capturing`, `validating`, `applying`, `rejected`, `failed` run은 baseline으로 선택하지 않는다. 최초
`projection_apply` run은 baseline이 없으므로 현재 유효 행을 `initial_import`로 반영하고 과거
부재나 퇴직을 추론하지 않는다. 최초 ERP `snapshot_only` run은 원본을 수락할 뿐 사용자를
생성하거나 과거 부재를 판정하지 않는다.

## Projection 적용 원천의 사용자 변경 판정

다음 규칙은 현재 `projection_apply`인 그룹웨어에만 적용한다. ERP `snapshot_only`에는 사용자
변경 판정이나 자동 처리를 수행하지 않는다.

| Baseline | Candidate | 과거 성공 이력   | 판정                       | 자동 처리                                          |
| -------- | --------- | ---------------- | -------------------------- | -------------------------------------------------- |
| 있음     | 없음      | 해당 없음        | `retired`                  | 기존 계정을 정지하고 활성 세션을 폐기한다.         |
| 없음     | 있음      | 같은 사번이 없음 | `hired`                    | 새 계정을 생성·활성화한다.                         |
| 없음     | 있음      | 같은 사번이 있음 | `rehired`                  | 같은 내부 UUID의 계정을 다시 활성화한다.           |
| 있음     | 있음      | 해당 없음        | `changed` 또는 `unchanged` | 상태·프로필·조직 필드의 canonical diff만 반영한다. |

퇴직 판정은 검증을 통과한 완전한 candidate에서 baseline의 원천 사용자 행이 사라진 경우에만 한다.
원천이 명시적인 비재직 상태 행을 제공하면 기존 계정은 같은 방식으로 정지하되, 원천 상태 코드의
업무 명칭은 source interface가 확인한 범위에서만 사용한다.

같은 사번의 재입사는 `user_num`이나 로그인 ID가 바뀌어도 기존 Open ALM 사용자 UUID를 유지한다.
새 사번은 같은 이름, 이메일 또는 과거 로그인 ID와 닮았더라도 새 사람·새 계정으로 처리하며
기존 계정과 자동 병합하거나 권한·데이터를 이전하지 않는다. 새 사번이 기존의 고유 로그인 ID와
충돌하거나 사번이 누락·중복되어 한 계정을 고를 수 없으면 identity conflict로 기록하고 해당
행을 자동 생성·재활성화하지 않는다. 이름, 이메일, 로그인 ID만으로 사람을 추정해 병합하지 않는다.

## Projection 적용 원천의 계정 상태 불변식

퇴직 처리는 계정을 삭제하지 않는다.

- 사용자 상태를 `suspended`로 바꾸고 모든 활성 인증 세션을 폐기한다.
- 내부 사용자 UUID, HR 이력, 사용자 소유 데이터, system role, workspace/team membership과
  기타 기존 권한 연결을 보존한다.
- 관리자가 별도로 설정한 `login_blocked` 값을 변경하지 않는다.

같은 사번의 재입사는 보존한 계정의 상태를 `active`로 바꾸지만 퇴직 때 폐기한 세션을 복구하지
않는다. 사용자는 새로 인증해야 한다. `login_blocked`가 이미 `true`이면 HR 재입사가 이를 해제하지
않으므로 계정은 active여도 관리자가 차단을 해제하기 전까지 로그인할 수 없다.

HR 동기화는 workspace membership, system role, 앱 entitlement를 새로 부여하거나 제거하지
않는다. 조직 snapshot에서 사라진 조직은 삭제하지 않고 비활성화하며, 사용자와 조직의 원본 및
change event는 같은 run으로 추적한다.

## ERP snapshot-only 경계

ERP는 승인된 `dbo.UV_H_EMPLOYEE_LIST_DWC`의 23개 컬럼을 사용자 raw snapshot으로 저장하고,
같은 View의 `DEPT_CD`, `DEPT_NM`을 그룹화한 평면 부서 목록을 조직 raw snapshot으로 저장한다.
ERP run 자체는 `org_units`나 통합 master를 직접 생성·갱신하지 않으며 결과는
`projection_applied = false`, `master_rows_applied = 0`을 유지한다.

ERP snapshot 수집은 다음 동작을 하지 않는다.

- 기존 플랫폼 `users`의 이름, 이메일, 사번, 직급, 조직 또는 상태 변경
- 사용자 생성·정지·재활성화와 인증 세션 폐기
- ERP 부서 코드와 그룹웨어 조직 코드의 자동 연결
- ERP source run 안에서 ERP와 그룹웨어 행을 직접 결합

`load_latest_accepted_erp_employee_snapshot()`은 최신 `succeeded` ERP run의 행 수·schema
version·필수 field와 날짜 형식을 확인하는 HR domain 내부의 source typed reader다. v1/v2
source 호환성 확인과 migration·진단에는 사용할 수 있지만 업무 앱의 employee-list 경계가
아니다. 업무 앱은 raw row나 이 source reader를 직접 호출하지 않고 위의 기준 projection을
선택한다. Master builder는 평면 부서 snapshot이 있는 v2 run만 입력으로 허용한다.

행 데이터가 필요 없는 source 수집 상태 확인은
`load_latest_accepted_erp_employee_snapshot_metadata()`를 사용한다. 이 interface는 run ID,
schema version, 수집 시각, snapshot hash와 집계 행 수만 반환하며 개인정보 raw row를 조회하지
않는다.
HR 밖의 호출 도메인은 `HrSyncUserSnapshotRow.raw_payload`의 JSON key, snapshot table 또는
source typed reader를 직접 조회하지 않는다. ERP source의 `succeeded`는 snapshot 수락일 뿐
consumer용 master가 fresh하거나 Open ALM 계정 identity가 확정됐다는 뜻이 아니다.

## 통합 인사 master

통합 master run은 같은 KST 날짜의 최신 `succeeded` ERP·그룹웨어 run ID와 snapshot hash를
입력으로 고정한다. 앞뒤 공백을 제거하고 대문자로 정규화한 사번이 양측에서 각각 하나일 때만
`matched`로 결합한다. 이름·이메일 또는 조직 유사성은 identity에 사용하지 않는다.

유일한 실사번이 한쪽에만 있으면 `erp_only` 또는 `groupware_only` person으로 보존한다.
활성 그룹웨어 사용자의 빈 사번, `Z0000`, `Z00000`은 중복 conflict가 아니라 안정적인
`(domain_num, user_num)` source identity별 external person으로 보존하고 `해외/외부`로
분류한다. 그 밖의 중복 그룹웨어 사번은 conflict row로 격리하므로 다른 정상 행의 반영을
막지 않는다. 같은 정규화 사번의 유일한 ERP row가 있으면 ERP person은
`identity_conflict`로 보존하되 어떤 그룹웨어 row도 연결하지 않는다. ERP 연결 person의
이름·직위/직종·그룹은 ERP를, 로그인 ID·인증 계정·이메일과 그룹웨어 조직 경로는 그룹웨어를
정본으로 사용한다. 그룹웨어 이메일이 비어 있을 때만 ERP 이메일을 사용한다.

ERP 연결 person은 ERP 평면 부서를 그룹으로 사용한다. `groupware_only` person은 그룹웨어
primary 조직을 fallback 그룹으로 사용한다. 두 source의 조직 코드나 이름을 이용해 자동
매핑하지 않는다.

Master는 versioned consumer view가 raw snapshot 없이 동작하는 데 필요한 canonical field를
불변으로 materialize한다. `hr-master-erp-employee-v2`는 사번, 이름, 부서 코드·명, 직위,
직종, 생년월일, 입사일, 전화번호 9개 field와 그 projection hash를 계약한다. ERP raw
snapshot이 수집하는 나머지 14개 field는 이 view나 master person에 복사됐다고 간주하지 않는다.
추가 ERP field가 필요하면 consumer view schema version을 올리고 master field, build 검증,
projection hash와 consumer를 함께 migration한다. Groupware와 integrated 기준은 앞에서 정한
field authority에 따라 각자의 versioned contract만 materialize한다.

Master provenance는 master run ID·schema version·checksum, 정확한 ERP/그룹웨어 source run ID와
snapshot hash, row별 source snapshot row ID와 reconciliation status다. Source snapshot row ID는
live foreign key가 아니라 당시 입력을 가리키는 불변 provenance 값이다. Raw row가 retention으로
삭제된 뒤에는 이를 dereference하지 않고 master에 복사한 canonical value와 장기 보존 source run
metadata/hash로 ERP·integrated view를 계속 제공한다.

Master row는 실행별 불변 데이터이며 최신 `succeeded` master run만 현재 조회본이 된다. 통합
실패나 당일 source pair 누락은 직전 성공 master를 변경하지 않는다. 플랫폼 관리자 목록·상세
조회에서는 자동 분류와 유효 분류를 분리해 표시한다. 기본 자동 분류는 `internal`,
`field`(현장직·ERP 전용), `external`, `unresolved`이고, 관리자는 기본 구분의 표시 이름·설명을
수정하거나 custom 구분을 추가·수정·보관할 수 있다. 사람별 유효 분류는 ERP 연결 사람의 ERP
사번 또는 ERP가 없는 사람의 그룹웨어 안정 식별자에 수동 지정하며 자동 분류보다 우선한다.
관리자는 수동 지정을 초기화해 자동 분류로 되돌릴 수 있다. Conflict row에는 수동 분류를
지정하지 않는다.

관리자는 현재 master의 전체 `groupware_only`와 `erp_only` 목록에서 각 사용자를 검색하고 직접
선택해 수동 매칭을 생성·해제할 수 있다. 이름은 검색·검토 정보이지 후보 제한이나 자동 identity
근거가 아니다. 이름이 다른 사용자를 연결할 때는 확인 사유가 필수다. 빈 사번과 `Z0000`,
`Z00000` external person, 식별 conflict row는 매핑 대상으로 제공하지 않는다. 링크는 그룹웨어
`source_identity`와 ERP 사번을 연결하며 원천 사번·Open ALM 계정·권한을 변경하지 않는다.
다음 성공 master에서는 두 source-only row를 하나의 `matched` person으로 materialize하고
`identity_resolution_kind=manual`로 표시한다. 관리자 목록은 이 값을 필터로 받아 수동 매핑된
사람만 조회할 수 있으며, 상세에서 링크를 해제하면 다음 성공 master에서 다시 두 source-only
row로 분리한다.
양쪽에 서로 다른 관리자 지정 인력 구분이 활성화되어 있으면 매핑을 거부하고 분류를 먼저
정리하게 한다. 한쪽 지정만 있거나 양쪽 지정이 같으면 ERP 지정, 그룹웨어 지정 순으로 유효
분류를 materialize한다.

수동 링크나 사람별 인력 구분 지정 변경마다 하나의 identity resolution revision을 증가시키고
활성 링크·분류 지정 집합 hash와 함께 master 입력·checksum·provenance에 기록한다. 각 링크와
분류 지정에는 활성 revision과 해제 revision을 저장하므로 builder는 캡처한 revision의 일관된
snapshot만 읽는다. 동일 source pair라도 revision이 다르면 새 불변 master를 만들며, 변경 해제로
과거 집합과 hash가 같아져도 과거 run을 현재본으로 재사용하지 않는다. 변경 직후에는 당일 source
탐색이 아니라 현재 master의 정확한 ERP·그룹웨어 run ID로 재생성한다.
`building`·`failed` 최신 시도는 관리자 배치 상태에 노출하되 consumer head로 선택하지 않는다.
관리자 화면은 목록 전체를 반복 조회하지 않고 master 상태 endpoint로 요청한 revision을
폴링한다. 요청 revision의 `failed` 시도를 확인하거나 대기 시간이 초과되면 자동 갱신을
중지하고 매핑은 저장되었지만 통합본 반영은 실패했음을 표시한다.
종합검진은 별도 age threshold 없이 latest `succeeded` `hr-master-v5`를 last-known-good head로
읽으므로 최신 시도의 실패만으로 직전 성공본을 stale 또는 unavailable로 만들지 않는다. 호환되는
master 성공본이 없거나 ERP view schema, projection hash, 필수 field 또는 row count 검증이
실패하면 raw source나 다른 기준으로 fallback하지 않고 fail-closed한다.

## 보존과 접근

- Raw snapshot과 생성된 row-level change event는 run 완료 시각부터 365일 보존한다.
- Retention 후보는 `(source_system, scope_key)`별로 계산한다. 한 source의 cleanup이 다른 source
  또는 scope의 snapshot을 삭제해서는 안 된다.
- 각 source scope의 현재 baseline을 구성하는 raw snapshot은 365일이 지나도 같은 scope의 다음
  `succeeded` run이 baseline을 대체할 때까지 삭제하지 않는다. 대체된 뒤에는 일반 365일 정책을
  적용한다.
- Master row도 완료 후 365일 보존하고 현재 `succeeded` master는 다음 성공본이 대체할 때까지
  보호한다. Source raw retention과 master consumer availability는 분리하며 raw cleanup이 master
  canonical value나 provenance ID를 null로 바꾸거나 현재 view를 깨뜨리지 않는다.
- Run 상태, 시각, source scope, baseline 관계, 집계 count, checksum과 validation/application
  결과 같은 aggregate metadata는 자동 만료 없이 장기 보존한다.
- 원본 이름, 이메일, 사번 등 개인정보의 조회·export는 platform admin으로 제한하고 조회 행위를
  감사한다. 일반 사용자용 API나 로그에는 raw payload를 노출하지 않는다.

## 감사와 운영 조회

일반 audit log는 raw snapshot 저장소를 대신하지 않는다. Audit entry는 run ID, source scope,
최종 상태, baseline run ID와 집계 결과를 가리키는 요약 projection으로 사용한다. 운영 조회는
최소한 수집, 거부 사유, baseline과 source mode를 한 run 단위로 추적할 수 있어야 한다.
`projection_apply`는 사용자·조직 change count와 계정·세션 적용 결과·conflict를, ERP
`snapshot_only`는 원본 row count와 `projection_applied = false`를 함께 보여야 한다.
