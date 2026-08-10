# DWDCC 도메인 라우팅/TLS 기준

상태: 현재 운영/개발 도메인 라우팅과 TLS 기준.

이 문서는 `dwdcc.kr`의 현재 route, TLS, Nginx와 environment 계약을 소유한다. 외부 접속
별칭과 운영 LiveKit 분리는 아직 별도 후속 작업이다.

## Target Routing

- 운영 웹/API: `https://dwdcc.kr`, `https://www.dwdcc.kr`
- 운영 외부 접속 별칭 구조: `https://ext.dwdcc.kr`
- 운영 draw.io: `https://drawio.dwdcc.kr`
- 개발 웹/API/LiveKit: `https://dev.dwdcc.kr`
- 운영 Grafana: `https://grafana.dwdcc.kr`

## DNS

- `dwdcc.kr` A 레코드는 현재 내부 IP `128.1.253.101`을 가리킨다.
- `dev.dwdcc.kr`, `www.dwdcc.kr`, `grafana.dwdcc.kr`은 같은 내부 IP 또는 와일드카드 레코드를 통해 해석된다.
- `ext.dwdcc.kr`은 운영 외부 접속 별칭으로 예약한다. 아직 외부 공인 IP/프록시 작업이 완료되지 않았으므로 Nginx 수용 구조만 잡아 둔다.
- 공인 HTTP/TLS 검증 경로가 내부 IP 때문에 안정적이지 않으므로 TLS 인증서는 DNS-01 방식으로 발급한다.
- 현재 DNS 사업자는 Gabia이며, ACME 자동 DNS provider가 연결되지 않아 수동 TXT 레코드 입력으로 발급한다.

## TLS

- 발급 대상: `dwdcc.kr`, `*.dwdcc.kr`
- 발급 도구: `lego`
- 최근 갱신 완료: 2026-08-10 09:33 KST
- 인증서 유효 기간:
  - notBefore: 2026-08-10 08:35:10 KST
  - notAfter: 2026-11-08 08:35:09 KST
- 인증서 경로:
  - cert: `/etc/lego/production/certificates/dwdcc.kr.crt`
  - key: `/etc/lego/production/certificates/dwdcc.kr.key`
- 최근 갱신 전 백업: `/var/backups/ai-do/tls/20260810T000912Z/`
- 현재는 Gabia 수동 DNS-01 방식이므로 갱신도 수동이다.
- 운영 배포 담당자는 **2026-10-09 08:35:09 KST 이전**에 다음 갱신을 완료해야 한다. 이 시점부터
  잔여 유효 기간이 30일 이하가 되어 production smoke와 일일 expiry check가 fail-closed한다.

### Expiry gate와 일일 감시

다음 checker는 secret을 읽거나 출력하지 않는다. 기본값으로 live `dwdcc.kr:443` 인증서의
신뢰 체인/hostname, `dwdcc.kr`과 `*.dwdcc.kr` SAN, 30일 초과 잔여 기간을 검사한다.

```bash
python3 scripts/check_live_tls_expiry.py
```

연결/검증 실패, 인증서 파싱 실패, 필수 SAN 누락, 잔여 기간 30일 이하는 모두 exit 1이다.
재현 가능한 경계 진단에는 `--now 2026-10-08T23:35:09Z`처럼 명시적 UTC clock을 쓸 수
있지만 production smoke와 timer는 실제 clock만 사용한다. 기본 `pnpm prod:smoke`는 서비스
readiness 재시도 전에 이 검사를 한 번 실행하며 실패를 우회하지 않는다. 기본
`pnpm prod:deploy`도 dependency 설치나 DB/서비스 변경 전에 같은 검사를 preflight로 실행한다.

인증서가 현재 유효하고 신뢰 체인·hostname·필수 SAN이 모두 정상이나 잔여 기간만 30일 이하인
경우, 명시적으로 승인된 배포 한 번에 한해 다음 break-glass 절차를 사용할 수 있다.

```bash
pnpm prod:deploy -- --dry-run --tls-expiry-break-glass
pnpm prod:deploy -- --tls-expiry-break-glass
pnpm prod:smoke --tls-expiry-break-glass
```

이 옵션은 해당 프로세스에서 잔여 기간 임계값만 30일에서 0일로 낮춘다. 실제 만료,
신뢰 체인 또는 hostname 검증 실패, 필수 SAN 누락, 연결·파싱 실패는 계속 fail-closed한다.
dry-run의 옵션은 실제 배포에 유지되지 않으므로 실제 명령에도 다시 명시해야 한다. 기본 deploy와
smoke 및 일일 systemd timer의 30일 기준은 변경되지 않으며, break-glass 배포 후 인증서 갱신은
여전히 즉시 처리해야 하는 운영 후속 작업이다.

root systemd 일일 감시 unit의 정본은 다음과 같다.

- `ops/systemd/system/ai-do-tls-expiry-check.service`
- `ops/systemd/system/ai-do-tls-expiry-check.timer`

설치 helper는 기본 실행이 검증 전용 dry-run이다. 실제 설치는 명시적인 `--apply`가 필요하다.
기존 파일이 다르면 덮어쓰지 않으며, 검토 후 `--apply --replace`를 사용해야 기존 파일을
`/var/backups/ai-do/tls-expiry-monitor/` 아래에 먼저 백업한다.

```bash
bash ops/systemd/install-tls-expiry-monitor.sh
sudo -n true
bash ops/systemd/install-tls-expiry-monitor.sh --apply
systemctl is-enabled ai-do-tls-expiry-check.timer
systemctl is-active ai-do-tls-expiry-check.timer
systemctl list-timers ai-do-tls-expiry-check.timer --no-pager
systemctl show ai-do-tls-expiry-check.service -p Result -p ExecMainStatus
```

checker 실패는 `ai-do-tls-expiry-check.service`를 failed 상태로 남기고 JSON 원인을 journal에
기록한다. 운영 점검은 `systemctl --failed`와 이 unit 상태를 확인하며, 실패를 발견하면 아래
수동 갱신 절차를 즉시 실행한다.

### 2026 수동 갱신 절차

Gabia에서 DNS를 수정할 수 있는 운영자와 Nginx 운영자가 같은 작업 창에 참여한다. 계정 ID와
DNS credential 값은 채팅, shell 인자, journal에 출력하지 않는다. 먼저 현재 lego material을
root-only 경로에 백업한다.

```bash
tls_backup_dir="/var/backups/ai-do/tls/$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -o root -g root -m 0700 "$tls_backup_dir"
sudo cp --preserve=all \
  /etc/lego/production/certificates/dwdcc.kr.crt \
  /etc/lego/production/certificates/dwdcc.kr.issuer.crt \
  /etc/lego/production/certificates/dwdcc.kr.key \
  /etc/lego/production/certificates/dwdcc.kr.json \
  "$tls_backup_dir/"
```

기존 account ID는 root shell 변수에만 담아 lego에 전달한다. Gabia의 TXT 최소 TTL은 600초이므로
manual provider 전파 제한을 900초로 늘린다. `--renew-days 45`는 현재 인증서를 갱신 대상으로
만들되 `--renew-force`에 의한 불필요한 CA 요청은 피한다.

```bash
tls_account_json="$(
  sudo find /etc/lego/production/accounts -type f -name account.json -print -quit
)"
test -n "$tls_account_json"
tls_account_id="$(sudo jq -r '.id' "$tls_account_json")"
test -n "$tls_account_id"

sudo env MANUAL_PROPAGATION_TIMEOUT=900 MANUAL_POLLING_INTERVAL=5 \
  /usr/local/bin/lego run \
  --path /etc/lego/production \
  --server letsencrypt \
  --account-id "$tls_account_id" \
  --cert.name dwdcc.kr \
  --dns manual \
  --domains dwdcc.kr \
  --domains '*.dwdcc.kr' \
  --renew-days 45
```

lego가 제시하는 `_acme-challenge.dwdcc.kr` TXT 값만 Gabia에 입력하고 authoritative NS에서
전파된 뒤 진행한다. `dwdcc.kr`과 `*.dwdcc.kr`은 같은 TXT 이름을 사용하므로 lego가 두 값을
순서대로 요청하면 이전 값을 제거하고 새 값 하나만 둔다. 성공 후 challenge TXT를 완전히
삭제한다. 새 인증서의 SAN과 만료일이 정확하고 30일보다 오래 남았을 때만 Nginx를 reload한다.

Gabia authoritative NS 모두와 신뢰할 수 있는 공개 recursive resolver에서 현재 challenge 값이
정확히 확인됐지만 운영 서버의 recursive cache만 TTL 때문에 지연되는 경우에만
`--dns.propagation.disable-rns`를 lego 인자에 추가할 수 있다. 이 옵션은 lego의 중복 recursive
전파 대기만 끄며 authoritative NS 확인과 Let’s Encrypt의 DNS-01 검증은 그대로 유지한다.

```bash
sudo openssl x509 \
  -in /etc/lego/production/certificates/dwdcc.kr.crt \
  -noout -dates -ext subjectAltName -checkend 2592000
sudo nginx -t
sudo systemctl reload nginx
python3 scripts/check_live_tls_expiry.py
```

lego, SAN/만료일 검증 또는 `nginx -t`가 실패하면 reload하지 않는다. reload 후 live 검증이
실패하면 백업한 네 파일을 원래 경로로 복원하고 `nginx -t` 성공 후 다시 reload한다.

### 갱신 운영 원칙

- `dwdcc.kr` authoritative DNS와 ACME challenge TXT는 모두 Gabia에서 관리한다.
- 외부 DNS provider로 challenge CNAME을 위임하거나 DNS API credential을 사용하는 자동
  갱신 방식은 사용하지 않는다.
- 수동 갱신 이후에도 위 expiry checker와 production smoke gate는 독립 안전장치로 유지한다.

## Nginx

- 공통 WebSocket upgrade map:
  - 원본: `ops/nginx/ai-do-connection-upgrade-map.conf`
  - 설치 경로: `/etc/nginx/conf.d/ai-do-connection-upgrade-map.conf`
- 운영 프록시:
  - 원본: `ops/nginx/dwdcc.kr.proxy-only.conf`
  - 설치 경로: `/etc/nginx/sites-available/dwdcc.kr`
  - 활성화 링크: `/etc/nginx/sites-enabled/dwdcc.kr`
  - server_name: `dwdcc.kr`, `www.dwdcc.kr`, `ext.dwdcc.kr`
  - upstream: `127.0.0.1:8000`
  - `/inference-gateway/`는 인증 없는 backend 노출을 막기 위해 404 반환
  - Docs/Whiteboard collab WebSocket upstream: `127.0.0.1:8009`
- draw.io 프록시:
  - 원본: `ops/nginx/dwdcc.kr.proxy-only.conf`
  - server_name: `drawio.dwdcc.kr`
  - upstream: `127.0.0.1:18083`
  - 메인 origin의 `/drawio/`는 `https://drawio.dwdcc.kr/`로 redirect
- 개발 프록시:
  - 원본: `ops/dev/nginx-dev.dwdcc.kr.conf`
  - 설치 경로: `/etc/nginx/sites-available/dev.dwdcc.kr`
  - 활성화 링크: `/etc/nginx/sites-enabled/dev.dwdcc.kr`
  - `/rtc/` upstream: `127.0.0.1:7880`
  - `/api/` upstream: `127.0.0.1:8001`
  - `/` upstream: `127.0.0.1:4200`
- Grafana 프록시:
  - 원본: `ops/nginx/grafana.dwdcc.kr.proxy-only.conf`
  - 설치 경로: `/etc/nginx/sites-available/grafana.dwdcc.kr`
  - 활성화 링크: `/etc/nginx/sites-enabled/grafana.dwdcc.kr`
  - upstream: `127.0.0.1:3000`

## Environment

- 개발:
  - `AI_DO_LIVEKIT_PUBLIC_URL=wss://dev.dwdcc.kr`
  - `AI_DO_API_DEV_LOGIN_ALLOWED_HOSTS`에는 `dev.dwdcc.kr`을 포함한다.
  - 이전 임시 도메인 `dwdcc.lumejs.com`은 개발 허용 호스트에서 제거한다.
- 운영:
  - `AI_DO_PROD_SMOKE_WEB_HOST=dwdcc.kr`
  - 운영 LiveKit public URL은 `dwdcc.kr` 기준을 유지하고 `ext.dwdcc.kr`로 바꾸지 않는다. 현재 runtime은 별도 운영 인스턴스를 만들 때까지 비워 둔다.
- AI-DO Desktop 패키징/update trusted origin 값은 별도 desktop repo
  `/projects/ai-do/ai-do-desktop`의 release 환경에서 관리한다. 포털 운영 env는
  update feed 정적 디렉터리와 웹 installer link만 가진다.

## Separation Notes

- 개발 LiveKit은 `dev.dwdcc.kr/rtc/`에서만 노출한다.
- 운영 도메인은 현재 개발 LiveKit upstream을 공유하지 않는다.
- 운영 LiveKit을 켜려면 별도 LiveKit 포트, Redis/egress/ingress 설정, TURN 설정, 운영 env를 분리한 뒤 운영 프록시에 추가한다.

## 남은 운영 작업

- runtime `.env`와 GitLab Secure Files에서 이전 임시 도메인 값을 제거한다.
- 2026-10-09 08:35:09 KST 이전에 다음 수동 갱신을 완료한다.
- root systemd expiry timer의 enabled/active 상태와 매일 성공 결과를 유지·확인한다.
- 다음 수동 갱신 작업 창과 Gabia DNS 담당자를 확정한다. 갱신 종료 후
  `_acme-challenge.dwdcc.kr` TXT가 비어 있는지 authoritative NS에서 확인한다.
- 운영 LiveKit을 켜려면 별도 LiveKit 포트, Redis/egress/ingress 설정, TURN 설정,
  운영 env를 분리한 뒤 운영 프록시에 추가한다.
