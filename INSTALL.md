# 리눅스 개발 환경 설치 가이드

현업 참여자가 Codex 또는 Claude Code로 코드를 수정하고 브라우저에서 확인하기 위한 설치 절차다.
Web·API·Worker는 저장소 소스에서 실행하고, 최초 셋업의 PostgreSQL·Redis는 호스트에 네이티브로 설치한다.
기존 Docker Compose 방식은 선택 사항이며, 추가 서비스는 사용할 기능에 따라 준비한다.
조직 최초 도입은 GitHub 원본에서 시작하고, 최초 실행을 확인한 뒤 내부 서버의 GitLab을 구성해
이후 코드와 협업을 관리한다. 이미 내부 GitLab이 준비된 조직의 참여자는 그 저장소에서 시작한다.
서버 셋업은 개발 Web을 `0.0.0.0`에서 실행하고 PC가 서버 IP로 직접 접속할 수 있도록 준비한다.
조직 최초 도입의 완료 기준은 GitLab 관리자·인증·프로젝트·Runner·CI 변수 구성, 실제 개발 MR 파이프라인 성공, 외부 접속과 개발 시드 계정 로그인이다.
운영 배포는 [Release Domain](docs/domains/release/README.md)의 별도 절차를 따른다.

## 설치 계정 권한

네이티브 최초 설치 계정은 비밀번호 없이 `sudo`를 실행할 수 있는 `sudo` 그룹 소속 일반 사용자여야 한다. 관리자가 [README의 설치 계정 권한 설정](README.md#0-설치-계정-권한-설정)을 먼저 완료한다. 에이전트는 `sudo -n true`로 권한을 확인하고, 실패하면 권한을 자동 변경하거나 비밀번호를 요청하지 말고 관리자에게 사전 설정을 요청한다.

## PostgreSQL·Redis 최초 설치 버전

- 새로 설치하는 프로젝트용 PostgreSQL과 Redis Open Source는 **설치 시점의 최신 안정 버전(최신 정식 메이저의 최신 패치)**을 사용한다. beta·RC·nightly는 제외한다.
- Ubuntu 기본 패키지를 최신으로 간주하지 않는다. [PostgreSQL 공식 APT 저장소(PGDG)](https://www.postgresql.org/download/linux/ubuntu/)와 [Redis 공식 APT 저장소](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/apt/) 안내를 따라 공식 릴리스·OS 지원·APT 후보 버전을 확인한 뒤 호스트에 네이티브로 설치하고 systemd로 관리한다.
- 실제 설치 버전과 출처, 연결·마이그레이션 확인 결과를 셋업 결과에 기록한다. 최신 안정판의 OS 지원이나 프로젝트 호환성에 문제가 있으면 임의로 낮추지 말고 이유와 대안을 안내하여 사용자와 결정한다.
- 기존 서비스·데이터는 보존한다. 기존 데이터베이스의 메이저 업그레이드는 백업·호환성·복구 계획과 별도 승인이 필요하다. GitLab 번들 데이터베이스와 기존 개발·운영 Compose DB의 버전은 이 네이티브 최초 설치 작업에서 변경하지 않는다.
- 새 CI 테스트 DB와 검증 이미지의 PostgreSQL 클라이언트는 설치한 프로젝트 DB의 메이저 버전에 맞춘다. 셋업 범위에 맞는 이미지 선택·재빌드는 포함하며, 예전 검증 이미지에 맞추려고 다른 메이저 버전의 DB를 추가 설치하지 않는다. [검증 이미지와 DB 계약](docs/domains/release/README.md#validation-image-platform-and-database)을 따른다.

## 1. 에이전트에 설치 요청하기

먼저 서버에 접근할 수 있는 Codex 또는 Claude Code를 설치하고 로그인한다.
Codex의 사전 패키지 설치와 실행 명령은 [README](README.md)를 따른다.
도구 설치는 [Codex 공식 안내](https://learn.chatgpt.com/docs/codex/cli) 또는
[Claude Code 공식 안내](https://code.claude.com/docs/en/quickstart)를 따른다.
서버 접근 권한과 필요한 OS 패키지를 설치할 권한을 준비한다.
최초 도입에는 GitHub 원본을 읽을 수 있는 네트워크가 필요하고,
기존 조직에 참여할 때는 내부 GitLab 저장소 접근 권한이 필요하다.
코딩 에이전트의 로그인과 프로젝트 안에서 사용하는 AI 서비스 인증은 별개다.
Codex 실행 후 `/permissions`에서 **Full access**를 선택한다.
새 세션에도 같은 권한을 기본으로 적용하려면 [README의 Codex 권한 설정 프롬프트](README.md#3-codex-설치와-인증)를 입력하고, Codex를 다시 실행해 적용 여부를 확인한다.

2절에서 상황에 맞는 경로로 저장소를 내려받아 연 뒤 다음과 같이 요청한다.

> AGENTS.md와 INSTALL.md를 읽고 이 리눅스 서버에
> 개발 환경을 설치해줘. 기존 설정과 데이터를 보존하고 필요한 도구만 설치해줘.
> PostgreSQL·Redis는 Docker가 아닌 호스트에 네이티브로 설치하고 systemd 서비스로 관리해줘.
> 개발 설정을 해당 서비스에 맞추고 OPEN_WORK_HUB_WEB_DEV_HOST=0.0.0.0으로 ./dev.sh --minimal-infra --no-infra를 실행해줘.
> API·개발 DB·Redis는 loopback 수신을 유지하고, 내 PC에서 서버 IP로 직접 접속해 시드 계정으로 로그인할 수 있게 해줘.
> pnpm dev:login-smoke 명령과 agent-browser로 서버 IP 주소의 로그인과 화면을 확인해줘.
> 조직 최초 도입이면 README 4절의 셋업 요청 범위로 GitLab·Runner·CI 변수와 개발 MR 파이프라인 성공까지 진행해줘. GitLab 도메인·DNS 설정은 제외하고 서버 IP를 사용해줘.
> 비밀값은 대화에 요청하지 말고 서버에서 입력할 방법을 안내해줘.
> 로그인 정보는 1.1절에 따라 프로젝트 루트의 .auth_info에 기록·갱신하고, 비밀값 대신 파일 경로를 알려줘.
> 끝나면 접속 방법, 실행한 검사, 사용 가능한 기능과 추가 설정이 필요한 기능을 알려줘.

에이전트는 [AGENTS.md](AGENTS.md)와
[개발 환경 스킬](.agents/skills/owh-dev-environment/SKILL.md)을 따른다.
이 문서는 설치 절차의 진입점이며 기능별 설정은 아래의 소유 문서에서 확인한다.

### 1.1. 로그인 정보 파일 관리

셋업을 진행하는 프로젝트 루트에 **`.auth_info`** 파일 하나를 만들어 사용자가 서버에서 직접 열어 볼 수 있는 일반 텍스트로 관리한다.
기본 설치 경로에서는 `open-work-hub/dev/.auth_info`이며, 개발·운영 체크아웃을 분리한 뒤에도 이 파일을 기준으로 갱신한다.

- GitLab 관리자·자동화 계정, 개발·운영 시드 계정, PostgreSQL 등 데이터베이스 계정과 Redis 등 인증이 필요한 서비스의 로그인 정보를 기록한다. 파일 안에서 공통(GitLab)·개발·운영을 구분한다.
- 각 항목에는 서비스명, 접속 URL 또는 호스트·포트, 계정 아이디, 비밀번호, 해당하는 DB 이름, 최종 갱신일을 적는다. 비밀번호 대신 토큰을 사용하는 계정은 토큰과 만료일도 기록한다.
- 승인된 셋업 범위에서 생성·변경하거나 사용자가 제공한 정보만 기록한다. 아직 준비하지 않은 운영 환경이나 알 수 없는 계정 정보는 `미설정` 또는 `사용자 입력 필요`로 표시한다.
- 기존 파일과 다른 항목을 보존하고, 계정 생성·비밀번호 변경·토큰 교체 시 해당 항목을 최신 값으로 갱신한다. 폐기한 비밀번호나 토큰은 남기지 않는다.
- 설치 계정 소유로 만들고 생성 시 `umask 077`, 생성·편집 후 `chmod 600 .auth_info`를 적용해 소유자만 읽고 쓸 수 있게 한다. 비밀값은 서버의 편집기나 보호된 입력으로 기록하고 명령 인자·셸 이력·대화·검사 로그에 출력하지 않는다.
- 루트 [`.gitignore`](.gitignore)는 `.auth_info`와 `.auth_info.*`, `.auth_info~` 백업본을 제외한다. 강제로 추가하거나 다른 체크아웃·공유 문서·배포 산출물에 복사하지 않는다. `.env` 등 실제 서비스 설정은 기존 절차로 관리하며, `.auth_info`는 사용자가 확인하는 기록용 파일이다.

프로젝트 루트에서 파일 내용을 출력하지 않고 Git 제외·미추적 상태를 확인한다.

```bash
git check-ignore -v -- .auth_info
git ls-files -- .auth_info
```

첫 명령에 루트 `.gitignore`의 제외 규칙이 표시되고 두 번째 명령에는 출력이 없어야 한다.
설치 완료 시에는 이 파일의 절대 경로와 기록한 서비스 목록, 미설정 항목을 안내한다. 사용자는 서버의 편집기로 파일을 열어 실제 로그인 정보를 확인한다.

## 2. 서버와 저장소 준비

권장 OS와 최소 서버 사양은 [README의 사전 준비](README.md#사전-준비)를 따른다.
이는 프로젝트를 위한 최소 준비 기준이며, 전체 기능이나 GitLab 동시 운영의 성능을 보장하는 실측 사양은 아니다.

Git과 CA 인증서가 없으면 Linux 배포판의 패키지 관리자로 먼저 설치한다.
기존 체크아웃이 있으면 그 위치에서 `git status --short --branch`로 상태를 확인하고,
기존 변경사항과 원격 설정을 보존한다. 아래의 clone·원격 추가·브랜치 생성은 새 체크아웃용이다.
저장소 주소에는 토큰이나 비밀번호를 넣지 않고 SSH 키 또는 자격증명 관리자를 사용한다.

| 설치 상황 | 진행 순서 |
| --- | --- |
| 조직 최초 도입: 내부 GitLab이 아직 없음 | 2.1절에서 GitHub 원본을 clone → 2.4절과 3~5절에서 최소 실행 확인 → 2.2절에서 내부 GitLab 구성과 초기 코드 등록 |
| 기존 조직에 개발자·서버 추가 | 2.3절에서 내부 GitLab을 clone → 2.4절 이후 개발 환경 설치 |

| 원격 이름 | 대상 | 용도 |
| --- | --- | --- |
| `upstream` | `https://github.com/hurxxxx/open-work-hub.git` | 원본 코드와 업데이트를 가져오는 곳 |
| `origin` | 조직 내부 GitLab 프로젝트 | 내부 변경사항, MR, CI와 배포 기준을 관리하는 곳 |

원격 역할과 브랜치·게시 권한은 [저장소 정책](AGENTS.md#git-and-delivery)을 따른다.
체크아웃은 하나의 `open-work-hub` 디렉터리 아래에서 관리한다.
최소 첫 실행은 `open-work-hub/dev`에서 준비한다. 내부 GitLab의 `main` 등록 뒤 개발·운영 경로를 함께
준비하는 설치에서는 2.5절에 따라 `open-work-hub/prod`를 만든다. 작업별 체크아웃은 필요할 때
`open-work-hub/worktrees/<작업명>`에 추가한다.

### 2.1. 조직 최초 도입: GitHub 원본에서 시작

원하는 작업 위치에 `open-work-hub`를 만들고 그 아래의 새 `dev` 디렉터리에 Git 이력을 포함해 내려받는다.
이 예시는 원본 `main`의 체크아웃 시점 커밋을 최초 기준으로 사용한다.

```bash
mkdir -p open-work-hub
cd open-work-hub
git clone --origin upstream --branch main https://github.com/hurxxxx/open-work-hub.git dev
cd dev
git switch --no-track -c dev
git config remote.pushDefault origin
git rev-parse HEAD
```

원본은 처음부터 `upstream`으로 등록하고, 로컬 `dev`는 원본 브랜치를 추적하지 않도록 만든다.
기본 push 대상은 앞으로 연결할 `origin`으로 지정한다. 아직 `origin`이 없으므로
이 단계에서 기본 push가 실패하는 것은 정상이며, GitHub로 내부 변경사항을 보내지 않는다.
출력된 최초 기준 커밋 SHA를 설치 결과에 기록한다.

이제 2.4절의 개발 도구를 준비하고 3~5절에서 최소 환경의 로그인과 화면을 확인한다.
첫 실행 확인 뒤 같은 체크아웃에서 2.2절과 2.5절을 진행하고, 7절의 완료 기준까지 확인한다. 최소 환경 실행만으로 조직 최초 도입을 완료했다고 보고하지 않는다.

### 2.2. 내부 GitLab 구성과 최초 코드 등록

조직 관리자가 내부 서버에 GitLab을 별도 관리 서비스로 준비한다.
에이전트에게 맡길 때는 서버 설치, 관리자 설정, `glab` 인증, 초기 코드 push와 CI 준비를 작업 범위에 명시한다.
[README의 셋업 프롬프트](README.md#4-codex에-셋업-요청)는 검증용 작업 브랜치·설치 관련 변경의 커밋과 push·`dev` 대상 Draft MR 생성·파이프라인 재실행까지 포함한다. 그 범위로 요청받았다면 같은 권한을 다시 확인하느라 중단하지 않는다.
README의 셋업 프롬프트에는 관리자 계정 준비·필요한 계정 생성·PAT 발급·`glab` 인증도 포함된다. 에이전트가 서버에서 끝까지 수행한다.
실제 비밀값은 보호된 파일이나 표준 입력으로 전달하고 명령 인자·대화·로그에 남기지 않는다.
새 설치의 계정 생성·토큰 발급·인증을 사용자에게 기본 단계로 넘기지 않는다. 기존 계정의 MFA 등 에이전트가 처리할 수 없는 인증 요소가 실제로 요구될 때만 필요한 입력을 요청하고 독립 작업은 계속한다.
이미 GitLab이나 프로젝트가 있다면 기존 설정과 이력을 확인해 사용하고 새로 초기화하지 않는다.
GitLab 서버, `glab` 클라이언트, 실제 작업을 실행하는 GitLab Runner는 각각 설치해야 한다.

#### 2.2.1. GitLab 서버 설치

GitLab 도메인·DNS 설정은 이 셋업에서 제외한다. 현재 SSH 접속 대상과 서버 네트워크를 확인해 PC·Runner에서 도달 가능한 IP를 사용한다.
HTTPS 포트는 사용 가능한 `8443`을 기본 예시로 삼고, 충돌하면 빈 포트를 선택해 실제 주소를 기록한다. 도메인 이름을 받기 위해 대기하지 않는다.
설치 전에 IP용 HTTPS 인증서, SSH 포트, 데이터·설정의 영속 저장과 백업 위치를 준비한다.
앱과 같은 서버라면 기존 서비스의 포트와 메모리·디스크 사용량을 확인한다.
GitLab 자체 DB·Redis는 프로젝트 개발용 DB·Redis와 구분하며 임의로 같은 데이터베이스에 연결하지 않는다.

[공식 Ubuntu 설치 안내](https://docs.gitlab.com/install/package/ubuntu/)와
[지원 플랫폼](https://docs.gitlab.com/install/package/#supported-platforms)에서 실제 OS·CPU 아키텍처와 선택한 GitLab 버전의 지원 여부를 확인한다.
다음은 **새 서버의 Community Edition Linux 패키지 설치 예시**다.
아래 IP·포트·패키지 버전은 서버에서 확인한 값으로 바꾼다.
기존 인증서가 없으면 서버에서 사설 CA와 접속 IP를 SAN에 넣은 서버 인증서를 준비하고, [수동 HTTPS 설정](https://docs.gitlab.com/omnibus/settings/ssl/#configure-https-manually)에 따라 설치 전에 `/etc/gitlab/gitlab.rb`에 `letsencrypt['enable'] = false`와 인증서 경로를 설정한다.
CA·서버 개인키는 서버에 제한된 권한으로 보관하고, 기존 CA·인증서가 있으면 보존한다. 외부 도메인이나 자동 인증서 발급 대기를 선행 조건으로 두지 않는다.

```bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates openssh-server openssl tzdata perl
curl -fsSL https://packages.gitlab.com/install/repositories/gitlab/gitlab-ce/script.deb.sh | sudo bash
apt-cache policy gitlab-ce
sudo EXTERNAL_URL='https://<서버-IP>:8443' apt-get install 'gitlab-ce=<설치할-패키지-버전>'
sudo gitlab-ctl status
```

대상 OS의 패키지가 없으면 다른 Ubuntu 버전의 저장소를 섞지 않는다.
지원되는 별도 서버 또는 [공식 Docker 설치 방식](https://docs.gitlab.com/install/docker/installation/)을 선택하고 버전을 고정한다.
Docker 방식은 앱의 PostgreSQL·Redis 네이티브 설치 방식을 바꾸지 않는다.
설치 후 브라우저에서 정한 HTTPS 주소에 접속한다. 사설 CA는 개발 서버와 Runner에도 신뢰하도록 등록하고 TLS 검증을 끄지 않는다.
Docker executor의 작업·helper 컨테이너에도 [Runner 인증서 설정](https://docs.gitlab.com/runner/configuration/tls-self-signed/)을 적용한다.

PC에서 직접 접속할 IP 기반 주소를 `external_url`로 사용한다. [GitLab의 외부 URL 설정](https://docs.gitlab.com/omnibus/settings/configuration/#configure-the-external-url-for-gitlab)은 서버 IP를 지원한다.
예를 들어 `https://<서버-IP>:8443`으로 설정했다면 인증서 SAN에 해당 **IP 주소**를 포함하고,
NGINX가 PC에서 도달 가능한 인터페이스에서 수신하도록 해당 버전의
[NGINX 설정](https://docs.gitlab.com/omnibus/settings/nginx/)을 적용한 뒤 `sudo gitlab-ctl reconfigure`를 실행한다.
GitLab 19.2 이상에서는 수신 주소·인증서 같은 Rails용 설정 키가 `gitlab_rails['nginx'][...]` 아래에 있다.
HTTPS 포트에는 `http://`로 접속할 수 없다. VM 네트워크와 방화벽은 필요한 HTTPS·SSH 포트만 허용한다.

사설 CA의 **공개 인증서만** 신뢰할 수 있는 SSH 연결 등으로 PC에 전달한다. CA 개인키는 서버 밖으로 복사하지 않는다.
Windows는 인증서 관리자의 신뢰할 수 있는 루트 인증 기관, macOS는 키체인 접근의 시스템 키체인,
Linux는 배포판의 CA 저장소에 등록한다. 별도 인증서 저장소를 사용하는 브라우저도 확인한다.
서버 내부 점검은 `/-/readiness?all=1`, PC 접속 점검은 `/users/sign_in`과 실제 로그인을 사용한다.
모니터링 경로의 IP 허용 목록을 PC 접속을 위해 넓히지 않는다.

#### 2.2.2. 초기 관리자와 비밀번호 설정

새 GitLab의 초기 셋업은 에이전트가 다음 계정으로 완료한다. GitLab이 만드는 `root`를 사용하며 별도 관리자 계정 생성을 사용자에게 요구하지 않는다.

| 초기 셋업 항목 | 값 |
| --- | --- |
| 관리자 로그인 아이디 | `root` |
| 초기 셋업 비밀번호 | `test1234!` |
| `glab` 인증 | `root` 소유 PAT를 에이전트가 발급해 표준 입력으로 전달 |

1. GitLab이 생성한 `root` 계정과 현재 초기화 상태를 확인한다. 자동 생성된 초기 비밀번호가 필요하면 서버의 `/etc/gitlab/initial_root_password`를 보호된 입력으로 사용한다. Docker 설치에서는 컨테이너 내부의 같은 경로다.
2. 새 설치의 `root` 비밀번호를 위 초기 셋업 값으로 설정하고 실제 GitLab 로그인까지 확인한다. 자동 생성 비밀번호는 이 값과 같다고 가정하지 않는다. 공식 관리자 화면 또는 아래 비밀번호 재설정 절차를 에이전트가 수행한다.
3. 셋업에 필요한 계정 상태·이메일 확인·권한을 점검하고, 추가 계정이 필요한 경우 에이전트가 생성·설정한다. 기존 사용자 ID·이메일·멤버십은 보존한다. 개인 담당자 계정 생성은 초기 `root` 셋업의 선행 조건이 아니다.
4. 2.2.3절에 따라 `root` 소유 PAT 발급·`glab` 인증·API 신원 확인까지 이어서 수행한다. 관리자 비밀번호나 PAT를 CI 변수·작업·아티팩트에 넣지 않는다.
5. [로그인 정보 파일](#11-로그인-정보-파일-관리)에 GitLab 주소, `root` 로그인 정보, PAT와 만료일, `glab` 인증 계정을 갱신한다.

위 비밀번호는 새 설치의 공개된 초기 셋업 값이다. 운영 사용 전에는 고유한 값으로 교체한다.
기존 GitLab의 관리자 비밀번호를 이 초기값으로 덮어쓰지 않는다. 비밀번호 정책이 값을 거부하면 정책을 낮추지 말고 실제 오류와 필요한 조치를 안내한다.

미확인 계정은 PAT 인증이 되더라도 CI lint나 파이프라인 생성이 거부될 수 있다. 에이전트가 관리자 권한으로 필요한 계정 확인을 수행한다.
SMTP가 준비되어 있으면 확인 메일을 사용하고, 미설정이면 공식 관리자 확인 절차를 사용해 셋업을 계속하며 SMTP를 후속 항목으로 기록한다. 인스턴스의 계정 확인 정책이나 기존 MFA를 끄지 않는다.

새 설치의 비밀번호 설정·복구가 필요하면 **에이전트가 서버에서** 다음 공식 대화형 재설정 명령을 실행하고 비밀번호를 표준 입력으로 전달한다.
비밀번호를 명령 인자나 스크립트에 쓰지 않는다. 실제 설치 방식에 맞는 명령만 사용한다.

```bash
# Linux 패키지 설치
sudo gitlab-rake 'gitlab:password:reset[root]'

# Docker 설치: 실제 GitLab 컨테이너 이름으로 변경
sudo docker exec -it '<GitLab-컨테이너>' gitlab-rake 'gitlab:password:reset[root]'
```

기준 문서: [최초 로그인](https://docs.gitlab.com/install/next_steps/),
[사용자 생성](https://docs.gitlab.com/user/profile/account/create_accounts/),
[비밀번호 변경·복구](https://docs.gitlab.com/security/reset_user_password/).
GitLab의 `root`는 OS의 `root`나 Open Work Hub의 개발용 `administrator` 계정과 별개다.

#### 2.2.3. glab 설치와 내부 GitLab 인증

`glab`은 Codex가 작업하는 개발 서버에서 OS 설치 계정으로 실행하고, GitLab 인증 신원은 위에서 준비한 `root`로 맞춘다.
Ubuntu 패키지를 사용하는 예시는 다음과 같다. 패키지가 없거나 필요한 옵션을 지원하지 않으면
[공식 CLI 배포 안내](https://gitlab.com/gitlab-org/cli)에서 버전·CPU 아키텍처에 맞는 배포 패키지를 설치한다.

```bash
sudo apt-get update
sudo apt-get install -y glab jq
glab --version
```

에이전트가 `root`의 [Personal access token](https://docs.gitlab.com/user/profile/personal_access_tokens/)을 발급한다. 사용자의 수동 토큰 발급을 기다리지 않는다.
GitLab 웹의 토큰 발급 기능이나 [공식 서버 관리 방식](https://docs.gitlab.com/user/profile/personal_access_tokens/#create-a-personal-access-token-programmatically)을 사용하고, 토큰은 대화·도구 출력에 표시하지 않고 보호된 파일에 직접 기록한다.
프로젝트·CI 변수 관리에는 해당 프로젝트의 관리 권한과 `api` 범위가 필요하다.
`glab auth login --help`의 요구 범위(`api`, `write_repository`)를 확인한다.
[Runner 생성 API](https://docs.gitlab.com/api/users/#create-a-runner-linked-to-a-user)도 사용할 때는 `create_runner`를 추가한다.
만료일을 설정한다. 초기 관리자·프로젝트·Runner 구성에는 `root`의 셋업용 토큰을 사용하며, 일상적인 프로젝트 자동화에는 별도 비관리자 계정에 필요한 그룹·프로젝트 역할만 부여한다.
SSH 방식의 Git 접근은 에이전트가 서버 설치 계정의 SSH 공개키를 GitLab 계정에 등록하고 연결을 확인한다.

이미 유효한 `root` 인증이 있으면 신원·권한·만료를 확인해 재사용한다. 새 인증이 필요하면 발급한 PAT만 담은 권한 `0600`의 임시 파일을 준비해 아래 명령의 표준 입력으로 전달한다.
호스트·그룹과 임시 파일 경로는 실제 값으로 바꾼다. `.auth_info`에는 여러 항목이 있으므로 파일 전체를 인증 입력으로 넘기지 않는다.
`--token <비밀값>`처럼 명령에 직접 쓰거나 셸 이력·대화에 남기지 않는다.

```bash
GITLAB_HOST='<서버-IP>'
GITLAB_API_HOST="$GITLAB_HOST:8443" # 실제 GitLab HTTPS 포트로 변경
GITLAB_REPO="https://$GITLAB_API_HOST/group/open-work-hub"
glab auth login --hostname "$GITLAB_HOST" --api-host "$GITLAB_API_HOST" \
  --api-protocol https --git-protocol ssh --stdin < '<PAT만-담은-임시파일>'
glab auth status --hostname "$GITLAB_HOST"
glab api --hostname "$GITLAB_HOST" user | jq '{username, is_admin}'
```

API 응답이 `username=root`, `is_admin=true`인지 확인한다. 실제 프로젝트·Runner 관리 권한까지 확인하고 토큰·만료일은 `.auth_info`에 기록한 뒤, 성공·실패 여부와 무관하게 이번에 만든 PAT 임시 파일을 삭제한다.

[glab 인증](https://docs.gitlab.com/cli/auth/login/)은 GitLab 계정 비밀번호와 별개다.
PAT로 인증했다면 비밀번호 변경만으로 다시 인증할 필요는 없다. 토큰의 만료·폐기·회전,
계정 차단이나 권한 변경은 별도로 영향을 준다. 다른 자동화 계정의 PAT는 관리자 비밀번호 변경과도 무관하다.
키링이 없는 서버에서는 토큰이 사용자 설정 파일에 평문으로 저장될 수 있으므로 해당 파일을 소유자만 읽게 보호한다.
토큰·설정 파일을 저장소나 CI 아티팩트에 복사하지 않는다.
인증 성공은 프로젝트 관리 권한을 보장하지 않으므로 그룹·프로젝트 역할도 확인한다.

#### 2.2.4. 내부 프로젝트와 원격 등록

1. 내부 그룹에 [비공개 빈 프로젝트](https://docs.gitlab.com/user/project/)를 만든다.
   README·라이선스·`.gitignore` 자동 생성은 선택하지 않는다.
   운영 담당자에게 그룹 Owner 또는 필요한 프로젝트 Maintainer 권한을 부여한다.
2. 프로젝트의 Clone 메뉴에서 조직이 사용할 SSH 또는 HTTPS 주소를 받는다.
   개발 서버에서 그 주소에 접근할 수 있도록 SSH 키 또는 자격증명 관리자를 설정한다.

2.1절에서 만든 체크아웃의 `dev` 브랜치에서, 초기 등록 권한이 있는 계정으로 실행한다.
아래 push는 비어 있는 새 프로젝트에 `main`·`dev`와 그 Git 이력을 등록하는 일회성 작업이다.

```bash
git remote add origin '<GitLab에서-받은-저장소-주소>'
git config remote.pushDefault origin
git push --set-upstream origin main dev
```

태그는 필요한 것만 별도로 이전한다. 태그 push로 패키지 게시 CI가 실행될 수 있으므로
기존 태그를 일괄 push하지 않는다. 기존 저장소에 `--mirror`나 강제 push로 이력을 덮어쓰지 않는다.

등록 후 내부 `dev`·`main`을 [보호 브랜치](https://docs.gitlab.com/user/project/repository/branches/protected/)로
구성하고 MR 병합 권한과 필수 검사를 적용한다. 일반 개발 MR의 기본 대상은 `dev`로 맞춘다.
`main`은 내부 운영 배포 기준이며, `dev → main` 릴리스 MR 뒤에도 `dev`를 삭제하지 않는다.
이 초기 코드 등록은 운영 배포를 실행하지 않는다.

새 프로젝트의 기본 브랜치와 파이프라인 성공 필수 설정은 저장소 루트에서 `glab`으로 적용할 수도 있다.
기존 프로젝트에서는 현재 설정과 조직 정책을 확인한 뒤 필요한 값만 변경한다.

```bash
glab api --hostname "$GITLAB_HOST" --method PUT 'projects/:id' \
  --field default_branch=dev \
  --field only_allow_merge_if_pipeline_succeeds=true \
  --silent
```

이 명령은 보호 브랜치·리뷰 승인 규칙까지 구성하지는 않는다.
브랜치별 push·병합 권한은 프로젝트 설정에서 별도로 적용한다.
새 프로젝트는 최초 push 이후 기본 브랜치가 `dev`인지 다시 확인한다.
`dev`·`main`의 직접 push와 force push를 금지하고 병합은 필요한 관리 역할에만 허용한다.
보호 브랜치 API는 에디션·버전별 지원 범위가 다르므로 응답 성공만 믿지 말고 저장된 권한을 다시 읽는다.
권한 변경이 반영되지 않으면 `Settings > Repository > Branch rules`에서 해당 규칙을 편집한다.
파이프라인 성공·미해결 토론 해소를 병합 조건으로 유지하고 릴리스 후 `dev` 자동 삭제를 끈다.

토큰 없는 주소로 구성한 새 체크아웃에서 연결 결과를 확인한다.

```bash
git remote -v
git branch -vv
git config --get remote.pushDefault
git ls-remote --heads origin main dev
```

`origin`은 내부 GitLab, `upstream`은 GitHub 원본이어야 한다.
로컬 `dev`·`main`의 추적 대상은 각각 `origin/dev`·`origin/main`이고 기본 push 대상은 `origin`이어야 한다.
원격의 두 브랜치가 등록한 커밋을 가리키는지 확인한다.
개발·운영 경로 분리는 2.5절에서 준비한다. 코드 등록과 경로 생성만으로 CI가 실행되거나 운영 앱이 배포되지는 않는다.

#### 2.2.5. Runner와 파이프라인 준비

`glab`은 GitLab API를 조작하는 도구이며 Runner나 CI 실행 환경을 대신 설치하지 않는다.
정확한 실행 조건과 이미지·태그는 [현재 CI 정의](.gitlab-ci.yml)가 기준이다.

| 현재 실행 대상 | 필요한 준비 |
| --- | --- |
| 같은 프로젝트의 작업 브랜치 → `dev` MR | `codex-local` 태그의 리뷰 Runner와 설치된 Codex 리뷰 실행기 |
| 같은 프로젝트의 `dev` → `main` 릴리스 MR | `open-work-hub-validation` 태그의 검증 Runner, 검증 이미지, 테스트 DB와 CI 변수 |
| `contracts-v<버전>` 형식 중 CI 규칙에 맞는 태그 | 검증 Runner와 GitLab npm Package Registry 접근. 실제 패키지 게시이므로 설치 확인용 태그를 만들지 않는다. |

일반 브랜치 push나 `glab ci run --branch dev`는 현재 workflow의 MR 조건을 만족하지 않는다.
실행되지 않는다고 CI 규칙이나 필수 검사를 완화하지 않는다.

1. Runner 호스트에 [GitLab Runner](https://docs.gitlab.com/runner/install/)를 설치한다.
   검증용은 Docker executor, 리뷰용은 신뢰된 전용 호스트의 shell executor 등 설치된 리뷰 실행기를 사용할 수 있는 환경으로 준비한다.
   리뷰 Runner를 운영 서버·운영 자격증명과 분리하고 다른 프로젝트에 공유하지 않는다.
2. 프로젝트의 `Settings > CI/CD > Runners`에서 검증용과 리뷰용 Runner를 각각 만들고 위 태그를 지정한다.
   프로젝트에 실행 범위를 한정하고 태그 없는 작업 실행은 끈다.
   리뷰 Runner는 일반 작업 브랜치 MR을, 검증 Runner는 보호된 릴리스 브랜치·게시 태그를 실행할 수 있도록 접근 정책을 맞춘다.
3. 생성된 `glrt-` Runner 인증 토큰으로 각 Runner를 등록한다.
   아래 명령의 질문에 GitLab URL·토큰·executor를 입력한다. 오래된 registration token 방식은 사용하지 않는다.

```bash
sudo gitlab-runner register
sudo gitlab-runner verify
```

등록 절차는 [공식 Runner 안내](https://docs.gitlab.com/runner/register/)를 따른다.
등록 성공만으로 작업 실행 준비가 끝나는 것은 아니다. 검증 Runner가 사용하는 Docker 데몬에서
**승인된 저장소 커밋**으로 다음 이미지를 준비한다.
프로젝트 DB에 읽기 전용으로 접속해 실제 서버 메이저 버전을 확인한다. `psql --version`은 클라이언트 버전이므로 서버 버전 대신 사용하지 않는다.
아래 예시의 `owh-dev`는 에이전트가 기존 개발 DB 설정을 바탕으로 준비한 [libpq 연결 서비스](https://www.postgresql.org/docs/current/libpq-pgservice.html) 이름이다. 비밀번호는 소유자만 읽을 수 있는 passfile로 전달하고 명령 인자에 쓰지 않는다. `psql`, Docker, Buildx와 `jq`가 필요하다.

```bash
project_postgres_version_num="$(psql -XAtw 'service=owh-dev' -c 'SHOW server_version_num')"
if [[ ! "$project_postgres_version_num" =~ ^[0-9]{6,}$ ]]; then
  echo '프로젝트 PostgreSQL 서버 버전을 확인하지 못했습니다.' >&2
  exit 1
fi
project_postgres_major="$((10#$project_postgres_version_num / 10000))"
bash scripts/build-ci-validation-image.sh --postgres-major "$project_postgres_major"
docker build -f ops/opensearch/Dockerfile -t open-work-hub-opensearch:3.3.2-nori .
```

검증 이미지 이름은 현재 `open-work-hub-validation:node22-python312`다.
개발 서버의 Node.js 24 설치와는 별도이며, 이름만 같은 다른 이미지로 대체하지 않는다.
빌드 스크립트는 선택한 PostgreSQL 메이저의 공식 Bookworm 이미지 태그를 불변 digest로 확인한다. PostgreSQL 버전·digest·Docker 플랫폼·Dockerfile·의존성이 일치하면 기존 이미지를 다시 검사해 재사용하고, 다르면 빌드한다. 빌드·클라이언트 검사 실패는 설치 실패로 처리한다.
출력된 PostgreSQL 버전·이미지 digest·플랫폼·의존성 해시를 셋업 결과에 기록한다. 같은 입력으로 재현하려면 `--postgres-client-image 'postgres@sha256:<기록한-digest>'`를 전달한다. ARM64를 포함한 [플랫폼·재빌드 계약](docs/domains/release/README.md#validation-image-platform-and-database)을 따른다.
로컬 이미지를 쓰는 전용 Runner는 `if-not-present` 등 그 배포 방식에 맞는 pull 정책을 구성한다.
다른 Docker 데몬에서 실행하는 Runner라면 같은 검증된 이미지가 그 데몬에도 준비되어야 한다.
CI의 Redis·MinIO 서비스 이미지도 내려받을 수 있어야 한다.
OpenSearch는 앱의 최소 첫 실행에는 선택 사항이지만 현재 릴리스 CI에는 필요한 서비스다.
개발 앱의 추가 서비스 시작을 보류해도, GitLab CI까지 포함한 셋업에서는 필요한 검증 이미지·테스트 DB·CI 서비스 준비를 끝낸다.
리뷰 Runner 준비와 릴리스 검증 준비를 구분하며, 필요한 이미지·서비스·DB와 등록·온라인 상태를 확인한다. 릴리스 파이프라인 실행은 별도 릴리스 범위를 따른다.

리뷰 Runner의 **실제 실행 계정**에 Git·Node.js·Codex·Linux 샌드박스 선행 도구와 Codex 인증을 준비한다.
개발 사용자의 로그인이나 nvm 설정이 Runner 서비스에 자동으로 전달된다고 가정하지 말고 서비스의 PATH를 맞춘다.
승인된 커밋의 체크아웃에서 신뢰된 실행기를 설치한다.

```bash
bash scripts/install-codex-review-runner-entrypoint.sh
```

설치 대상은 `/usr/local/bin/open-work-hub-codex-review-ci`다.
MR 소스의 스크립트를 직접 실행하도록 바꾸지 않으며, 리뷰의 읽기 전용 실행과 CI 신원·이미지 검사를 유지한다.
상세 계약은 [Local Codex MR Review](docs/agents/local-codex-review.md),
검증 이미지·실행 계약은 [Release Domain](docs/domains/release/README.md)을 따른다.

#### 2.2.6. CI 변수 등록과 실제 실행 확인

검증 Runner에서 접근할 수 있는 **CI 전용 비운영 PostgreSQL DB와 계정**을 준비한다.
테스트용 DB 생성·삭제에 필요한 권한만 부여하고 GitLab 자체 DB, 개발 업무 DB나 운영 DB를 사용하지 않는다.
Docker 작업 안의 `127.0.0.1`은 호스트 DB 주소가 아니므로 Runner의 실제 네트워크에서 접속 가능한 주소를 사용한다.
CI 서버와 검증 이미지 클라이언트의 메이저 버전은 프로젝트 DB와 맞춘다. PostgreSQL 17 같은 특정 메이저 버전을 요구하지 않는다.
같은 비운영 PostgreSQL 인스턴스에 별도 CI DB·계정을 둘 수 있으며, CI 계정은 개발 업무 DB를 소유하거나 접근하지 못하게 한다. 별도 CI 클러스터가 필요하면 같은 메이저 버전으로 만들고 별도 데이터 디렉터리·포트·계정을 사용한다.
릴리스 CI는 실제 DB 서버와 이미지의 `pg_dump`·`pg_restore`·`psql` 버전이 일치하는지 테스트 시작 전에 검사한다. 불일치 시 DB 연결 대상과 [검증 이미지 구성](docs/domains/release/README.md#validation-image-platform-and-database)을 바로잡고 재실행한다.
Docker 전용 네트워크로 연결할 때는 해당 인터페이스와 CIDR에만 DB 수신·`pg_hba.conf` 접근을 허용하고,
부팅 시 네트워크를 만드는 Docker 서비스가 DB보다 먼저 준비되도록 systemd 의존성을 설정한다.
Debian 계열에서 클러스터 이름은 `ci`처럼 하이픈 없이 정해 systemd 인스턴스 이름의 경로 변환을 피한다.

새 프로젝트에 `OPEN_WORK_HUB_CI_POSTGRES_DSN`을 아래와 같이 등록한다.
기존 변수가 있으면 새로 만들거나 덮어쓰기 전에 환경 범위와 소유자를 확인한다.
에이전트가 셋업한 CI DB의 값은 보호된 입력에서 표준 입력으로 전달한다. 이미 알고 있는 값을 사용자에게 다시 요청하지 않는다.
사용자가 직접 인증 정보를 제공하는 경우에만 아래 대화형 입력을 사용한다. 비밀값을 명령 인자·대화·로그에 남기지 않는다.

```bash
set +x
read -r -s -p 'CI PostgreSQL DSN: ' ci_postgres_dsn
printf '\n'
printf '%s' "$ci_postgres_dsn" | glab variable set OPEN_WORK_HUB_CI_POSTGRES_DSN \
  --repo "$GITLAB_REPO" --masked --protected --raw --scope ci-validation
unset ci_postgres_dsn
```

`ci-validation`은 현재 검증 job의 environment 이름이다.
`dev`·`main` 보호와 함께 프로젝트의 MR 파이프라인에서 보호 변수·Runner를 사용할 수 있는 설정과 실행자 권한을 확인한다.
필요 조건은 [보호 리소스 접근 안내](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/#control-access-to-protected-variables-and-runners)를 따른다.
변수가 보이지 않는다고 보호를 해제하거나 관리자 토큰을 대신 넣지 않는다.
`CI_JOB_TOKEN` 등 GitLab이 공급하는 기본 변수를 수동으로 재정의하지 않는다.

저장소 루트에서 CI 설정을 검사하고 파이프라인 목록을 확인한다.

```bash
glab ci lint .gitlab-ci.yml --repo "$GITLAB_REPO"
glab ci list --repo "$GITLAB_REPO"
```

실제 실행은 **명시적으로 승인된 작업 브랜치와 MR**에서 확인한다.
README의 전체 셋업 프롬프트로 위임받은 경우에는 그 범위 안에서 검증용 작업 브랜치를 준비하고, 설치 관련 변경을 검토·커밋·push한 뒤 `dev` 대상 Draft MR을 생성한다. 기존 검증용 MR이 있으면 재사용한다.
MR에는 비밀값이나 서버별 실행 로그를 포함하지 않는다. 준비된 source 브랜치에서 다음과 같이 생성할 수 있다.

```bash
glab mr create --source-branch '<검증용-작업-브랜치>' --target-branch dev \
  --draft --title 'Validate development setup' \
  --description 'Verify the installation changes and GitLab CI setup.' \
  --repo "$GITLAB_REPO" --yes
```

MR 생성·새 커밋 push로 파이프라인이 생성되며, 이미 열린 MR을 다시 실행하려면 대상 source 브랜치를 지정한다.

```bash
glab ci run --mr --branch '<MR의-source-브랜치>' --repo "$GITLAB_REPO"
```

명령 기준: [Draft MR 생성](https://docs.gitlab.com/cli/mr/create/), [CI lint](https://docs.gitlab.com/cli/ci/lint/),
[MR 파이프라인 실행](https://docs.gitlab.com/cli/ci/run/),
[CI 변수 등록](https://docs.gitlab.com/cli/variable/set/).
lint 성공이나 파이프라인 생성만으로 설치 완료로 판단하지 않는다.
최신 MR 커밋에서 예상한 job이 실제 실행되어 성공했는지 확인하고, pending·인증·이미지·DB 연결 실패를 구분해 보고한다.
실행 실패는 셋업 범위에서 원인을 해결하고 재실행한다. `dev` 대상 MR의 `codex_review` 성공을 개발 파이프라인 완료 증거로 남기며, `release_validation` 실행 여부와 혼동하지 않는다.
`dev → main` 릴리스 MR·병합·운영 배포는 각각 별도 승인 대상이다.
GitLab 접속, 관리자 로그인·비밀번호 변경, `glab` 인증, Runner 온라인, 변수 등록, 실제 CI 통과 여부를 나누어 설치 결과에 기록한다.

### 2.3. 기존 조직에 개발자·서버 추가

내부 GitLab에 `dev` 브랜치가 준비되어 있으면 프로젝트의 Clone 메뉴에서 주소를 받아
원하는 작업 위치의 `open-work-hub/dev`에 내려받는다.

```bash
mkdir -p open-work-hub
cd open-work-hub
git clone --branch dev '<GitLab에서-받은-저장소-주소>' dev
cd dev
git remote add upstream https://github.com/hurxxxx/open-work-hub.git
git config remote.pushDefault origin
```

이 경로에서는 clone한 내부 GitLab이 자동으로 `origin`이 된다.
다른 체크아웃의 추가 원격 설정은 clone으로 승계되지 않으므로 각 체크아웃에 `upstream`을 등록한다.
GitHub와 내부 GitLab 사이에 자동 미러링을 구성할 필요는 없다. 원본 업데이트는 8절을 따른다.
이 서버에 운영 체크아웃도 준비하기로 했다면 2.5절을 따른다.

### 2.4. 공통 서버 확인과 개발 도구 준비

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
| Node.js와 npm | Codex 실행 전에 [README](README.md)의 nvm 설치·Bash 재로드·`nvm install 24` 명령을 따른다. 버전 범위는 [package.json](package.json)의 `engines.node`가 기준이다. |
| bubblewrap (Linux Codex) | Codex 실행 전에 설치한다. [README](README.md) · [공식 샌드박스 요건](https://developers.openai.com/codex/concepts/sandboxing#prerequisites) |
| pnpm | 루트 `package.json`의 `packageManager`에 지정된 버전을 사용한다. [공식 설치 안내](https://pnpm.io/installation) |
| uv와 앱용 Python | [uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)와 [Python 설치 안내](https://docs.astral.sh/uv/guides/install-python/)를 따른다. Python 범위는 [API](apps/api/pyproject.toml)·[Worker](apps/worker/pyproject.toml)의 `requires-python`이 기준이다. |
| agent-browser | 최초 셋업과 에이전트의 화면 확인에 사용한다. CLI가 없을 때 `npm install --global agent-browser`로 설치하고 `agent-browser --version`으로 확인한다. 브라우저 준비와 검사는 4.1절을 따른다. |
| PostgreSQL·Redis | 4절에 따라 호스트에 네이티브로 설치하고 systemd 서비스로 관리한다. |
| Docker Engine와 Compose 플러그인 (선택) | Docker 기반 추가 서비스나 기존 Compose 방식을 사용할 때만 [Docker 공식 설치 안내](https://docs.docker.com/engine/install/)를 따른다. 네이티브 최소 구성에는 필요하지 않다. |

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
command -v git curl lsof pgrep
```

Docker를 선택한 경우에만 다음 명령으로 데몬 연결과 사용 권한을 확인한다.

```bash
docker compose version
docker info --format '{{.ServerVersion}}'
```

`docker` 실행 파일만 존재하거나 기존 컨테이너가 보인다는 이유로 준비 완료로 판단하지 않는다.
첫 Python 의존성 설치에는 AI 라이브러리도 포함되어 다운로드가 클 수 있다.
추가 기능의 모델 다운로드·브라우저 설치까지 고려하고, 서버 사양이 검증되었다고 추정하지 않는다.

### 2.5. 개발·운영 체크아웃 경로 분리

내부 GitLab의 `origin/dev`·`origin/main`이 준비된 뒤, 개발·운영 경로 구성을 포함한 설치에서 진행한다.
운영 서비스 실행과 자격증명 설정은 별도 단계다. 개발만 필요한 참여자에게 운영 접근 권한을 추가하지 않는다.

| 상대 경로 | 브랜치·용도 | 환경설정 |
| --- | --- | --- |
| `open-work-hub/dev` | `dev` → `origin/dev`, 개발 실행과 통합 | 개발용 `.env` |
| `open-work-hub/prod` | `main` → `origin/main`, 승인된 운영 작업 전용 | 운영 준비 시 별도 `.env` 구성 |
| `open-work-hub/worktrees/<작업명>` | 요청된 기능·MR 작업 브랜치 | 해당 작업에 필요한 개발 설정 |

`dev`에서 실행하는 아래 명령은 **`prod`가 아직 없는 경우**의 예시다.
기존 디렉터리나 등록된 worktree가 있으면 브랜치·dirty 상태·소유자를 먼저 확인해 재사용하고 덮어쓰지 않는다.
로컬 `main`이 원격과 다르면 명령은 중단한다. 강제 reset 대신 이력과 진행 중인 작업을 확인한다.

```bash
(
  set -e
  git fetch origin dev main
  git worktree list
  if ! git show-ref --verify --quiet refs/heads/main; then
    git branch --track main origin/main
  fi
  test "$(git rev-parse main)" = "$(git rev-parse origin/main)"
  git branch --set-upstream-to=origin/main main
  git worktree add ../prod main
  mkdir -p ../worktrees
)
git -C ../prod status --short --branch
git worktree list
```

연결된 worktree는 Git 이력·원격 설정을 공유하지만 파일·환경설정은 별도다.
`origin`·`upstream`을 다시 추가하거나 개발 `.env`·가상환경·데이터를 `prod`로 복사하지 않는다.
운영 실행 준비 전에는 `prod/.env`를 비워 둔 파일로 만들지 않고 미생성 상태로 둔다.
운영 설정은 [운영 앱 계약](docs/domains/release/README.md#production-app-contract)에 따라 별도로 준비한다.
`prod`의 HEAD가 `origin/main`과 같고 작업 트리가 깨끗한지 확인한다.

CI의 작업 브랜치 → `dev` 리뷰와 `dev` → `main` 릴리스 검증은 2.2.5~2.2.6절의 MR 조건으로 실행된다.
Runner의 job 체크아웃은 이 두 상시 경로와 별도이며, 경로를 만들었다고 자동 배포 job이 추가되지는 않는다.
`main` 승격·운영 체크아웃 갱신·운영 배포는 각각 승인된 절차에서 수행한다.

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
PostgreSQL·Redis는 에이전트가 호스트에 네이티브로 설치하며 사람이 미리 설치할 필요는 없다.
OpenSearch를 포함한 추가 서비스는 이 단계에서 필요하지 않으며, 사용할 기능에 따라 6절에서 준비한다.

1. 문서 앞의 **PostgreSQL·Redis 최초 설치 버전** 기준에 따라 최신 안정 버전을 확인하고,
   [PostgreSQL Ubuntu 설치 안내](https://www.postgresql.org/download/linux/ubuntu/)와
   [Redis 공식 APT 설치 안내](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/apt/)를 따라 네이티브 패키지를 설치한다.
   [개발 Compose](ops/compose/open-work-hub-dev.infra.yml)의 고정 메이저 버전을 네이티브 신규 설치 버전으로 대신 사용하지 않는다.
2. 프로젝트용 개발 DB·사용자와 Redis 인스턴스를 준비하고 loopback 주소에서만 접근하도록 구성한다.
   기존 서비스·데이터·포트를 보존하고, 실제 PostgreSQL 클러스터와 Redis의 systemd unit을 확인해 시작·자동 시작을 설정한다.
3. `.env`의 `OPEN_WORK_HUB_POSTGRES_DSN`, `OPEN_WORK_HUB_INFRA_POSTGRES_PORT`,
   `OPEN_WORK_HUB_INFRA_REDIS_PORT`를 실제 네이티브 서비스에 맞춘다.
   템플릿의 포트 `55433`·`56380`을 네이티브 기본 포트와 같다고 가정하지 않는다.
   기존 개발용 Redis·Worker 연결 재정의도 [개발 환경 설정](scripts/dev-env.sh)에 따라 함께 맞추고 비밀값은 출력하지 않는다.
   Redis 인증이 필요하면 `OPEN_WORK_HUB_DEV_REDIS_URL`과 `OPEN_WORK_HUB_DEV_REDIS_RESULT_BACKEND`를 설정한다.
   `--minimal-infra`는 PostgreSQL DSN을 `OPEN_WORK_HUB_INFRA_POSTGRES_*`에서 구성하므로 사용자·비밀번호·DB 이름도 맞춘다.
4. systemd 상태뿐 아니라 실제 대상에 대한 `pg_isready`, DB 사용자 인증과 쿼리,
   Redis의 인증된 `PING` 응답으로 연결을 확인한다. 기존 데이터베이스를 재생성하거나 Redis 데이터를 비우지 않는다.

개발용 PostgreSQL의 메이저 버전을 변경할 때는 해당 OS·CPU를 지원하는 공식 PGDG 패키지를 사용하고,
마이그레이션·인증 쿼리·로그인 검사를 수행한다. 개발 DB의 선택이 Compose나 CI DB 버전을 함께 변경하지는 않는다.
기존 클러스터를 업그레이드할 때는 백업·포트·확장 호환성을 먼저 확인하고
[pg_upgradecluster](https://manpages.debian.org/unstable/postgresql-common/pg_upgradecluster.1.en.html) 등 배포판의 전환 절차를 따른다.
검사 옵션으로 사전 확인한 뒤 전환하며, 이전 클러스터는 중지 상태와 복구 가능한 데이터로 보존한다.
`pg_lsclusters`로 실제 포트와 대상 버전을 확인하고 구 클러스터가 자동 시작되어 충돌하지 않게 한다.

필요한 Redis 메이저 버전의 패키지가 없다면 다른 배포판 저장소를 섞지 않는다.
[공식 소스 빌드](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-from-source/)를 선택할 수 있다.
릴리스와 [공식 체크섬](https://github.com/redis/redis-hashes)을 고정·검증하고 일반 사용자로 빌드한다.
`Type=notify` 서비스에는 `USE_SYSTEMD=yes` 빌드와 `supervised systemd` 설정을 함께 사용한다.
바이너리는 root 소유로 설치하고, 전용 비로그인 서비스 계정에 데이터 디렉터리 쓰기 권한만 부여한다.
인증을 포함한 설정 파일은 해당 서비스만 읽도록 제한하고 loopback·protected mode·영속 저장을 유지한다.
systemd unit에는 실제 바이너리·설정·데이터 경로를 사용하고 서비스 계정으로 인증 연결을 검증한다.

첫 실행 전에 개발 `.env`에서 다음 항목을 설정한다. 서버 IP는 PC에서 실제로 접속할 주소로 바꾸고 기존의 다른 설정은 보존한다.

```dotenv
OPEN_WORK_HUB_WEB_DEV_HOST=0.0.0.0
OPEN_WORK_HUB_WEB_DEV_PORT=4200
OPEN_WORK_HUB_API_DEV_LOGIN_ALLOWED_HOSTS=<서버-IP>
```

Web은 모든 IPv4 인터페이스에서 수신하고 API 요청을 loopback의 API로 프록시한다.
API·개발 PostgreSQL·Redis의 수신 주소는 loopback으로 유지한다. `0.0.0.0`은 수신 설정이며 사용자에게 전달할 접속 주소는 서버 IP다.
새 개발 DB의 시드 비밀번호는 첫 실행 전에 `OPEN_WORK_HUB_API_DEV_LOGIN_PASSWORD`에 고유한 값으로 설정하고 `.auth_info`에 기록한다.
기존 DB에서는 기존 계정·비밀번호를 보존한다. 이 환경값을 바꾸는 것만으로 기존 계정의 비밀번호가 갱신되지는 않는다.

첫 실행은 터미널에서 아래 명령으로 확인한다. 최종 인계 전에는 7절의 지속 실행과 외부 로그인 확인까지 마친다.

```bash
./dev.sh --minimal-infra --no-infra
```

`--minimal-infra`는 선택 기능의 시작 의존성을 끄고, `--no-infra`는 Docker 인프라 시작을 건너뛴다.
기본 설정에서는 API 시작 전에 Alembic 마이그레이션을 실행한다.
DB를 지우거나 `stamp`로 오류를 건너뛰지 않는다. 이전 스키마라면
[API 마이그레이션 안내](apps/api/README.md#alembic)를 먼저 확인한다.

기존 Docker 방식을 선택한 경우에만 위 실행 명령 대신 `pnpm dev:minimal`을 사용하고,
컨테이너 상태는 `pnpm dev:infra:minimal:status`로 확인한다. 네이티브 구성에서는 이 명령들을 사용하지 않는다.

두 번째 터미널에서 같은 저장소로 이동해 확인한다.

```bash
./dev.sh --status
pnpm dev:login-smoke
```

PC에 안내할 Web 주소는 `http://<서버-IP>:4200`이며, 서버 내부 API 주소는 `http://127.0.0.1:8001`이다.
포트를 변경한 환경에서는 실제 개발 설정을 따른다. 서버 내부의 loopback 검사 통과 후에도 5절의 외부 접속 검사를 완료해야 한다.
개발용 로그인 아이디는 `administrator`이며 비밀번호는 `.auth_info`에서 확인한다. 템플릿의 초기 비밀번호는 `open-work-hub-dev-only`이므로 새 설치에서는 위 단계에서 바꾼 값을 사용한다.
공유·공개 운영 서비스에는 개발용 기본 계정을 사용하지 않는다.
확인한 개발용 시드 계정과 DB·Redis 접속 정보는 [로그인 정보 파일](#11-로그인-정보-파일-관리)의 개발 항목에 기록한다.

### 4.1. agent-browser로 셋업 화면 확인

최초 셋업과 에이전트의 화면 확인에는 **`agent-browser`를 기본으로 사용한다.**
2.4절에서 CLI를 준비한 뒤 설치된 버전의 지원 명령을 확인한다.

```bash
agent-browser --version
agent-browser --help
```

사용 가능한 브라우저가 없을 때만 `agent-browser install`로 준비한다.
기존 Chromium을 사용할 때는 `--executable-path '<검증된-Chromium-실행파일>'`을 지정한다.
Linux에서 OS 라이브러리 누락으로 실행이 실패하면 `agent-browser install --with-deps`로 필요한 의존성을 준비한다.
설치된 CLI가 `skills` 명령을 제공하면 `agent-browser skills get core`도 참고한다.

PC에서 사용할 서버 IP의 개발 주소로 로그인 화면을 열고 현재 화면의 요소를 확인한다. IP·포트는 실제 설정으로 바꾼다.

```bash
agent-browser --session owh-setup open 'http://<서버-IP>:4200/login'
agent-browser --session owh-setup snapshot -i
```

1.1절의 비밀값 취급 절차를 지키며 로그인하고, 앱 목록·주요 화면의 접근과 로그아웃 후 로그인 화면 복귀까지 확인한다.
페이지 열기나 snapshot 출력만으로 로그인 검사를 통과했다고 보고하지 않는다. 검사 결과와 미확인 항목을 구분하고, 실패한 경우에도 사용한 세션을 종료한다.

```bash
agent-browser --session owh-setup close
```

사설 GitLab 인증서는 2.2.1절의 CA 신뢰 설정을 적용하고 TLS 검증을 유지한다.

### 4.2. 기존 Playwright 회귀검사가 필요한 경우

기존 Playwright 로그인 회귀검사나 E2E를 실행하는 작업, 또는 변경 범위상 해당 검사가 필요한 작업에서만 다음 준비를 수행한다.
이 절은 최초 셋업의 기본 필수 단계가 아니다. `agent-browser` 화면 확인은 기존 자동 테스트·CI의 필수 검사를 대체하지 않는다.

```bash
pnpm e2e:install
pnpm dev:login-browser-smoke
```

`pnpm e2e:install`은 저장소의 Playwright용 Chromium을 설치하고, `pnpm dev:login-browser-smoke`는 기존 로그인 회귀검사를 실행한다.
`pnpm agent-browser:smoke`도 현재 Playwright E2E를 실행하는 별칭이므로, 직접 화면을 확인할 때는 4.1절의 `agent-browser` CLI를 사용한다.

Chromium의 OS 라이브러리가 빠졌다면
[Playwright 시스템 의존성 안내](https://playwright.dev/docs/browsers#install-system-dependencies)에 따라
`pnpm exec playwright install-deps chromium`으로 준비한 뒤 다시 검사한다.

새 Ubuntu 릴리스가 고정된 Playwright의 다운로드 목록에 없다면 OS 이름만으로 지원을 추정하지 않는다.
예를 들어 Playwright 1.59.1의 Ubuntu 26.04 지원 범위는
[공식 이슈](https://github.com/microsoft/playwright/issues/40117)를 확인한다.
동일 CPU의 호환 배포본을 검증할 때만 `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-arm64 pnpm e2e:install`처럼
일회성 다운로드 대상을 지정할 수 있다. 시스템 의존성은 현재 OS의 패키지로 준비하고 실제 Chromium 실행·로그인 검사를 통과해야 한다.
필요 패키지는 같은 플랫폼 지정으로 `pnpm exec playwright install-deps chromium --dry-run`을 실행해 먼저 확인한다.

### 4.3. Chromium 실행이 AppArmor에 차단된 경우

Ubuntu의 AppArmor가 Chromium의 사용자 네임스페이스를 차단하면
[Chromium의 AppArmor 안내](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md)를 따른다.
실행파일은 일반 사용자가 바꿀 수 없는 관리자 소유 경로에 두고 그 **정확한 경로만** 허용하는 프로필을 적용한다.
`--no-sandbox`나 시스템 전체의 사용자 네임스페이스 제한 해제로 우회하지 않는다.
적용 후 `chrome://sandbox`에서 namespace·seccomp 샌드박스가 활성화되었는지 확인한다.
최소 환경 검사 통과는 전체 업무 기능의 설치 완료를 뜻하지 않는다.

## 5. 내 PC 브라우저에서 서버 접속

기본 접속 방식은 **SSH 터널 없이 서버 IP로 직접 접속**하는 것이다.
4절에서 설정한 `.env`의 `OPEN_WORK_HUB_WEB_DEV_HOST=0.0.0.0`과 실제 Web 포트를 확인한다.
개발 앱을 재시작한 뒤 `ss -ltn`으로 `0.0.0.0:<개발-Web-포트>` 수신을 확인한다.
VM 네트워크·라우팅·방화벽에서 PC가 해당 IP와 Web 포트에 도달할 수 있게 구성한다. NAT 환경이면 필요한 포트 전달을 함께 설정한다.
사용자에게 `http://<서버-IP>:<개발-Web-포트>/login`을 안내한다. `0.0.0.0`이나 서버의 `127.0.0.1`을 PC 접속 주소로 안내하지 않는다.
기본 Web 개발 서버가 API 요청을 프록시하므로 API·개발 PostgreSQL·Redis는 loopback 바인딩을 유지한다.

서버에서는 실제 PC 접속 주소를 대상으로 다음 검사를 수행한다. IP·포트는 환경에 맞춘다.

```bash
OPEN_WORK_HUB_DEV_SMOKE_API_URL='http://<서버-IP>:4200' pnpm dev:login-smoke
agent-browser --session owh-setup open 'http://<서버-IP>:4200/login'
agent-browser --session owh-setup snapshot -i
```

4.1절에 따라 시드 계정으로 로그인·화면·로그아웃을 확인하고 `agent-browser --session owh-setup close`로 세션을 종료한다.
**PC 또는 같은 외부 접속 경로의 브라우저에서도** 로그인 화면을 열고 `.auth_info`의 시드 계정으로 실제 로그인해 앱 화면까지 확인한다.
서버에서 자기 IP로 실행한 검사만으로 PC의 접속 성공을 단정하지 않는다. PC 조작 권한이 없으면 사용자에게 이 마지막 확인만 요청하고, 그동안 GitLab·CI 등 나머지 셋업을 계속한다.
GitLab의 별도 HTTPS 접속·인증서 설정은 2.2.1절을 따른다.

도메인·DNS 연결은 이번 셋업의 선행 조건이 아니다. 필요한 Web·GitLab·SSH 포트만 허용한다.
Bento 등 별도 주소를 쓰는 기능은 사용 시 해당 기능 문서의 접속 설정을 추가한다.
기능별 사용자 수용 검사는 [사용자 수용 검사](docs/product/core-platform-user-acceptance.md)를 따른다.

## 6. 실제 기능 개발용 서비스 연결

사용할 기능의 설정을 준비한 뒤 최소 실행을 종료하고 전체 개발 경로로 전환한다.
`.env.example`에는 추가 서비스와 모델 준비를 전제로 한 설정도 있으므로
복사만으로 모든 기능이 준비된다고 가정하지 않는다.

| 확인 대상 | 준비할 내용과 소유 문서 |
| --- | --- |
| PostgreSQL·Redis·파일 저장소·검색 | 네이티브 DB·Redis 연결은 유지하고 필요한 저장소·검색만 추가한다. 개발 DB, 큐, 버킷, 색인 연결이 실제 실행 대상과 일치하는지 확인한다. Docker 서비스 정의는 [개발 Compose](ops/compose/open-work-hub-dev.infra.yml), 앱 연결 설정은 [개발 환경 설정](scripts/dev-env.sh)을 따른다. |
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

네이티브 PostgreSQL·Redis를 유지하는 경우 추가 서비스만 해당 소유 문서에 따라 준비한다.
`pnpm dev:infra:up`은 Redis 등을 포함한 전체 Docker 인프라를 준비하므로 네이티브 구성에서 그대로 실행하지 않는다.
전체 인프라를 Docker로 구성하기로 선택한 경우에만 다음을 실행한다.

```bash
pnpm dev:infra:up
```

필요한 서비스와 설정이 준비되면 최소 실행 터미널에서 `Ctrl+C`를 누른 뒤 다음을 실행한다.

```bash
./dev.sh --with-worker --no-infra
```

네이티브 DB·Redis는 4절의 연결 검사로, Docker 서비스는 `pnpm infra:dev:status`로 확인한다.
별도 터미널에서 Worker를 포함한 앱 상태를 확인한다.

```bash
./dev.sh --with-worker --status
pnpm dev:login-smoke
curl --fail --silent --output /dev/null http://127.0.0.1:8001/readyz
```

기능별 준비 실패는 해당 설정을 해결하고 재검사한다. 설치를 통과시키려고 필수 검사나
AI 보호 정책을 끄지 않는다. 추가 키·서버가 필요한 기능은 미설정 상태로 명시한다.
별도의 사용자 요청 없이 준비 확인만을 위해 유료 추론을 실행하지 않는다.

## 7. 실행 종료·재시작과 완료 확인

`dev.sh`는 전경 실행이다. `Ctrl+C` 또는 터미널 종료 시 앱 프로세스가 멈추며 네이티브 DB·Redis와 Docker 인프라는 남는다.
네이티브 최소 실행은 `./dev.sh --minimal-infra --no-infra`, Docker 최소 실행은 `pnpm dev:minimal`,
전체 실행은 6절의 명령으로 다시 시작한다.
다른 터미널에서 중지할 때는 실행 대상에 맞춰 `./dev.sh --stop` 또는
`./dev.sh --with-worker --stop`을 사용한다. 호스트 감독 서비스로 실행 중이면
[지속 실행 계약](docs/domains/release/README.md#persistent-development-runtime)에 따라 그 감독 서비스를 사용한다.
네이티브 DB·Redis를 멈춰야 한다면 대상이 이 프로젝트 전용인지 확인한 뒤 해당 systemd unit만 중지한다.
공유 서비스는 임의로 중지하지 않는다. Docker 최소 인프라만 멈출 때는 `pnpm dev:infra:minimal:down`을 사용한다.
데이터 디렉터리나 볼륨을 삭제하지 않는다.

네이티브 서비스는 설치 시 확인한 unit 이름으로 관리한다. PostgreSQL은 전체 클러스터를 함께 조작하는
상위 unit 대신 개발 대상 인스턴스를 지정한다.

```bash
sudo systemctl stop '<개발-PostgreSQL-unit>' '<개발-Redis-unit>'
sudo systemctl start '<개발-PostgreSQL-unit>' '<개발-Redis-unit>'
# DB·Redis 연결을 다시 확인한 뒤 앱 실행
./dev.sh --minimal-infra --no-infra
```

GitLab Linux 패키지는 `sudo gitlab-ctl stop`, `sudo gitlab-ctl start`, `sudo gitlab-ctl restart`로 관리한다.
Runner는 `sudo systemctl stop gitlab-runner`, `sudo systemctl start gitlab-runner`로 관리한다.
앱 종료가 이 서비스들을 멈추지는 않는다. 재부팅 자동 시작은 해당 systemd unit의 enabled 상태로 확인하고,
셋업 인계 시 개발 앱은 SSH·에이전트 세션이 끝나도 실행 중이어야 한다.
위 지속 실행 계약에 따라 systemd 등 호스트 감독 서비스로 같은 체크아웃의 최소 실행 명령을 관리하고, 자동 시작·재시작과 로그를 준비한다.
호스트별 서비스 파일은 저장소 밖에서 관리하고 실제 서비스 이름과 중지·재시작 명령을 인계한다.

**조직 최초 도입은 아래 조건을 모두 확인한 뒤 완료로 보고한다.**

- 개발 Web의 `0.0.0.0` 수신과 PC에서 서버 IP로 접속 가능한 상태, 로그인 화면 표시·시드 계정 로그인·앱 화면 접근.
- 세션 종료와 무관한 개발 앱 실행, PostgreSQL·Redis 인증 연결과 API readiness.
- IP 기반 GitLab 로그인, 관리자 설정·`glab` 인증, 비공개 프로젝트와 `origin` 연결, `dev`·`main` 등록·보호와 개발·운영 체크아웃 분리.
- Runner 등록·온라인 상태와 필요한 이미지·CI 변수·테스트 DB 준비, 검증용 `dev` 대상 MR의 최신 커밋에 대한 실제 파이프라인 성공.
- `.auth_info`의 최신 개발·GitLab·DB 로그인 정보, 소유자 전용 권한과 Git 제외·미추적 상태.

GitLab 패키지 다운로드·lint·최소 환경 실행은 중간 단계다. 실패한 필수 항목은 원인을 해결하고 재검사한다.
필수 인증이나 외부 네트워크 권한처럼 사용자만 처리할 수 있는 항목이 남으면 정확한 미완료 항목과 필요한 조치만 요청하며, 독립적으로 가능한 설치 작업은 계속한다.
운영 배포와 `dev → main` 릴리스는 이 개발 셋업 완료 기준에 포함하지 않는다.

설치 완료 시 사용자에게 다음을 전달한다.

- 선택한 최소/전체 실행 구성, 작업 경로와 브라우저 접속 방법.
- 최초 도입/기존 조직 참여 경로, 최초 기준 커밋과 원격·브랜치 연결 결과. GitLab 코드 등록과 CI 준비 상태는 구분한다.
- 실제 실행한 명령과 로그인·브라우저·준비 상태 검사 결과. 미실행 검사는 구분한다.
- PC에서 사용할 개발 로그인 URL과 GitLab URL, 시드 계정 로그인 결과, 검증 MR·파이프라인 링크·최신 커밋·성공한 job.
- 요청된 업무 기능의 문서 저장·다시 열기, 파일 업로드·다운로드 등 실제 확인 결과.
- 작은 화면 수정이 개발 서버에 반영되는지 확인한 결과와 변경한 파일. 불필요한 확인용 수정은 남기지 않는다.
- 추가 자격증명·서비스가 필요한 기능과 중지·재시작 방법.
- [로그인 정보 파일](#11-로그인-정보-파일-관리)의 절대 경로, 기록한 서비스와 미설정 항목, 소유자 전용 권한·Git 제외·미추적 상태 확인 결과. 비밀번호·토큰은 전달 메시지에 포함하지 않는다.

설치 관련 코드나 설정을 바꿀 때는 [문서 유지 지침](AGENTS.md#documentation-and-skills)에 따라
이 가이드의 영향받는 절차와 연결된 소유 문서를 같은 변경에서 갱신한다.
이 문서에는 다른 설치에서도 재사용할 절차·전제 조건·복구 방법을 남긴다.
특정 서버의 로그인 정보는 `.auth_info`에서 관리하고, 비밀값을 제외한 접속 안내·실행 시각·검사 결과만 설치 결과로 전달한다.

## 8. 내부 관리 시작 후 원본 업데이트

일상적인 코드 공유와 MR은 내부 GitLab `origin`에서 진행한다.
`upstream` 등록만으로 원본 변경이 자동 반영되지는 않는다. 원본 업데이트를 검토할 때는
내부 저장소와 원본의 최신 브랜치 정보를 가져와 아직 통합되지 않은 커밋을 확인한다.

```bash
git fetch origin
git fetch --no-tags upstream
git log --oneline origin/dev..upstream/main
```

이 명령들은 작업 중인 브랜치에 원본 변경을 병합하지 않는다.
반영할 업데이트는 내부 `origin/dev`를 기준으로 한 승인된 작업 브랜치에서 통합하고,
충돌 해결과 영향 범위에 맞는 검사를 거쳐 GitLab MR로 `dev`에 반영한다.
설정·의존성·마이그레이션 요구사항도 함께 확인한다. 내부 운영 `main`으로의 승격과 배포는
[릴리스 절차](docs/domains/release/README.md)를 따른다.

`origin`·`upstream`은 원격 이름이며 접근 권한을 차단하는 장치는 아니다.
`remote.pushDefault=origin`은 기본 push 목적지를 정할 뿐 명시적인 다른 원격 push를 막지는 않는다.
일상적인 내부 개발에서는 원본을 읽기용으로 사용하고 내부 사이트 변경사항은 GitLab에서 관리한다.
원본 프로젝트 개선을 위한 GitHub PR 생성·병합은 명시적으로 요청받은 범위에서
[저장소 정책](AGENTS.md#git-and-delivery)에 따라 진행한다.
원격 관리 방식은 [Git 공식 설명](https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes)과
[GitHub의 upstream 설정 안내](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/configuring-a-remote-repository-for-a-fork)를 참고한다.
