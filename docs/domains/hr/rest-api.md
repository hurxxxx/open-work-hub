# 통합 인사 REST API

이 문서는 외부 시스템이 ERP·그룹웨어·통합 기준 인사정보를 읽는 REST 계약의 정본이다.
통합 master와 기준별 field authority는 [HR 동기화 계약](README.md)과
[ADR 0011](../../../adr/0011-unified-hr-master.md), 공통 API 키와 OpenAPI는
[외부 REST 연계 계약](../api-integrations/README.md)을 따른다.

## 인증과 기본 호출

모든 데이터 endpoint는 `hr:read` scope가 있는 플랫폼 API 키를 요구한다.

```http
GET /api/v1/integrations/hr/employees?basis=integrated&page=1&page_size=100
Authorization: Bearer aido_pk_REDACTED
Accept: application/json
```

키는 관리자 설정의 `API 키` 화면에서 발급·조회·폐기한다. 키 원문을 query string이나
custom URL에 넣지 않는다.

## Endpoint

| Method | Path                                           | 설명                                               |
| ------ | ---------------------------------------------- | -------------------------------------------------- |
| `GET`  | `/api/v1/integrations/hr/status?basis=...`     | 선택 기준의 현재 제공 version과 source/master 상태 |
| `GET`  | `/api/v1/integrations/hr/employees?basis=...`  | 선택 기준의 사람·사용자 목록                       |
| `GET`  | `/api/v1/integrations/hr/groups?basis=...`     | 선택 기준의 source-qualified 조직 목록             |
| `GET`  | `/api/v1/integrations/hr/workforce-categories` | 통합 기준 인력 구분 code와 표시 metadata           |

`basis`는 필수이며 `erp`, `groupware`, `integrated` 중 하나다. 요청 중 다른 기준으로
자동 fallback하지 않는다.

### 기준별 의미

| basis        | 모집단과 정본                                                                                                                                                                                                                  | schema                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------- |
| `erp`        | 최신 호환 성공 master에서 ERP row가 연결된 사람. 종합검진과 같은 ERP 모집단이며 groupware-only·external·격리 conflict는 제외한다.                                                                                              | `hr-master-erp-employee-v2`         |
| `groupware`  | 그룹웨어 HR sync로 적용된 AI-DO 사용자·조직 projection. ERP-only 인력과 로컬 계정은 제외한다. 로그인 ID, 실제 이메일, 계정 상태와 그룹웨어 조직을 정본으로 사용한다. 내부 대체 이메일(`@groupware.local`)은 `null`로 반환한다. | `groupware-v1`                      |
| `integrated` | 최신 호환 성공 master의 person, 해외/외부 person과 격리 conflict 정보. ERP 연결 field와 master에 고정된 그룹웨어 field의 authority는 ADR 0011을 따른다. 호출 시점의 변경 가능한 사용자 계정 상태는 섞지 않는다.                | 현재 master schema (`hr-master-v5`) |

ERP response가 제공하는 생년월일·입사일·전화번호는 ERP v2 계약에 포함된다. `phone_number`는
ERP `HAND_TEL_NO`를 materialize한 값이며 ERP row가 연결된 `integrated` person에도 제공한다.
그룹웨어 원천에는 전화번호 계약이 없으므로 `groupware`와 ERP가 없는 통합 person에서는
`null`이다. 급여등급과 나머지 ERP 원천 컬럼은 이 API 계약에 포함하지 않는다.

## 목록과 snapshot

- `page` 기본값은 `1`이다.
- `page_size` 기본값은 `100`, 최댓값은 `200`이다.
- 응답의 `snapshot_id`와 `schema_version`은 다음 page 호출과 consumer import 결과에 함께
  보존한다.
- endpoint가 `snapshot_id` query를 지원하는 경우 첫 page가 반환한 값을 후속 page에
  전달해 같은 불변 master를 고정한다.
- Groupware 기준의 `source_groupware_run_id`는 원천 동기화 run을 나타내고,
  `snapshot_id`와 `projection_hash`는 최신 적용 시각의 사용자·조직 공개 DTO로 계산한
  결정론적 hash다. 같은 run에 연결된 현재 projection이 page 사이 변경되어도 hash가 바뀌므로
  조용히 섞지 않고 `409`로 재시작을 요구한다. 과거 동기화 시각의 잔존 행은 최신 projection에
  포함하지 않는다.
- 정렬은 사번 또는 source identity에 기반한 서버 고정 순서를 사용한다. Consumer는 반환
  순서를 자체 identity로 사용하지 않는다.

ERP·통합 일반 person의 `subject_id`는 사번 기반이다. Groupware 기준의 각 계정과 통합 기준의
외부 person은 원천 identity 기반의 결정론적인 opaque ID를 사용한다. 따라서 그룹웨어에서
같은 실사번을 가진 계정이 둘 이상이어도 `subject_id`는 충돌하지 않으며 내부 사용자 UUID를
직접 노출하지 않는다. Master 실행별 내부 row UUID와 raw snapshot row ID는 반환하지 않으므로
이를 consumer key로 사용하지 않는다.

## 제공 field

공통 사람 DTO는 기준별 필드를 nullable로 명시한다.

- 식별: `subject_id`, `employee_code`, `name`
- 조직·직무: `group_code`, `group_name`, `group_source`, `position`, `occupation`
- 계정: `email`, `login_id`, `account_status`
- ERP v2 개인정보: `birth_date`, `hire_date`, `phone_number`
- 출처: `source_systems`, `has_erp`, `has_groupware`
- 통합 정합: `record_kind`, `reconciliation_status`, `identity_resolution_kind`
- 인력 분류: `inferred_workforce_category`, `workforce_category`,
  `workforce_category_resolution_kind`
- 격리 정보: 외부 공개 allowlist에 포함된 `reconciliation_detail`

내부 사유 code가 외부 공개 allowlist에 없으면 `reconciliation_detail`은
`unclassified_conflict`로 일반화한다. 내부 대체 이메일(`@groupware.local`)과 공백 이메일은
모든 기준에서 `null`로 반환한다.

Custom 인력 구분을 사용하는 consumer는 사람 응답의 code를 하드코딩된 네 가지 기본값만으로
해석하지 않고 `workforce-categories` catalog와 결합한다. 보관된 code가 과거 snapshot row에
남을 수 있으므로 장기 import metadata에는 당시 code도 함께 보존한다.

응답 envelope는 최소한 `basis`, `schema_version`, `snapshot_id`, 생성/적용 시각,
source/master ID와 hash/checksum 중 해당 기준이 보장하는 provenance, `items`, `total`,
`page`, `page_size`를 포함한다.

다음 값은 반환하지 않는다.

- raw snapshot `raw_payload`, row hash와 row ordinal
- source snapshot row UUID와 원천 DB 내부 identity
- 수동 매핑 link ID, 인력 구분 assignment ID와 관리자 사유
- password/session/token, role, workspace/team membership
- ERP 급여등급과 계약되지 않은 raw 컬럼

## 동기화 예시

1. `status`에서 필요한 `basis`의 `available`이 `true`인지 확인한다.
2. `employees` 첫 page를 호출하고 `snapshot_id`, `schema_version`, checksum/hash를 기록한다.
3. 같은 snapshot을 유지하며 마지막 page까지 읽는다.
4. `total`과 실제 수집 건수, checksum/hash를 consumer import metadata에 보존한다.
5. `503`이면 다른 basis나 raw source로 fallback하지 않고 직전 성공 import를 유지한 채
   운영자에게 알린다.

키나 개인정보를 application log에 출력하지 않는다. 요청·응답 전체 body dump를 운영
환경에서 활성화하지 않는다. 모든 응답은 `Cache-Control: private, no-store`와
`Pragma: no-cache`를 사용한다. 잘못된 `snapshot_id` 원문은 감사 로그에 보존하지 않고
요청에 값이 있었는지와 안정적인 오류 code만 기록한다.

## 자동 스펙

정확한 query enum, nullable field, response와 오류 schema는 배포 환경의
`/openapi.json`에서 자동 생성된다. `/docs`에서 `hr-integrations` tag를 선택하면 브라우저에서
Bearer key를 넣어 호출을 확인할 수 있고, `/redoc`은 읽기용 스펙을 제공한다. 이 문서는 업무
의미와 운영 규칙을 소유하며 field의 기계 판독 계약은 OpenAPI가 소유한다.
