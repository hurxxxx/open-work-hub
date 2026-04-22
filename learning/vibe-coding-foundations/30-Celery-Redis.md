# 30. Celery · Redis — 비동기 작업과 큐

> **한 줄 요약.** 오래 걸리는 일(파일 처리, 이메일 발송, AI 응답, 예약 작업)은 웹 요청과 분리해야 한다. **Celery**가 작업을 비동기 워커로 분리하고, **Redis**가 작업 큐를 관리한다.

> **🔑 한 마디로.** API는 작업을 큐에 등록한 뒤 즉시 응답하고, Celery 워커가 Redis 큐에서 작업을 가져와 백그라운드에서 처리하는 구조입니다.

### 큐 시스템 핵심 개념 정리

- API는 작업을 큐에 등록한 뒤 즉시 응답하고, 워커가 백그라운드에서 실제 처리를 수행합니다.
- 큐 적재와 실행을 분리하면 요청 처리 지연을 줄이고 서버 응답성을 유지할 수 있습니다.
- Redis 브로커는 작업 대기열을 관리해 워커 수평 확장과 부하 완충 역할을 수행합니다.

### ⚠️ 큐 도입에서 자주 듣는 오해

- **"FastAPI의 `BackgroundTasks`로 충분하다"** — 같은 프로세스 내에서 실행되므로 서버 재시작 시 작업 유실, 부하 분산 불가, 재시도 없음. 짧은 "fire and forget"엔 쓸 수 있지만 장기 작업엔 부적합합니다.
- **"async/await과 Celery는 같은 것이다"** — async는 **한 프로세스 안의 동시성**, Celery는 **요청과 별개의 프로세스에서 나중에 실행**. 층위가 완전히 다릅니다.
- **"Redis는 메모리라서 언제든 데이터가 날아간다"** — AOF(Append Only File, 모든 쓰기를 로그로 기록) 또는 RDB 스냅샷으로 영속화 옵션이 있습니다. 다만 캐시 용도는 사라져도 괜찮게 설계해야 합니다.
- **"Celery만 깔면 자동으로 신뢰성 있는 큐가 된다"** — **멱등성**(같은 작업 여러 번 실행해도 결과가 같음)·재시도·DLQ(Dead Letter Queue)를 직접 설계해야 합니다. 기본 설정 그대로 운영하면 중복 결제·중복 발송 같은 사고가 날 수 있습니다.
- **"Celery는 오래된 기술이라 피해야 한다"** — 2026년에도 Python 비동기 큐의 기본 선택지입니다. Dramatiq·arq·RQ·Temporal·Prefect 같은 대안이 있지만, 생태계·예제·모니터링 도구(Flower)의 두께는 Celery가 우위에 있습니다.

---

## 1. 왜 비동기 큐가 필요한가

### 1.1 동기 처리의 한계

```
사용자: "PDF 보고서 만들어 주세요"
서버: [30초 동안 PDF 생성 중...]
브라우저: ⌛️ 기다림
사용자: "서버 망가졌나?"
```

- 웹 요청은 대개 수 초 안에 응답해야 합니다. 30초 이상이면 사용자가 이탈합니다.
- 서버 워커가 오래 잡혀 있으면 다른 요청을 못 받음.

### 1.2 비동기 처리의 구조

```
사용자: "PDF 보고서 만들어 주세요"
서버: "작업 접수! id=1234 (즉시 응답)"
        ↓ 큐에 넣음
Celery 워커: 1234 작업 처리 → 결과 저장
사용자: 폴링 또는 알림으로 결과 수신
```

**긴 작업 = 백그라운드**. 요청은 빨리 끝내고, 실제 일은 별도 프로세스가.

---

## 2. Celery — 파이썬의 분산 작업 큐

### 2.1 무엇인가

**Celery 5.5** 는 2009년부터 존재하는 파이썬용 분산 **작업 큐(task queue, 비동기 작업 대기열)** 프레임워크입니다. 가장 오래되고 널리 쓰이는 선택지. 이 프로젝트의 워커 앱 코드 위치는 `apps/worker`.

### 2.2 구성 요소

```
[Client]  →  [Broker(Redis)]  →  [Worker(Celery)]  →  [Result Backend]
```

- **Client**: FastAPI 앱. 작업을 "던지는" 쪽.
- **Broker**: 작업을 담아두는 대기줄. Redis 또는 RabbitMQ.
- **Worker**: 실제로 작업을 실행하는 별도 프로세스.
- **Result Backend**: 작업 결과를 저장(Redis/DB). 결과가 필요 없는 경우 생략.

### 2.3 태스크 정의 예시

```python
# apps/api/src/.../tasks.py
from celery import Celery

app = Celery("aidoo", broker="redis://redis:6379/0", backend="redis://redis:6379/1")

@app.task
def send_welcome_email(user_id: int):
    # DB 조회, 이메일 발송 등
    ...
```

### 2.4 호출

```python
# FastAPI 쪽에서
send_welcome_email.delay(42)          # 즉시 반환, 큐에 적재
result = send_welcome_email.apply_async(args=[42], countdown=30)  # 30초 뒤 실행
```

### 2.5 예약 작업 (Celery Beat)

`beat` 라는 스케줄러가 주기적 작업을 자동 투입합니다.

```python
app.conf.beat_schedule = {
    "daily-cleanup": {
        "task": "tasks.cleanup_old_drafts",
        "schedule": crontab(hour=3, minute=0)
    }
}
```

이 프로젝트에서 활용될 예시:
- **일정한 주기로 알림 보내기** (곧 있을 회의 리마인드)
- **오래된 draft 정리**
- **AI 요약 재집계**

---

## 3. Redis — "In-Memory Everything"

### 3.1 무엇인가

**Redis 5.2**(REmote DIctionary Server, 원격 사전 서버)는 2009년 Salvatore Sanfilippo가 만든 **인메모리(in-memory, 주메모리 위에서 동작) 데이터 저장소**. 메모리에 키·값을 두는 초고속 DB이며, 동시에 Pub/Sub(Publisher/Subscriber, 발행/구독), 스트림, 큐, 캐시의 역할까지 합니다.

### 3.2 이 프로젝트의 Redis 용도

1. **Celery 브로커 + 결과 백엔드** (이 장)
2. **캐시** — 자주 조회되는 결과를 메모리에 저장해 DB 부담 경감
3. **세션/토큰 임시 저장** — 필요 시
4. **Rate Limit 카운터** — API 호출 제한 구현
5. **Pub/Sub** — SSE/WebSocket 브로드캐스트 경로로도 쓰임

한 서비스가 여러 역할을 하지만, 내부적으로 DB 번호를 0·1·2처럼 나눠 관리합니다.

### 3.3 특징

- **매우 빠름** — 메모리 기반, 보통 수만 ops/초.
- **데이터 타입 풍부** — String, List, Hash, Set, SortedSet, Stream.
- **영속 옵션** — RDB 스냅샷, AOF(Append Only File). 기본은 인메모리 + 주기적 저장.
- **클러스터·복제** 지원.

### 3.4 주의

- 메모리가 부족하면 TTL 설정한 키부터 삭제(정책). 절대 내용 의존 금지.
- "캐시는 언제든 사라질 수 있다"는 전제 위에 설계.

---

## 4. 왜 Celery + Redis인가

### 4.1 대안

| 도구 | 비고 |
|---|---|
| **Celery + Redis** | 파이썬의 표준. 풍부한 문서. 우리 선택. |
| **Celery + RabbitMQ** | 더 강한 메시지 보장. 운영 복잡. |
| **RQ (Redis Queue)** | 간단·경량. 기능 제한. |
| **Dramatiq** | Celery 대안으로 현대적 설계. 문법 간결. |
| **arq** | asyncio 네이티브·경량. Python 3.10+ 친화. |
| **FastAPI BackgroundTasks** | 같은 프로세스 내 짧은 작업용. 재시작 시 유실 위험. 장기 작업엔 부적합. |
| **Huey** | 소규모에 훌륭. |
| **Prefect / Airflow** | 데이터 파이프라인 오케스트레이션. "웹 요청의 백그라운드"보다는 배치 워크플로 중심. |
| **Temporal** | 장기 실행 워크플로의 상태 머신. 복잡한 비즈니스 워크플로에 강점. 러닝 커브 있음. |

### 4.2 우리 선택의 이유

- **성숙도**: Celery는 15년 이상 실전 검증. 2026년에도 Python 큐 1군.
- **생태계**: 모니터링(Flower), 스케줄러(Beat), 재시도/체인/그룹 기능 내장.
- **Redis 이중 역할**: 브로커 + 캐시 + Pub/Sub을 한 인프라로 커버.
- **운영 단순성**: RabbitMQ는 더 강력하지만, 이 프로젝트 규모엔 Redis로 충분.
- **대안과의 차이**: Dramatiq/arq는 더 현대적이지만, 우리는 스케줄러·모니터링·재시도 패턴 전부가 필요해 Celery가 실용적.

---

## 5. 신뢰성 있는 작업 처리의 개념들

### 5.1 Idempotency(멱등성)

"같은 작업을 여러 번 실행해도 결과가 같다"는 성질. 네트워크 불안정으로 Celery가 **재실행**할 수 있으므로, 중요한 작업은 멱등해야 합니다.

예: "결제 처리" 태스크가 두 번 실행돼도 같은 결제 건은 한 번만 되도록.

### 5.2 Retry(재시도)

```python
@app.task(bind=True, autoretry_for=(OperationalError,), retry_backoff=True, max_retries=5)
def sync_with_openai(self, prompt: str):
    ...
```

실패 시 지수 백오프로 재시도. 네트워크·일시 오류에 강함.

### 5.3 Dead Letter (죽은 편지)

계속 실패하는 작업은 별도 큐로 빼두고 사람이 조사. Celery는 `on_failure` 훅이나 외부 처리로 구현.

### 5.4 가시성

**Flower**(별도 오픈소스)는 Celery 실시간 대시보드. 큐 길이, 워커 상태, 실패율을 한눈에.

---

## 6. 동기/비동기/백그라운드의 위치

혼동 주의:

- **동기**: 호출자가 결과를 기다린다.
- **비동기(async)** (파이썬 문법): 한 프로세스 안에서 I/O를 기다리는 동안 다른 일을 하는 **동시성**. 여전히 같은 요청 안.
- **백그라운드 작업(Celery)**: 요청과 **분리된 프로세스**에서 나중에 돌리는 방식.

이 세 가지는 다른 층위입니다. AIDOO는 FastAPI의 `async` + Celery의 백그라운드를 같이 씁니다.

---

## 7. AI 시대의 큐 활용

AI 기능은 큐의 가치를 증폭시킵니다.

1. **긴 LLM 호출**: 문서 100장 요약 같은 건 수십 초. SSE로 스트림하거나 Celery로 뒤로 돌려 완료 시 알림.
2. **임베딩 배치**: 문서 업로드 시 임베딩 생성을 큐로 처리.
3. **RAG 인덱싱**: 대량 문서를 벡터 DB에 넣는 작업을 큐로 분산.
4. **비용 제어**: 급한 일과 배치 일을 **우선순위 큐**로 분리, 비싼 호출을 야간에.

---

## 8. 이 프로젝트의 실제 위치

Docker Compose 에 나란히 뜹니다.

```
services:
  redis:
    image: redis:7-alpine
  api:
    ...               # FastAPI
  worker:
    command: celery -A aidoo_api worker --loglevel=info
  beat:
    command: celery -A aidoo_api beat --loglevel=info
```

워커 코드는 `apps/worker` 아래에 위치하며, API와 같은 가상환경·의존성을 공유하되 실행 엔트리포인트만 다릅니다. 태스크 정의 자체는 `apps/api/src/aidoo_api/tasks/` 같은 폴더에 도메인별로 나뉘어 있습니다.

### 8.1 🏢 업무 시나리오

**케이스 — "회의록 자동 요약"**
1. 사용자가 회의록 탭에서 "요약하기" 클릭 → `POST /meeting/{id}/summarize`.
2. API는 Celery로 `summarize_meeting.delay(meeting_id)` 만 던지고 **즉시 202 Accepted + job_id** 반환.
3. 워커(`apps/worker`)가 Redis 큐에서 집어 OpenAI 호출 → 결과 DB 저장.
4. 프런트는 SSE 혹은 폴링으로 완료를 감지, 요약 내용을 표시.
5. 같은 `meeting_id`로 두 번 눌러도 **멱등 키**(meeting_id + 모델 버전)로 중복 호출 방지.

**케이스 — "매일 오전 9시 회의 리마인더"**
- Celery Beat 스케줄에 `remind_upcoming_meetings`를 crontab(hour=9)으로 등록.
- 워커가 해당 시각에 당일 회의를 조회해 참석자에게 Slack/메일 전송.
- 사람이 수동으로 `cron`을 관리하지 않아도 애플리케이션 코드 안에서 함께 버전 관리됩니다.

### 8.2 🛠️ 5분 실습

1. `docker compose ps` 로 `redis`, `worker`, `beat` 컨테이너가 떠 있는지 확인.
2. `docker compose logs -f worker` 로 워커 로그를 열어둔 상태에서,
3. API `/docs`에서 백그라운드 작업을 트리거하는 엔드포인트 하나(예: 큰 문서 임베딩)를 호출.
4. 워커 로그에 태스크 수신 → 처리 → 완료 라인이 찍히는 걸 실시간으로 관찰.

---

## 9. 핵심 요약

- **Celery**: 파이썬 표준 분산 작업 큐. 즉시 응답 후 뒤로 처리.
- **Redis**: 인메모리 초고속 저장소. 여기선 **브로커·결과·캐시** 역할.
- **Beat**: 예약 작업 스케줄러.
- 운영에서 **재시도·멱등성·모니터링**이 필수.
- 우리 선택 이유: 성숙도, Redis의 다역할, 문서/생태계.

---

## 10. 이해도 체크

1. 동기 처리만 쓰는 서버에 30초짜리 작업이 한꺼번에 100건 들어오면 왜 문제가 되는지 설명하세요.
2. "멱등성"을 실제 업무 사례로 설명해 보세요(예: 메일 발송, 결제, 보고서 생성).
3. RabbitMQ 대신 Redis를 브로커로 쓰는 선택의 장단점을 각각 한 가지씩.
4. "async/await"와 "Celery 백그라운드 작업"의 차이를 3문장 안에 설명하세요.
5. AI 프로젝트에서 큐가 특히 유용한 이유 두 가지를 들어 보세요.
6. `FastAPI BackgroundTasks`로 충분한 경우와, 반드시 Celery로 가야 하는 경우의 기준을 한 줄로 써 보세요.
7. Celery 대신 Dramatiq·arq·Temporal 중 하나를 선택한다면 어떤 프로젝트 특성에 적합할지 하나 골라 설명해 보세요.
