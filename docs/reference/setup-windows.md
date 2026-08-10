# Windows 네이티브 로컬 개발 셋업

Windows에서 WSL 없이 AI-DO를 개발하는 표준 절차다. 앱(web/api)만 로컬에서 실행하고,
DB·Redis·MinIO·OpenSearch·Qdrant는 server dev host `128.1.253.101`, local LLM과
Inference Gateway는 DGX application LB `128.1.253.103`의 공유 dev 인프라를 직접 쓴다.

전제:

- 레포는 `C:\projects\ai-do` 등 `C:\projects` 하위 통일 경로에 둔다.
- 인프라 접속값은 GitLab Secure Files 의 **`.env.local`** 을 받아 루트에 둔다(4단계). 키는 `AI_DO_*` 계약(`.env.example`)을 따른다.
- API 는 로컬 **단일 인스턴스**로 띄우고, 공유 dev DB 에 로컬에서 migration 을 적용하지 않는다.
- 개발은 `dev` 에서 분기한 feature 브랜치에서 하고 **MR(`feature` → `dev`)** 로 합친다. GitLab 기본 target이 `main`이어도 기능 MR은 반드시 `dev`로 지정한다. 로컬에서 `dev`/`main` 직접 push 금지.

> Claude Code 로 작업할 때의 도구 샌드박스 주의사항은 [`CLAUDE.md`](../../CLAUDE.md) 참고.

## 1. 사전 도구

| 도구 | 설치 |
|---|---|
| Node.js LTS | 설치 후 `node -v` |
| pnpm 10.33.0 | `npm i -g pnpm@10.33.0` (corepack `--activate` 는 Program Files 권한오류) |
| uv | `winget install astral-sh.uv` |
| glab | 자동 설치됨 — 아래 3단계의 `scripts\dev-windows-fetch-env.ps1` 가 winget 으로 깐다. 수동 설치는 `winget install GLab.GLab` (`.env.local` Secure File 다운로드에 필요). |
| Rust + MSVC | `winget install Rustlang.Rustup` |
| VS Build Tools (C++) | `winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"` |

- VS Build Tools 는 `--override` 로 **VCTools(C++) 워크로드**까지 지정해야 한다. 옵션 없이 설치하면 컴파일러·Windows SDK 가 빠진다.
- Rust + C++ 빌드 도구는 `y-py` 컴파일 전용이다(2단계).
- PowerShell 스크립트는 **Windows PowerShell 5.1**(`powershell.exe`)에서 동작한다. PowerShell 7(`pwsh`)은 필수가 아니다.

## 2. 부트스트랩 (의존성 + y-py 빌드)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-windows-bootstrap.ps1
```

1. `pnpm install --frozen-lockfile`
2. `uv sync --python 3.12 --no-install-package y-py` (apps/api, 단일 venv)
3. `y-py 0.6.2` wheel 을 maturin 으로 로컬 빌드 후 venv 에 설치

> **y-py 만 따로 빌드하는 이유**: `y-py 0.6.2`(마지막 릴리스)는 Linux 에는 cp312 wheel 이 있지만 Windows cp312 wheel 이 없다.
> Windows 에서는 Rust + MSVC 로 직접 컴파일한다. sdist 의 `[project]` 에 version 이 없어 `dynamic = ["version"]` 을 보강해 maturin 으로 빌드하고, 산출물은 `.dev/wheelhouse/`(gitignore) 에 둔다.
> worker 도 필요하면 `cd apps\worker; uv sync --python 3.12`.

## 3. `.env.local` 받기 (GitLab Secure Files)

`.env.local` 값은 GitLab Secure Files 에만 둔다. 값을 문서·커밋·채팅에 남기지 않고,
다운로드된 파일도 레포 루트의 gitignore 대상 파일로만 둔다.

토큰 준비:

1. 브라우저에서 `http://128.1.253.101:8929/` 로그인.
2. 사용자 메뉴 → Preferences → Access tokens 에서 Personal Access Token(PAT) 생성.
3. Scope 는 `api` 를 포함하고, 만료일을 설정한다.
4. 생성된 토큰은 한 번만 보이므로 복사한다. `.env.local` 내용 자체는 복사하거나 공유하지 않는다.

에이전트가 대신 셋업하는 흐름:

- 에이전트는 `.env.local` 이 없고 `glab auth status --hostname 128.1.253.101:8929` 가 실패할 때 사용자에게 위 PAT 생성을 안내한다.
- 사용자는 가능하면 채팅이 아니라 터미널의 보안 프롬프트에 PAT 를 붙여넣는다. 터미널 프롬프트를 쓸 수 없는 환경에서 토큰을 에이전트에게 전달했다면, 에이전트는 아래 `--stdin` 방식으로 한 번만 사용하고 출력·파일·히스토리에 남기지 않는다.
- 에이전트는 인증 후 Secure Files 메타데이터만 확인하고, 파일 내용은 출력하지 않는다.

```powershell
# 자동: glab 미설치면 winget 으로 깔고, host 설정 → 인증 → secure file 다운로드까지 한 번에.
powershell -ExecutionPolicy Bypass -File scripts\dev-windows-fetch-env.ps1
```

- 사전에 `http://128.1.253.101:8929` 에서 **api 스코프 PAT** 를 발급해 둔다.
- 사람은 토큰을 넘기지 말고 그냥 실행한다 — `glab auth login` 보안 프롬프트가 떠서 PAT 를 셸 히스토리에 남기지 않고 입력받는다. **PAT literal 을 `$env:GLAB_PAT = '...'` 처럼 직접 타이핑하지 말 것**(PSReadLine 히스토리에 남는다).
- `GLAB_PAT`/`GITLAB_TOKEN` env var 경로는 CI·agent 환경에서 러너가 **이미 마스킹된 비밀로 주입한** 경우에만 쓰는 비대화식 흐름이다.
- 이미 `.env.local` 이 있으면 건너뛴다. 강제 재다운로드: `-Force`.

수동으로 인증·다운로드할 때는 PAT 를 PowerShell 히스토리/프로세스 인자에 남기지 않는다:

```powershell
# PAT 를 PowerShell 히스토리/프로세스 인자에 남기지 않고 glab 에 저장한다.
$secure = Read-Host "GitLab PAT (api scope)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  $plain | glab auth login `
    --hostname 128.1.253.101:8929 `
    --api-host 128.1.253.101:8929 `
    --api-protocol http `
    --git-protocol ssh `
    --use-keyring `
    --stdin
}
finally {
  if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
  Remove-Variable -Name plain,secure -ErrorAction SilentlyContinue
}

# 인증 상태와 Secure Files 메타데이터만 확인한다. 토큰/파일 내용은 출력하지 않는다.
glab auth status --hostname 128.1.253.101:8929
glab securefile list -R dwdcc/ai-do

# .env.local 을 이름으로 다운로드한다. glab 이 checksum 을 검증한다.
glab securefile download --name .env.local --path .env.local -R dwdcc/ai-do
Get-Item .env.local | Select-Object Name,Length,LastWriteTime
```

`--use-keyring` 이 해당 Windows 환경에서 실패하면 같은 명령을 `--use-keyring` 없이 다시 실행한다.
그 경우 glab 은 토큰을 사용자 홈의 glab 설정 파일에 저장한다. 이후 에이전트는 저장된 인증으로
`glab securefile download --name .env.local --path .env.local -R dwdcc/ai-do` 를 직접 재실행할 수 있다.

`.env.local` 은 gitignore 대상이며 `AI_DO_*` 키만 쓴다(레거시 프로젝트 prefix 금지). 루트의 `.env` 는 만들지 않는다.

## 4. 실행

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-windows.ps1            # web + api
powershell -ExecutionPolicy Bypass -File scripts\dev-windows.ps1 -ApiOnly   # api 만
powershell -ExecutionPolicy Bypass -File scripts\dev-windows.ps1 -WebOnly   # web 만, 기존 API 또는 기본 127.0.0.1:8001 프록시 사용
```

- Web: http://localhost:4200
- API docs: http://127.0.0.1:8001/docs · health: http://127.0.0.1:8001/healthz
- 포그라운드로 떠 있다(Ctrl+C 로 종료). 터미널을 닫으면 서버도 내려간다.

런처는 API 를 띄울 때 `.env.local` 을 프로세스 환경에 주입하고, 로컬 docker 인프라를 띄우지 않으며,
공유 dev DB 에 auto-migrate 하지 않고(`AI_DO_API_AUTO_MIGRATE=0`), LLM 백엔드로 기동을 막지 않는다.
`-WebOnly` 는 `.env.local` 이 있으면 읽고, 없으면 기존 환경변수와 Vite 기본 프록시를 쓴다.

## 5. 검증 (실제 확인됨)

```powershell
# DB 인증 (psycopg)
$dsn = ((Get-Content .env.local | sls '^AI_DO_POSTGRES_DSN=').Line -replace '^AI_DO_POSTGRES_DSN=','') -replace '\+psycopg',''
$env:_T=$dsn; apps\api\.venv\Scripts\python.exe -c "import os,psycopg;c=psycopg.connect(os.environ['_T']);print('PG OK',c.execute('select current_user').fetchone()[0]);c.close()"; $env:_T=$null

# health + dev-login (api 기동 후)
Invoke-RestMethod http://127.0.0.1:8001/healthz
Invoke-RestMethod -Method Post http://127.0.0.1:8001/api/v1/auth/dev-login -ContentType application/json -Body '{"account_key":"administrator"}'
```

정상 기준: `healthz` `status=ok`, `dev-login` `200`. (`127.0.0.1` 요청은 dev-login 호스트 게이트에서 항상 허용된다.)

## 6. Windows 엣지케이스 (런처/부트스트랩이 처리)

| 증상 | 처리 |
|---|---|
| `pnpm nx ...` 가 `'env' is not recognized` 로 실패 | 루트 `nx` 스크립트의 Unix `env -u` 래퍼 회피 → `pnpm exec nx` |
| nx plugin worker 5초 소켓 실패로 그래프 멈춤 | `NX_ISOLATE_PLUGINS=false` (+`NX_DAEMON=false`) |
| `uv run`/`uv sync` 가 매번 재싱크하며 y-py 재빌드 시도 | API 를 `uv run` 대신 `apps\api\.venv\Scripts\python.exe -m uvicorn` 으로 직접 기동 |
| `dev.sh`/`dev-api.sh` 의 `.venv/bin/python` 경로 | Windows 는 `.venv\Scripts\python.exe` |
| nx api `dev` 타깃의 `VAR=val cmd` POSIX 프리픽스 | 런처가 env 를 분리 설정 후 직접 실행 |
| corepack `pnpm --activate` EPERM | `npm i -g pnpm@10.33.0` |

## 7. 규칙

- `.env.local`·`.env.*`·토큰·API key 는 커밋 금지(`.env.example` 만 추적).
- 공유 dev DB migration 은 GitLab 이슈/MR 로 조율하고 서버 dev checkout 에서 적용한다.
- 로컬에서 `dev`/`main` 직접 push 금지 — feature 브랜치 + MR.
- `check:env-contract`/`check:runtime-separation` 은 루트 `.env` 기반 서버/CI 검사다. 로컬(`.env.local`)에서는 위 5단계로 검증한다.
