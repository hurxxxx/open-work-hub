# Prod-Like Docs Collaboration Validation

이 저장소의 web 앱은 `Next router` 가 아니라 `Vite build + BrowserRouter SPA` 다.  
운영 유사 검증은 `정적 파일 서빙 + SPA history fallback + /api websocket proxy` 를 기준으로 맞춘다.

## Stack

- Docker: `redis`, `nginx`
- Optional Docker: `minio` only when `DOOWON_DEV_USE_LOCAL_MINIO=1` or endpoint 가 `127.0.0.1:59000` 를 가리킬 때
- Optional Docker: `postgres` only when `DOOWON_DEV_USE_LOCAL_POSTGRES=1` or DSN 이 `127.0.0.1:55432` 를 가리킬 때
- Host process: `nx build web`, `uvicorn` API `8001..8008`
- Entry URL: `http://127.0.0.1:4200`
- Root runner: `./prod.sh`

## Entry Points

- `./prod.sh start`
- `./prod.sh stop`
- `./prod.sh status`
- `./prod.sh log`
- `./prod.sh restart`
- `./prod.sh smoke`

## Current VM Public Preview

`https://dwdcc.lumejs.com` currently points at a VM app preview stack, not the
`prod.sh` nginx/static stack.

- Infra containers use host networking and listen on local ports:
  - Postgres: `127.0.0.1:55432`
  - Redis: `127.0.0.1:56379`
  - MinIO: `127.0.0.1:59000`
- VM profile uses `compose.dev.host.yml` for those infra containers. The VM
  preview runner starts only infra services, not the nginx service, because the
  preview web process owns port `4200`.
- API listens on `127.0.0.1:8000` with `DOOWON_API_INSTANCE_ID=remote-api`.
- Web listens on `0.0.0.0:4200` through Vite and proxies `/api` to `127.0.0.1:8000`.

Use this runner for the current public preview:

- `pnpm vm:app:deploy` builds web, restarts API/web, and prints route checks.
- `pnpm vm:app:restart` restarts only API/web.
- `pnpm vm:app:status` checks the local API/web ports and public collab route.

For the unauthenticated whiteboard collaboration session probe, `401` is expected.
`404` means the backend route is not deployed:

```bash
curl -i https://dwdcc.lumejs.com/api/v1/workspaces/hq/whiteboard/collab/items/probe/session
```

Do not run `prod.sh restart` while the VM app preview owns port `4200`; the
`prod.sh` nginx stack also wants that port.

## Notes

- `nginx` 는 `dist/apps/web` 를 정적으로 서빙하고 `/api` 는 `8001..8008` 로 round-robin proxy 한다.
- deep link 새로고침은 `try_files ... /index.html` 로 처리한다.
- websocket upgrade 는 같은 `/api` proxy 에서 처리한다.
- `prod.sh` 는 루트 `.env` 를 먼저 읽고, `DOOWON_POSTGRES_DSN` 이 remote DB 를 가리키면 local postgres 는 띄우지 않는다.
- `prod.sh` 는 루트 `.env` 를 먼저 읽고, `DOOWON_MINIO_ENDPOINT` 가 remote MinIO 를 가리키면 local minio 는 띄우지 않는다.
- dev 프로필에서도 `dev login` 은 유지한다. `./prod.sh start` 가 fresh DB 에 dev login 계정까지 seed 한다.
- host API 는 `DOOWON_API_INSTANCE_ID=dev-api-N` 으로 뜨고, 모든 HTTP 응답 헤더에 `X-Doowon-Instance-Id` 가 실린다.
- dev 기본 포트는 로컬 dev 충돌을 피하려고 분리했다.
  - `nginx`: `4200`
  - `postgres`: `55432` (`local postgres` 를 쓸 때만)
  - `redis`: `56379`
  - `minio`: `59000` (`local minio` 를 쓸 때만)
- 운영과 의도적으로 다른 점은 `dev login 유지` 하나뿐이다.
