# Shared Contracts

공통 TS/JSON 계약이 두 개 이상 반복될 때 승격할 공간이다.

현재 포함 계약:

- `@open-alm/contracts/dm`: DM web/desktop 공통 응답 타입, API route builder,
  realtime reducers, list/composer/attachment view-model projections.
- `@open-alm/contracts/openapi`: FastAPI OpenAPI generated 타입.
- `@open-alm/contracts/api`: generated OpenAPI 타입을 다루는 공통 TS helper.
- `@open-alm/contracts/open-alm-desktop-update-feed`: Open ALM Desktop 설치/업데이트 feed 경로와 파일명 계약.

앱별 transport, 인증 토큰, Electron IPC 같은 adapter 세부는 각 앱에 남긴다. 여러 앱이 알아야 하는 path, query invariant, payload shape만 이 패키지로 승격한다.

## Publish

이 패키지는 `open-alm/open-alm` GitLab npm Package Registry에 발행한다. 발행 태그는 패키지 버전과 정확히 맞아야 한다.

```bash
git tag contracts-v0.0.3
git push origin contracts-v0.0.3
```

운영 절차와 split repo 소비 규칙은 `docs/domains/release/shared-contracts-package.md`를 정본으로 본다.
