# 전체 시스템 재시작 점검 및 복구 Runbook

상태: 현재 운영 참고 문서

대상:

- Portal: `dwdcc-OMEN-35L-GT16-0xxx`
- Local AI replica: `dgx-spark-102`, `dgx-spark-103`

이 문서는 Portal과 두 DGX Spark를 재시작하는 순서, 안전 경계, 완료 판정을
소유한다. 일회성 장애 조사 결과와 고정 버전·서비스 개수는 기록하지 않는다.
운영 배포는 [Production Deployment Layout](../domains/release/production-deployment-layout.md),
DGX topology와 watchdog은
[Inference Gateway 운영 문서](../domains/inference-gateway/backend-operations.md)와
[DGX Spark 운영 계약](../domains/inference-gateway/dgx-spark-servers.md)을 따른다.

## 검증된 기준 상태

2026-08-04 전체 재부팅과 후속 개선 뒤 다음 기준을 확인했다. 이 기록은 다음
점검을 생략하는 근거가 아니며, 아래 명령의 실시간 결과를 우선한다.

- Portal과 두 DGX의 systemd 상태가 `running`이고 failed unit이 없다.
- 운영·개발 runtime smoke와 환경 분리 검사가 통과한다.
- 두 DGX의 vLLM replica와 HAProxy endpoint가 같은 모델을 제공한다.
- Portal과 DGX Inference Gateway는 `ready=true`이며 embedding, reranker,
  docling, asr가 모두 loaded 상태다.
- PostgreSQL은 loopback과 관리 LAN 주소에서 기동하며, 외부 접근은
  `pg_hba.conf`에서 개발 DB와 승인 계정으로 제한한다.
- PostgreSQL main cluster는 `network-online.target`과
  `NetworkManager-wait-online.service` 뒤에 시작한다. 저장소 정본은
  `ops/systemd/system/postgresql@18-main.service.d/network-online.conf`다.
- CI validation cluster는 Docker가 `ai-do-validation` bridge를 복구한 뒤 시작한다.
  저장소 정본은
  `ops/systemd/system/postgresql@18-ai_do_ci.service.d/network-online.conf`다.
- Portal Inference Gateway user unit은 부팅 시 사용할 PATH를 명시하고 기존
  `.venv`에서 직접 시작한다.
- 폐기된 `rag-infra.service`는 표준 runtime 대상이 아니며 disabled/inactive다.
- 과거 MinIO 고아 데이터 정리는 일회성으로 완료했다. 재부팅 절차에서 삭제나
  별도 상시 무결성 monitor를 실행하지 않는다.
- NAS는 backup/archive 대상이다. NAS 장애만으로 PostgreSQL, MinIO, vector
  store 등 primary runtime을 중단하지 않는다.

## 안전 경계

- 계획된 maintenance에서는 두 DGX를 동시에 수동 재시작하지 않는다.
- 사용자 작업과 장기 worker job을 확인하고 시작 시각을 기록한다.
- `docker compose down -v`, volume 삭제, Redis queue 삭제, DB restore를 최초
  대응으로 실행하지 않는다.
- 운영 checkout이 `main`이고 clean인지 확인한다. 개발 checkout은 `dev`를
  유지한다.
- 재부팅은 배포를 대신하지 않는다. 코드 변경은 MR 병합 후 표준
  `pnpm prod:deploy`로 적용한다.
- 비밀값을 명령 출력이나 장애 기록에 남기지 않는다.
- 장애 node 하나만 진단하고 정상 peer는 계속 유지한다.

## 재시작 전 점검

### Portal

```bash
date --iso-8601=seconds
hostnamectl --static
uptime

systemctl is-system-running
systemctl --failed --no-pager
systemctl is-active docker containerd nginx postgresql@18-main.service ssh
systemctl is-active ai-do-tls-expiry-check.timer
pg_lsclusters
ss -lnt '( sport = :5432 )'
systemctl show postgresql@18-main.service -p Wants -p After

loginctl show-user "$(id -un)" -p Linger -p State
systemctl --user --failed --no-pager
systemctl --user list-units 'ai-do-*.service' --all --no-pager

git -C /projects/ai-do/prod status --short --branch
git -C /projects/ai-do/dev status --short --branch
docker ps --format 'table {{.Names}}\t{{.Status}}'

uname -r
cat /sys/module/nvidia/version
modinfo -F version nvidia
nvidia-smi
test ! -e /run/reboot-required || cat /run/reboot-required

cd /projects/ai-do/prod
pnpm prod:status
pnpm prod:smoke

cd /projects/ai-do/dev
pnpm dev:systemd:status
pnpm dev:smoke
pnpm inference-gateway:status
pnpm inference-gateway:smoke
```

`nvidia-smi`가 실패하거나 loaded module, disk module, userspace driver가 맞지
않으면 Gateway를 반복 재시작하지 않는다. 실행 kernel과 boot journal을 먼저
보존하고 driver/kernel 정렬 문제로 분리한다.

개발 PC는 raw container port가 아니라 `.env.local`의 공개 개발 endpoint를
사용한다. 현재 계약은 PostgreSQL `5432`, Redis `56380`, MinIO `59010`이다.
Redis `6379`와 MinIO `9000`은 container 내부 기본 포트이며 외부 개발 endpoint가
아니다.

### DGX Spark

```bash
for host in dgx-spark-102 dgx-spark-103; do
  ssh "$host" '
    systemctl is-system-running
    systemctl --failed --no-pager
    systemctl is-active docker vllm-qwen36-docker.service \
      ai-do-local-ai-backend.service ai-do-local-ai-backend-watchdog.timer
    systemctl list-timers ai-do-local-ai-backend-watchdog.timer --no-pager
    nvidia-smi
    free -h
    df -h /
  '
done

ssh dgx-spark-103 \
  'systemctl is-active haproxy; sudo haproxy -c -f /etc/haproxy/haproxy.cfg'
```

endpoint 기준 상태:

```bash
curl -fsS http://128.1.253.102:8000/v1/models | jq -r '.data[].id'
curl -fsS http://128.1.253.103:8001/v1/models | jq -r '.data[].id'
curl -fsS http://128.1.253.103:8000/v1/models | jq -r '.data[].id'

for url in \
  http://128.1.253.102:18080/health \
  http://128.1.253.103:18081/health \
  http://128.1.253.103:18080/health; do
  curl -fsS "$url" |
    jq -e '.ready == true and
      (.models | length == 4) and
      ([.models[].loaded] | all)'
done
```

세 vLLM endpoint의 실제 served model ID가 같아야 한다. 세 Gateway endpoint는
모든 모델이 loaded 상태여야 한다.

## 권장 재시작 순서

1. DGX 102를 재시작한다.
2. 102의 GPU, vLLM `/v1/models`, Gateway `/health`가 정상일 때까지 기다린다.
3. DGX 103을 재시작한다.
4. 103 replica endpoint와 HAProxy의 vLLM/Gateway endpoint를 모두 확인한다.
5. Portal host를 마지막에 재시작한다.
6. Portal root/user systemd, PostgreSQL listener, 컨테이너, GPU, 운영·개발
   smoke와 외부 URL을 확인한다.

전체 전원 복구처럼 동시 시작이 불가피하면 Local AI의 cold load가 끝날 때까지
일시적인 실패가 발생할 수 있다. watchdog의 시작 유예는 240초다. 이 구간에서
추가 재시작을 겹치지 말고 GPU, vLLM, Gateway journal과 endpoint를 먼저 확인한다.

## 재시작 후 검증

### DGX 102

```bash
ssh dgx-spark-102 '
  systemctl is-system-running
  systemctl --failed --no-pager
  systemctl is-active docker vllm-qwen36-docker.service \
    ai-do-local-ai-backend.service ai-do-local-ai-backend-watchdog.timer
  systemctl list-timers ai-do-local-ai-backend-watchdog.timer --no-pager
  nvidia-smi
'

curl -fsS http://128.1.253.102:8000/v1/models | jq -r '.data[].id'
curl -fsS http://128.1.253.102:18080/health |
  jq -e '.ready == true and ([.models[].loaded] | all)'
```

102가 정상일 때만 계획된 103 재시작으로 넘어간다.

### DGX 103과 HAProxy

```bash
ssh dgx-spark-103 '
  systemctl is-system-running
  systemctl --failed --no-pager
  systemctl is-active docker vllm-qwen36-docker.service \
    ai-do-local-ai-backend.service ai-do-local-ai-backend-watchdog.timer haproxy
  systemctl list-timers ai-do-local-ai-backend-watchdog.timer --no-pager
  nvidia-smi
  sudo haproxy -c -f /etc/haproxy/haproxy.cfg
'

curl -fsS http://128.1.253.103:8001/v1/models | jq -r '.data[].id'
curl -fsS http://128.1.253.103:8000/v1/models | jq -r '.data[].id'
curl -fsS http://128.1.253.103:18081/health |
  jq -e '.ready == true and ([.models[].loaded] | all)'
curl -fsS http://128.1.253.103:18080/health |
  jq -e '.ready == true and ([.models[].loaded] | all)'
```

### Portal

```bash
systemctl is-system-running
systemctl --failed --no-pager
systemctl is-active docker containerd nginx postgresql@18-main.service ssh
pg_lsclusters
ss -lnt '( sport = :5432 )'

systemctl --user --failed --no-pager
systemctl --user list-units 'ai-do-*.service' --all --no-pager
docker ps --format 'table {{.Names}}\t{{.Status}}'
nvidia-smi

cd /projects/ai-do/prod
pnpm prod:status
pnpm prod:smoke

cd /projects/ai-do/dev
pnpm dev:systemd:status
pnpm dev:smoke
pnpm inference-gateway:smoke
```

외부 경로도 확인한다.

```bash
for url in \
  https://dwdcc.kr/ \
  https://dev.dwdcc.kr/ \
  https://matomo.dwdcc.kr/ \
  https://grafana.dwdcc.kr/; do
  curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' "$url"
done
```

Grafana의 인증 redirect는 정상일 수 있다. 무조건 200만 요구하지 말고 HTTP
status와 `Location`을 함께 확인한다.

## 실패 대응과 완료 판정

실패 node에서는 해당 boot의 journal을 먼저 수집한다.

```bash
journalctl -b --no-pager -p warning
journalctl --user -b --no-pager -p warning
```

DGX에서는 실패한 node의 vLLM, Gateway, watchdog journal만 추가로 확인하고 정상
peer는 유지한다. Portal에서는 PostgreSQL이 loopback에만 열렸다면 network-online
dependency와 NIC 주소 할당 시각을 확인한다. 컨테이너의 단순 `running` 상태만으로
완료 판정하지 않고 공식 smoke를 실행한다.

재시작은 다음을 모두 만족해야 완료다.

1. Portal과 두 DGX가 `systemctl is-system-running=running`이고 failed unit이 없다.
2. Portal PostgreSQL cluster와 관리 LAN listener가 복구됐다.
3. Portal GPU와 두 DGX GPU가 정상이다.
4. 세 vLLM endpoint의 served model ID가 일치한다.
5. 세 DGX Gateway와 Portal Gateway가 모든 모델 loaded 상태다.
6. 운영·개발 status/smoke와 주요 외부 경로가 정상이다.
7. checkout branch와 dirty 상태, NAS 같은 비핵심 외부 의존성의 경고를 별도로
   기록했다.
