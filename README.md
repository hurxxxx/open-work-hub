# Agentic Biz Hub

## VM Preview 배포

이 VM의 공개 preview는 `https://dwdcc.lumejs.com` 이며, 루트 스크립트
`scripts/vm-app-stack.sh` 를 `pnpm` script로 호출해서 운영한다.

### 배포

```bash
pnpm vm:app:deploy
```

이 명령은 다음을 수행한다.

- `nx build web` 로 web production build가 깨지지 않는지 확인한다.
- 기존 API, web, worker, worker-beat 프로세스를 중지한다.
- VM profile (`AI_DO_ENV_PROFILE=vm`) 기준으로 API, web dev server, worker, worker-beat를 다시 시작한다.
- 마지막에 API health, web shell, collab route 상태를 출력한다.

### 재시작만 할 때

코드 빌드 없이 실행 중인 VM preview 프로세스만 다시 띄울 때 사용한다.

```bash
pnpm vm:app:restart
```

### 상태 확인

```bash
pnpm vm:app:status
```

정상 상태의 핵심 체크는 다음과 같다.

- `api health: 200`
- `web shell: 200`
- `collab route: 401`

`collab route` 의 `401` 은 비로그인 요청이므로 정상이다. `404` 이면 backend route가 배포되지 않았거나 잘못 연결된 것이다.

### 로그 확인

```bash
pnpm vm:app:logs
```

### VM 포트

- API: `127.0.0.1:8000`
- Web: `0.0.0.0:4200`
- Postgres: `127.0.0.1:55432`
- Redis: `127.0.0.1:56379`
- MinIO: `127.0.0.1:59000`

### 주의

- 이 VM preview에서는 `prod.sh restart` 를 쓰지 않는다. `prod.sh` nginx stack도 `4200` 포트를 사용하므로 현재 preview web 프로세스와 충돌할 수 있다.
- VM Docker 접근은 일반 `docker` socket 권한이 없을 수 있으므로 repo helper (`dev_docker`) 또는 `sudo -n docker` 경로를 사용한다.
- API pytest의 Docker fixture는 `AI_DO_ENV_PROFILE=vm` 또는 `AI_DO_TEST_DOCKER_NETWORK=host` 를 붙여 실행해야 host-network fixture가 맞게 동작한다.

자세한 운영 유사 검증 메모는 `docs/working/dev-collab-validation.md` 를 참고한다.
