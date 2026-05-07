# Windows + WSL 개발 환경 셋업 가이드

이 문서는 Windows 환경에서 `agentic-biz-hub` 를 개발하기 위한 WSL2 기반 셋업 절차를 정리한다.
모든 개발 작업(코드 편집, 빌드, 테스트, 컨테이너 실행)은 **WSL2 안에서** 수행하고,
Docker 데몬만 Windows 측 Docker Desktop 을 통해 공유한다.

> **권장 환경**
> - Windows 11 (22H2 이상)
> - 가상화 지원이 켜진 CPU (BIOS 의 Intel VT-x / AMD-V 활성화)
> - 16GB 이상 RAM 권장 (WSL + Docker 동시 구동 시 8GB 는 빠듯함)
> - 30GB 이상 여유 디스크 (이미지/볼륨 포함)

---

## 1. WSL2 설치

### 1.1 WSL 활성화 및 Ubuntu 배포판 설치

PowerShell **(관리자 권한)** 을 열고:

```powershell
wsl --install -d Ubuntu-24.04
```

이 한 줄로 WSL 기능/가상머신 플랫폼 활성화, 리눅스 커널 설치, Ubuntu 24.04 설치, WSL2 기본 설정까지 모두 처리된다. 설치 후 재부팅하고, 시작 메뉴에서 **Ubuntu** 를 실행해 UNIX 계정명/비밀번호를 설정한다.

설치 확인:

```powershell
wsl --list --verbose
```

`Ubuntu-24.04` 옆 `VERSION` 이 `2` 로 표시되면 정상.

### 1.2 Ubuntu 패키지 업데이트 및 기본 도구 설치

WSL(Ubuntu) 터미널에서:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  build-essential curl wget git ca-certificates \
  unzip zip jq make pkg-config \
  libssl-dev libffi-dev \
  python3-venv
```

---

## 2. VS Code 에서 WSL 연결

### 2.1 VS Code 및 확장 설치

1. Windows 측에 [VS Code](https://code.visualstudio.com/) 설치 (User installer 권장).
2. Extensions 탭에서 **WSL** (`ms-vscode-remote.remote-wsl`) 설치. SSH/Containers 까지 한 번에 받고 싶으면 **Remote Development** 확장팩 (`ms-vscode-remote.vscode-remote-extensionpack`) 설치.

### 2.2 WSL 에서 VS Code 열기

WSL 터미널에서:

```bash
cd ~/projects/agentic-biz-hub
code .
```

처음 실행 시 VS Code Server 가 WSL 내부에 자동 설치된다. 좌측 하단 상태바가 `WSL: Ubuntu-24.04` 면 정상. 이 상태에서 설치하는 확장은 WSL 측에 따로 설치되며, 자동 동기화되지 않는다.

### 2.3 권장 확장 (WSL 측)

- `ms-python.python`
- `ms-python.vscode-pylance`
- `charliermarsh.ruff`
- `dbaeumer.vscode-eslint`
- `esbenp.prettier-vscode`
- `ms-azuretools.vscode-docker`
- `bradlc.vscode-tailwindcss`
- `eamodio.gitlens`

---

## 3. Docker Desktop 설치 및 WSL 통합

### 3.1 Docker Desktop 설치

[Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) 를 다운로드해 설치한다. 최신 버전은 WSL2 백엔드가 기본이므로 별도 옵션 변경 없이 진행하면 된다.

### 3.2 WSL Integration 활성화

Docker Desktop → **Settings** → **Resources** → **WSL Integration**

1. **Enable integration with my default WSL distro** 체크
2. 아래 목록에서 `Ubuntu-24.04` 토글을 ON
3. **Apply & Restart**

### 3.3 동작 확인

WSL 터미널에서:

```bash
docker version
docker compose version
docker run --rm hello-world
```

`hello-world` 메시지가 출력되면 성공. Docker Desktop 이 실행 중이어야 WSL 의 `docker` 명령이 작동한다.

---

## 4. 프로젝트 클론

### 4.1 Git 기본 설정

```bash
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
git config --global init.defaultBranch main
git config --global pull.rebase false
```

### 4.2 클론

반드시 WSL 네이티브 경로(`~/projects/...`) 에 클론한다. `/mnt/c/...` 같은 Windows 마운트 경로에 두면 I/O 가 5–10배 느려지고 hot reload 가 동작하지 않는다.

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/hurxxxx/agentic-biz-hub.git
cd agentic-biz-hub
```

---

## 5. Claude Code 용 프로젝트 셋업 프롬프트

레포 클론 직후, WSL 의 `~/projects/agentic-biz-hub` 에서 `claude` (Claude Code CLI) 를 실행한 뒤 아래 프롬프트를 그대로 붙여 넣으면 된다.

> 프롬프트는 `compose.local.yml` (postgres / redis / opensearch / minio / qdrant) 을 기준으로 작성되었다. 변경된 부분이 있다면 본 문서를 함께 갱신할 것.

````markdown
나는 Windows + WSL2 (Ubuntu 24.04) 환경에서 이 모노레포(`agentic-biz-hub`)를 처음 셋업한다.
Docker Desktop 의 WSL Integration 이 활성화되어 있어 WSL 안에서 `docker`, `docker compose` 명령이 동작한다.
아래 작업을 **순서대로 점검하며** 실제로 실행해 주세요. 각 단계마다 어떤 명령을 왜 실행하는지 한 줄씩 설명하고, 실패하면 원인을 찾아 고치고 재시도하세요.

## 0. 사전 점검
- `uname -a` 로 WSL2 (Linux ...microsoft-standard-WSL2...) 인지 확인
- `docker version`, `docker compose version` 으로 Docker Desktop 통합 상태 확인
- 현재 디렉터리가 레포 루트(`agentic-biz-hub`) 인지 확인

## 1. 시스템 / 언어 런타임 설치
- **Node.js**: `fnm` (https://github.com/Schniz/fnm) 으로 Node LTS 설치 후 `corepack` 으로 `package.json` 의 `packageManager` 에 명시된 pnpm 버전(`pnpm@10.33.0`)을 활성화
  - `curl -fsSL https://fnm.vercel.app/install | bash`
  - `fnm install --lts && fnm use lts-latest`
  - `corepack enable && corepack prepare pnpm@10.33.0 --activate`
- **Python**: `apps/api/pyproject.toml` 의 `requires-python = ">=3.12,<3.13"` 만족 필요
  - `uv` 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - `uv python install 3.12`
- 설치 후 `node -v`, `pnpm -v`, `uv --version`, `uv python list` 결과를 보여줄 것

## 2. 의존성 설치
- 루트에서 `pnpm install --frozen-lockfile`
- API 쪽: `cd apps/api && uv sync` (가상환경 자동 생성)
- 끝난 후 `pnpm nx graph --file=/tmp/nx-graph.json` 으로 워크스페이스 정상 인식 여부 확인

## 3. Docker 인프라 기동 (필수 컨테이너 전부)
`compose.local.yml` 에 정의된 다음 5개 컨테이너를 전부 띄워야 한다:
- `doowon-postgres` (Postgres 18, host port 55432)
- `doowon-redis` (Redis 7, host port 56379)
- `doowon-opensearch` (OpenSearch 3.3.2, host port 59200 / 59600)
- `doowon-minio` (MinIO, host port 59000 API / 59001 Console, root: minioadmin/minioadmin)
- `doowon-qdrant` (Qdrant, host port 6333)

작업:
1. `mkdir -p data/postgres data/redis data/opensearch data/minio data/qdrant`
2. `docker compose -f compose.local.yml up -d`
3. `docker compose -f compose.local.yml ps` 로 전부 `healthy` 가 될 때까지 기다리기 (최대 2분 polling)
4. 헬스체크:
   - `pg_isready` 로그 확인 또는 `docker exec doowon-postgres pg_isready -U ai_do_db -d ai_do_portal_dev`
   - `docker exec doowon-redis redis-cli ping` → `PONG`
   - `curl -fsS http://127.0.0.1:59200` (OpenSearch 루트 응답 200)
   - `curl -fsS http://127.0.0.1:59000/minio/health/ready`
   - `curl -fsS http://127.0.0.1:6333/collections`
5. 실패한 컨테이너가 있으면 `docker compose -f compose.local.yml logs <svc>` 로 원인 파악

## 4. 환경변수 / 시크릿 파일
- 레포에 `.env.example`, `apps/api/.env.example`, `apps/web/.env.example` 등이 있는지 검색해서 있으면 같은 디렉터리의 `.env` 로 복사하고 값 채우기
- 없으면 README / `agents.md` / `docs/` 를 훑어 필수 환경변수(예: `DATABASE_URL`, `REDIS_URL`, OpenAI/Anthropic 키 등)를 정리해서 알려줄 것
- 비어 있는 키가 있으면 사용자에게 물어볼 것 (절대 가짜 값으로 채우지 말 것)

## 5. DB 마이그레이션 및 시드
- `apps/api/alembic` 디렉터리가 있으므로 `cd apps/api && uv run alembic upgrade head`
- 시드 스크립트나 fixture 가 있으면 실행 (있는 경우만)

## 6. 동작 확인
- `pnpm dev` 또는 `./dev.sh` 로 웹/API 동시 기동 가능한지 확인
- 별도 터미널에서:
  - API: `curl -fsS http://127.0.0.1:<api-port>/health` (포트는 코드에서 확인)
  - Web: 브라우저에서 http://localhost:<web-port>
- 단위 테스트 1회: `pnpm test` (오래 걸리면 한 패키지만)

## 7. 마무리 리포트
- 설치한 도구/버전, 띄운 컨테이너 목록과 헬스 상태, 마이그레이션 결과, dev 서버 기동 결과를 표 형태로 정리해서 보여주기
- 다음에 개발자가 사용할 자주 쓰는 명령들을 cheatsheet 로 출력 (인프라 up/down, 마이그레이션, 테스트, dev 서버)

진행 중 막히는 부분은 임의로 우회하지 말고 원인을 찾아 고친 뒤 진행해 주세요.
````

---

## 6. 자주 쓰는 명령 cheatsheet

WSL 터미널, 레포 루트(`~/projects/agentic-biz-hub`) 기준.

```bash
# 인프라
docker compose -f compose.local.yml up -d        # 전체 컨테이너 기동
docker compose -f compose.local.yml ps           # 상태 확인
docker compose -f compose.local.yml logs -f api  # 로그 추적
docker compose -f compose.local.yml down         # 컨테이너 정지 (볼륨 유지)

# 의존성
pnpm install                                      # JS/TS deps
(cd apps/api && uv sync)                          # Python deps

# 개발 서버
./dev.sh                  # web + api 동시 (기본)
./dev.sh --api-only       # API 만
./dev.sh --web-only       # Web 만
./dev.sh --status         # 현재 상태
./dev.sh --stop           # 정지

# 마이그레이션
(cd apps/api && uv run alembic upgrade head)
(cd apps/api && uv run alembic revision --autogenerate -m "msg")

# 테스트 / 린트
pnpm test
pnpm lint
(cd apps/api && uv run pytest)
```

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|-------------|
| `docker: command not found` (WSL) | Docker Desktop 미실행 또는 WSL Integration 토글 OFF. 3.2 단계 재확인 |
| 파일 변경이 hot reload 안 됨 | 레포가 `/mnt/c/...` 에 있을 가능성. 반드시 `~/projects` 로 이동 |
| 포트 충돌 (55432, 56379 등) | Windows 측에서 같은 포트를 쓰는 프로세스 확인 또는 `compose.local.yml` 의 host 포트 매핑 변경 |
| OpenSearch 컨테이너 OOM | `compose.local.yml` 의 `OPENSEARCH_JAVA_OPTS` 힙 크기 조정 |
| `pnpm` 권한 에러 | `corepack enable` 을 sudo 없이 다시 실행 |
| VS Code 가 Windows 측 확장만 보여줌 | 좌측 하단 원격 표시기 클릭 → `Reopen Folder in WSL` |

---

## 8. 디렉터리 규칙 요약

- 코드는 항상 `~/projects/agentic-biz-hub` (= WSL `/home/<user>/projects/agentic-biz-hub`)
- `data/` 하위는 docker 볼륨 마운트용 디렉터리 — git 에 커밋하지 않음
- `.env*` 파일은 절대 커밋하지 않음
- VS Code 는 항상 `WSL: Ubuntu-24.04` 컨텍스트로 열기
