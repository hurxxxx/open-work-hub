# 리눅스 개발 환경 설치 가이드

현업 참여자가 Codex 또는 Claude Code로 코드를 수정하고 브라우저에서 확인하기 위한 설치 절차다.
Web·API·Worker는 저장소 소스에서 실행하고, PostgreSQL·Redis 등 기반 서비스는 기존 Docker Compose로 실행한다.
운영 배포는 [Release Domain](docs/domains/release/README.md)의 별도 절차를 따른다.

## 1. 에이전트에 설치 요청하기

먼저 서버에 접근할 수 있는 Codex 또는 Claude Code를 설치하고 로그인한다.
도구 설치는 [Codex 공식 안내](https://learn.chatgpt.com/docs/codex/cli) 또는
[Claude Code 공식 안내](https://code.claude.com/docs/en/quickstart)를 따른다.
GitLab 저장소 접근 권한과 필요한 OS 패키지를 설치할 권한을 준비한다.
코딩 에이전트의 로그인과 프로젝트 안에서 사용하는 AI 서비스 인증은 별개다.

저장소를 연 뒤 다음과 같이 요청한다.

> AGENTS.md와 INSTALL.md를 읽고 이 리눅스 서버에
> 개발 환경을 설치해줘. 기존 설정과 데이터를 보존하고 필요한 도구만 설치해줘.
> 먼저 최소 환경에서 로그인과 화면을 확인한 뒤, 내가 개발할 기능에 필요한 서비스를 연결해줘.
> 비밀값은 대화에 요청하지 말고 서버에서 입력할 방법을 안내해줘.
> 끝나면 접속 방법, 실행한 검사, 사용 가능한 기능과 추가 설정이 필요한 기능을 알려줘.

에이전트는 [AGENTS.md](AGENTS.md)와
[개발 환경 스킬](.agents/skills/owh-dev-environment/SKILL.md)을 따른다.
이 문서는 설치 절차의 진입점이며 기능별 설정은 아래의 소유 문서에서 확인한다.

## 2. 서버와 저장소 준비

기존 체크아웃이 있으면 그 위치에서 먼저 상태를 확인한다.
새 서버라면 GitLab 프로젝트의 Clone 메뉴에서 주소를 받아 원하는 작업 경로 아래의
`dev` 디렉터리에 `dev` 브랜치를 내려받는다. 주소에 토큰을 넣지 않는다.

```bash
git clone --branch dev '<GitLab에서-받은-저장소-주소>' dev
cd dev
```

이후 명령은 별도 표시가 없으면 저장소 루트에서 실행한다.

```bash
cat /etc/os-release
uname -m
git status --short --branch
df -h .
free -h
```

배포판·CPU·사용 가능한 메모리와 저장 공간을 확인한 뒤 필요한 도구만 설치한다.
서버별 사용자명·절대 경로·기존 서비스가 있다고 가정하지 않는다.
사용 중인 체크아웃과 DB가 개발 대상인지 확인하고, 기존 변경사항과 데이터는 유지한다.

| 도구 | 버전 기준 및 설치 방법 |
| --- | --- |
| Bash, Git, curl, CA 인증서, 시스템 `python3`, `lsof`, `pgrep` | 해당 Linux 배포판의 패키지 관리자로 준비. 개발 스크립트와 환경설정 도구가 사용한다. |
| Node.js와 npm | [package.json](package.json)의 `engines.node`를 만족하도록 [Node.js 공식 안내](https://nodejs.org/en/download)를 따른다. |
| pnpm | 루트 `package.json`의 `packageManager`에 지정된 버전을 사용한다. [공식 설치 안내](https://pnpm.io/installation) |
| uv와 앱용 Python | [uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)와 [Python 설치 안내](https://docs.astral.sh/uv/guides/install-python/)를 따른다. Python 범위는 [API](apps/api/pyproject.toml)·[Worker](apps/worker/pyproject.toml)의 `requires-python`이 기준이다. |
| Docker Engine와 Compose 플러그인 | [Docker 공식 설치 안내](https://docs.docker.com/engine/install/)에서 배포판별 절차를 선택한다. |

Node/npm 설치 후 pnpm이 없거나 버전이 다르면 현재 Node 설치의 패키지 관리 방식에 맞춰
아래의 프로젝트 지정 버전을 설치한다. 프로젝트 의존성 설치는 일반 개발 사용자로 진행한다.

```bash
npm install --global "$(node -p 'require("./package.json").packageManager')"
uv python install 3.12
```

터미널을 다시 열어 새 도구가 PATH에 반영되었는지 확인한다.
OS의 `python3`를 교체할 필요는 없다. 앱은 uv가 관리하는 Python을 사용한다.

```bash
node --version
pnpm --version
python3 --version
uv --version
docker compose version
docker info --format '{{.ServerVersion}}'
command -v git curl lsof pgrep
```

Docker 데몬 연결과 사용 권한을 해결한 뒤 다음 단계로 간다.
`docker` 실행 파일만 존재하거나 기존 컨테이너가 보인다는 이유로 준비 완료로 판단하지 않는다.
첫 Python 의존성 설치에는 AI 라이브러리도 포함되어 다운로드가 클 수 있다.
추가 기능의 모델 다운로드·브라우저 설치까지 고려하고, 서버 사양이 검증되었다고 추정하지 않는다.

## 3. 의존성과 환경설정 준비

```bash
pnpm install --frozen-lockfile
uv sync --frozen --python 3.12 --directory apps/api
uv sync --frozen --python 3.12 --directory apps/worker
```

잠금 파일을 변경하거나 의존성을 업그레이드해서 설치 오류를 우회하지 않는다.
실패한 패키지·인증·네트워크·빌드 도구 문제를 구분하여 해결한다.

환경설정은 먼저 기존 파일 유무와 키 목록을 확인한다. 이 도구는 값을 출력하지 않는다.

```bash
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh status --source .env.example --target .env
```

결과가 `status=missing_target`일 때만 다음 명령으로 개발용 템플릿을 설치한다.

```bash
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh install --source .env.example --target .env
```

이미 `.env`가 있다면 유지한다. `status=different`는 사용자 설정이 있다는 뜻일 수 있으며
템플릿으로 덮어쓸 이유가 아니다. 필요한 키만 기존 값을 보존하여 맞춘다.
환경 파일 취급은 [환경설정 절차](.agents/skills/owh-env-contracts/references/env-files.md)를 따른다.

```bash
pnpm check:env-contract
pnpm check:path-hardcoding
```

API 키는 사용자가 서버의 편집기 또는 비밀 입력 경로로 `.env`에 넣는다.
파일 권한은 소유자만 읽고 쓸 수 있는 `0600`으로 유지한다.
키 확인 시에는 존재 여부만 보고하고, `.env` 내용·컨테이너 환경·해석된 Compose 설정을 출력하지 않는다.

Claude Code를 사용할 때 공통 스킬 연결도 확인한다.

```bash
pnpm setup:claude-skills
pnpm check:skills
```

## 4. 최소 환경으로 첫 로그인 확인

새 개발 DB에서 설치 경로를 확인하는 단계다. 기존 DB가 있다면 대상과 마이그레이션 호환성을 먼저 확인한다.
최소 환경은 PostgreSQL·Redis와 Web·API를 실행하고 개발용 계정을 준비한다.
파일 저장소·검색·AI·RAG·화상회의 기능이 빠진 로그인·화면 확인용 구성이다.

첫 터미널에서 실행하고 종료하지 않는다.

```bash
pnpm dev:minimal
```

`dev.sh`가 개발 인프라를 준비하고, 기본 설정에서는 API 시작 전에 Alembic 마이그레이션을 실행한다.
DB를 지우거나 `stamp`로 오류를 건너뛰지 않는다. 이전 스키마라면
[API 마이그레이션 안내](apps/api/README.md#alembic)를 먼저 확인한다.

두 번째 터미널에서 같은 저장소로 이동해 확인한다.

```bash
pnpm dev:infra:minimal:status
./dev.sh --status
pnpm dev:login-smoke
```

기본 Web 주소는 `http://127.0.0.1:4200`, API 주소는 `http://127.0.0.1:8001`이다.
포트를 변경한 환경에서는 실제 개발 설정을 따른다.
개발용 로그인 계정은 [README의 안내](README.md#dev)를 따른다.
공유·공개 운영 서비스에는 개발용 기본 계정을 사용하지 않는다.

브라우저 검사까지 수행하려면 다음을 실행한다.

```bash
pnpm e2e:install
pnpm dev:login-browser-smoke
```

Chromium의 OS 라이브러리가 빠졌다면
[Playwright 시스템 의존성 안내](https://playwright.dev/docs/browsers#install-system-dependencies)에 따라
`pnpm exec playwright install-deps chromium`으로 준비한 뒤 다시 검사한다.
최소 환경 검사 통과는 전체 업무 기능의 설치 완료를 뜻하지 않는다.

## 5. 내 PC 브라우저에서 서버 접속

서버의 `127.0.0.1`은 서버 자신을 가리킨다. 기본 개발 환경은 내 PC에서 SSH 터널로 확인할 수 있다.
다음 명령은 **내 PC의 터미널**에서 실행한다. 사용자·서버 주소는 실제 SSH 접속 대상으로 바꾼다.

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:4200:127.0.0.1:4200 '<사용자>@<서버주소>'
```

터널을 유지한 채 내 PC에서 `http://127.0.0.1:4200`에 접속한다.
기본 Web 개발 서버가 API 요청을 프록시하므로 첫 로그인에는 API 포트를 별도로 공개할 필요가 없다.
Bento처럼 별도 주소를 쓰는 기능은 해당 기능 문서의 접속 설정과 추가 터널을 함께 구성한다.

여러 사람이 사용할 공개 개발 도메인은 HTTPS 프록시·호스트 허용 설정·계정 구성을 따로 준비한다.
포트 전체를 공개하여 해결하지 않는다. 공개 접속 검사와 상시 실행 방식은
[지속 실행 계약](docs/domains/release/README.md#persistent-development-runtime) 및
[사용자 수용 검사](docs/product/core-platform-user-acceptance.md)를 따른다.

## 6. 실제 기능 개발용 서비스 연결

사용할 기능의 설정을 준비한 뒤 최소 실행을 종료하고 전체 개발 경로로 전환한다.
`.env.example`에는 추가 서비스와 모델 준비를 전제로 한 설정도 있으므로
복사만으로 모든 기능이 준비된다고 가정하지 않는다.

| 확인 대상 | 준비할 내용과 소유 문서 |
| --- | --- |
| PostgreSQL·Redis·파일 저장소·검색 | 개발 DB, 큐, 버킷, 색인 연결이 실제 실행 대상과 일치하는지 확인한다. [개발 Compose](ops/compose/open-work-hub-dev.infra.yml)와 [개발 환경 설정](scripts/dev-env.sh)이 실행 정의다. |
| 개인정보 필터 | `OPEN_WORK_HUB_OPF_SERVICE_BASE_URL`에 별도 서비스 주소가 있으면 해당 서비스를 먼저 준비한다. 아래 실행 예와 [서비스 구현](apps/api/src/open_work_hub_api/domains/ai/privacy_filter_service.py)을 따른다. |
| 일반 챗봇·Hermes Terminal | 키·서비스 활성화·공급자 정책·검증은 [Hermes 설치 문서](docs/domains/ai/hermes.md#fresh-environment-setup)를 따른다. 호스트에 Hermes를 별도 설치하지 않는다. |
| 문서 AI·OCR·음성 인식 | 설정한 [Inference Gateway](docs/domains/inference-gateway/README.md)와 [RAG](docs/domains/rag/README.md) 연결을 준비한다. 개발 Compose가 외부 추론 서버까지 설치하지는 않는다. |
| 슬라이드·다이어그램 | [Bento](docs/apps/bento/README.md)와 [Diagrams](docs/apps/diagrams/README.md)의 서버 주소·브라우저 연결을 확인한다. Bento의 별도 런타임 이미지와 Web bridge 프로토콜도 함께 맞춘다. |
| 화상회의·녹음 | [Recording](docs/apps/recording/README.md)의 LiveKit·네트워크·추론 서비스 요구사항을 확인한다. |

개발 개인정보 필터를 이 서버에서 실행하는 경우, 별도 터미널에서 설정된 loopback 주소를 사용한다.
이 프로세스도 계속 실행해야 하며 초기 모델 준비가 끝나야 API의 필수 검사에 통과한다.
이미 해당 주소의 서비스가 준비되어 있으면 중복 실행하지 않는다.

```bash
(
  cd apps/api
  uv run --frozen --python 3.12 python - <<'PY'
from urllib.parse import urlparse
import uvicorn
from open_work_hub_api.core.settings import get_settings

endpoint = urlparse(get_settings().opf_service_base_url)
if endpoint.scheme != 'http' or endpoint.hostname != '127.0.0.1' or not endpoint.port:
    raise SystemExit('Check the configured development privacy-filter endpoint first.')
uvicorn.run(
    'open_work_hub_api.domains.ai.privacy_filter_service:app',
    host=endpoint.hostname,
    port=endpoint.port,
)
PY
)
```

필요한 설정이 준비되면 최소 실행 터미널에서 `Ctrl+C`를 누른 뒤 다음을 실행한다.

```bash
pnpm dev:infra:up
./dev.sh --with-worker --no-infra
```

별도 터미널에서 인프라와 Worker를 포함한 앱 상태를 확인한다.

```bash
pnpm infra:dev:status
./dev.sh --with-worker --status
pnpm dev:login-smoke
curl --fail --silent --output /dev/null http://127.0.0.1:8001/readyz
```

기능별 준비 실패는 해당 설정을 해결하고 재검사한다. 설치를 통과시키려고 필수 검사나
AI 보호 정책을 끄지 않는다. 추가 키·서버가 필요한 기능은 미설정 상태로 명시한다.
별도의 사용자 요청 없이 준비 확인만을 위해 유료 추론을 실행하지 않는다.

## 7. 실행 종료·재시작과 완료 확인

`dev.sh`는 전경 실행이다. `Ctrl+C` 또는 터미널 종료 시 앱 프로세스가 멈추며 Docker 인프라는 남는다.
최소 실행은 `pnpm dev:minimal`, 전체 실행은 6절의 명령으로 다시 시작한다.
다른 터미널에서 중지할 때는 실행 대상에 맞춰 `./dev.sh --stop` 또는
`./dev.sh --with-worker --stop`을 사용한다. 호스트 감독 서비스로 실행 중이면
[지속 실행 계약](docs/domains/release/README.md#persistent-development-runtime)에 따라 그 감독 서비스를 사용한다.
최소 인프라만 멈출 때는 `pnpm dev:infra:minimal:down`을 사용한다. 데이터 볼륨을 삭제하지 않는다.

설치 완료 시 사용자에게 다음을 전달한다.

- 선택한 최소/전체 실행 구성, 작업 경로와 브라우저 접속 방법.
- 실제 실행한 명령과 로그인·브라우저·준비 상태 검사 결과. 미실행 검사는 구분한다.
- 요청된 업무 기능의 문서 저장·다시 열기, 파일 업로드·다운로드 등 실제 확인 결과.
- 작은 화면 수정이 개발 서버에 반영되는지 확인한 결과와 변경한 파일. 불필요한 확인용 수정은 남기지 않는다.
- 추가 자격증명·서비스가 필요한 기능과 중지·재시작 방법.

설치 관련 코드나 설정을 바꿀 때는 [문서 유지 지침](AGENTS.md#documentation-and-skills)에 따라
이 가이드의 영향받는 절차와 연결된 소유 문서를 같은 변경에서 갱신한다.
