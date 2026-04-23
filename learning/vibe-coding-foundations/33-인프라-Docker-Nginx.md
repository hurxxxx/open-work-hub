# 33. 인프라 — Docker Compose · Nginx · 운영 환경

> **한 줄 요약.** 개발·스테이징·운영 어디서든 **동일한 실행 구성을 재현**하기 위해, 컨테이너(**Docker**)로 패키징하고, 여러 컨테이너를 **Compose**로 오케스트레이션하며, 외부 트래픽은 **Nginx** 가 처리한다.

> 🔑 **한 마디로.** 개발/스테이징/운영의 실행 환경을 컨테이너로 표준화하고, Nginx를 단일 진입점으로 두어 요청 라우팅·TLS·정적 서빙을 일관되게 관리하는 구조다.

### 인프라 구성 요소 역할

1. **컨테이너**: 앱과 실행 의존성을 함께 묶어 서버가 바뀌어도 동일 실행 결과를 보장합니다.
2. **Compose**: 다중 서비스를 선언 파일로 정의해 같은 구성(서비스/네트워크/볼륨)을 반복 재현합니다.
3. **Nginx**: 외부 HTTP 요청을 내부 서비스(API/협업 서버/정적 파일)로 라우팅하는 단일 게이트웨이입니다.

### ⚠️ 인프라 선택에서 자주 듣는 오해

1. **"Docker = 가상 머신(VM)"** — 다릅니다. VM은 운영체제 전체를 복제하고, 컨테이너는 커널은 공유하고 **프로세스와 파일시스템만 격리**합니다. 그래서 훨씬 가볍고 빠릅니다.
2. **"Compose는 옛날 도구"** — 아닙니다. 2024년 Compose V2(Go 재작성)로 현역이고, 단일 호스트 배포의 **가성비 최고 선택**입니다. Kubernetes가 무조건 상위 호환인 것은 아닙니다.
3. **"Nginx는 구식, 요즘은 뭐 쓴다더라"** — Nginx는 여전히 웹 서버 점유율 1~2위이며 보수적으로 유지하는 것이 **가장 안전한 선택**입니다. Caddy·Traefik은 대안이지 대체는 아닙니다.
4. **"컨테이너는 보안이 취약하다"** — 프로세스 격리 + 읽기 전용 파일시스템 + non-root 유저로 띄우면 오히려 **맨 호스트 실행보다 안전**합니다. 요지는 운영 습관이지 도구가 아닙니다.
5. **"Kubernetes를 쓰면 자동으로 확장되고 알아서 돌아간다"** — Kubernetes는 **복잡도 예산이 큰 팀**을 위한 도구입니다. 소규모 팀은 오히려 운영 부담이 늘어 프로덕트에 쏟을 시간이 줄어듭니다.

---

## 1. 컨테이너의 세계관 (복습)

11장에서 개괄한 내용을 이 프로젝트에 맞춰 구체화합니다.

- **컨테이너** = 앱 + 그 앱이 필요로 하는 모든 환경을 얇게 포장한 박스.
- **이미지** = 그 박스의 템플릿(스냅샷).
- **Dockerfile** = 이미지 레시피.
- **Compose** = 여러 서비스를 선언적으로 함께 실행·관리하는 도구.

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

### 4.6 2024~2026 실무 대안 풍경

Compose가 "옛 도구"라는 건 오해입니다. 2024~2026 실무에서 단일 호스트 배포는 여전히 Compose가 주류이고, 큰 규모는 Kubernetes, 그 중간은 Nomad·ECS 정도로 정리됩니다.

| 규모 | 권장 스택 | 이유 |
|---|---|---|
| 단일 서버·소규모 팀 (≤5 서비스) | **VM + docker compose** | 단순성, 학습 비용 0에 가까움. 이 프로젝트 현 시점. |
| 2~3 서버 | Compose + SSH 배포 스크립트, 또는 Nomad | 오케스트레이션은 필요한데 K8s는 과함. |
| 중대형 멀티 서비스 | **Kubernetes** (또는 매니지드 K8s: EKS/GKE) | 자동 스케일·롤링·셀프힐링. 전담 인프라 인력 필요. |
| 서버리스 선호 | AWS ECS Fargate·Google Cloud Run | 컨테이너 단위로 관리되지만 호스트는 공급자 몫. |

**핵심 원칙**: Compose → Nomad → Kubernetes는 "업그레이드"가 아니라 **다른 문제를 푸는 도구들**입니다. "오버엔지니어링 방지"가 이 프로젝트의 선택 기준입니다.

### 4.7 "개발-운영 유사성(dev-prod parity)" 강조

12 Factor App에서 말하는 핵심 가치입니다. 내 노트북과 운영 서버가 **가능한 한 동일한 구성**이어야 배포 사고가 줄어듭니다. Compose는 이 가치를 자연스럽게 구현하는 도구입니다.

- dev와 prod가 같은 PostgreSQL 18 이미지를 쓴다 → "로컬은 SQLite, 운영은 Postgres"처럼 미묘한 차이로 터지는 버그가 사라진다.
- 같은 Dockerfile 기반으로 빌드된 이미지가 dev/staging/prod를 거친다 → 이미지가 바뀌지 않고 환경 변수만 바뀐다.
- AI에게 "로컬에서 재현돼?" 라고 물을 때 "예"라는 답이 의미 있어진다(로컬과 운영이 같은 형상이기 때문).

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

요청이 Nginx를 거쳐 내부 서비스로 들어가는 흐름을 트리로 나타내면:

- 사용자 브라우저 → HTTPS(443)
  - Nginx 리버스 프록시 (단일 진입점)
    - `/` → `web` (정적 SPA: HTML, JS, CSS)
    - `/api/` → `api:8000` (FastAPI REST + SSE)
    - `/collab/` → `collab:1234` (WebSocket Yjs)

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
- **타임아웃**: 기본값(60초)은 장기 연결에 짧습니다. 수 분 이상으로 늘려야 합니다.

### 5.5 대안

- **Caddy**: 자동 HTTPS가 매력. 사용이 매우 쉬움.
- **Traefik**: Docker와 궁합이 좋아 서비스 디스커버리가 편함.
- **Apache httpd**: 전통 강자지만 최신 트렌드는 Nginx/Caddy 쪽.
- **클라우드 LB (ALB 등)**: 클라우드 네이티브 배포라면 선택.

Nginx는 가장 보편적이고 자료가 풍부해 장기 유지에 유리합니다.

### 5.6 왜 이 프로젝트는 Nginx + Compose를 유지하는가

1. **팀 경험**: Nginx 설정은 인터넷에 자료가 가장 많고, AI(Claude/ChatGPT)도 가장 잘 짚어 냅니다. 누구에게 물어도 답을 얻습니다.
2. **단순성**: 자동 HTTPS가 없어도 `certbot`으로 충분합니다. 도구를 바꿀 이유보다 유지할 이유가 큽니다.
3. **오버엔지니어링 방지**: Traefik의 동적 라우팅, Caddy의 자동 HTTPS는 **우리 규모에선 필요 이상**입니다. 인력이 남을 때 도입 검토.
4. **SSE/WebSocket 검증**: Nginx의 `proxy_buffering off`, `Upgrade` 헤더 패턴은 오랜 기간 **프로덕션에서 검증**된 레시피입니다.

### 🏢 새 서버로 이사 가기

운영 서버 교체가 필요하다고 합시다. Compose 덕분에 이사는 다음 흐름으로 끝납니다.

1. 새 서버에 Docker 설치.
2. Git 저장소 클론 + `.env`만 복사(비밀값은 시크릿 매니저에서 받아오기).
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
4. DB 덤프 복원, Alembic 마이그레이션.
5. DNS를 새 서버 IP로 변경.

**이게 왜 AIDOO Portal에 중요한가**: 클라우드 비용 최적화로 인스턴스 사이즈를 바꾸거나, 리전 이전을 해야 할 때 **반나절에 끝낼 수 있는 루틴**이 된다는 뜻입니다. 수동 서버 구축이었다면 며칠이 걸립니다.

### 🛠️ 5분 실습 — 컨테이너 안 탐험

```bash
# 현재 실행 중인 컨테이너 목록
docker compose ps

# api 컨테이너 안으로 들어가 보기
docker compose exec api bash

# 안에서 파이썬 버전 확인
python --version
# 밖으로 나오기
exit

# api 로그만 실시간으로 보기
docker compose logs -f api
```

이 세 명령이 운영 트러블슈팅의 80%를 해결합니다.

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

- 컨테이너 이미지는 실행 환경을 고정해 어느 서버에서나 동일하게 동작합니다.
- Compose 파일은 다중 서비스 실행 구성을 선언적으로 정의합니다.
- Nginx는 외부 요청을 적절한 내부 서비스로 전달합니다.
- 서버 장애 시 동일 이미지를 새 호스트에서 재기동해 복구 시간을 단축할 수 있습니다.

---

## 10. 핵심 요약

- **Docker + Compose**: 개발·운영을 동일한 선언으로 재현. 이 프로젝트의 표준 배포 방식.
- **Nginx**: 바깥 요청을 안으로 라우팅, HTTPS·캐시·WebSocket/SSE 프록시.
- 개발/운영 Compose를 분리하고, 시크릿은 `.env`로 분리.
- 큰 규모로 넘어가면 Kubernetes를 고려하되, 이 프로젝트 규모엔 과함.
