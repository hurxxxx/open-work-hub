# Open Work Hub

## 사전 준비

Ubuntu Server 26.04 LTS 권장 · CPU 4코어 이상 · 메모리 32GB 이상 · 프로젝트용 여유 공간 100GB 이상

## 0. 설치 계정 권한 설정

설치용 일반 사용자 계정은 `sudo` 그룹에 속하고 **비밀번호 없이 `sudo`를 실행할 수 있어야 합니다**. 아래 명령은 기존 관리자 계정에서 실행하며, `user`는 실제 설치 계정명으로 바꾸세요.

```bash
sudo usermod -aG sudo user
sudo visudo -f /etc/sudoers.d/99-open-work-hub-installer
```

열린 편집기에 아래 규칙을 입력합니다. 여기의 `user`도 같은 설치 계정명으로 바꾸세요.

```sudoers
user ALL=(ALL:ALL) NOPASSWD: ALL
```

관리자 세션에서 문법을 확인합니다. 오류가 있으면 `visudo`로 수정하고, 확인이 끝날 때까지 관리자 세션을 유지하세요.

```bash
sudo visudo -c
```

설치 계정으로 새 SSH 세션에 접속한 뒤 아래 명령이 비밀번호 요청이나 오류 없이 끝나면 다음 단계로 진행합니다.

```bash
sudo -k
sudo -n true
```

이 설정은 전체 관리자 권한을 부여하므로 신뢰하는 설치 계정에만 적용하세요. [공식 visudo 안내](https://www.sudo.ws/docs/man/visudo.man/)

## 1. 기본 도구와 Node.js 설치

서버에 SSH로 접속한 뒤 설치 계정의 Bash에서 실행합니다.

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

새 세션에서도 Full access를 기본으로 사용하려면, 위 권한을 선택한 뒤 Codex 대화창에 아래 프롬프트를 입력하세요.

```text
새 세션을 시작해도 항상 Full access 권한으로 시작하도록 설정 변경해줘.
사용자 설정 파일(기본 ~/.codex/config.toml, CODEX_HOME이 지정되어 있으면 해당 경로의 config.toml)의 최상위 항목을 아래처럼 설정하고, 기존의 다른 설정은 유지해줘.

sandbox_mode = "danger-full-access"
approval_policy = "never"
```

설정 변경이 끝나면 Codex를 종료하고 다시 실행한 뒤 `/permissions`에서 적용 여부를 확인하세요.
사용자 기본 설정과 프로젝트·실행 옵션의 우선순위는 [공식 Codex 설정 안내](https://developers.openai.com/codex/config-basic)를 참고하세요.

## 4. Codex에 셋업 요청

PostgreSQL·Redis는 미리 설치하지 않아도 됩니다. 아래 프롬프트로 Codex가 네이티브 설치와 개발용 DB·연결 설정을 함께 준비하도록 요청합니다.

```text
AGENTS.md와 INSTALL.md를 따라 현재 open-work-hub/dev에 최소 개발 환경을 설치해줘.
기존 저장소·설정·데이터를 보존하고 필요한 도구와 의존성을 준비해줘.
PostgreSQL·Redis는 INSTALL.md의 버전 기준에 따라 설치 시점의 최신 안정 버전을 공식 패키지 저장소에서 확인해 호스트에 네이티브로 설치하고 systemd로 관리해줘.
개발 설정을 맞춰 ./dev.sh --minimal-infra --no-infra로 실행하고 로그인·브라우저 검사를 수행해줘.
OpenSearch 등 추가 서비스는 당장 설치하지 마.
최소 실행 확인 후 INSTALL.md 2.2절에 따라 내부 GitLab과 glab을 설치해줘.
INSTALL.md의 초기 관리자 설정과 glab 인증도 서버에서 수행해줘. 사용자 입력이 필요한 인증 단계만 안내하고 기다려줘.
비공개 프로젝트·초기 push·Runner·CI 변수와 파이프라인을 준비하고, 실제 MR 검증은 작업 범위를 확인한 뒤 진행해줘.
GitHub는 upstream, 내부 GitLab은 origin으로 유지하고 기존 GitLab 이력을 보존해줘.
내부 main 등록 후 INSTALL.md 2.5절에 따라 dev와 prod 체크아웃 경로를 분리하고, 운영 설정과 실행은 별도 단계로 남겨줘.
비밀값은 서버에서 안전하게 입력하도록 안내하고 검사·보호 정책을 끄지 마.
INSTALL.md 1.1절에 따라 프로젝트 루트의 .auth_info 한 파일에 GitLab, 개발·운영 시드 계정, 데이터베이스 계정 등의 접속 주소·아이디·비밀번호를 구분해 기록하고 변경 시 갱신해줘.
이 파일은 Git 추적에서 제외하고 소유자만 읽고 쓸 수 있게 관리해줘. 아직 준비하지 않은 계정은 미설정으로 표시하고, 완료 시 비밀값 대신 사용자가 직접 확인할 파일 경로를 알려줘.
접속 방법·검사 결과·미설정 기능·중지·재시작 방법을 알려줘. 운영 배포는 하지 마.
```

## 5. GitLab 설치 후 확인

1. PC에서 안내받은 GitLab **HTTPS** 주소에 접속합니다. 사설 CA를 쓰면 공개 인증서를 PC에서 신뢰하도록 등록합니다.
2. [INSTALL.md의 초기 관리자 설정](INSTALL.md#222-초기-관리자와-비밀번호-설정)을 확인하고 **임시 비밀번호를 반드시 변경한 뒤 사용합니다.**
3. 실제 담당자 이메일·계정 확인·2FA를 완료합니다. 관리자 계정과 프로젝트 자동화 계정의 권한은 구분합니다.
4. [glab 인증 절차](INSTALL.md#223-glab-설치와-내부-gitlab-인증)에 따라 인증 상태를 확인합니다.
   이미 PAT 인증이 되어 있으면 관리자 비밀번호 변경 때문에 다시 인증할 필요는 없습니다.

직접 처리하기로 정한 인증 단계가 있다면 토큰은 서버 터미널에만 입력하고, 완료 후 다음과 같이 요청합니다.

```text
GitLab 관리자 계정 준비와 glab 인증을 완료했어. INSTALL.md 2.2절의 프로젝트·원격 등록과 Runner·CI 구성을 이어서 진행해줘.
```

[상세 설치](INSTALL.md)
