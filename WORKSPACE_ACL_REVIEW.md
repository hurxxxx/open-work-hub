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
최종 API 기본 테스트 2,095개와 정적·아키텍처·API 계약 검사가 통과했다.

커밋·푸시·배포는 수행하지 않았으며 검토 가능한 미커밋 변경으로 남겼다.
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

## 변경 범위

- 권한·관리: `auth/access.py`, `auth/roles.py`, `auth/workspace_app_gate.py`, `admin/workspace_members.py`.
- 소스 ACL: `source_access/{policy,registry,access_scope}.py`, 다섯 소스 어댑터의 앱 소유자 선언.
- 문서·보드·미디어: `docs/access_context.py`, `whiteboard/access.py`, `media/{resource_access,content_access}.py`.
- 회귀 검증: 새 [test_workspace_acl_boundaries.py](apps/api/tests/test_workspace_acl_boundaries.py),
  기존 역할·관리·소스 범위·어댑터·미디어·커뮤니티·회사 파일 코퍼스 테스트.
- 문서: 위 세 개 소유 문서와 이 루트 보고서.

공통 권한 경계 보강을 기존 등록·실행 인터페이스에 적용했다. 새로운 앱·공급자·모델·API 경로·
응답 스키마·DB 스키마·작업 큐·환경 설정은 추가하지 않았다. 마이그레이션은 필요하지 않다.

## 검증 기록

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
