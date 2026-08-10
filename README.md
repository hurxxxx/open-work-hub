# AI-DO

## 운영/개발 분리

이 서버의 운영 checkout은 `/projects/ai-do/prod`이며 `main` 브랜치를 따른다.
개발 checkout은 `/projects/ai-do/dev`이며 `dev` 브랜치를 따른다.
운영 서비스는 user-level systemd의 `ai-do-prod-*` unit으로 관리한다.

일반 개발은 `/projects/ai-do/dev`의 `dev` 브랜치에서 수행한다. 개발 검증이 끝난
변경만 GitLab MR로 `main`에 병합하고, `/projects/ai-do/prod`는 병합된 `main`을 배포하는
운영 checkout으로 유지한다.

The standard deployment entrypoint is `pnpm prod:deploy`. Run
`pnpm prod:deploy -- --dry-run` first. `pnpm prod:install` is only for explicitly
installing or refreshing systemd unit files; it is not a deployment command.

운영 Nginx는 TLS와 reverse proxy만 담당한다. Web production build는 FastAPI가
`AI_DO_API_SERVE_FRONTEND=1` 설정으로 정적 서빙한다.

배포 후 별도 상태 확인이 필요하면:

```bash
pnpm prod:status
pnpm prod:smoke
```

배포의 backup, dependency/build, migration/head, release gate, 최종 smoke 계약은
[`production deployment layout`](./docs/domains/release/production-deployment-layout.md)을 따른다.

재시작만 필요하면:

```bash
pnpm prod:restart
```

문서 색인은 `docs/README.md` 를 먼저 본다.

## Local LLM / DGX Spark

DGX Spark `102` / `103` 서버의 SSH 접속, Dashboard, vLLM endpoint, CX7 직결 링크, Qwen3.6 운영 설정은 `docs/domains/inference-gateway/dgx-spark-servers.md` 를 정본으로 본다.
비밀번호와 Hugging Face token 원문은 저장소 문서에 기록하지 않는다.

## Inference Gateway

Embedding, reranker, Docling, ASR 풀로드 백엔드는 별도 레포
`/projects/ai-do/ai-do-inference-gateway`에서 운영한다. AI-DO 루트의
`pnpm inference-gateway:*` 스크립트는 해당 레포의 실행 스크립트로 위임한다.
운영/검증 절차는 `docs/domains/inference-gateway/backend-operations.md`를 정본으로 본다.

## AI-DO Desktop

Electron desktop client는 별도 레포 `/projects/ai-do/ai-do-desktop`에서 관리한다.
GitLab 프로젝트는 `dwdcc/ai-do-desktop`이다. 이 포털 repo에는 desktop update
feed serving contract와 웹 설치 링크 설정만 남긴다.

### 루트 Markdown 기준

루트에는 현재 진입점 `README.md`와 활성 에이전트 규칙 `agents.md`만 둔다.
예외로 `CLAUDE.md`는 Claude Code 도구 실행 환경 전용 운영 노트다.
완료됐거나 현재 구현과 달라진 계획/MR 로그는 기본 작업 컨텍스트에 넣지 않는다.
과거 계획은 저장소 정본 문서로 유지하지 않는다. 원문이 필요하면 사용자가 명시했을 때
Git 이력에서만 복원하고, 현재 상태는 `docs/current/`와 코드/테스트를 기준으로 확인한다.
