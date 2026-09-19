# Codex Console

본인의 ChatGPT 구독으로 로그인한 Codex를 사용하는 독립 개발 작업실이다.
요구사항 → 계획 확인 → 구현 → 실행 결과·diff 검토를 브라우저에서 진행한다.
소스는 같은 저장소에서 관리하며, OWH 개인 앱에서 새 탭으로 연다. 콘솔의 실행 프로세스·
로그인·업무 DB는 OWH와 분리되어 있다.

## 실행 경계

- 소유자 한 명, 설정한 Git 개발 체크아웃 하나를 대상으로 한다. 공개 가입이나 팀 공유는 없다.
- 공식 `codex app-server` **0.154.0**의 stdio 프로토콜을 사용한다. Codex가 구독 인증,
  토큰 갱신, 원본 대화와 도구 실행을 관리한다. 클라이언트는 인증 파일을 읽거나 복사하지 않는다.
- 이 도구는 개인 코딩 에이전트 클라이언트다. OWH 제품 앱의 생성형 호출, 공용 AI 공급자,
  사용자·회사 권한을 대신하지 않는다. 제품 AI 기능에는 기존 등록 workload 계약을 적용한다.
- 현재 서버의 Codex 사용자와 인증 저장소를 사용한다. 웹 비밀번호와 ChatGPT 로그인은 별개다.
  웹 로그아웃·비밀번호 변경은 웹 세션만 폐기한다.
- 공식 프로토콜의 실험적 계획·질문 기능을 사용하므로 버전을 고정한다. 다른 버전이면 실행을
  차단한다. 업그레이드 때 스키마 재생성, 계약 테스트, 실제 계정 smoke를 함께 수행한다.
- 개인 클라이언트가 필요한 HTTP 인증·문서 버전·실행 승인과 공식 RPC 사이만 변환한다.
  터미널 화면 파싱, 비공식 ChatGPT 엔드포인트, API 과금 fallback, 별도 OAuth 구현은 없다.

공식 근거: [App server](https://developers.openai.com/codex/app-server),
[Authentication](https://developers.openai.com/codex/auth).

### 개인 CLI 클라이언트와 제품 AI의 연결 경계

OWH API의 콘솔 연결 기능은 허용된 소유자에게 브라우저 launch URL만 반환한다. 제품 API나
worker가 콘솔에 생성 요청을 위임하는 경로는 없다. 콘솔은 별도 로그인·설치·DB를 사용하는
공식 [App Server 클라이언트](https://learn.chatgpt.com/docs/app-server)이며 소유자가 직접
입력한 개발 작업을 기존 ChatGPT 구독 세션에 전달한다. 제품 도메인 서비스의 workload와
공통 실행 계약은 [ADR 0005](../../../adr/0005-registered-llm-workload.md)를 따른다.

콘솔은 모델이나 공급자를 선택하지 않는다. `thread/start`·`thread/resume`에서 Codex가
결정한 모델을 0.154.0 공식 스키마의 필수 `collaborationMode.settings.model` 필드에
그대로 전달한다. API key 인증과 다른 공급자는 거부하며 API 과금 경로로 전환하지 않는다.
해당 경계는 API key 거부, 요청의 임의 실행 설정 거부, native 모델 상속 테스트로 검증한다.

## 설치

사전 준비는 [INSTALL.md](../../../INSTALL.md)를 따른다. Node·pnpm과 Python·uv 버전은
저장소의 package.json 및 각 앱의 pyproject.toml/lock을 사용한다. PostgreSQL 18과
현재 사용자로 `codex login status`가 성공하는 Codex 0.154.0이 필요하다.

1. PostgreSQL에 **전용 역할과 전용 DB** `codex_console`을 준비한다. OWH 업무 DB와 그
   migration을 재사용하지 않는다. DB 관리자는 전용 DB에만 소유권을 부여한다.
   호스트 PostgreSQL의 초기 생성 예는 아래와 같다. 기존 역할·DB가 있으면 재생성하지 말고
   소유권·접속 정보를 확인한다. PostgreSQL이 여러 인스턴스이면 대상 포트도 명시한다.

   ```bash
   sudo -u postgres createuser --pwprompt codex_console
   sudo -u postgres createdb --owner=codex_console codex_console
   sudo -u postgres psql -d postgres -c 'REVOKE ALL ON DATABASE codex_console FROM PUBLIC;'
   ```

2. `apps/codex-console-api/.env.example`을 같은 디렉터리의 무시되는 `.env`로 복사하고
   소유자만 읽을 수 있게 한다. 서버 편집기에서 DB 접속 정보, HTTPS origin, 실제 `dev` 경로,
   Codex 실행 파일 경로를 설정한다. 비밀값을 명령 인자나 공유 문서에 넣지 않는다.
3. 저장소 루트에서 아래 명령을 실행한다.

```bash
pnpm install --frozen-lockfile
uv sync --frozen --directory apps/codex-console-api --group dev
pnpm --dir apps/codex-console-web build
cd apps/codex-console-api
uv run --frozen codex-console migrate
uv run --frozen codex-console set-password
uv run --frozen codex-console serve
```

`set-password`는 보호된 터미널 입력으로 비밀번호를 받으며 기존 웹 세션을 폐기한다.
초기 계정도 이 명령으로 만든다. 웹 서버는 기본 `127.0.0.1:19365`에만 수신한다.
전용 HTTPS 주소는 `ops/codex-console/nginx.conf.example`을 참고해 기존 TLS 프록시에 연결한다.
프록시가 원래 Host를 전달하고 SSE 응답을 버퍼링하지 않아야 한다.

로컬 UI 개발은 origin을 `http://127.0.0.1:19366`으로 설정하고 API와 별도로
`pnpm --dir apps/codex-console-web dev`를 실행한다. HTTP origin은 loopback만 허용한다.

## 개인 앱과 HTTPS 접속 연결

OWH 루트 `.env`의 `OPEN_WORK_HUB_CODEX_CONSOLE_LAUNCH_URL`은 브라우저가 열 주소다.
빈 값은 미설치 상태이며 앱을 숨긴다. HTTPS 절대 URL 또는 `/codex-console/` 같은 같은 origin
경로를 사용한다. 로컬 단독 개발에는 loopback HTTP URL도 허용한다. URL에 사용자 정보나
토큰을 넣지 않는다. 설정 변경 후 **개발** API·Web 서비스를 해당 호스트의 감독 서비스로
재시작한다. 운영 OWH에 적용하는 작업은 별도 릴리스·배포 절차를 따른다.

개발 Web 재시작과 무관하게 접속하려면 **전용 HTTPS 도메인**을 사용하고 앞단 프록시를
콘솔에 직접 연결한다. DNS 등록뿐 아니라 프록시의 upstream 주소·포트도 준비해야 한다.

| 설정 위치 | 키 | 값 |
| --- | --- | --- |
| OWH 루트 `.env` | `OPEN_WORK_HUB_CODEX_CONSOLE_LAUNCH_URL` | `https://codex.example.com/` |
| 콘솔 `.env` | `OPEN_WORK_HUB_CODEX_CONSOLE_ORIGIN` | `https://codex.example.com` |
| 콘솔 `.env` | `OPEN_WORK_HUB_CODEX_CONSOLE_BASE_PATH` | 빈 값 |

실제 도메인으로 바꾸고 `브라우저 → HTTPS 프록시 → 콘솔(19365)`로 연결한다. 같은 호스트에서
TLS를 종료한다면 `ops/codex-console/nginx.conf.example`을 사용한다. 콘솔 API는 계속
`127.0.0.1:19365`에서 수신한다. 다른 호스트의 TLS 프록시는 아래의 전용 연결 지점을 사용한다.

기존 HTTPS 개발 사이트 아래의 경로를 사용하는 대안:

| 설정 위치 | 키 | 값 |
| --- | --- | --- |
| OWH 루트 `.env` | `OPEN_WORK_HUB_CODEX_CONSOLE_LAUNCH_URL` | `/codex-console/` |
| 콘솔 `.env` | `OPEN_WORK_HUB_CODEX_CONSOLE_ORIGIN` | 실제 개발 사이트의 HTTPS origin |
| 콘솔 `.env` | `OPEN_WORK_HUB_CODEX_CONSOLE_BASE_PATH` | `/codex-console` |

OWH Vite 개발·preview 서버에는 `/codex-console` → `127.0.0.1:19365` 프록시가 등록되어 있다.
앞단 HTTPS 프록시는 이 경로를 기존 Web으로 전달한다. 별도 프록시에서 콘솔에 직접
연결하는 경우에는 경로를 제거하지 않는 `ops/codex-console/nginx-path.conf.example`을 참고한다.
쿠키는 콘솔 경로에 한정되고 API·정적 파일·SSE도 같은 prefix로 동작한다.
Vite를 통하는 구성은 개발 Web이 멈추면 콘솔 화면 연결도 중단된다. 콘솔 프로세스의 독립성과
브라우저 접속 경로의 독립성은 별도로 확인한다.

DNS 없이 서버 IP로 구성할 때는 IP SAN 인증서와 PC의 CA 신뢰 등록을
[설치 운영 확인](../../domains/release/installation-operations.md#https-trust)에 따라 준비한다.
`https://<서버-IP>:<HTTPS-포트>/`를 launch URL로 사용하며 loopback API 포트를 공개하지 않는다.

이미 사용 중인 주소를 바꿀 때는 실행 중인 콘솔 작업을 먼저 완료·중단한다. 전용 프록시를
준비한 뒤 콘솔 origin·base path를 함께 변경하고 콘솔 서비스를 재시작한다. 새 주소에서
로그인·API·SSE·첨부 업로드를 확인한 후 OWH launch URL을 반영하고 개발 서비스를 재시작한다.
`.auth_info`의 콘솔 URL도 갱신한다. 도메인이 바뀌면 기존 웹 쿠키가 전달되지 않으므로 같은
작업실 비밀번호로 다시 로그인한다. 작업·첨부·ChatGPT 인증은 그대로 유지되며 UI 재빌드나
DB migration은 필요 없다.

OWH 플랫폼 관리자로 로그인하여 **관리자 설정 → 앱 사용/접근 설정**에서 `Codex 콘솔`을 켠다.
기존 설치에 새 앱을 등록하면 기본 비활성·선택 대상 상태이며 기존 권한을 자동 확대하지 않는다.
등록 계약은 `platform_admin`을 요구한다. 개인 앱의 링크가 표시되더라도 실제 코딩 작업은
콘솔의 별도 비밀번호 인증으로 보호된다. 이 링크는 OWH 인증 토큰이나 Codex 자격증명을 전달하지 않는다.

설치 완료 검사는 다음을 모두 포함한다.

1. 콘솔 서비스가 실행 중이고 `/codex-console/healthz` 또는 전용 호스트의 `/healthz`가 성공한다.
2. OWH **개인 앱 → Codex 콘솔** 클릭 시 새 탭에 로그인 화면이 표시되고 기존 탭이 유지된다.
3. 작업실 비밀번호로 로그인한 뒤 **구독 연결됨**이 표시된다. 미연결이면 공식 ChatGPT 로그인을 수행한다.
4. 새로고침 후 화면 복원, 로그아웃 후 API 접근 차단, 콘솔 URL 아래의 API·SSE 응답을 확인한다.
5. [.auth_info 관리](../../../INSTALL.md#11-로그인-정보-파일-관리)에 따라 주소·비밀번호를 서버에
   기록한다. 비밀번호·DB 비밀값은 채팅이나 도구 출력으로 전달하지 않는다.
6. 파일 두 개를 보관한 뒤 하나만 선택해 메시지를 전송한다. 선택한 파일의 뱃지와 전송 후
   선택 해제, 새로고침 후 파일 목록·첨부 기록 복원, 128 KiB 초과 파일 업로드를 확인한다.

### TLS 프록시가 다른 호스트에 있을 때

`ops/codex-console/nginx-upstream.conf.example`은 서버의 **지정한 사설 IP:19365**만 수신하는
선택적 Nginx 연결 지점이다. 실제 콘솔은 loopback 수신을 유지하고, Nginx는 설정한 도메인과
앞단 프록시의 실제 소스 IP만 허용한다. 템플릿의 주소·호스트를 설치 환경에 맞게 바꾼다.
이 구간은 신뢰하는 사설망에서만 사용하며 신뢰할 수 없는 네트워크에서는 호스트 간 TLS나
인증된 터널을 구성한다. 외부 포트 전달로 이 HTTP 포트를 공개하지 않는다.

Docker가 준비된 Linux 호스트에서는 OWH Compose와 별개로 실행할 수 있다. 다음 명령 전
설정 파일을 설치하고 템플릿의 예시 IP·도메인을 실제 값으로 바꾼다. 기존 파일을 덮어쓰지 않는다.

```bash
install -m 644 ops/codex-console/nginx-upstream.conf.example "$HOME/.config/owh-codex-console/upstream.conf"
# upstream.conf의 수신 IP, 허용 프록시 IP, 도메인을 서버 편집기에서 설정한다.
docker run --rm --network host --user 101:101 --read-only --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m,uid=101,gid=101 \
  --mount "type=bind,src=$HOME/.config/owh-codex-console/upstream.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --entrypoint nginx nginx:1.27-alpine -t
docker run -d --name codex-console-upstream --restart unless-stopped \
  --network host --user 101:101 --read-only --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m,uid=101,gid=101 \
  --mount "type=bind,src=$HOME/.config/owh-codex-console/upstream.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --entrypoint nginx nginx:1.27-alpine -g 'daemon off;'
```

앞단 HTTPS 프록시의 대상은 이 서버의 사설 IP:19365이며 원래 Host를 전달해야 한다.
앞단에도 최소 50 MiB 업로드·120초 요청 시간·SSE 버퍼링 해제와 충분한 읽기 시간을 적용한다.
HTTPS `/healthz`와 로그인, 첨부 업로드를 확인한다. 허용하지 않은 소스나 Host로는 접근되지
않아야 한다. 설정 변경 후 `docker exec codex-console-upstream nginx -t`로 검사하고
`docker exec codex-console-upstream nginx -s reload`로 반영한다. 중지·재시작은
`docker stop codex-console-upstream`, `docker restart codex-console-upstream`을 사용한다.

이 연결 지점과 콘솔은 OWH Web·API 재시작에 종속되지 않는다. Docker로 실행하면 Docker
재시작에는 영향을 받는다. 콘솔 전용 DB를 OWH와 같은 PostgreSQL 서버에 만들었다면 그 DB
서버의 재시작도 영향을 준다. 전용 DB는 PostgreSQL 인스턴스 자체의 분리를 의미하지 않는다.

## 파일 보관과 메시지별 첨부

- 오른쪽 **파일** 탭에서 모든 형식의 원본을 업로드·다운로드·삭제한다. 파일 보관만으로
  Codex에 자료가 전달되지는 않는다. 확장자 없는 파일·바이너리도 보관할 수 있다.
- 입력창의 **파일 첨부**에서 기존 파일을 선택하거나 새 파일을 올린다. 입력창에 파일을
  끌어 놓아도 된다. 입력창에서 올린 파일은 이번 메시지의 첨부 뱃지로 선택되며, 파일 영역에서
  보관만 한 파일은 선택되지 않는다. 여러 파일과 파일만 있는 메시지를 지원한다.
- 선택한 파일만 새 메시지·보충 지시·계획 생성에 전달한다. 구현 승인 창에도 이번에 전달할
  파일을 표시한다. 전송 성공 시 선택이 해제되고 실패 시 입력과 선택을 유지한다.
- 과거 메시지에는 당시 첨부한 파일의 다운로드 뱃지가 남는다. 선택 해제는 새 요청에 다시
  첨부하지 않는 의미이며 이미 Codex가 읽은 내용은 대화에 남을 수 있다. 실행 중이거나 상태가
  불확실한 작업은 파일을 삭제할 수 없다. 삭제 후에는 기존 뱃지에 **삭제됨**을 표시한다.
- Codex가 서버의 기존 도구로 원본을 직접 읽는다. 콘솔은 파일 형식별 변환·OCR·자동 실행·
  압축 해제를 하지 않는다. 실제 읽기 가능 여부는 파일 형식과 서버 도구에 따라 Codex가 설명한다.

원본은 콘솔 전용 PostgreSQL `console_attachments`에, 메시지별 참조는
`console_message_attachments`에 저장한다. 선택해 전송한 원본의 읽기용 사본만 Git 저장소
밖에 만들며 파일 권한은 `0400`, 디렉터리는 `0700`이다. 작업 디렉터리 전환과 서버 재시작 후
DB에서 사본을 복원한다. 원본을 삭제하면 DB 바이너리와 읽기용 사본을 제거하고 기록용 이름·
크기·참조 정보만 유지한다. 별도 파일 저장 서비스나 OpenAI API 키는 필요하지 않다.

| 콘솔 설정 | 기본값 | 용도 |
| --- | --- | --- |
| `OPEN_WORK_HUB_CODEX_CONSOLE_ATTACHMENT_CACHE` | `~/.local/share/owh-codex-console/attachments` | 소유자 전용 읽기 사본. Git 저장소·릴리스 디렉터리 밖의 고정 경로를 사용한다. |
| `OPEN_WORK_HUB_CODEX_CONSOLE_ATTACHMENT_MAX_BYTES` | `52428800` | 파일당 50 MiB. 최대 설정값은 100 MiB. |
| `OPEN_WORK_HUB_CODEX_CONSOLE_ATTACHMENT_TASK_MAX_BYTES` | `524288000` | 작업당 활성 원본 500 MiB. |

작업당 활성 파일은 200개, 메시지당 선택은 20개까지다. 업로드는 원본 바이너리
`PUT /api/tasks/{task_id}/attachments/{attachment_id}`로 전달하고 URL 인코딩한 파일 이름을
`X-File-Name` 헤더에 넣는다. 같은 ID·원본의 재시도는 중복 저장하지 않는다. 읽기·삭제도
콘솔 로그인과 작업별 파일 소속 검사를 거친다. 원본·이름·경로를 로그에 기록하지 않는다.

프록시도 파일당 제한 이상을 허용해야 한다. Nginx 예시는 콘솔 경로에 `client_max_body_size 50m`,
`client_body_timeout 120s`, `proxy_request_buffering off`를 설정한다. 기존 HTTPS → Vite → 콘솔
구성이면 가장 앞의 HTTPS 프록시에도 같은 크기 제한을 확인한다. 용량을 변경할 때 콘솔 설정과
프록시를 함께 맞춘다. 일반 JSON 요청은 128 KiB로 제한한다. 문서 저장은 100,000자,
메시지·보충 지시는 32,000자를 허용하며 해당 경로는 JSON Unicode 이스케이프의 최대
12바이트/자와 나머지 필드 4 KiB를 합친 바이트 제한을 적용한다.

전용 DB 백업에 첨부 원본도 포함되므로 용량·보존 정책을 함께 관리한다. 캐시는 원본 백업이
아니다. 캐시 경로는 원본 Codex 이력의 파일 경로를 유지하도록 업데이트 때 변경하지 않는다.
다른 서버로 복원할 때도 같은 절대 경로를 준비한다. 경로를 바꿨다면 보관된 파일을 다시 선택해
전송한다. 자료 삭제는 기존 Codex 대화나 과거 DB 백업에서 이미 읽힌 내용을 지우지 않는다.

## 서비스로 실행

개발 중인 소스를 서비스가 직접 읽지 않도록 새 릴리스 디렉터리를 만든다.
다음은 사용자의 홈 디렉터리에 설치하는 예다. 이미 존재하는 릴리스는 덮어쓰지 않는다.

```bash
bash scripts/build-codex-console.sh "$HOME/.local/share/owh-codex-console/releases/initial"
mkdir -p "$HOME/.config/owh-codex-console" "$HOME/.config/systemd/user"
install -m 600 apps/codex-console-api/.env.example "$HOME/.config/owh-codex-console/console.env"
ln -s "$HOME/.local/share/owh-codex-console/releases/initial" "$HOME/.local/share/owh-codex-console/current"
install -m 644 ops/codex-console/codex-console.service "$HOME/.config/systemd/user/"
```

`console.env`를 서버 편집기에서 설정한다. `OPEN_WORK_HUB_CODEX_CONSOLE_BINARY`는 현재 구독
로그인 사용자가 실행하는 Codex의 절대 경로로 지정한다. 서비스 설치 계정도 동일하게 유지한다.
서비스 활성화 전에 해당 환경으로 `migrate`, `set-password`를 수행한다. dotenv 형식으로
작성한 환경 파일은 릴리스의 API 디렉터리에 `.env` 심볼릭 링크로 연결하면 CLI에서도 읽는다.

```bash
ln -s "$HOME/.config/owh-codex-console/console.env" "$HOME/.local/share/owh-codex-console/current/apps/codex-console-api/.env"
cd "$HOME/.local/share/owh-codex-console/current/apps/codex-console-api"
.venv/bin/codex-console migrate
.venv/bin/codex-console set-password
systemctl --user daemon-reload
systemctl --user enable --now codex-console
```

user unit의 bus에 연결할 수 없는 셸에서는 설치 계정의 `XDG_RUNTIME_DIR=/run/user/$(id -u)`를
지정하고 사용자 manager가 실행 중인지 확인한다. 다른 사용자나 root의 Codex 인증으로 실행하지 않는다.
로그아웃 후에도 실행해야 하면 관리자가 `loginctl enable-linger <설치계정>`으로 lingering을 설정한다.
사용자 지정 Node·pnpm·uv 설치를 사용한다면 해당 실행 파일 디렉터리를 이 서비스의 `PATH`
drop-in에 명시한다. Codex 바이너리뿐 아니라 코딩 작업에서 사용하는 도구도 서비스 환경에서
해석되어야 한다. 해당 설정은 호스트별 user unit drop-in으로 관리한다.

```bash
systemctl --user is-active codex-console
systemctl --user is-enabled codex-console
systemctl --user restart codex-console
systemctl --user stop codex-console
```


개발 서버의 `./dev.sh`와 이 서비스는 서로 제어하지 않는다. 업데이트는 새 릴리스를 검증한 뒤
실행 중인 작업을 완료·중단하고 전용 DB를 백업한다. 서비스를 중지한 뒤 새 릴리스의
`codex-console migrate`를 실행하고 `current`를 전환해 별도로 재시작한다. 현재 서버는
`console_0003` migration까지 필요하다. 첨부 저장과 문서 생성 실행의 출처를 추가하며 기존
작업·로그인·계획 기록을 보존한다. 이전 서버는
새 schema에서 시작하지 않으므로 롤백에는 변경 전 DB와 이전 릴리스가 함께 필요하다.
서비스 배포·재시작은
설치 운영자의 명시적인 작업이며 소스 빌드가 자동으로 수행하지 않는다.

## 상태와 권한

- 웹 인증은 scrypt 비밀번호 해시, DB 세션, HttpOnly/SameSite 쿠키, 정확한 origin과 CSRF
  검증을 사용한다. 로그인 실패 5회는 5분 제한한다. API는 한 프로세스만 실행한다.
- PostgreSQL advisory lock으로 중복 서버를 차단하고 DB lease로 작업을 직렬화한다.
  작업·계획 버전·승인·요청 중복 방지·화면 projection을 DB에 저장한다. Codex 원본 이력이
  대화의 기준이며 화면 projection을 Codex에 원본 이력으로 되돌려 보내지 않는다.
- 요구사항·계획은 읽기 전용 sandbox와 승인 불허 정책을 사용한다. 구현 버튼은 최신 계획
  버전에 묶인다. 요구사항 변경은 기존 계획 승인을 무효화하며, 이후 다시 생성한 계획은
  내용이 같아도 새 버전으로 저장한다. 문서 편집 중 서버에 새 버전이 생겨도 입력 내용과
  편집 시작 버전을 유지한다. 충돌하면 저장을 막고 최신 버전을 명시적으로 불러오도록
  안내한다. 유지할 편집 내용은 불러오기 전에 복사한다. 미저장 초안은 열린 페이지 안에서
  작업·결과 탭별로 유지하고, 새로고침이나 페이지 종료 시 브라우저 경고를 제공한다.
  다른 브라우저나 다음 로그인에서도 보존하려면 문서를 저장한다.
- 첫 버전은 외부 쓰기 도구를 제공하지 않는다. 사설 app-server에서 Apps·Plugins를 끄고
  각 thread의 공식 설정 override로 MCP 서버를 비활성화한다. 원래 Codex 설정 파일은 바꾸지 않는다.
- 구현은 작업 디렉터리의 workspace-write sandbox를 사용한다. 권한 확대는 건별 명령·파일
  승인 또는 표시된 권한을 현재 턴에만 부여하는 승인으로 처리한다. 포괄적인 세션 승인이나
  임의 RPC 전달 엔드포인트는 제공하지 않는다.
- `dev`에 무관한 변경이 있으면 `origin/dev` 기준의 detached `../worktrees/codex-<task-id>`에서
  구현한다. 원래 변경은 보존된다. 결과는 미커밋 diff로 남기며 임시 worktree도 검토를 위해
  유지한다. 반영·정리는 저장소의 기존 명시적 Git 작업 절차로 수행한다.
- 작업 도중 브라우저를 닫아도 실행은 계속된다. URL의 task ID로 새로고침 후 동일 작업을 연다.
  SSE는 DB 변경 알림이며 재접속 때 저장 상태를 읽는다. 로그아웃된 SSE는 다음 주기에 종료한다.
- 요청 준비와 실제 제출 경계를 DB에 구분해 기록한다. 제출 전 실패한 요청은 같은 요청 ID로
  재시도할 수 있고, 준비 중 서버가 종료되면 실행 잠금을 해제한다. 이미 접수된 요청만 중복
  전송에 성공 응답을 돌려주며 접수 여부가 불확실하면 성공으로 처리하거나 자동 재전송하지 않는다.
- 백엔드·Codex 종료 또는 제출 후 접수 응답 유실은 `uncertain`이다. workspace lease를 유지하고
  승인 요청을 폐기한다. **실행 상태 확인**은 공식 thread를 재개·조회한다. 스레드 생성 전에
  중단된 이전 버전의 작업도 실행되지 않았음을 확인한 뒤 잠금을 해제할 수 있다.
  복구가 성공하면 다음에 사용자가 직접 보내는 요청은 새 요청 ID를 사용한다. 복구 실패나
  단순 화면 갱신으로는 ID를 바꾸지 않으며 불확실한 기존 요청을 자동으로 재전송하지 않는다.
  전송 응답을 잃었지만 실제 실행이 계속되는 경우 **중단**은 공식 스레드에서 현재 실행 ID를
  확인한 뒤 중단을 요청한다. 완료 이벤트나 명시적 복구 전에는 작업 잠금을 유지한다.
  완료 알림을 놓친 요구사항·계획은 공식 이력에서 현재 요청의 완료 문서를 복원한다.
  실행별 문서 출처로 중복을 막고 이후의 사용자 편집은 보존한다. 작업 목록 검색은 서버의
  전체 작업을 대상으로 하므로 최신 200개 밖의 격리 작업도 제목으로 찾을 수 있다.
  구현 도중 중단되었다면 먼저 diff를 확인하고 현재 변경을 해당 작업에 포함하는 데 동의한다.
  복구는 같은 작업 디렉터리와 변경사항을 유지하고 이후 외부 편집은 다시 검사한다.
  변경 지문을 읽을 수 없으면 복구 상태를 유지한다. 이전 CLI 대화는 원래 실행을 종료한 후에만 가져온다.
- 원본 Codex 대화와 DB 작업 기록은 소유자가 유지한다. 자동 삭제는 하지 않는다. 임시 웹 세션은
  만료되고 다음 로그인에서 제거한다. DB 백업·보존은 별도 DB 관리 정책으로 운영한다.
  화면은 최근 항목 2,000개를 표시하며 더 긴 대화에는 생략 안내를 표시한다.
- 서버 로그에 원본 프롬프트·토큰·upstream 오류 본문을 기록하지 않는다. 파일 읽기는 상위
  디렉터리까지 링크를 거부하며, 검사 후 경로 교체도 파일 디스크립터 기반 접근으로 차단한다.
  diff 조회는 비밀 파일,
  경로 이탈·외부 symlink·대형 출력에 경계를 적용한다. 웹 UI는 API 키를 입력받지 않는다.

## 검증과 복구

```bash
pnpm check:codex-console-contract
pnpm --dir apps/codex-console-web test
pnpm --dir apps/codex-console-web typecheck
uv run --frozen --directory apps/codex-console-api --group dev ruff check .
uv run --frozen --directory apps/codex-console-api --group dev pytest -q
pnpm --dir apps/codex-console-web build
pnpm --dir apps/codex-console-web e2e
```

DB/E2E 검사는 `OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN`에 비운영 PostgreSQL 18 접속 정보를
설정한다. 테스트 계정은 임시 `console_test_*` DB를 생성·제거할 권한이 필요하다. 없으면 DB
pytest가 skip되며 전체 검증 통과로 취급하면 안 된다. E2E는 실제 HTTP·DB와 테스트 전용
공식 프로토콜 대역을 사용한다. production 앱에는 mock 실행 모드가 없다.

메시지 첨부의 실제 파일 읽기·미선택 파일 제외·공식 메시지 ID 연결은 아래의 별도 구독 smoke로
확인한다. 임시 DB·저장소를 사용하고 원본 대화는 완료 후 archive한다. 파일 내용·대화 본문을
로그로 출력하지 않는다.

```bash
uv run --frozen --directory apps/codex-console-api --group dev python tests/live_attachment_smoke.py
```

Codex 업그레이드 계약은 설치된 고정 버전으로 검사한다.

```bash
uv run --frozen --directory apps/codex-console-api python scripts/generate_protocol.py --check
```

실제 구독을 사용하는 선택적 smoke는 위 테스트 DB 설정 후 아래 명령으로 실행한다.
임시 Git 저장소에서 요구사항·계획 단계의 읽기 전용 동작과 승인 후 실제 구현·테스트를
확인하며, 종료 시 이 테스트가 만든 Codex 대화만 보관 처리한다. 구독 사용량을 소비한다.

```bash
uv run --frozen --directory apps/codex-console-api python tests/live_smoke.py
```

E2E 대역 통과는 실제 구독 실행
검증을 대신하지 않는다. 로그인 만료는 사용량 창의 **ChatGPT 연결**에서 공식 device-code
로그인을 진행한다. 계정에서 device-code가 허용되지 않으면 서버에서 `codex login`을 완료한다.
인증 파일을 UI로 업로드하거나 내용을 공유하지 않는다.

장애 확인은 `/healthz`, 서비스 상태, UI 오류 코드로 시작한다. DB migration 실패를 `stamp`나
테이블 재생성으로 우회하지 않는다. 버전 불일치는 고정 Codex 바이너리 경로를 복구한다.
사용량 제한에는 API fallback을 두지 않는다. 비밀번호 분실은 서버의 `set-password`로 복구한다.
