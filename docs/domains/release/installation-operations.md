# 설치 환경별 운영 확인

[INSTALL.md](../../../INSTALL.md)의 네이티브 설치·브라우저·GitLab·Runner 절차에서 사용하는 환경별 선택과 복구 절차다.
설치 순서는 INSTALL, 지속 실행과 CI 이미지 계약은 [Release Domain](README.md)이 소유한다.
`<...>`는 실제 설치 환경에서 확인해 대체할 값이다. 공식 설정 파일 경로·설정 키·프로토콜 주소는 그대로 표기한다.
호스트별 값과 검사 결과는 설치 인계에 기록하고 비밀값은 [로그인 정보 관리](../../../INSTALL.md#11-로그인-정보-파일-관리)를 따른다.

## PostgreSQL locale

### 클러스터 생성 전 확인

PostgreSQL 서버 패키지 설치 **전**에 실행한다. Debian 계열은 패키지 설치 중 기본 클러스터를 자동 생성할 수 있다.
선택한 PostgreSQL 버전과 배포판의 [로케일 지원](https://www.postgresql.org/docs/current/locale.html),
[클러스터 생성 설정](https://manpages.debian.org/bookworm/postgresql-common/pg_createcluster.1.en.html)을 확인한다.

```bash
locale
locale -a
locale charmap
```

`LANG`, `LC_ALL`, 범주별 `LC_*`가 존재하는 로케일을 가리키는지, 오류 없이 UTF-8 문자셋을 사용할 수 있는지 확인한다.
`locale -a`의 실제 이름을 사용한다. UTF-8 로케일의 이름·제공 방식은 배포판마다 다르며 특정 언어나 지역을 강제하지 않는다.
정렬·문자 분류 요구에 따라 로케일과 provider를 선택하고, DB 인코딩 `UTF8`과 로케일을 별도로 확인한다.
SSH 셸의 로케일이 클러스터 생성 계정이나 systemd 서비스에도 적용된다고 가정하지 않는다.

```bash
LC_ALL='<사용-가능한-UTF-8-로케일>' locale charmap
```

신규 설치는 선택한 로케일을 준비한 다음 패키지·클러스터를 설치한다. 명시적으로 클러스터를 생성해야 한다면
배포판이 지원하는 자동 생성 설정을 먼저 확인하고, 새 대상의 버전·이름·데이터 경로·포트가 기존 환경과 겹치지 않게 한다.
`initdb` 또는 배포판 생성 도구의 로케일·인코딩 옵션은 **비어 있는 신규 대상**에만 적용한다.
이미 패키지나 데이터가 있으면 먼저 `pg_lsclusters`(Debian 계열)와 대상 서비스·데이터 경로를 확인하고 아래 복구 분기를 따른다.

### 누락·손상 복구와 기존 환경 보존

1. 로케일은 존재하지만 현재 설정만 잘못됐으면 해당 계정·서비스의 로케일 설정을 바로잡는다. 다른 서비스가 사용하는 시스템 기본값을 일괄 변경하지 않는다.
2. 필요한 로케일이 없으면 현재 배포판의 로케일 패키지와 생성 도구를 준비한다. Debian 계열은 `/etc/locale.gen`의 기존 선택을 보존하고 `<로케일-이름> UTF-8` 항목을 추가한 뒤 `sudo locale-gen --keep-existing`으로 생성할 수 있다. 설치한 버전의 [locale-gen](https://manpages.debian.org/bookworm/locales/locale-gen.8.en.html) 지원 옵션을 먼저 확인한다.
3. 아카이브 오류가 있으면 `localedef --list-archive`와 패키지 무결성 검사로 원인을 확인한다. [개별 로케일 파일 방식](https://manpages.ubuntu.com/manpages/focal/man1/localedef.1.html)도 있으므로 아카이브가 없다는 사실만으로 손상으로 판단하지 않는다.
4. 손상이 확인된 경우에만 기존 로케일 선택 목록·사용 중인 로케일·실제 아카이브를 관리자 전용 백업 위치에 보존한다. 배포판의 패키지 복구 절차로 로케일 원본을 복구하고, 기존에 필요한 모든 로케일이 생성 목록에 포함됐는지 확인한다. Debian의 아카이브 재생성은 백업 후 `sudo locale-gen`을 사용한다. 다른 배포판은 해당 버전의 공식 재생성 절차를 따른다. 전체 로케일 디렉터리나 DB 데이터를 삭제하지 않는다.
5. `locale`, `locale -a`, 선택한 로케일의 `locale charmap`을 다시 확인한다. 기존 PostgreSQL 대상에는 필요한 서비스 재시작 후 인증 연결과 읽기 전용 쿼리로 복구를 확인한다.

기존 DB는 재생성·덮어쓰기·`pg_dropcluster`로 복구하지 않는다. OS 로케일 복구는 DB의 기존 인코딩·정렬 규칙을 바꾸는 작업이 아니다.
기존 libpq 연결 서비스와 소유자 전용 passfile을 사용해 대상 DB에서 다음을 확인할 수 있다. 비밀번호는 명령 인자에 넣지 않는다.

```bash
psql -Xw 'service=<대상-DB-연결-서비스>' -c 'SHOW server_encoding'
psql -Xw 'service=<대상-DB-연결-서비스>' \
  -c 'SELECT datcollate, datctype FROM pg_database WHERE datname = current_database()'
psql -Xw 'service=<대상-DB-연결-서비스>' -c 'SELECT 1'
```

ICU 등 별도 provider를 쓰면 해당 버전의 DB 카탈로그에서 provider·로케일도 확인한다.
libc·ICU 변경으로 collation version 경고가 발생하면 [PostgreSQL collation 복구](https://www.postgresql.org/docs/current/sql-altercollation.html)를 따른다.
영향 인덱스 등의 재구성과 검증 없이 버전 메타데이터만 갱신하지 않는다. 기존 DB의 로케일 변경·메이저 업그레이드는 별도 데이터 전환 작업이다.

## Browser installation and rendering

설치한 `agent-browser --version`, `agent-browser --help`와 OS·CPU를 확인하고
[공식 설치 안내](https://agent-browser.dev/installation)의 지원 범위에 따라 선택한다.

| 조건 | 선택과 검증 |
| --- | --- |
| 자동 다운로드가 지원되고 사용 가능한 브라우저가 없음 | `agent-browser install`; OS 라이브러리 누락은 지원되는 환경에서 `agent-browser install --with-deps` |
| 검증된 시스템 Chromium이 있음 | `--executable-path '<Chromium-실행파일>'`로 실행하고 실제 페이지를 검사 |
| OS·CPU 조합에 자동 다운로드 빌드가 없음 | 해당 배포판·CPU를 지원하는 시스템 Chromium을 설치하고 실제 실행·샌드박스를 확인. 다른 CPU의 바이너리로 대체하지 않음 |
| 패키지 격리로 자동 시작·연결이 실패함 | 시스템 Chromium을 직접 실행하고 [공식 CDP 연결](https://agent-browser.dev/cdp-mode) 사용 |

CLI 바이너리 지원과 브라우저 다운로드 지원은 별개다. Linux ARM64의 Chrome for Testing 빌드 부재처럼
다운로드가 지원되지 않는 경우 `--with-deps`만 반복해 해결하려 하지 않는다. Ubuntu의 Chromium 패키지는 Snap으로 제공될 수 있다.

CDP를 사용할 때는 일반 사용자로 별도 터미널에서 다음과 같이 전경 실행한다.
프로필은 해당 패키지가 접근할 수 있는 **검사용 소유자 전용 디렉터리**를 준비한다.
일상 브라우저 프로필을 재사용하지 않는다. [Chrome의 디버깅 프로필 조건](https://developer.chrome.com/blog/remote-debugging-port)도 확인한다.

```bash
'<Chromium-실행파일>' --headless \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port='<CDP-포트>' \
  --user-data-dir='<검사용-프로필-절대경로>' about:blank
```

별도 터미널에서 `ss -ltnp`로 CDP 포트가 loopback에만 수신하는지 확인한 뒤 연결한다.
외부에 디버깅 포트를 공개하지 않는다.

```bash
agent-browser --session '<검사용-세션>' --cdp '<CDP-포트>' open '<검사할-접속-URL>'
agent-browser --session '<검사용-세션>' --cdp '<CDP-포트>' snapshot -i
agent-browser --session '<검사용-세션>' close
```

검사 실패 시에도 세션을 닫고 직접 실행한 Chromium은 해당 터미널의 `Ctrl+C`로 종료한다.
CDP 수신 종료를 확인한다. 다른 사용자의 브라우저까지 일괄 종료하지 않는다.
[샌드박스 검사](../../../INSTALL.md#43-chromium-실행이-apparmor에-차단된-경우)를 통과해야 하며 `--no-sandbox`나 시스템 전체 제한 해제를 사용하지 않는다.
이 경로는 설치 화면 검사용이다. 저장소 Playwright 회귀검사의 브라우저·검사 계약을 대체하지 않는다.

### 한글 글꼴 확인

로그인 화면과 앱 화면에서 한글이 사각형·빈칸으로 보이지 않는지 실제 렌더링 또는 화면 캡처로 확인한다.
snapshot에 한글 텍스트가 있다는 사실이나 호스트의 `fc-match` 결과만으로 통과를 판단하지 않는다.
누락 시 배포판이 지원하는 한글 글꼴 패키지를 설치하고 브라우저를 다시 실행한다.

Snap 등 격리된 패키지는 글꼴 디렉터리·캐시·설정의 가시성이 호스트와 다를 수 있다.
호스트 글꼴 설치만으로 해결되지 않으면 해당 패키지 버전의 공식 글꼴·fontconfig·desktop 인터페이스 안내를 따른다.
Snap은 `snap connections '<브라우저-snap-이름>'`으로 연결 상태를 확인한다.
[Snap 인터페이스 문서](https://snapcraft.io/docs/reference/interfaces/)에서 패키지에 필요한 연결을 확인하고,
패키지 소유자가 안내하는 글꼴 위치와 캐시 갱신 절차를 적용한 뒤 같은 브라우저·사용자·프로필로 한글을 재검사한다.
격리를 해제하거나 호스트·패키지의 글꼴 캐시를 일괄 삭제하는 방법은 사용하지 않는다.

## HTTPS trust

OS, CLI 런타임, 브라우저, Runner와 컨테이너는 서로 다른 인증서 저장소를 사용할 수 있다.
한 환경의 접속 성공이 다른 환경의 신뢰 등록을 증명하지 않는다. 내부 CA를 사용할 때는 먼저
신뢰할 수 있는 경로로 CA **공개 인증서**와 지문을 확인하고 필요한 실행 환경마다 등록한다.
CA·서버 개인키는 클라이언트나 이미지에 배포하지 않는다. 기존 CA·정책은 보존한다.

| 실행 환경 | 공식 설정과 확인 |
| --- | --- |
| Debian/Ubuntu 호스트 | PEM 형식의 CA 공개 인증서를 인증서당 하나의 `.crt` 파일로 배포판의 로컬 CA 디렉터리에 추가하고 `sudo update-ca-certificates`. 기존 파일·목록을 덮어쓰지 않음. [공식 명령](https://manpages.debian.org/bookworm/ca-certificates/update-ca-certificates.8.en.html) 참고 |
| 다른 OS·클라이언트 PC | OS 공식 신뢰 저장소에 등록. Windows의 신뢰할 수 있는 루트 인증 기관, macOS의 키체인 등에서 실제 사용자·시스템 적용 범위를 확인 |
| Git·curl·glab·Node/Python 등 CLI | 각 도구·런타임 버전의 공식 CA 설정 사용. 대화형 셸과 서비스 실행 계정을 각각 확인. CA 번들을 재정의할 때 기존에 필요한 신뢰를 유지 |
| Chromium·Chrome | 실제 패키지의 인증서 관리자 또는 지원되는 관리 정책 사용. 아래 절차로 적용 확인 |
| Runner·helper·작업 컨테이너 | [Runner TLS 설정](https://docs.gitlab.com/runner/configuration/tls-self-signed/) 적용. 호스트 등록이 이미지 내부로 전파된다고 가정하지 말고 helper와 작업 이미지의 HTTPS 연결을 각각 확인 |

인증서 체인·유효기간과 URL의 호스트명 또는 IP에 맞는 SAN을 확인한다. IP로 접속하면 SAN의 IP 항목에 그 주소가 있어야 한다.
각 환경의 기본 신뢰 설정으로 실제 HTTPS 요청을 수행하고, 브라우저에서는 인증서 경고 없이 로그인 화면과 로그인을 확인한다.
`curl --cacert '<CA-공개-인증서-경로>' '<HTTPS-URL>'`은 지정 CA의 연결 진단에 사용할 수 있지만 기본 신뢰 저장소 등록 성공을 대신하지 않는다.
`curl -k`, 인증서 오류 무시 옵션, TLS 검증 비활성화 환경변수는 사용하지 않는다.

### Chromium 관리 정책 또는 CLI별 CA 등록

[공식 Linux 정책 안내](https://www.chromium.org/administrators/linux-quick-start/)로 브라우저 배포본의 정책 경로를 확인한다.
Chrome·Chromium·Snap 경로를 동일하게 가정하지 않는다. 정책은 관리자만 수정할 수 있게 한다.

1. 설치 버전의 [CACertificates 정책](https://chromeenterprise.google/intl/en_us/policies/ca-certificates/) 지원 여부와 현재 정책을 확인한다.
2. 지원하는 경우 CA 공개 인증서를 정책 형식인 **DER 인증서의 base64 문자열**로 준비한다. PEM 헤더·개인키를 넣지 않는다.
3. 기존 `CACertificates` 항목이 있으면 같은 소유 정책에서 기존 목록을 보존하며 추가한다. 서로 다른 JSON 파일에 같은 키를 중복 정의하면 병합이 보장되지 않으므로 새 파일로 기존 정책을 가리지 않는다. 다른 정책 키도 보존한다.
4. 브라우저의 `chrome://policy`에서 정책을 다시 로드하고 인식·값·오류·충돌 여부를 확인한다. 실제 HTTPS 페이지를 새로 열어 검증한다. 미지원이면 해당 배포본의 공식 인증서 관리자·신뢰 저장소 방식을 사용한다.

설치한 agent-browser가 지원하면 로컬 Chromium 시작 시 `--ca-cert '<CA-공개-인증서-경로>'`도 사용할 수 있다.
[해당 버전의 지원 범위](https://agent-browser.dev/configuration)를 확인한다. CDP로 이미 실행 중인 브라우저에 연결할 때나 영속 프로필에서는
이 옵션이 지원된다고 가정하지 말고 브라우저 자체의 신뢰 설정을 적용한다. 실제 사용 모드에서 HTTPS를 재검사한다.

## Development access checks

시작·재부팅·복구 후 검사 조건은 다음과 같다. 먼저 같은 체크아웃에서 `./dev.sh --status`로 선택한 서비스 상태를 확인하고,
실제 수신 주소·포트와 로컬 API `/readyz`의 HTTP 성공 및 JSON `status: ok`를 확인한다. Worker를 선택한 환경은 `./dev.sh --with-worker --status`를 사용한다.
`pnpm dev:login-smoke`는 API health·로그인·사용자·앱 bootstrap을 검사하며 readiness·화면 렌더링·로그아웃을 대신하지 않는다.

| 접속 구성 | 필요한 접속 검사 |
| --- | --- |
| HTTP 개발 접속 | `OPEN_WORK_HUB_DEV_SMOKE_API_URL='http://<개발-호스트>:<Web-포트>' pnpm dev:login-smoke`와 같은 주소의 브라우저 로그인·앱 화면·로그아웃 |
| HTTPS 공개 도메인의 개발 접속 | 개발 `.env`의 `OPEN_WORK_HUB_UAT_BASE_URL`을 `https://<개발-공개-도메인>:<HTTPS-포트>`로 맞춘 뒤 `pnpm dev:public-smoke` 실행. 실제 브라우저 로그인·화면·로그아웃도 확인 |
| HTTPS IP 기반 개발 접속 | [CA 신뢰](#https-trust)와 IP SAN을 확인한 뒤 HTTPS Web 주소로 `dev:login-smoke`와 브라우저 검사. `dev:public-smoke`에는 IP URL을 넣지 않음 |

`dev:public-smoke`는 **HTTPS 공개 도메인 origin**을 요구한다. IP 주소·localhost·`.local`·단일 호스트명과
경로·쿼리·자격증명이 포함된 URL은 허용하지 않는다. 루트 개발 `.env`의 해당 설정만 실제 origin에 맞추고 다른 설정은 보존한다.
[개발 환경 로더](../../../scripts/dev-env.sh)는 `.env`에 같은 키가 있으면 명령 앞에서 지정한 값보다 나중에 덮어쓴다.
`OPEN_WORK_HUB_DEV_SMOKE_API_URL`도 해당 키가 `.env`에 있다면 검사하려는 주소와 일치시킨다. 환경설정 전체나 자격증명은 출력하지 않는다.
이 검사는 로컬/공개 health의 개발 런타임 일치, readiness, bootstrap과 로그인 HTML을 확인한다.
HTTP·IP 설치를 통과시키려고 [기존 검사](../../../scripts/live-uat-preflight.mjs)나 HTTPS 요구를 완화하지 않는다.
GitLab의 HTTPS IP 검사에는 아래의 별도 GitLab 경로를 사용한다.

원격 PC 접속이 필요한 설치는 서버가 자신의 접속 주소로 수행한 검사와 별도로 **클라이언트 PC 또는 같은 외부 접속 경로**에서
브라우저 로그인·앱 화면·로그아웃을 확인한다. 실패 시 클라이언트 측 DNS(사용 시)·라우팅·방화벽·프록시·CA 신뢰를 점검한다.
PC 조작 권한이 없으면 사용자에게 해당 검사만 요청하고 결과를 미확인으로 기록한다. 서버 자체 검사 성공으로 대신 보고하지 않는다.
접속 설정은 [INSTALL 5절](../../../INSTALL.md#5-내-pc-브라우저에서-서버-접속), 실행 관리는 [지속 실행 계약](README.md#persistent-development-runtime)을 따른다.

## GitLab listeners and readiness

GitLab 설치·업데이트·`gitlab-ctl reconfigure` 후 웹·SSH 외에도 exporter, Prometheus, Alertmanager 등
상태 확인·모니터링 서비스가 소켓을 열 수 있다. [GitLab 모니터링 설정](https://docs.gitlab.com/administration/monitoring/prometheus/)과
설치한 버전의 각 서비스 설정을 확인한다. 서비스별 기본 수신 주소가 같다고 가정하지 않는다.

```bash
sudo gitlab-ctl status
sudo ss -lntup
```

IPv4·IPv6의 실제 수신 주소·TCP/UDP 포트·프로세스를 식별하고 설치 전 목록과 비교한다.
Docker 설치라면 호스트 소켓만으로 게시 상태를 판단하지 말고 `docker port '<GitLab-컨테이너>'`와 방화벽/NAT 규칙도 확인한다.
외부 접근이 필요 없는 서비스는 해당 버전의 지원 설정으로 loopback에 제한한다.
별도 모니터링 노드가 필요하면 필요한 내부 인터페이스와 접근 소스만 허용하고 기존 scrape 대상도 함께 맞춘다.
예를 들어 Prometheus의 `listen_address` 등 **각 서비스의 설정 키**를 사용하며 생성된 설정 파일을 직접 고치지 않는다.
재구성 후 소켓 목록과 모니터링 연결을 다시 확인한다. 불필요한 포트를 열거나 모니터링을 일괄 비활성화해 검사를 통과시키지 않는다.

### HTTPS readiness

`/-/readiness?all=1`의 성공에는 **TLS 신뢰·호스트명/IP 검증**과 **모니터링 접근 정책**이 모두 필요하다.
허용된 점검 위치에서 인증서 SAN과 일치하는 HTTPS URL로 요청하고 HTTP 상태와 전체 readiness JSON의 성공을 확인한다.
[GitLab 모니터링 IP 허용 목록](https://docs.gitlab.com/administration/monitoring/ip_allowlist/)은 PC 로그인 허용 목록과 다르다.

서버의 HTTPS 리스너가 loopback에서도 수신한다면 아래처럼 URL의 인증서 신원을 유지하고 연결 대상만 loopback으로 지정할 수 있다.
`<인증서와-일치하는-호스트-또는-IP>`는 인증서 SAN과 `external_url`에 맞춰 선택한다.
[curl의 `--connect-to`](https://curl.se/docs/manpage.html#--connect-to)는 연결 주소만 바꾸고 TLS 검증 신원은 유지한다.

```bash
curl --fail --silent --show-error --connect-timeout 5 --max-time 20 \
  --noproxy '<인증서와-일치하는-호스트-또는-IP>' \
  --connect-to '<인증서와-일치하는-호스트-또는-IP>:<HTTPS-포트>:127.0.0.1:<HTTPS-포트>' \
  'https://<인증서와-일치하는-호스트-또는-IP>:<HTTPS-포트>/-/readiness?all=1'
```

loopback에 해당 리스너가 없으면 이 명령을 사용하지 않는다. 실제 수신 인터페이스와 이미 허용된 점검 경로를 사용하거나
운영자가 필요한 점검 소스만 허용한다. 프록시가 있다면 GitLab이 판단하는 요청 소스와 신뢰 프록시 설정도 확인한다.
URL을 무조건 `https://127.0.0.1`로 바꾸거나 `Host` 헤더만 바꿔 인증서 검증을 해결하려 하지 않는다.
CA 오류·SAN 불일치·접근 거부·서비스 미준비를 구분해 수정한다. PC는 `/users/sign_in`과 실제 로그인으로 확인하고 readiness 접근 권한을 넓히지 않는다.

## Runner installation and updates

[공식 Runner 패키지 안내](https://docs.gitlab.com/runner/install/linux-repository/)에 따라 설치할 버전·배포판·helper 패키지를 확인한다.
패키지 버전의 설치·업데이트 스크립트가 Docker 정리를 수행할 수 있으므로 공유 호스트에서는 **패키지 실행 전** 실제 동작과 대상 Docker 데몬을 확인한다.
미사용 판정에는 나중에 사용할 CI 리소스도 포함될 수 있다. 공식 안내의 `NO_DOCKER_PRUNE` 지원 여부를 대상 패키지에서 확인하고,
지원하는 Debian 계열 패키지는 다음처럼 패키지 프로세스에 직접 전달해 정리를 생략할 수 있다.

```bash
sudo env NO_DOCKER_PRUNE=1 apt-get install \
  'gitlab-runner=<설치할-버전>' 'gitlab-runner-helper-images=<대응하는-버전>'
```

이것은 Runner 패키지 자체의 공식 옵션이며 프로젝트 `.env`에 추가할 설정이 아니다.
외부 셸에만 변수를 지정하고 `sudo`가 보존할 것이라고 가정하지 않는다. 해당 버전이 옵션을 지원하지 않거나
정리 범위를 확인할 수 없으면 기존 리소스가 있는 공유 Docker 데몬에서 그대로 실행하지 말고 전용 Runner 호스트 또는 지원되는 설치 방식을 선택한다.

### 초기 설치 순서

1. 기존 Docker 리소스와 서비스·네트워크의 소유자를 확인하고 Runner 패키지 설치를 먼저 완료한다.
2. [INSTALL의 Runner 등록](../../../INSTALL.md#225-runner와-파이프라인-준비)을 마친 뒤 검증 Runner가 실제 사용하는 Docker 데몬·executor 네트워크를 확인한다.
3. 선택한 구성에 필요한 CI 전용 네트워크와 테스트 DB·서비스를 준비한다. 고정 CI 네트워크를 선택한 경우 패키지 설치가 끝난 뒤 생성하고 Runner의 공식 `network_mode` 설정과 일치시킨다. job별 네트워크를 쓰는 구성에 고정 네트워크를 강제하지 않는다.
4. [DB·이미지 계약](README.md#validation-image-platform-and-database)과 INSTALL의 CI 변수 절차에 따라 실제 작업 네트워크의 연결을 검사한다. 그 뒤 승인된 개발 MR 파이프라인을 확인한다.

### 업데이트 후 재검사와 복구

업데이트 전에 활성 job과 유지보수 시간을 확인하고 필요한 네트워크의 이름·driver·CIDR·gateway·연결 서비스를 기록한다.
Docker 설정·인증 파일 전체를 공유 로그에 출력하지 않는다. 업데이트 후 다음을 확인한다.

```bash
sudo gitlab-runner verify
docker network inspect --format '{{.Name}} {{.Driver}} {{json .IPAM.Config}}' '<CI-전용-네트워크>'
```

Docker 명령은 **Runner와 같은 Docker 데몬·context**를 선택한 상태에서 실행한다. 고정 네트워크를 쓰는 경우에만 위 이름으로 검사한다.
job별 네트워크는 실제 job의 서비스 연결을 확인한다. 등록 검증만으로 CI 인프라가 정상이라고 판단하지 않는다.

- 네트워크 존재뿐 아니라 CIDR·gateway·Runner 연결 설정, DB의 바인딩·HBA·방화벽, 필요한 서비스 상태를 확인한다.
- 실제 검증 이미지와 작업 네트워크에서 CI 전용 계정으로 인증 연결과 `SELECT 1`, `SHOW server_version_num`을 확인한다. 호스트에서의 `pg_isready`만으로 대신하지 않는다. 연결 정보는 보호된 입력·libpq 서비스와 passfile 등으로 전달하고 DSN·비밀번호를 출력하지 않는다.
- 이미지의 PostgreSQL 클라이언트 메이저와 실제 CI 서버 메이저가 맞는지 [기존 검사 계약](README.md#validation-image-platform-and-database)을 따른다. GitLab TLS 신뢰와 필요한 이미지·서비스도 재확인한다.
- 네트워크가 없어졌다면 다른 네트워크와 충돌하지 않는지 확인하고 기록한 설정으로 **누락된 프로젝트 소유 네트워크만** 복구한다. 필요한 서비스 연결과 DB 시작 의존성을 복구한 뒤 같은 연결 검사를 반복한다. 이름이 같아도 설정이 다른 기존 리소스를 삭제·덮어쓰지 않는다.

Docker 전체 prune, 컨테이너·네트워크·볼륨 일괄 삭제, 기존 DB 재생성은 복구 절차로 사용하지 않는다.
실제 파이프라인 검사는 기존 CI 라우팅과 승인 범위를 유지한다. Runner 업데이트 확인만을 위해 릴리스 MR·게시 태그를 생성하지 않는다.
