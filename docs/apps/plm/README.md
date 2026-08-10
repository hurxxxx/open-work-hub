# PLM App

PLM은 AI-DO의 원장 시스템이 아니다. 현재 코드에는 PLM 데이터를 변경하는 write endpoint나 AI tool이 없다.

## 현재 구현

- `/api/v1/workspaces/{workspace_slug}/search/plm`은 workspace ACL과 allowlist template 검사를 수행하지만 Oracle을 실행하지 않고 고정 preview를 반환한다.
- `/api/v1/workspaces/{workspace_slug}/plm/raw/*`는 workspace admin 전용 Oracle JDBC 조회 API다.
- Raw API는 객체 목록, 객체 행 조회, 사용자 입력 SELECT 실행과 최대 500행 단위 pagination을 제공한다.
- 사용자 SQL은 단일 `SELECT`만 허용하며 세미콜론, SQL 주석, DML/DDL 토큰을 거부한다. 실제 접근 가능한 객체 범위는 Oracle 계정 권한에도 종속된다.
- `/w/:workspaceSlug/plm`에는 테이블 탐색과 SQL 조회 UI가 구현되어 있다. 프런트엔드 route 자체에는 별도 admin role 차단이 없고 backend API가 권한을 검사한다.
- PLM은 현재 RAG source로 등록되어 있지 않다.

접속 환경 계약과 smoke 절차는 [PLM Oracle interface](../../../interfaces/plm/oracle-database.md)를 따른다.
