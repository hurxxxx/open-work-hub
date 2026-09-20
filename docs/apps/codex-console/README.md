# Codex Console

본인의 ChatGPT 구독으로 로그인한 Codex를 사용하는 독립 개발 작업실이다.
계획과 실행 두 모드로 질문·조사·문서 정리·코딩과 결과 검토를 진행한다.
소스는 같은 저장소에서 관리하며, OWH 개인 앱에서 새 탭으로 연다. 콘솔의 실행 프로세스·
로그인·업무 DB는 OWH와 분리되어 있다.

## 실행 경계

- 소유자 한 명, 설정한 Git 개발 체크아웃 하나를 대상으로 한다. 공개 가입이나 팀 공유는 없다.
- 공식 `codex app-server`의 stdio 프로토콜을 사용한다. 기준 계약은 **0.155.1**이며,
  그 이상의 안정 CLI는 콘솔이 사용하는 요청·응답·알림 RPC 스키마가 기준 계약과 같을 때
  자동으로 허용한다.
  더 오래된 버전·시험판·스키마가 달라진 버전은 실행 전에 차단한다. Codex가 구독 인증,
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

모델 목록은 공식 `model/list`에서 현재 구독 계정이 제공하는 항목을 읽는다. 선택한 모델과
추론 강도를 공식 `turn/start`·`collaborationMode.settings`에 전달한다. 선택을 생략하면
native thread의 모델을 이어받는다. 공급자·인증·fallback 설정은 제공하지 않으며 API key 인증과
다른 공급자는 계속 거부한다. 제품 앱의 모델 라우팅과 연결하지 않는다.

새 메시지의 화면 기본값은 `gpt-5.6-sol`과 `medium`이다. 현재 계정의 `model/list`에 해당
모델이 없으면 공식 기본 모델, 공식 기본 모델도 없으면 목록의 첫 모델을 사용한다. 선택된
모델이 `medium`을 지원하지 않으면 그 모델의 권장 추론 강도를 사용한다. 화면에는 실제로
전송할 모델과 추론 강도를 표시하며 별도의 모호한 "기본값" 선택지는 제공하지 않는다.

추론 강도는 콘솔의 허용 목록과 해당 모델의 `supportedReasoningEfforts`가 겹치는 값만
표시·허용한다. 기본 목록은 `none, minimal, low, medium, high, xhigh`이므로 `max`, `ultra`와
새로 추가된 이름은 자동으로 노출되지 않는다. Codex 0.155.1의 강도는 문자열이며 공식
`model/list`에는 수치 순위나 정렬 보장이 없으므로 응답 순서로 상한을 추정하지 않는다.
허용 목록은 낮은 강도부터 높은 강도 순서의 JSON 배열로 설정한다.

| 설정 | 기본값 | 용도 |
| --- | --- | --- |
| `OPEN_WORK_HUB_CODEX_CONSOLE_ALLOWED_REASONING_EFFORTS` | `["none","minimal","low","medium","high","xhigh"]` | 콘솔에서 선택·실행할 수 있는 강도. 빈 목록·빈 이름은 거부한다. |

강도를 생략하면 같은 모델의 native thread 강도가 허용 범위에 있을 때 유지하고, 그렇지
않으면 모델 권장 기본값을 사용한다. 권장값도 허용되지 않으면 해당 모델이 지원하는 허용
목록의 마지막 값을 사용한다. 허용되는 강도가 없는 모델은 목록에서 제외하고 새 턴 실행도
거부한다. 이전 작업의 숨겨진 선택값은 다음 실행 설정에서 기본값으로 되돌리며, API에서
명시적으로 요청하면 거부한다. 이미 실행 중인 턴과 과거 실행 기록은 바꾸지 않는다.
설정 변경은 콘솔 서비스 재시작 후 적용된다.

## 실행 설정과 중단 후 계속하기

새 작업은 **계획** 모드로 시작한다. 공식 native plan 모드와 읽기 전용 권한으로 질문,
조사와 계획 수정을 수행한다. **실행**은 native default 모드로 사용자의 직접 요청을 수행한다.
저장된 계획 없이도 실행할 수 있으며, 문서의 **이 계획으로 실행**은 확인한 계획 버전을 함께
전달한다. 모델·추론 강도·권한은 다음 메시지에 적용한다. 실행 중인 턴에는 보충 지시를
보낼 수 있고 설정 변경은 턴이 끝난 뒤 적용한다.
모델과 추론 강도는 입력창 하단의 현재 선택값에서 여는 팝오버로 변경한다. 팝오버는 입력창
위에 겹쳐 표시되어 열고 닫아도 프롬프트 영역의 높이와 하단 조작 위치를 바꾸지 않는다.

질문만으로 문서를 만들지 않는다. 처음 문서 작성을 요청하면 요구사항 또는 계획을 저장하고,
그 뒤 해당 문서와 관련된 확정된 변경을 논의하면 최신 문서를 자동 갱신한다. 검토 중인 대안은
확정 사항으로 기록하지 않는다. 답변에 변경 내용을 안내하고 문서 버전을 보관한다.
공식 `turn/start.outputSchema`로 답변과 선택적 문서 갱신을 한 응답에서 구분하며 추가 LLM
호출이나 키워드 분류를 하지 않는다. 문서 버전이 충돌하거나 응답 형식이 잘못되면 저장하지
않고 오류를 표시한다. 두 문서는 모든 버전을 먼저 검증한 뒤 요구사항→계획 순서로 저장하므로
응답 배열 순서와 관계없이 같은 변경의 계획을 실행할 수 있다. 문서별 최대 100,000자를 포함한
최종 응답은 RPC의 4 MiB 상한 안에서 보존하며 모드 전환 후 이력 복원에도 적용한다.
일반 명령 출력은 마지막 100,000자만 보관한다.
계획 모드의 문서는 콘솔 DB에만 저장하며 저장소 파일은 수정하지 않는다.

실행 권한의 기본값은 **필요할 때 승인 요청**이다. **YOLO · 전체 권한**을 선택하면 공식
`approvalPolicy: never`, `sandboxPolicy: dangerFullAccess`로 실행한다. YOLO는 서버 계정의
파일·네트워크 접근에 대한 샌드박스 제한과 개별 승인 요청을 없앤다. 계획 모드는 YOLO 선택과
관계없이 읽기 전용이다. 마지막 모델·강도·실효 권한은 DB에 저장된다.

**현재 실행 상태**는 모드·모델·권한, 현재 명령과 Codex가 보고한 단계별 진행 상황을 표시한다.
페이지 이동·탭 종료·웹 로그아웃 후에도 서버 작업은 계속된다. **중단**으로 실행을 멈출 수 있다.
서버·Codex 프로세스 자체의 종료는 별도다. SSE 재연결과 함께 10초마다 상태를 확인하고
페이지 복귀 때 즉시 갱신한다.

중단된 작업은 입력창에 이어서 수행할 내용을 요청한다. 연결 유실로 접수 여부가 불확실하면
새 메시지를 받기 전에 공식 thread 이력을 조회한다. 기존 턴이 실행 중이면 새 메시지를 보충
지시로 전달하고, 완료됐다면 같은 thread에서 새 턴을 시작한다. 실행 중인 턴은 저장된 turn ID나
원래 메시지의 clientUserMessageId와 연결된 공식 userMessage.clientId로 접수를 검증한 경우에만
재개하며 승인 요청도 이어서 처리한다. 실행 중인 턴과 요청의 모드·권한이나 명시한 모델·추론 강도가 다르면 전송을
거부하므로 턴을 완료·중단한 뒤 새 설정으로 요청한다. 생략한 모델·추론 강도는 기존 값을 유지한다. 조회 중 작업·요청 상태가 바뀌면 오래된 결과를 반영하지
않는다. 불확실했던 원래 요청을 자동
재전송하지 않는다. 동일 요청 ID의 재시도는 확인된 접수 결과를 반환하며 중복 실행·보충 지시를
만들지 않는다. 새 계획 버전으로 실행하는 요청은 기존 턴이 끝나거나 중단된 뒤 제출한다.
**실행 상태 확인**으로 상태만 확인할 수도 있다. 전송 전 실패한 본문은
**전송하지 못한 요청 불러오기**로 복원한다. 필요한 첨부는 다시 선택한다.

Codex 0.155.1은 `thread/resume`에 이전 sandbox와 cwd를 반환할 수 있다. 콘솔이 이전에 부여한
권한만 받아들이고 새 `turn/start`에 현재 경로와 선택 모드의 전체 권한을 지정한다.
권한 전환의 접수가 불확실하면 직전 확인된 sandbox도 DB에 보존해 기존 턴의 복구를 허용한다. 알 수
없거나 기록보다 넓은 권한은 차단한다. 소유한 워크트리가 정리된 경우 native 실행이 끝났음을
확인한 뒤 설정된 작업 폴더로 복귀한다. 폴더만 삭제되어 Git 등록이 남은 경우에는 해당 작업이
소유한 정확한 경로에만 `git worktree remove`를 적용한다. 잠긴 등록·존재하는 경로·다른 등록은
보존하며 force나 전체 prune은 사용하지 않는다. 대화와 첨부·문서는 유지하고 이전 폴더의 변경 지문과
계획 승인은 재사용하지 않는다. 실행 중인 폴더는 해당 턴이 끝나기 전에 삭제하지 않는다.

## 브랜치와 작업 공간

작업 상단에는 실제 브랜치와 변경 파일 수를 간단히 표시한다. **브랜치** 탭에서 작업 경로,
HEAD, 스테이징/미스테이징/새 파일·충돌 수, 추적 브랜치와 앞선/뒤처진 커밋 수,
변경 파일과 diff를 확인한다. 이름 없는 워크트리는 **브랜치 없음 (detached HEAD)**으로 표시한다.
상태는 10초마다, 페이지 복귀와 수동 새로고침 때 조회한다. 원격 비교는 로컬 추적 참조 기준이며
자동 fetch하지 않는다. 변경 파일 수만으로 병합 여부를 판단하지 않는다.

병합 대상 선택이나 병합 요청 자동 완성은 제공하지 않는다. 사용자가 실행 모드에서 원하는
Git 작업을 직접 요청하면 Codex가 해당 저장소 지침에 따라 수행한다. 콘솔 자체에 특정
브랜치·호스팅·MR/PR·배포 순서를 넣지 않는다. 실행 모드 선택만으로 커밋·푸시·병합·배포·삭제를
승인한 것으로 간주하지 않는다.

기본적으로 설정한 깨끗한 체크아웃을 사용한다. 무관한 변경이 있으면 지정한 기준 ref의
커밋에서 detached 워크트리를 만든다. 작업마다 이름 있는 브랜치를 만드는 규칙은 해당
저장소 지침과 사용자 요청으로 정한다. 다음 설정은 콘솔 전용 환경 파일의 typed 계약이다.

| 설정 | 기본값 | 용도 |
| --- | --- | --- |
| `OPEN_WORK_HUB_CODEX_CONSOLE_WORKTREE_BASE_REF` | `HEAD` | 격리 작업의 기준 ref. 실제 커밋으로 검증한다. |
| `OPEN_WORK_HUB_CODEX_CONSOLE_WORKTREE_ROOT` | `~/.local/share/owh-codex-console/worktrees` | 설정한 체크아웃 밖의 절대 경로. |
| `OPEN_WORK_HUB_CODEX_CONSOLE_PROTECTED_WORKSPACES` | `[]` | 접근 금지할 운영 체크아웃의 절대 경로 JSON 배열. |
| `OPEN_WORK_HUB_CODEX_CONSOLE_FORBIDDEN_DATABASE_NAMES` | `[]` | 재사용 금지할 제품 DB 이름 JSON 배열. |

OWH 서버에서는 기준 ref를 `origin/dev`, 워크트리 경로를 체크아웃 루트의 `worktrees`로 설정하고
실제 `prod` 경로와 dev/prod 제품 DB 이름을 금지 목록에 넣는다. 다른 저장소는 그 저장소의
구성에 맞춘다. 전용 DB는 모든 설치에 필요하며 migration은 기존 비콘솔 테이블이 있으면 거부한다.

## 설치

사전 준비는 [INSTALL.md](../../../INSTALL.md)를 따른다. Node·pnpm과 Python·uv 버전은
저장소의 package.json 및 각 앱의 pyproject.toml/lock을 사용한다. PostgreSQL 18과
현재 사용자로 `codex login status`가 성공하는 Codex 0.155.1 이상의 안정 버전이 필요하다.
서비스는 Codex 프로세스를 연결할 때 설치된 CLI가 기준 RPC 계약과 호환되는지 검사한다.

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
   소유자만 읽을 수 있게 한다. 서버 편집기에서 DB 접속 정보, HTTPS origin, 실제 Git 작업 경로,
   Codex 실행 파일 경로와 위 작업 공간 설정·운영 경로/제품 DB 금지 목록을 설정한다. 비밀값을 명령 인자나 공유 문서에 넣지 않는다.
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
6. 계획 기본값, 질문 후 문서 미생성, 명시적 문서 생성과 이후 확정 변경의 자동 갱신을 확인한다.
   실행 모드의 직접 요청과 저장된 계획 실행, 모델·승인/YOLO 선택, 브랜치 탭을 확인한다.
   검증용 작업 중 탭을 닫았다가 같은 URL로 돌아와 진행·결과가 복원되는지 확인한다.
   중단된 작업은 새 프롬프트로 이어서 진행하고 기존 파일이 보존되는지 확인한다.
7. 파일 두 개를 보관한 뒤 하나만 선택해 메시지를 전송한다. 선택한 파일의 뱃지와 전송 후
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
메시지·보충 지시·구현 지시는 32,000자를 허용하며 해당 경로는 JSON Unicode 이스케이프의 최대
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
`console_0006` migration까지 필요하다. 0004에서 업그레이드할 때 기존 계획 operation에는
`legacy_plan` 형식 표식을 남겨 완료 알림을 놓친 Markdown 문서만 원래 종류로 복구한다.
이미 초기 0005를 적용한 중간 설치본은 이 표식이 없으므로, 교체 전에 보존한 0004 백업의
operation ID·task ID·kind·digest와 일치하는 구형 계획만 운영자가 표식으로 보정한다.
새 JSON 요청이나 형식을 입증할 수 없는 응답은 Markdown으로 추정하지 않는다. 계획 응답의 문서별 실행 출처와 이전 실행 경로,
권한 전환 제출 직전 확인된 sandbox를 저장하며 기존
작업·로그인·계획 기록을 보존한다. 이전 서버는
새 schema에서 시작하지 않으므로 롤백에는 변경 전 DB와 이전 릴리스가 함께 필요하다.
서비스 배포·재시작은
설치 운영자의 명시적인 작업이며 소스 빌드가 자동으로 수행하지 않는다.

### 배포 완료 확인

소스 수정·커밋·푸시·dev/main 동기화와 실행 중인 콘솔 업데이트는 별개의 단계다.
OWH 개발 서버나 운영 앱만 재시작해도 콘솔에는 반영되지 않는다. 사용자가 화면에 반영할
Codex Console 구현을 요청하면 로컬 변경 또는 검증만으로 범위를 제한하지 않은 한 전용 콘솔
릴리스와 공개 검증까지 완료해야 작업 완료로 보고한다. 실제 소스 통합과 서비스 변경 권한은
루트 `AGENTS.md`를 따른다. 배포 승인이 아직 없다면 검증된 릴리스를 구체적으로 준비한 뒤
서비스 교체 전에 한 번만 승인을 요청하고, 승인 후에는 다음 항목을 중단 없이 완료한다.

1. 실행 중인 서비스의 실제 릴리스 경로와 적용할 소스 커밋을 확인한다. 해당 커밋에서 새
   릴리스를 빌드하고 [검증과 복구](#검증과-복구)의 관련 검사를 수행한다.
2. 위 업데이트 절차대로 진행 중인 작업의 종료를 확인하고 전용 DB를 백업한 뒤,
   서비스 중지·migration·`current` 전환·재시작을 수행한다. 기존 인증과 설정을 유지하고
   이전 릴리스와 DB 백업은 복구용으로 보존한다.
3. 서비스가 새 릴리스를 실행하는지와 직접·공개 주소의 `/healthz`를 확인한다. 실제
   로그인 세션에서 변경된 API 응답과 브라우저 동작도 검사한다. 추론 강도 변경은
   `/api/codex/models`와 실제 선택 목록을 모두 확인한다. 공개 경로의 prefix가 있으면
   각 경로에 적용한다. 쿠키·비밀번호·대화 내용은 검사 출력에 남기지 않는다.
4. 배포한 소스 커밋·릴리스 경로·서비스 상태·동작 검사 결과를 구분해 보고한다.
   빌드만 완료했거나 이전 릴리스가 실행 중이면 배포 완료로 간주하지 않는다.

## 상태와 권한

- 웹 인증은 scrypt 비밀번호 해시, DB 세션, HttpOnly/SameSite 쿠키, 정확한 origin과 CSRF
  검증을 사용한다. 로그인 실패 5회는 5분 제한한다. API는 한 프로세스만 실행한다.
- PostgreSQL advisory lock으로 중복 서버를 차단하고 DB lease로 작업을 직렬화한다.
  작업·계획 버전·승인·요청 중복 방지·화면 projection을 DB에 저장한다. Codex 원본 이력이
  대화의 기준이며 화면 projection을 Codex에 원본 이력으로 되돌려 보내지 않는다.
- 계획 모드는 읽기 전용 sandbox와 승인 불허 정책을 사용한다. 저장된 계획의 실행 버튼은 최신 계획
  버전에 묶인다. 요구사항 변경은 기존 계획 승인을 무효화하며, 이후 다시 생성한 계획은
  내용이 같아도 새 버전으로 저장한다. 문서 편집 중 서버에 새 버전이 생겨도 입력 내용과
  편집 시작 버전을 유지한다. 충돌하면 저장을 막고 최신 버전을 명시적으로 불러오도록
  안내한다. 유지할 편집 내용은 불러오기 전에 복사한다. 미저장 초안은 열린 페이지 안에서
  작업·결과 탭별로 유지하고, 새로고침이나 페이지 종료 시 브라우저 경고를 제공한다.
  다른 브라우저나 다음 로그인에서도 보존하려면 문서를 저장한다.
- 첫 버전은 외부 쓰기 도구를 제공하지 않는다. 사설 app-server에서 Apps·Plugins를 끄고
  각 thread의 공식 설정 override로 MCP 서버를 비활성화한다. 원래 Codex 설정 파일은 바꾸지 않는다.
- 기본 실행은 작업 디렉터리의 workspace-write sandbox를 사용한다. YOLO의 명시적 선택은
  [실행 설정](#실행-설정과-중단-후-계속하기)을 따른다. 기본 권한 확대는 건별 명령·파일
  승인 또는 표시된 권한을 현재 턴에만 부여하는 승인으로 처리한다. 스레드 생성·재개·턴 시작에서
  공식 `approvalsReviewer: user`를 명시해 기존 자동 검토 설정을 상속하지 않는다. 포괄적인 세션 승인이나
  임의 RPC 전달 엔드포인트는 제공하지 않는다.
- 보호 경로 설정은 기본 workspace뿐 아니라 기존 작업의 저장된 root와 이전 실행 경로에도
  적용한다. Git 조회·격리 준비·복구·보충 지시·승인 응답 전에 현재 설정으로 검사한다.
  보호된 작업도 중단할 수 있으며 실패·접수 결과 기록과 실행 잠금 해제는 차단하지 않는다.
- 무관한 변경은 [작업 공간 설정](#브랜치와-작업-공간)에 따라 격리한다. 반영·정리는 저장소의
  지침과 사용자가 요청한 범위에 따라 수행한다.
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
  실행 도중 중단되었다면 diff를 확인하고 새 프롬프트로 이어서 수행할 내용을 요청한다.
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

끊김 진단은 `journalctl --user -u codex-console`에서 `Codex transport stopped`의 안전한
사유 코드·예외 종류·프로세스 종료 코드만 확인한다. 원본 이벤트·명령 출력·오류 본문을 로그에
추가하지 않는다. `codex_event_failed`는 DB/event 처리 실패, `codex_output_limit`는 단일
4 MiB 메시지 초과, `codex_event_overflow`는 2,048개 이벤트 큐 초과,
`codex_protocol_error`는 잘못된 JSON/envelope, `codex_disconnected`는 프로세스/연결 종료다.
브라우저의 **실시간 표시 재연결**과 native 프로세스 종료를 구분한다. 명령의 초기 출력이
`null`인 정상 이벤트는 빈 문자열로 누적하며 연결을 종료하지 않는다. 이전 프로세스 세대의
늦은 이벤트는 새 연결의 작업 상태에 반영하지 않는다.


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

Codex 업그레이드 계약은 설치된 안정 CLI가 최소 버전 이상이고 선택된 RPC 스키마와 호환되는지
검사한다. 스키마가 같으면 소스 변경 없이 새 CLI를 사용할 수 있다. 스키마가 다르면 이 검사가
실패하며, 기준 버전과 생성 계약을 함께 검토·갱신해야 한다.

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
테이블 재생성으로 우회하지 않는다. Codex 호환성 오류는 안정 버전과 생성된 RPC 스키마를
확인하고, 스키마가 바뀐 경우 기준 계약을 검토해 갱신한다.
사용량 제한에는 API fallback을 두지 않는다. 비밀번호 분실은 서버의 `set-password`로 복구한다.
