# 외부 REST 연계 계약

이 문서는 Open ALM 외부 REST interface가 공통으로 사용하는 API 키, scope, OpenAPI와 운영
경계의 정본이다. 설계 결정은
[ADR 0012](../../../adr/0012-platform-api-keys-and-rest-integrations.md)를 따른다.
도메인별 field와 조회 규칙은 각 도메인 문서가 소유한다. 첫 적용 대상인 통합 인사는
[통합 인사 REST API](../hr/rest-api.md)를 따른다.

## 공통 경로와 인증

- 외부 연계 endpoint prefix: `/api/v1/integrations`
- 인증 header: `Authorization: Bearer <platform-api-key>`
- 키 형식: `aido_pk_` + URL-safe opaque 43자
- 현재 scope: `hr:read`
- 관리자 키 관리: `/admin/api-keys`

플랫폼 API 키는 외부 연계 endpoint 전용이다. 같은 값을 기존 사용자, 관리자 또는 workspace
API에 전달해도 사용자 session이나 관리자 권한으로 해석하지 않는다. 각 연계 endpoint는
필요한 scope를 서버에서 검사한다.

응답 오류는 공통 API 형식인 `detail`, 안정적인 `code`, 선택적인 `params`를 사용한다.

| 상태  | 의미                                                                  |
| ----- | --------------------------------------------------------------------- |
| `401` | Bearer key 누락, 형식 오류, 알 수 없는 키 또는 폐기된 키              |
| `403` | 유효한 키지만 endpoint에 필요한 scope가 없음                          |
| `404` | 요청한 version/snapshot 또는 resource가 없음                          |
| `409` | page를 고정한 snapshot과 현재 projection 상태가 충돌함                |
| `422` | query/path/body validation 실패                                       |
| `503` | 해당 기준의 호환 가능한 consumer projection을 안전하게 제공할 수 없음 |

## 키 발급과 보관

`platform_admin`은 관리자 설정의 `API 키` 화면에서 다음 작업을 수행한다.

1. 식별 가능한 이름과 허용 scope를 골라 새 키를 발급한다.
2. 발급 직후 원문을 복사해 연계 시스템의 secret 저장소에 넣는다.
3. 기존 키 원문이 다시 필요하면 `키 보기`를 눌러 확인한다. 서버는 현재 session의
   platform admin 권한을 다시 확인하고 조회 이력을 감사한다.
4. 교체할 때는 새 키로 consumer smoke를 통과시킨 뒤 기존 키를 폐기한다.

목록에는 원문 대신 prefix만 표시된다. 검증용 hash와 재조회용 암호문은 서버 DB에 분리
저장한다. 원문·암호화 root는 로그, audit payload, 문서, 브라우저 storage에
남기지 않는다. 원문을 표시하는 dialog는 닫을 때 메모리 상태를 초기화한다.
키 이름에는 운영 화면을 속일 수 있는 제어 문자와 bidi formatting 문자를 허용하지 않는다.
현재 v1 암호문은 API와 worker에 이미 배포된
`OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` root에서 플랫폼 API 키 전용 purpose key를
파생해 보호한다. 이 값의 변경은 AI model credential뿐 아니라 기존 플랫폼 API 키의 재조회에도
영향을 주므로 rotation 전에 두 종류의 암호문 재암호화 계획을 함께 세운다. 검증은 별도 hash를
사용하므로 복호화 설정 장애를 사용자 session이나 다른 인증 방식으로 우회하지 않는다.

폐기는 즉시 적용되고 재조회용 암호문도 제거하며 복구하지 않는다. 현재 expiry, IP allowlist,
quota와 자동 rotation은 미지원이다. 연계 소유자는 정기 교체 주기와 장애 시 회수 절차를
운영 정책으로 정해야 한다.

키 목록·발급·원문 조회·폐기 응답과 `/api/v1/integrations/*`의 개인정보 응답은 성공과
도메인 오류 모두 `Cache-Control: private, no-store`, `Pragma: no-cache`를 사용한다.
Consumer나 reverse proxy는 이 응답을 공유 cache 또는 브라우저 영구 저장소에 보관하지 않는다.

## OpenAPI

FastAPI request/response model이 실행 계약과 API 스펙의 단일 정본이다.

| 용도                           | 경로 또는 명령             |
| ------------------------------ | -------------------------- |
| OpenAPI JSON                   | `/openapi.json`            |
| Swagger UI                     | `/docs`                    |
| ReDoc                          | `/redoc`                   |
| 저장소 TypeScript 계약 생성    | `pnpm generate:api-client` |
| 스펙·generated type drift 검사 | `pnpm check:api-contract`  |

외부 consumer는 배포 환경의 `/openapi.json`에서 `/api/v1/integrations/*` path와 참조 schema를
가져가거나, 저장소에서 생성한 `@open-alm/contracts/openapi` type을 사용할 수 있다. Endpoint를
추가하거나 response field를 바꿀 때는 OpenAPI와 generated type을 같은 변경으로 갱신한다.

## 감사와 데이터 최소화

키 발급·원문 조회·폐기와 개인정보 연계 조회를 감사한다. 조회 audit에는 key ID,
endpoint/basis, 실제 snapshot/version, page, 결과 건수, 성공 여부와 안정적인 오류 code만
기록한다. 호출자가 보낸 잘못된 snapshot 원문, 키 원문, 검색어와 반환 row의 개인정보를
기록하지 않는다.

도메인은 별도 allowlist DTO를 정의해야 한다. DB model, raw payload, 내부 control ID를
자동 직렬화하지 않는다. Write API, webhook, file/network fetch, AI tool을 API key로 열 때는
이 read-only 계약을 그대로 확대하지 말고 해당 위험과 승인 정책을 별도로 결정한다.

## mcloudoc 상태

mcloudoc는 아직 이 문서의 외부 REST prefix나 플랫폼 API key scope를 사용하지 않는다.
대상 시스템에서 REST pull, webhook push, 파일 교환 중 어느 방식을 제공할지 정해지지 않았기
때문이다. 현재 구현은 외부 transport와 분리된 change/run DTO, Files 수용 port, 멱등
incremental/snapshot 원장과 명시적 ACL까지만 제공한다.

향후 방식이 확정되더라도 기존 `hr:read` scope를 재사용하거나 사용자 session으로 우회하지
않는다. write/push/pull 방향, 원문 byte 전달, 인증, TLS, rate limit, replay, audit와 secret
보관을 별도 위협 모델로 검토한 후 전용 scope·endpoint를 추가한다. 현재 계약과 활성화 조건은
[mcloudoc 연계 경계](../mcloudoc/README.md)가 소유한다.
