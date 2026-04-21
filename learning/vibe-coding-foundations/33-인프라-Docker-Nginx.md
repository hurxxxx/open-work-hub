# 33. 인프라 — Docker Compose · Nginx · 운영 환경

> **한 줄 요약.** 개발·스테이징·운영 어디서든 "**같은 그림**"으로 서비스를 띄우기 위해, 컨테이너(**Docker**)로 감싸고, 여러 컨테이너를 한 번에 올리는 **Compose**로 묶고, 바깥 세상과는 **Nginx** 가 연결한다.

---

## 1. 컨테이너의 세계관 (복습)

11장에서 개괄한 내용을 이 프로젝트에 맞춰 구체화합니다.

- **컨테이너** = 앱 + 그 앱이 필요로 하는 모든 환경을 얇게 포장한 박스.
- **이미지** = 그 박스의 템플릿(스냅샷).
- **Dockerfile** = 이미지 레시피.
- **Compose** = 여러 박스를 한꺼번에 지휘하는 선언.

---

## 2. 이 프로젝트의 컨테이너 구성

`docker-compose.yml` / `docker-compose.prod.yml` 에 다음 서비스들이 정의됩니다(프로젝트 구조 기반).

| 서비스 | 이미지 | 역할 |
|---|---|---|
| `web` | 자체 빌드 | 프런트엔드 정적 자산 서빙(또는 Nginx 경유) |
| `api` | 자체 빌드 | FastAPI (gunicorn/uvicorn) |
| `worker` | 자체 빌드 | Celery 워커 |
| `beat` | 자체 빌드 | Celery Beat 스케줄러 |
| `postgres` | `postgres:18` | DB |
| `redis` | `redis:7-alpine` | 브로커·캐시 |
| `minio` | `minio/minio` | 객체 저장소 |
| `nginx` | `nginx:1.27` | 리버스 프록시 · TLS |
| `collab` | 자체 빌드 | `packages/docs-collab-hub` y-websocket 서버 |

각 서비스는 **같은 Docker 네트워크**를 공유해 `postgres:5432`, `redis:6379` 처럼 **서비스 이름**으로 서로를 찾습니다.

---

## 3. Dockerfile 패턴 — 이 프로젝트의 예

### 3.1 멀티 스테이지 빌드(프런트)

```dockerfile
# 1단계: 빌드
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm nx build web

# 2단계: 서빙
FROM nginx:1.27-alpine
COPY --from=build /app/dist/apps/web /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

빌드 단계의 무거운 도구가 최종 이미지에 빠지므로 **이미지 크기가 작아집니다**.

### 3.2 백엔드(파이썬)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .
CMD ["uv", "run", "uvicorn", "aidoo_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.3 .dockerignore

Node_modules·`.venv`·`dist` 같은 큰 폴더를 이미지에 넣지 않도록 제외. 빌드 속도와 보안에 중요.

---

## 4. Docker Compose — "여러 박스의 오케스트라"

### 4.1 개념

`docker-compose.yml` 한 파일에 서비스·볼륨·네트워크를 선언하고, `docker compose up` 한 줄로 전부 기동.

### 4.2 단순 예

```yaml
version: "3.9"
services:
  api:
    build: ./apps/api
    env_file: .env
    depends_on: [postgres, redis]
    ports: ["8000:8000"]
  postgres:
    image: postgres:18
    environment:
      POSTGRES_USER: aidoo
      POSTGRES_PASSWORD: ...
      POSTGRES_DB: aidoo
    volumes: [pg_data:/var/lib/postgresql/data]
volumes:
  pg_data:
```

### 4.3 개발 vs 운영

이 프로젝트는 **개발용**과 **운영용** Compose 파일을 분리합니다.

- **dev**: 코드 볼륨 마운트(핫 리로드), 디버그 포트 오픈, MinIO 웹 콘솔 노출.
- **prod**: 이미지 빌드 후 실행, 볼륨 대신 내장, HTTPS, 시크릿 관리.

`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` 처럼 **여러 파일을 합쳐** 구성.

### 4.4 `.env` 와 시크릿

민감값(DB 비밀번호, OpenAI API 키)은 `.env`. Git에는 올리지 않음(`.gitignore`). 운영에선 **시크릿 매니저**(Vault, Doppler, 1Password 등) 연동 권장.

### 4.5 언제 Compose가 부족한가

- **여러 서버**에 자동 배치 → Kubernetes·Nomad 필요.
- **자동 스케일·롤링 업데이트** → Kubernetes 장점.
- **사내 단일 호스트**에서 돌리는 중규모 서비스엔 Compose만으로도 충분.

이 프로젝트는 규모와 운영 난이도를 고려해 Compose 선택.

---

## 5. Nginx — 세상과의 접점

### 5.1 왜 필요한가

백엔드 FastAPI·프런트 정적 파일을 직접 공개하면 여러 문제가 있습니다.

- HTTPS 종료·인증서 관리
- 도메인·경로 라우팅
- 정적 파일 캐싱·압축
- 버퍼링, 레이트 리밋
- 여러 서비스를 **하나의 도메인** 아래로 모으기

**Nginx 1.27** 가 이 모든 역할을 맡습니다.

### 5.2 전형적 구성

```
                [사용자 브라우저]
                      │ HTTPS
                      ▼
                  ┌──────┐
                  │ Nginx│  (443/80)
                  └──────┘
                 /   │   \
       정적파일  API   WS/SSE
         │      │       │
      [web]   [api]  [collab]
```

### 5.3 예시 설정 스니펫

```nginx
server {
  listen 443 ssl http2;
  server_name aidoo.example.com;

  ssl_certificate     /etc/letsencrypt/live/aidoo/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/aidoo/privkey.pem;

  # 정적 SPA
  root /usr/share/nginx/html;
  location / {
    try_files $uri /index.html;
  }

  # API
  location /api/ {
    proxy_pass         http://api:8000/;
    proxy_set_header   Host $host;
    proxy_read_timeout 300s;
    proxy_buffering    off;           # SSE에 필수
  }

  # WebSocket (Yjs 협업)
  location /collab/ {
    proxy_pass http://collab:1234/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
  }
}
```

### 5.4 SSE와 WebSocket의 프록시 주의

- **SSE**: `proxy_buffering off` 가 중요. 기본값으로 두면 응답이 뭉쳐서 지연됨.
- **WebSocket**: `Upgrade`, `Connection` 헤더를 그대로 전달해야 업그레이드 성공.
- **타임아웃**: 기본값(60초)은 장기 연결에 짧음. 수 분 이상으로 늘려야 함.

### 5.5 대안

- **Caddy**: 자동 HTTPS가 매력. 사용이 매우 쉬움.
- **Traefik**: Docker와 궁합이 좋아 서비스 디스커버리가 편함.
- **Apache httpd**: 전통 강자지만 최신 트렌드는 Nginx/Caddy 쪽.
- **클라우드 LB (ALB 등)**: 클라우드 네이티브 배포라면 선택.

Nginx는 가장 보편적이고 자료가 풍부해 장기 유지에 유리합니다.

---

## 6. 배포 파이프라인(개념)

11장의 CI/CD를 이 프로젝트 기준으로 구체화하면:

1. **Git Push**
2. **CI**: 테스트, 린트, 이미지 빌드 → 레지스트리(GHCR 등)에 푸시
3. **CD**: 서버에 SSH 접속 → `docker compose pull && docker compose up -d` (또는 Ansible·Portainer)
4. **Alembic 마이그레이션**: api 컨테이너 안에서 `alembic upgrade head`
5. **헬스체크**: Nginx 앞단에서 `/health` 확인, 이상 시 롤백

---

## 7. 모니터링·로그 (개념)

- 표준 출력 로그를 docker가 수집. 운영에선 **Loki / ELK / Grafana Cloud** 등으로 전송.
- 지표: Prometheus + Grafana가 사실상 표준.
- 알림: Grafana Alert, PagerDuty, Slack 등.
- 트레이싱: OpenTelemetry(Otel). FastAPI는 공식 통합 존재.

작은 규모에선 **Portainer 같은 GUI**만 있어도 모니터링이 편합니다.

---

## 8. 보안 원칙(인프라 편)

- **원칙적으로 비공개**: 내부 서비스(redis, postgres, minio API)는 호스트 외부로 포트를 열지 않음.
- **비밀번호·API 키**: `.env`는 절대 공개 저장소에 커밋 금지.
- **HTTPS 필수**: 운영에선 Let's Encrypt 자동 갱신.
- **이미지 취약점 스캔**: Trivy 같은 도구 주기 실행.
- **백업·복구 연습**: 백업은 해 봤지만 복구는 안 해 봤다 → 최악의 상태.

---

## 9. 비개발자를 위한 "컨테이너 실감" 정리

- 컨테이너를 **택배 상자**라고 생각하세요. 어느 트럭에 실어도 내용물이 흔들리지 않습니다.
- Compose는 **상자들의 주문서**. "이 상자 7개를 이 순서대로 이렇게 연결해 주세요".
- Nginx는 **빌딩 로비의 안내 데스크**. 외부인을 적절한 사무실로 안내.
- 서버가 죽어도, 새 서버에 상자만 다시 실으면 **같은 그림**이 금방 뜹니다. 이것이 컨테이너의 가치.

---

## 10. 핵심 요약

- **Docker + Compose**: 개발·운영을 동일한 선언으로 재현. 이 프로젝트의 표준 배포 방식.
- **Nginx**: 바깥 요청을 안으로 라우팅, HTTPS·캐시·WebSocket/SSE 프록시.
- 개발/운영 Compose를 분리하고, 시크릿은 `.env`로 분리.
- 큰 규모로 넘어가면 Kubernetes를 고려하되, 이 프로젝트 규모엔 과함.

---

## 11. 이해도 체크

1. 같은 앱이 "내 노트북에서는 되는데 서버에선 안 돼요" 문제가 컨테이너로 어떻게 해결되는지 설명해 보세요.
2. Compose로 DB 비밀번호를 관리할 때 `.env`를 Git에 커밋하면 왜 위험한가요?
3. SSE/WebSocket을 Nginx 뒤에 둘 때 신경 써야 할 설정 두 가지를 들어 보세요.
4. Compose로 충분한 규모와 Kubernetes가 필요한 규모의 기준을 여러분 말로 설명해 보세요.
5. 백업을 해 두어도 "실수로 테이블을 드롭"한 사고에서 왜 복구 연습이 중요한지 적어 보세요.
