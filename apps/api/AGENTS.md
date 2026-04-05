# API App Rules

- `apps/api` 는 FastAPI 조립 계층이다.
- 앱 생성, 설정 로딩, router registration 만 여기서 직접 소유한다.
- 도메인 로직은 `src/aidoo_api/domains/*` 아래에서만 확장한다.
- 관련 public interface 는 `/search/documents`, `/search/plm`, `/templates`, `/drafts`, `/wiki/pages` 부터 시작한다.
