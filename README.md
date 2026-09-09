# Open Work Hub

## 사전 준비

Ubuntu Server 26.04 LTS 권장 · CPU 4코어 이상 · 메모리 32GB 이상 · 프로젝트용 여유 공간 100GB 이상

## 설치

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates bubblewrap

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc # 현재 Bash에 nvm 적용
nvm install 24

mkdir -p open-work-hub
cd open-work-hub
git clone --origin upstream --branch main https://github.com/hurxxxx/open-work-hub.git dev
cd dev
git switch --no-track -c dev
git config remote.pushDefault origin

node --version
node -p 'require("./package.json").engines.node'

curl -fsSL https://chatgpt.com/codex/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
codex login --device-auth
codex
```

`/permissions` → **Full access**

## Codex 셋업 프롬프트

```text
AGENTS.md와 INSTALL.md를 따라 현재 open-work-hub/dev에 최소 개발 환경을 설치해줘.
기존 저장소·설정·데이터를 보존하고 필요한 도구와 의존성을 준비해줘.
PostgreSQL·Redis는 호스트에 네이티브로 설치하고 systemd로 관리해줘.
개발 설정을 맞춰 ./dev.sh --minimal-infra --no-infra로 실행하고 로그인·브라우저 검사를 수행해줘.
OpenSearch 등 추가 서비스는 당장 설치하지 마.
최소 실행 확인 후 내부 GitLab의 대상·주소를 확인하고, 필요하면 설치·비공개 프로젝트 생성·초기 push까지 진행해줘.
GitHub는 upstream, 내부 GitLab은 origin으로 유지하고 기존 GitLab 이력을 보존해줘.
비밀값은 서버에서 안전하게 입력하도록 안내하고 검사·보호 정책을 끄지 마.
접속 방법·검사 결과·미설정 기능·중지·재시작 방법을 알려줘. 운영 배포는 하지 마.
```

[상세 설치](INSTALL.md)
