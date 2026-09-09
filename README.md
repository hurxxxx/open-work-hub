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

아래 예시를 그대로 실행하면 `/projects/open-work-hub/dev`에 설치됩니다.
다른 위치를 원하면 첫 줄의 `owh_install_root`를 원하는 상위 디렉터리 경로로 바꾸세요.
그 아래에 개발 저장소 `dev`를 만들고, 이후 같은 상위 경로에 `prod`와 `worktrees`를 추가해 관리할 수 있습니다.
기존 체크아웃이 있다면 해당 저장소로 이동해 3절부터 진행하고 아래 명령은 건너뛰세요.

설치 계정으로 실행합니다. 상위 디렉터리가 없으면 새로 만들어 설치 계정에 소유권을 부여합니다.
이미 있다면 소유권을 유지하므로, 설치 계정에 해당 디렉터리의 쓰기 권한이 있어야 합니다.

```bash
owh_install_root=/projects/open-work-hub
if [ ! -e "$owh_install_root" ] && [ ! -L "$owh_install_root" ]; then
  sudo install -d -m 0755 -o "$(id -u)" -g "$(id -g)" "$owh_install_root"
fi
cd "$owh_install_root"
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
인증이 끝나면 앞에서 준비한 개발 저장소 루트에서 Codex를 실행하세요.

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
셋업은 GitLab 파이프라인이 실제로 성공하고, 내 PC에서 서버 IP로 개발 로그인 화면에 접속해 시드 계정으로 로그인할 수 있을 때 완료됩니다.

```text
AGENTS.md와 INSTALL.md를 따라 현재 체크아웃 경로에 최소 개발 환경을 설치해줘. 사용자가 선택한 설치 경로를 유지해줘.
기존 저장소·설정·데이터를 보존하고 필요한 도구와 의존성을 준비해줘.
PostgreSQL·Redis는 INSTALL.md의 버전 기준에 따라 설치 시점의 최신 안정 버전을 공식 패키지 저장소에서 확인해 호스트에 네이티브로 설치하고 systemd로 관리해줘.
개발 .env의 OPEN_WORK_HUB_WEB_DEV_HOST=0.0.0.0으로 설정하고 ./dev.sh --minimal-infra --no-infra로 실행해줘. API·개발 DB·Redis는 loopback 수신을 유지해줘.
VM 네트워크와 필요한 포트를 확인해 내 PC에서 http://<서버-IP>:<개발-Web-포트>/login으로 직접 접속하고 시드 계정으로 로그인할 수 있게 해줘.
pnpm dev:login-smoke 명령과 agent-browser로 실제 서버 IP 주소의 로그인·화면·로그아웃을 검사해줘.
개발 앱에는 OpenSearch 등 추가 서비스를 당장 띄우지 마. GitLab CI에 필요한 검증 이미지·테스트 DB·서비스 준비는 설치 범위에 포함해줘.
CI 테스트 DB와 PostgreSQL 클라이언트는 설치한 프로젝트 DB의 메이저 버전에 맞춰줘. 해당 버전·플랫폼·의존성에 맞는 검증 이미지는 검사 후 재사용하고, 없으면 새로 빌드해줘. 예전 CI 이미지 때문에 다른 메이저 버전의 PostgreSQL을 추가 설치하지 마.
최소 실행 확인 후 INSTALL.md 2.2절에 따라 내부 GitLab과 glab을 설치해줘. GitLab 도메인·DNS 설정은 제외하고, 서버에서 확인한 접속 가능한 IP와 사용 가능한 포트로 구성해줘. 도메인 입력을 기다리지 마.
INSTALL.md 2.2.2절의 초기 설정값으로 GitLab root 계정을 준비하고, 필요한 계정 설정·PAT 발급·glab 인증까지 서버에서 직접 완료해줘. 사용자에게 계정 생성이나 토큰 발급·인증을 맡기지 마.
비공개 프로젝트·초기 push·Runner 등록·CI 변수 설정과 실제 파이프라인 성공까지 완료해줘. 검증용 작업 브랜치 생성, 설치 관련 변경의 커밋·push, dev 대상 Draft MR 생성·재실행을 이번 셋업 범위로 승인해. MR 병합과 dev→main 릴리스는 하지 마.
GitHub는 upstream, 내부 GitLab은 origin으로 유지하고 기존 GitLab 이력을 보존해줘.
내부 main 등록 후 INSTALL.md 2.5절에 따라 dev와 prod 체크아웃 경로를 분리하고, 운영 설정과 실행은 별도 단계로 남겨줘.
비밀값은 서버에서 안전하게 입력하도록 안내하고 검사·보호 정책을 끄지 마.
INSTALL.md 1.1절에 따라 프로젝트 루트의 .auth_info 한 파일에 GitLab, 개발·운영 시드 계정, 데이터베이스 계정 등의 접속 주소·아이디·비밀번호를 구분해 기록하고 변경 시 갱신해줘.
이 파일은 Git 추적에서 제외하고 소유자만 읽고 쓸 수 있게 관리해줘. 아직 준비하지 않은 계정은 미설정으로 표시하고, 완료 시 비밀값 대신 사용자가 직접 확인할 파일 경로를 알려줘.
최소 환경만 실행한 상태에서 끝내지 말고 GitLab 관리자 로그인·glab 인증·파이프라인 성공과 개발 시드 계정 로그인을 모두 확인해줘. 설정·인증 실패는 원인을 해결하고 재검사해줘.
개발 앱은 셋업 세션이 끝난 뒤에도 실행되도록 관리하고, 접속 URL·파이프라인 링크와 커밋·검사 결과·미설정 기능·중지·재시작 방법을 알려줘. 운영 배포는 하지 마.
```

## 5. GitLab 설치 후 확인

GitLab 관리자 계정 설정·PAT 발급·`glab` 인증은 위 셋업 요청에 따라 Codex가 완료합니다. 사용자는 아래 결과를 확인하면 됩니다.

1. PC에서 안내받은 서버 IP 기반 GitLab **HTTPS** 주소에 접속합니다. 도메인·DNS 설정은 필요하지 않습니다. 사설 CA를 쓰면 공개 인증서를 PC에서 신뢰하도록 등록합니다.
2. `.auth_info`의 GitLab 관리자 정보를 확인합니다. Codex의 완료 보고에는 `root` 로그인과 `glab` 인증·관리 권한 확인 결과가 포함되어야 합니다.
3. 검증용 MR의 최신 커밋에서 파이프라인이 성공했는지 확인합니다. lint 통과나 Runner 등록만으로 완료하지 않습니다.
4. 안내받은 `http://<서버-IP>:<개발-Web-포트>/login`에 SSH 터널 없이 접속하고, `.auth_info`의 개발 시드 계정으로 로그인해 앱 화면이 열리는지 확인합니다.

[상세 설치](INSTALL.md)
