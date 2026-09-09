# Open Work Hub

## 사전 준비

Ubuntu Server 26.04 LTS 권장 · CPU 4코어 이상 · 메모리 32GB 이상 · 프로젝트용 여유 공간 100GB 이상

## 1. 기본 도구와 Node.js 설치

서버에 SSH로 접속한 뒤 일반 사용자의 Bash에서 실행합니다. `sudo` 비밀번호는 서버 터미널에 입력하세요.

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates bubblewrap

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc # 현재 Bash에 nvm 적용
nvm install 24
```

## 2. 원본 코드 받기

`open-work-hub/dev`에 설치합니다. 이후 같은 상위 경로에 `prod`와 `worktrees`를 추가해 관리할 수 있습니다.
기존 체크아웃이 있다면 clone 명령을 다시 실행하지 마세요.

```bash
mkdir -p open-work-hub
cd open-work-hub
git clone --origin upstream --branch main https://github.com/hurxxxx/open-work-hub.git dev
cd dev
git switch --no-track -c dev
git config remote.pushDefault origin

# 현재 Node.js 버전과 프로젝트 요구 범위 확인
node --version
node -p 'require("./package.json").engines.node'
```

## 3. Codex 설치와 인증

인증 명령이 표시하는 링크를 내 PC의 브라우저에서 열고 일회용 코드를 입력합니다.
인증이 끝나면 현재 `open-work-hub/dev` 경로에서 Codex를 실행하세요.

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
codex login --device-auth
codex
```

`/permissions` → **Full access**

## 4. Codex에 셋업 요청

PostgreSQL·Redis는 미리 설치하지 않아도 됩니다. 아래 프롬프트로 Codex가 네이티브 설치와 개발용 DB·연결 설정을 함께 준비하도록 요청합니다.

```text
AGENTS.md와 INSTALL.md를 따라 현재 open-work-hub/dev에 최소 개발 환경을 설치해줘.
기존 저장소·설정·데이터를 보존하고 필요한 도구와 의존성을 준비해줘.
PostgreSQL·Redis는 INSTALL.md의 버전 기준에 따라 설치 시점의 최신 안정 버전을 공식 패키지 저장소에서 확인해 호스트에 네이티브로 설치하고 systemd로 관리해줘.
개발 설정을 맞춰 ./dev.sh --minimal-infra --no-infra로 실행하고 로그인·브라우저 검사를 수행해줘.
OpenSearch 등 추가 서비스는 당장 설치하지 마.
최소 실행 확인 후 INSTALL.md 2.2절에 따라 내부 GitLab과 glab을 설치해줘.
관리자 계정 생성·비밀번호 변경·glab 인증은 내가 직접 하도록 안내하고 기다려줘.
인증 완료를 알리면 비공개 프로젝트·초기 push·Runner·CI 변수와 파이프라인을 준비하고, 실제 MR 검증은 작업 범위를 확인한 뒤 진행해줘.
GitHub는 upstream, 내부 GitLab은 origin으로 유지하고 기존 GitLab 이력을 보존해줘.
비밀값은 서버에서 안전하게 입력하도록 안내하고 검사·보호 정책을 끄지 마.
접속 방법·검사 결과·미설정 기능·중지·재시작 방법을 알려줘. 운영 배포는 하지 마.
```

## 5. GitLab 설치 후 직접 할 일

1. GitLab 웹 주소에 초기 `root` 계정으로 로그인하고 비밀번호를 변경합니다. 초기 비밀번호 확인 방법은 [INSTALL.md 2.2절](INSTALL.md)을 따릅니다.
2. `Admin > Overview > Users > New user`에서 본인 계정을 만들고 `Administrator` 권한과 비밀번호를 설정합니다.
3. 본인 계정으로 로그인한 뒤 `Access tokens`에서 만료일과 `api` 범위를 지정해 Personal access token을 발급합니다.
4. 서버 터미널에서 아래 명령을 실행합니다. `gitlab.example.com`은 실제 내부 GitLab 호스트명으로 바꾸세요.

```bash
glab auth login --hostname gitlab.example.com --api-protocol https --git-protocol ssh
glab auth status --hostname gitlab.example.com
```

인증 질문에서 토큰 방식을 선택하고 토큰은 터미널에만 입력합니다. Codex 대화에는 붙여 넣지 마세요.
완료 후 Codex에 다음과 같이 요청합니다.

```text
GitLab 관리자 계정 준비와 glab 인증을 완료했어. INSTALL.md 2.2절의 프로젝트·원격 등록과 Runner·CI 구성을 이어서 진행해줘.
```

[상세 설치](INSTALL.md)
