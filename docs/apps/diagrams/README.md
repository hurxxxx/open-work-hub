# Diagrams App Operations

Open ALM 다이어그램 앱은 draw.io UI를 별도 컨테이너로 실행하고, Open ALM API가 다이어그램 XML과 PNG 미리보기를 저장한다.

## Runtime Components

| Component             | Dev                                                                          | Prod                                   |
| --------------------- | ---------------------------------------------------------------------------- | -------------------------------------- |
| Open ALM web/API         | 기존 dev/prod runtime                                                        | 기존 prod systemd runtime              |
| draw.io               | `open-alm-dev-drawio`, 기본 `:18082`                                            | `open-alm-prod-drawio`, `127.0.0.1:18083` |
| Browser iframe origin | private/local host는 접속 중인 host의 `:18082`, public dev host는 `/drawio/` | `https://drawio.open-alm.example/`             |
| Storage               | Open ALM MinIO bucket                                                           | Open ALM production MinIO bucket          |

개발에서는 고정 Tailscale IP를 설정하지 않는다. private/local host로 접속하면 웹 앱은 현재 접속한 `window.location.hostname`에 `OPEN_ALM_DRAWIO_PORT`를 붙여 iframe URL을 만든다. 예를 들어 사용자가 `http://100.87.48.58:4200`으로 접속하면 draw.io iframe은 `http://100.87.48.58:18082/`를 사용한다. `https://dev.open-alm.example`처럼 public HTTPS dev host로 접속하면 브라우저가 TLS 없는 `:18082` 포트를 직접 열지 않도록 같은 origin의 `/drawio/` 프록시를 사용한다.

## Environment Contract

- Dev `.env`: `OPEN_ALM_DRAWIO_BIND_HOST=0.0.0.0`, `OPEN_ALM_DRAWIO_SERVER_URL=`을 사용한다.
- Prod `.env`: `OPEN_ALM_DRAWIO_BIND_HOST=127.0.0.1`, `OPEN_ALM_DRAWIO_PORT=18083`, `OPEN_ALM_DRAWIO_SERVER_URL=https://drawio.open-alm.example/`을 사용한다.
- `OPEN_ALM_DRAWIO_IMAGE_TAG`는 draw.io 이미지 버전을 고정한다.
- `OPEN_ALM_DRAWIO_PORT`는 host port이며 개발 기본값은 `18082`, 운영 기본값은 `18083`이다. 같은 서버에서 dev/prod draw.io를 함께 띄우기 때문에 운영은 별도 loopback 포트를 쓴다.

운영 `.env`를 바꾸면 GitLab Secure File의 `.env.production`도 같은 키셋과 값으로 갱신해야 한다. 값은 비밀이 아니지만, 전체 `.env` 파일은 비밀 파일로 취급한다.

## Deploy Checklist

1. 운영 DNS와 TLS 인증서가 `drawio.open-alm.example`을 포함하는지 확인한다.
2. `/projects/open-alm/prod/.env`에서 draw.io 키를 확인한다.
3. 운영 checkout에서 `pnpm infra:prod:up` 또는 `scripts/infra-stack.sh prod up`으로 `open-alm-prod-drawio`를 기동한다.
4. `docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' open-alm-prod-drawio`가 `healthy`인지 확인한다.
5. `curl -fsSI http://127.0.0.1:18083/`가 성공하는지 확인한다.
6. `pnpm prod:deploy` 또는 표준 운영 배포 절차를 실행한다.
7. `pnpm prod:smoke`와 `pnpm check:runtime-separation:live`를 통과시킨다.

## Nginx

운영 nginx는 `drawio.open-alm.example`를 `127.0.0.1:18083`로 프록시한다. 메인 앱 origin의 `/drawio/`는 같은 origin iframe 경로로 쓰지 않고 `drawio.open-alm.example`로 리다이렉트한다.

`drawio.open-alm.example` 서버 블록은 draw.io를 Open ALM origin과 분리하기 위한 보안 경계다. 인증 토큰은 Open ALM origin의 browser storage에 있으므로, draw.io를 메인 origin 아래에 직접 프록시하지 않는다.

## Rollback

앱 코드를 이전 버전으로 되돌려도 draw.io 컨테이너는 남겨 둬도 된다. 다만 신규 다이어그램 앱을 다시 활성화하려면 아래가 모두 살아 있어야 한다.

- `open-alm-prod-drawio` healthy
- `https://drawio.open-alm.example/` TLS 정상
- API Alembic revision이 다이어그램 테이블 revision을 포함
- MinIO 접근 정상
