# 워크스페이스·ACL 보안 검토 및 개선 기록

검토일: 2026-09-07. 대상: 로컬 `dev` 체크아웃의 정책, 서버 구현, 관련 클라이언트 경계와 테스트.
이 파일은 이번 검토의 결과 기록이다. 지속적으로 관리할 계약은 아래 기존 소유 문서에 반영했다.

- [App Platform](docs/domains/app-platform/README.md): 역할, 워크스페이스 실행, 전역 공유 경계.
- [Source Access](docs/domains/source-access/README.md): 검색·RAG·교차 앱 자료 ACL.
- [Content Access](docs/domains/content-access/README.md): 미디어·다운로드 권한 재검사.
- [ADR 0007](adr/0007-company-tenant-workspace-scope.md), [ADR 0011](adr/0011-app-first-workspace-context.md): 회사·워크스페이스 범위와 명시적 실행 컨텍스트.

## 결론

라우터의 기본 멤버십 검사와 콘텐츠 다운로드의 세션 결합은 갖춰져 있었지만,
전역 공유, 공통 소스 ACL, 팀 권한, 미디어 연결, 과거 역할 호환 처리에서 동일한 정책이 유지되지 않았다.
특히 워크스페이스 탈퇴 뒤 잘못된 공유 토큰으로 문서를 읽는 경우와,
명시적 관리자 역할 회수 후에도 기존 관리자 플래그가 남는 경우를 실제 API 테스트로 재현했다.
확인한 문제를 아래와 같이 수정하고 거부·정상 접근 회귀 테스트를 추가했다.
1차 검토에서는 문제 9종을 수정하고 API 기본 테스트 2,095개와 정적·아키텍처·API 계약 검사를 통과했다.
후속 재검토에서 문제 4종(ACL-10~13)을 추가로 재현·수정했다. 검증 결과는 아래 차수별로 구분했다.
최종 2차 코드의 API 기본 테스트는 2,109개가 모두 통과했다.

사용자의 후속 커밋·푸시 요청에 따라 1차 수정 `accb30bb`를 GitLab `origin/dev`에 푸시했다.
2차 개선과 이 보고서 갱신도 같은 `dev → origin/dev` 전달 범위에 포함한다. 운영 배포는 수행하지 않았다.
운영 계정·권한 데이터는 열람하거나 일괄 변경하지 않았다.

## 검토 범위와 판단 기준

| 경계 | 확인한 구현·증거 | 판단 |
| --- | --- | --- |
| 회사·워크스페이스 | `api_registry.py`, `auth/dependencies.py`, `auth/access.py`, 부트스트랩·관리 API | 회사 계정과 워크스페이스 멤버십을 구별하고, 경로는 식별자일 뿐 권한으로 사용하지 않아야 함 |
| 시스템·팀 역할 | `auth/roles.py`, `admin/workspace_members.py`, PMS 접근 정책 | 역할 이름 정규화가 권한을 확대하면 안 되며 하위 팀 멤버십은 상위 접근 회수를 우회할 수 없어야 함 |
| Docs·Whiteboard 공유 | 접근 컨텍스트, 전역/워크스페이스 라우터, 공유 링크·협업 테스트 | 전역 링크의 범위와 워크스페이스 경로의 권한을 섞지 않아야 함 |
| 검색·RAG·파일 | Source Access 어댑터, 파일 코퍼스 ACL, 검색·retrieval 후처리 | 인덱스·파티션·이전 정책 객체 대신 현재 원본 ACL로 최종 판단해야 함 |
| 미디어·첨부·다운로드 | `media/resource_access.py`, 콘텐츠 발급·검증, PMS·회의 첨부 경계 | 자료 본문보다 미디어 권한이 넓어지면 안 되며 연결 작업에는 쓰기 권한이 필요함 |
| 알림·실시간 | 알림 가시성의 배치 앱/원본 검사, Docs·Whiteboard 연결의 재인증 루프 | 저장된 알림과 열린 연결이 독립적인 접근권한이 되어서는 안 됨 |
| AI·비동기 실행 | 도구 실행/승인 공통 경로, 실행 앱 게이트, 기본 API 회귀 테스트 | 등록된 도구·승인·소스 ACL 및 실행 시점 앱 상태를 함께 검사해야 함 |
| 클라이언트 | 공통 워크스페이스 접근 헬퍼, 부트스트랩 기반 진입 판단 | UI의 표시·탐색 상태는 서버 권한을 대체하지 않음; 이번 변경은 서버에 적용 |

검토 깊이는 공통 권한 경계와 발견한 우회 경로에 집중했다. 전체 API 기본 회귀 테스트도 실행했지만,
모든 개별 라우트와 운영 배포를 대상으로 침투 테스트를 완료했다는 의미는 아니다.

## 발견 사항과 적용한 수정

### ACL-01 · 높음 · 잘못된 공유 토큰으로 문서 전역 API 접근

기존에는 `share_token`이 있으면 워크스페이스 컨텍스트 검사를 생략하면서,
토큰이 실제로 일치하지 않아도 소유권·사용자 공유·회의 공유·연결 대상 권한 중 하나로 접근을 허용했다.
탈퇴한 소유자와 직접 공유 사용자가 워크스페이스 API에서는 403을 받으면서도
전역 문서 API에 임의의 토큰을 전달하면 200을 받는 것을 재현했다.

수정: 토큰이 제공된 요청은 정확히 일치하는 활성 링크만 사용한다.
권한은 해당 링크의 `read`/`edit`로 제한하며 소유권이나 직접 공유로 확대하지 않는다.
공유·관리 권한을 링크에서 부여하지 않으며, 동일한 제한을 Whiteboard에도 적용했다.
유효한 링크를 가진 비멤버의 정상적인 회사 내부 공유 읽기·편집 경로는 유지한다.

근거: `docs/access_context.py`, `whiteboard/access.py`;
`test_global_doc_api_requires_valid_link_after_membership_revocation`,
`test_shared_link_limits_owner_rights_and_denies_inactive_workspace`, 기존 `test_docs_hub.py` 공유 테스트.

### ACL-02 · 높음 · 재사용된 소스 ACL에서 권한 회수 미반영

문서 소유자·회의 주최자 등의 자료 권한을 검사하면서, 일부 공통 호출은 현재 워크스페이스 멤버십이나
계정·워크스페이스 상태를 다시 확인하지 않았다. 기존 정책 객체를 유지한 채 별도 DB 세션에서
멤버십을 삭제하거나 워크스페이스/계정을 비활성화해도 단건 소스 접근이 허용되는 것을 재현했다.

수정: 소스 어댑터의 명시적 `app_id`를 사용하여 호출 시점의 계정·워크스페이스 역할·앱 활성화를 검사한다.
단건, 배치, RAG, 소스 유무 조회와 문서 소스 종류 조회에 같은 경계를 적용한다.
배치에서는 자료 유형별로 검사하고, 반환 ID를 입력 후보와 교집합으로 제한한다.
어댑터에 전달하는 역할도 현재 DB 값으로 갱신한다.

근거: `source_access/policy.py`, `source_access/registry.py`, Docs/Files/PMS/Meeting/Planner 어댑터;
`test_source_acl_rechecks_revoked_execution_context`의 멤버십·워크스페이스·계정·앱 회수 조합.

### ACL-03 · 중간 · 단건과 배치의 실행 범위 정책 불일치

배치·RAG 경로는 실행 범위를 검사했지만 단건·소스 유무 조회는 같은 방어가 없었다.
회사 컨텍스트에서 워크스페이스 전용 문서·회의 어댑터를 호출하면 거부 대신 예외가 발생했다.
기존 소유 문서에도 이 제한이 미해결 상태로 기술되어 있었다.

수정: 공통 실행 범위 검사로 어댑터 호출 전에 거부한다.
회사 파일 코퍼스는 회사 정책으로 계속 조회할 수 있고, 다른 워크스페이스의 전용 자료가 회사 자료로
승격되는 일은 없다. 기존 소유 문서의 단건 예외 설명도 제거했다.

근거: `test_company_source_dispatch_denies_workspace_only_adapters`, `test_file_manager_corpora.py`.

### ACL-04 · 높음 · 과거 역할 이름의 자동 권한 확대

`audit_viewer`와 `workspace_admin` 시스템 역할이 `platform_admin`으로 변환되고,
워크스페이스 `viewer`가 쓰기 가능한 `member`로 변환되었다.
이는 해당 값이 관리자 입력·과거 저장 데이터·동기화 경로를 통해 들어왔을 때의 권한 확대 문제이며,
일반 사용자가 역할 관리 API를 직접 호출할 수 있었다는 의미는 아니다.

수정: 좁은 과거 시스템 역할과 워크스페이스 `viewer`는 권한을 부여하지 않는다.
`platform-admin`의 동등한 표기와 `owner → admin`의 축소 호환은 유지한다.
단건·비동기·배치 앱 게이트도 멤버십 행의 존재만 보지 않고 지원되는 역할인지 검사한다.
관리자 멤버 필터에서도 `viewer`를 `member`로 묶지 않는다. PMS 팀의 읽기 전용 `viewer`는 유지한다.

근거: `auth/roles.py`, `auth/workspace_app_gate.py`, `admin/workspace_members.py`;
역할 단위 테스트와 실제 관리 API 거부·앱 실행 게이트 테스트.

### ACL-05 · 높음 · 상위 워크스페이스 탈퇴 후 하위 팀 권한 잔존

`resolve_workspace_role`은 이미 로드된 사용자 관계를 읽었고, `resolve_team_role`은
워크스페이스 역할이 없어도 남아 있는 `TeamMember`로 팀 권한을 계산했다.
팀 관리 API처럼 전역 경로에서 하위 권한을 직접 확인하는 곳에 영향을 줄 수 있었다.

수정: 워크스페이스 역할은 현재 DB의 멤버십·활성 상태·로그인 차단 상태를 조회한다.
상위 워크스페이스 접근이 없거나 팀이 비활성/휴지통 상태이면 하위 팀 권한도 거부한다.
기존 팀 구성 데이터는 보존하되 그 데이터 자체가 탈퇴 후 권한이 되지 않도록 했다.

근거: `auth/access.py`; 같은 ORM 사용자 객체를 재사용하는 회수 테스트와 팀 조회·삭제 API 거부 테스트.

### ACL-06 · 높음 · PMS 미디어 ACL 및 전역 미디어 연결 검사 불일치

PMS 미디어는 태스크 원본 정책 대신 일반 팀 역할 해석을 사용했다.
그 결과 워크스페이스 관리자가 비공개 PMS 스페이스의 미디어에 더 넓은 권한을 갖고,
뷰어에게도 미디어 연결 작업을 허용할 수 있었다. 반대로 정상적인 태스크 읽기 공유는 반영하지 못했다.
전역 미디어 연결은 Docs/PMS 소스의 현재 앱 실행 조건을 공통으로 재검사하지 않았다.

수정: 읽기는 PMS 원본 소스 ACL을 재사용하여 직접 스페이스 멤버십 또는 유효한 태스크 공유를 따른다.
연결은 PMS의 직접 편집 역할을 요구한다. 모든 지원 미디어 연결 작업에 콘텐츠 전달과 동일한
소유 앱 실행 게이트를 적용하여 앱 비활성화와 워크스페이스 탈퇴 후 연결을 차단한다.

근거: `media/resource_access.py`, `media/content_access.py`;
`test_pms_media_obeys_source_acl_and_write_role`, `test_global_media_link_rechecks_docs_execution_context`.

### ACL-07 · 중간 · 묵시적 워크스페이스 선택과 관리자 범위 과대 허용

Docs/Whiteboard 서비스는 컨텍스트가 없으면 사용자의 첫 워크스페이스를 선택했다.
공통 범위 규칙도 워크스페이스 관리자에게 알 수 없는 범위와 다른 워크스페이스 ID를 무조건 허용했다.
현재 호출부의 외부 필터가 일부를 제한하지만 공통 API 자체가 선언된 정책과 달랐다.

수정: 워크스페이스 서비스에 컨텍스트가 없으면 거부한다.
관리자라도 다른 워크스페이스 ID, 현재 워크스페이스 밖의 팀, 누락된 팀 ID, 미지원 범위는 거부한다.
범위 SQL 조건과 단건 판정이 동일하도록 테스트했다. 원본 쿼리의 워크스페이스 필터는 계속 필요하다.

근거: Docs/Whiteboard 컨텍스트 헬퍼, `source_access/access_scope.py`, `test_source_access_scope.py`.

### ACL-08 · 중간 · 비활성 워크스페이스의 전역 공유 자료 노출

소유자는 자료 ACL에서 즉시 통과할 수 있어, 전역 공유 조회에서 자료가 속한 워크스페이스의
활성 상태를 항상 확인하지 않았다.

수정: Docs/Whiteboard의 공통 자료 로딩 쿼리가 활성 워크스페이스에 속한 자료만 반환한다.
유효한 링크를 가진 소유자도 워크스페이스 비활성화 후에는 404를 받는다.

### ACL-09 · 높음 · 시스템 역할 회수 후 레거시 관리자 플래그 잔존

관리 API가 `system_roles: []`를 저장해도 별도의 `User.is_admin` 플래그는 남아 있었다.
그 플래그가 있는 테스트 계정에서 역할 제거 API가 성공했는데도 응답 역할이 계속
`platform_admin`으로 나타나는 것을 재현했다.

수정: 명시적인 시스템 역할 교체는 동일 트랜잭션에서 레거시 플래그를 해제하고 역할 행을 교체한다.
이미 로드된 역할 관계도 무효화한다. 사용자의 기존 로그인 세션으로 다음 관리 API 요청을 보내면
현재 권한에 따라 거부된다. 관리자가 명시적으로 교체하지 않은 다른 계정은 일괄 변경하지 않는다.

### ACL-10 · 높음 · 관리자 권한 회수 후 대리 로그인 세션 유지

대리 로그인 발급 시에는 관리자 역할을 검사했지만 이후 요청은 대리 대상 계정만 검사했다.
관리 API에서 최초 관리자의 역할을 제거한 뒤에도 이미 발급한 대리 세션으로 `/auth/me`가 200을 반환했다.
별도 DB 트랜잭션으로 최초 계정의 역할·활성·차단 상태를 바꾸는 경우도 재현했다.
일반 관리 API의 계정 차단은 기존에도 대리 세션을 회수했으며, 이 부분이 누락되어 있었다고 주장하는 것은 아니다.

수정: 공통 인증 경계가 최초 대리 실행자의 현재 계정 상태와 `platform_admin`을 매번 검사한다.
명시적인 역할 교체로 관리자 권한이 없어지면 해당 계정이 발급한 대리 세션들을 같은 트랜잭션에서 폐기한다.
관리자 역할을 다시 부여해도 폐기된 대리 세션은 살아나지 않는다. 대상 계정의 독립 로그인 세션은 유지한다.
인증용 사용자 그래프도 새로 로드해 같은 ORM 세션 재사용 시 계정 차단을 반영한다.
계정 삭제에서는 외래 키의 `ON DELETE SET NULL`로 대리 실행자 정보가 지워져 세션이 일반 로그인처럼
남는 200 응답도 별도로 재현했다. 삭제 트랜잭션에서 먼저 해당 사용자의 직접·대리 세션을 회수하여 차단했다.

근거: `auth/access.py`, `auth/dependencies.py`, `auth/session_lifecycle.py`, `admin/router.py`;
`test_impersonation_requires_current_origin_admin`, `test_reused_auth_context_refreshes_current_account_state`,
`test_deleting_impersonator_cannot_turn_delegation_into_independent_session`.
기존 콘텐츠·실시간 인증 호출도 동일한 토큰 해석기를 사용한다. 이미 열린 연결의 재검사 주기는 변경하지 않았다.

### ACL-11 · 높음 · 문서 REST보다 넓은 검색·RAG 원본 ACL

PMS 비공개 스페이스에 연결된 문서는 직접 스페이스 멤버가 아니면 REST에서 404였지만,
소스 SQL은 일반 관리자 범위 규칙을 재사용해 워크스페이스 관리자에게 모든 팀 문서를 허용했다.
별도로 미지원 `access_level`의 직접 공유·회의 공유 행도 원본 SQL에서는 존재만으로 읽기 권한이 됐다.
원본 REST 거부와 공통 소스 읽기 허용이 동시에 발생하는 테스트로 재현했다.

수정: Docs 원본 SQL과 키워드 팀 후보를 직접 스페이스 멤버십으로 제한한다.
명시적 공유 행은 `read`/`edit`만 인정한다. 단건·배치·RAG·자료 유형 조회에 같은 SQL이 적용된다.
소유권 및 유효한 독립 공유는 유지하며, 정상 공유/팀 역할 부여 시 허용되고 회수 시 다시 거부되는 것을 검사했다.

근거: `docs/source_access.py`; `test_docs_source_acl_cannot_exceed_document_acl`.
키워드 등록 검사의 DB 없는 프로브 계약은 기존 인터페이스를 유지하며 실제 실행은 DB의 직접 멤버십을 조회한다.

### ACL-12 · 높음 · 태스크 공유 권한으로 다른 워크스페이스 경계 우회

태스크 읽기 헬퍼는 직접 목록 접근이 실패해도 유효한 `TaskUserAccess`가 있으면 태스크를 반환했다.
원본 워크스페이스에서 탈퇴한 사용자가 자신의 다른 워크스페이스 경로에 원본 태스크 ID를 넣어
상세를 읽는 200 응답을 재현했다. 원본 팀이 비활성·휴지통 상태인 경우도 공유 권한이 이를 우회했다.

수정: 공유를 인정하기 전에 요청의 명시적 워크스페이스에 속한 활성 스페이스인지,
현재 원본 멤버십과 PMS 실행 권한이 있는지 검사한다. 태스크 상세와 커스텀 필드 조회 모두 기존 403 계약으로 거부한다.
미지원 태스크 공유 수준도 REST·소스 SQL에서 거부한다. 기존 보관된 목록의 상세 읽기 정책은 유지한다.

근거: `pms/access.py`, `pms/source_access.py`;
`test_task_grant_does_not_bypass_resource_context`, 기존 `test_pms_list_archive.py`.

### ACL-13 · 중간 · 미지원 팀 역할의 목록·소스 접근 허용

단건 역할 해석기는 알 수 없는 팀 역할을 거부했지만 PMS 목록·개인 태스크 위젯·소스 SQL과
공통 팀 범위 쿼리는 멤버십 행의 존재만 사용했다. `unknown` 역할의 스페이스가 목록에 나타나는 것을 재현했다.
이는 과거/비정상 저장 역할의 처리 문제이며 일반 사용자가 임의 역할을 저장할 수 있음을 확인한 것은 아니다.

수정: 지원 역할과 최소 역할을 검사하는 공통 SQL 조건을 추가해 목록·위젯·소스·범위 쿼리에 적용했다.
`viewer`의 정상 읽기 및 대소문자·주변 공백 호환을 유지하고 쓰기는 거부한다.
기존 역할 행을 일괄 변경하거나 관리자 권한을 자동 부여하지 않는다.

근거: `auth/roles.py`, `pms/access.py`, `pms/service.py`, `pms/source_access.py`,
`source_access/access_scope.py`; `test_unsupported_team_role_cannot_read_lists_or_sources`.

## 변경 범위

- 권한·관리: `auth/access.py`, `auth/roles.py`, `auth/workspace_app_gate.py`, `admin/workspace_members.py`.
- 소스 ACL: `source_access/{policy,registry,access_scope}.py`, 다섯 소스 어댑터의 앱 소유자 선언.
- 문서·보드·미디어: `docs/access_context.py`, `whiteboard/access.py`, `media/{resource_access,content_access}.py`.
- 회귀 검증: 새 [test_workspace_acl_boundaries.py](apps/api/tests/test_workspace_acl_boundaries.py),
  기존 역할·관리·소스 범위·어댑터·미디어·커뮤니티·회사 파일 코퍼스 테스트.
- 문서: 위 세 개 소유 문서와 이 루트 보고서.
- 2차 추가: `auth/dependencies.py`, `auth/session_lifecycle.py`, `admin/router.py`, `pms/access.py`, `pms/service.py`,
  `tests/test_workspace_acl_followup.py`; 기존 `auth/access.py`, `auth/roles.py`, Docs/PMS 소스 SQL,
  공통 팀 범위 및 App Platform/Source Access 소유 문서도 후속 보강했다.

공통 권한 경계 보강을 기존 등록·실행 인터페이스에 적용했다. 새로운 앱·공급자·모델·API 경로·
응답 스키마·DB 스키마·작업 큐·환경 설정은 추가하지 않았다. 마이그레이션은 필요하지 않다.

## 1차 검증 기록

새 보안 회귀 파일에 26개 실행 케이스를 추가했다. 수정 전에 기존 집중 테스트는 18개가 통과했지만,
새로 작성한 탈퇴·공유 토큰·정책 재사용 테스트로 기존 허용/예외 동작을 재현했다.
별도로 관리자 플래그 회수 실패도 수정 전 실제 API 응답으로 확인했다.

아래 `pytest`, `ruff`, `compileall` 명령은 `apps/api`에서 실행했다.

| 명령·검사 | 결과 |
| --- | --- |
| `uv run --python 3.12 --group dev python -m pytest tests/test_workspace_acl_boundaries.py tests/test_source_access_scope.py tests/test_file_manager_corpora.py -q --tb=no` | 45 passed |
| `uv run --python 3.12 --group dev python -m pytest tests/test_community.py tests/test_workspace_acl_boundaries.py tests/test_media_resource_access.py -q --tb=no` | 64 passed |
| `uv run --python 3.12 --group dev python -m pytest -n 8 --dist=worksteal -m 'not slow and not external_integration and not migration' -q --tb=no` | 2,095 passed, 경고 10건, 116.76초 |
| `uv run --python 3.12 --group dev ruff check .` | 통과 |
| `uv run --python 3.12 python -m compileall -q src` | 통과 |
| `pnpm check:api-architecture` | API i18n 통과, import 계약 2개 유지 |
| `pnpm check:api-contract` | 통과, 생성 API 계약 변경 없음 |
| `git diff --check`, 변경 문서 4개의 상대 링크 검사 | 통과, 누락 링크 없음 |

전체 기본 테스트 확대 과정의 실패는 누락된 테스트용 앱 제어 테이블, 잘못 지정한 테스트 URL,
이동된 미디어 게이트를 가리키던 테스트 대역 참조로 구분해 수정했다.
기존 거부 단언이나 CI 제외 조건을 완화하지 않았다.

실행하지 않은 검사: `slow`, `external_integration`, `migration` 마커의 별도 테스트,
실제 브라우저 E2E, 독립 worker 전체 테스트, 운영 배포·실제 외부 서비스 테스트.
DB 스키마·worker 코드·UI 코드는 변경하지 않았다. 실제 Redis 릴레이 및 MinIO 동작의 외부 통합 검증은
기본 API 테스트 통과와 별개다.
검증 중 Starlette/AnyIO deprecation과 일부 Yjs 객체의 다른 스레드 정리 경고가 관찰되었으며,
해당 라이브러리 경고는 이번 ACL 변경에서 수정하지 않았다.

## 2차 검증 기록

`tests/test_workspace_acl_followup.py`에 14개 실행 케이스를 추가했다.
기존 동작에서 대리 권한 회수·Docs 소스 ACL·태스크 컨텍스트·팀 역할 11개 실패 케이스를 확인했고,
관리자 삭제 후 대리 세션 유지도 별도 API 테스트로 재현한 뒤 수정했다.
같은 인증용 ORM 세션에서 계정 차단 반영, 정상 공유/뷰어 읽기, 공유 회수,
관리자 역할 재부여 후 폐기 세션 비복구, 대상 계정의 독립 세션 보존도 확인했다.

아래 `pytest`, `ruff`, `compileall`은 `apps/api`에서 실행했다.

| 명령·검사 | 결과 |
| --- | --- |
| `uv run --python 3.12 --group dev python -m pytest tests/test_workspace_acl_followup.py tests/test_workspace_acl_boundaries.py tests/test_auth_impersonation.py tests/test_source_access_policy.py tests/test_pms_list_archive.py -n 4 -q --tb=short --show-capture=no` | 49 passed; 삭제 경로 케이스 추가 전 |
| `uv run --python 3.12 --group dev python -m pytest tests/test_workspace_acl_followup.py -k deleting_impersonator -q --tb=short --show-capture=no` | 수정 전 200 응답으로 실패, 수정 후 1 passed |
| `uv run --python 3.12 --group dev python -m pytest -n 4 --dist=worksteal -m 'not slow and not external_integration and not migration' -q --tb=short --show-capture=no` | 최종 삭제 경로 수정 포함 2,109 passed, 경고 6건, 182.05초 |
| `uv run --python 3.12 --group dev ruff check .` | 통과 |
| `uv run --python 3.12 python -m compileall -q src` | 통과 |
| `pnpm check:api-architecture` | API i18n 및 import 계약 2개 통과 |
| `pnpm check:api-contract` | 통과, 생성 API 계약 변경 없음 |
| `git diff --check`, 변경 Markdown 3개의 상대 링크 및 새 테스트 공백 검사 | 통과 |

검증 중 테스트용 목록 키 길이 오류를 고쳤으며, 소스 키워드 등록 검사의 DB 없는 프로브 계약에 맞게
후속 SQL 변경을 보완했다. 두 경우 모두 제품 취약점의 증거로 계산하지 않았다.
집중 테스트를 8개 프로세스로 동시에 준비할 때 테스트 PostgreSQL에서
`out of shared memory / max_locks_per_transaction` 오류가 발생했다.
DB 설정이나 검사 제외 조건을 바꾸지 않고 병렬 수를 4개로 낮춰 같은 범위의 검사를 통과했다.
1차 기록의 미실행 검사와 라이브러리 경고에 대한 한계는 2차에도 적용한다.

## 호환성 영향과 검토 한계

1. 과거 `workspace_admin`/`audit_viewer` 또는 워크스페이스 `viewer`만 가진 계정은 이제 해당 권한이 없다.
   필요한 사용자에게 관리 API에서 지원 역할을 명시적으로 재할당해야 한다.
   이미 `platform_admin`으로 변환·저장된 계정은 현재 데이터만으로 원래 의도를 알 수 없으므로 자동 강등하지 않았다.
2. 유효한 회사 내부 공유 링크는 워크스페이스 멤버십과 별도 권한이다. 탈퇴자의 모든 공유 접근도 회수하려면
   해당 링크를 비활성화하거나 계정을 차단해야 한다. 읽기 링크로 들어간 소유자도 링크 경로에서는 관리 권한이 없다.
3. 소스 어댑터 확장은 명시적 `app_id`를 선언해야 한다. 누락되면 공통 ACL이 거부하며 우회 기본값은 없다.
4. 조회 시점의 권한 회수를 검증했다. 이미 전달한 파일 바이트·화면 내용은 회수할 수 없으며,
   실시간 협업 연결의 주기적 재검사 간격과 작업 시작 후의 동시 권한 변경까지 선형화하는 변경은 하지 않았다.
5. 테스트 전용 DB와 저장소 대역을 사용했다. 운영 데이터, 외부 실제 서비스, 프록시/네트워크 배포 구성,
   실제 브라우저 수동 조작과 부하 측정은 이 검토에 포함하지 않았다.
   자동 회귀 통과를 미발견 취약점이 없다는 보장으로 해석해서는 안 된다.
6. 2차 개선 후에는 관리자 강등·삭제로 폐기된 대리 세션을 다시 사용할 수 없다. 지원 작업을 계속하려면
   현재 권한이 있는 관리자가 새 대리 세션을 발급해야 한다. 워크스페이스 관리자라도 비공개 PMS 문서를
   검색하려면 직접 팀 멤버십 또는 별도의 유효한 문서 권한이 필요하다.
7. 과거 잘못된 역할/공유 수준 행은 권한을 부여하지 않는다. 이미 삭제되어 최초 실행자 정보가 사라진
   기존 대리 세션은 일반 세션과 런타임에서 구별할 수 없으므로 자동 정정하지 않았다.
   이번 삭제 경로 보강은 앞으로의 삭제에서 동일한 상태가 생기는 것을 방지한다.
