# Open Work Hub

문서·파일·프로젝트·AI 기능을 제공하는 사내 업무 플랫폼입니다.
리눅스 서버에서 원본 코드를 받은 뒤 Codex에 셋업을 요청하세요.

## 사전 준비

| 구분 | 준비할 항목 |
| --- | --- |
| 권장 OS | [Ubuntu Server 26.04 LTS](https://ubuntu.com/download/server) |
| 최소 서버 사양 | CPU 4코어 이상, 메모리 32GB 이상, 이 프로젝트를 위한 디스크 여유 공간 100GB 이상 |
| 사람이 미리 준비 | 리눅스 서버, SSH·sudo 권한, Git·curl·CA 인증서, Codex 사용이 가능한 ChatGPT 계정, 외부 다운로드 연결 |
| Codex가 설치 | Node.js·pnpm, Python·uv, PostgreSQL·Redis와 프로젝트 의존성. PostgreSQL·Redis는 호스트에 네이티브로 설치합니다. |
| 최소 실행 서비스 | Web·API와 PostgreSQL·Redis. 최소 구성에는 Docker가 필요하지 않습니다. |

최소 구성은 로그인·화면 확인용입니다. OpenSearch·파일 저장소·AI 등은 사용할 기능에 따라 나중에 준비합니다.
GitLab 동시 운영, AI 모델, 데이터·백업 용량은 최소 사양 외에 추가 자원을 고려하세요.

## 1. 원본 코드 받기

서버에 일반 사용자로 SSH 접속합니다. Ubuntu/Debian의 기본 도구 설치 예시입니다.

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates
```

원하는 작업 위치에서 `open-work-hub/dev`를 만듭니다. 기존 체크아웃이 있으면 재실행하지 마세요.

```bash
mkdir -p open-work-hub
cd open-work-hub
git clone --origin upstream --branch main https://github.com/hurxxxx/open-work-hub.git dev
cd dev
git switch --no-track -c dev
git config remote.pushDefault origin
```

이후 `open-work-hub` 아래에 `prod/`와 `worktrees/`를 필요할 때 추가해 함께 관리합니다.
GitHub는 `upstream`, 내부 GitLab은 이후 연결할 `origin`입니다.
이미 내부 GitLab이 있다면 [INSTALL.md](./INSTALL.md)의 2.3절에서 시작하세요.

## 2. Codex 설치하고 인증하기

[공식 Linux 설치기](https://learn.chatgpt.com/docs/codex/cli)를 사용합니다. Node.js 사전 설치는 필요 없습니다.

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

설치 출력의 PATH 안내를 적용한 뒤 서버에서 인증을 시작합니다.

```bash
codex login --device-auth
```

표시된 링크를 **내 PC의 브라우저**에서 열어 로그인하고 일회용 코드를 입력합니다.
기기 코드 인증이 비활성화되어 있으면 [공식 인증 안내](https://learn.chatgpt.com/docs/auth#login-on-headless-devices)를 따르세요.

## 3. Codex에 셋업 요청하기

`open-work-hub/dev` 디렉터리에서 Codex를 실행합니다.

```bash
codex
```

Codex 입력창에서 `/permissions`를 입력하고 **Full access**를 선택한 뒤 다음 프롬프트로 작업하세요.
Full access는 파일·네트워크 접근 제한과 승인 확인을 해제하므로 신뢰하는 전용 셋업 서버에서 사용하고,
설치 후에는 기본 권한으로 되돌리세요. OS의 `sudo` 권한은 별도로 필요합니다.
자세한 범위는 [공식 권한 안내](https://learn.chatgpt.com/docs/sandboxing#how-permissions-work)를 따릅니다.

```text
AGENTS.md와 INSTALL.md를 따라 현재 open-work-hub/dev에 최소 개발 환경을 설치해줘.
이미 clone한 저장소와 기존 설정·데이터를 보존하고 필요한 도구와 의존성을 준비해줘.
PostgreSQL·Redis는 Docker가 아닌 호스트에 네이티브로 설치하고 systemd 서비스로 관리해줘.
개발 설정을 해당 서비스에 맞추고 ./dev.sh --minimal-infra --no-infra로 실행한 뒤 로그인·브라우저 검사를 수행해줘.
OpenSearch 등 추가 서비스는 당장 설치하지 말고 사용할 기능을 확인한 뒤 준비해줘.
최소 실행 확인 후 내부 GitLab의 대상·주소를 확인하고, 필요하면 설치·비공개 프로젝트 생성·초기 push까지 진행해줘.
기존 GitLab이 있으면 그 이력을 보존해서 연결하고 GitHub는 upstream, 내부 GitLab은 origin으로 유지해줘.
비밀값은 서버에서 안전하게 입력하도록 안내하고 검사·보호 정책을 끄지 마.
접속 방법, 검사 결과, 미설정 기능, 중지·재시작 방법을 알려줘. 운영 배포는 별도 요청 전에는 진행하지 마.
```

## Dev

설치 후 브라우저 접속은 Codex의 완료 안내와 [INSTALL.md](./INSTALL.md)의 5절을 따릅니다.
개발용 기본 계정은 `administrator` / `open-work-hub-dev-only`이며 공유·공개 운영 서비스에는 사용하지 않습니다.
`.env`, 인증정보, 운영·고객 데이터는 Git에 넣지 마세요.

상세 설치: [INSTALL.md](./INSTALL.md) · 프로젝트 규칙: [AGENTS.md](./AGENTS.md) · 문서 목록: [docs/README.md](./docs/README.md)
