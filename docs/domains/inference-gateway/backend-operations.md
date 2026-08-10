# Inference Gateway 운영 문서

## 목적

`/projects/open-alm/open-alm-inference-gateway`는 Open ALM 메인 API/worker와 분리된 범용 추론
게이트웨이다. 소스는 별도 Git 레포
`http://128.1.253.101:8929/open-alm/open-alm-inference-gateway.git`에서 관리한다.
이 서비스만 띄워도 다른 프론트엔드/백엔드가 REST API로 embedding, rerank, Docling
문서 변환, ASR을 사용할 수 있어야 한다.

LLM 호출 정책, audit, 사용량/비용 귀속, throttling 계획은 이 문서가 아니라
[`../ai/gateway.md`](../ai/gateway.md)를 정본으로 본다. 이 문서는 GPU 추론 백엔드 운영만
다룬다.

운영 원칙은 단순하다.

```text
서비스 시작 = 모든 모델 풀로드
모델 하나라도 실패 = 서비스 시작 실패
기본값은 부분 로드/degraded/fallback 없음
```

DGX Spark처럼 Qwen vLLM과 같은 GPU에서 함께 운영하는 환경에서는 task별 enable flag로
모델 로드를 명시적으로 끌 수 있다. 기본값은 모두 enabled다. disabled task endpoint는
503을 반환한다.

## 모델

| task | API 모델명 | 실제 로드 모델 | 기본 revision |
|---|---|---|---|
| embedding | `dragonkue/snowflake-arctic-embed-l-v2.0-ko` | `dragonkue/snowflake-arctic-embed-l-v2.0-ko` | `55ec6e9358a56d56af759bc8372e970caf8c305f` |
| reranker | `dragonkue/bge-reranker-v2-m3-ko` | `dragonkue/bge-reranker-v2-m3-ko` | `2aca5884ecac490192af9ebd86836d9073d826cd` |
| docling | 해당 없음 | `docling.document_converter.DocumentConverter` | 해당 없음 |
| asr | `transcribe-v1` | `CohereLabs/cohere-transcribe-03-2026` | `32d9e4ba6271d78168c095c2f90bc173eaad97d2` |

ASR은 Open ALM 메인 API의 `asr_cohere_model` 기본값인 `transcribe-v1`을 공개
모델명으로 받는다. 내부적으로는 Hugging Face 모델
`CohereLabs/cohere-transcribe-03-2026`을 로드한다. ASR 요청의 `model` 값은
공개 모델명만 허용하며, 실제 HF 모델명은 요청 모델명으로 쓰지 않는다.
공개 모델명은 `OPEN_ALM_INFERENCE_GATEWAY_ASR_PUBLIC_MODEL`로 바꿀 수 있다.

ASR 모델은 Hugging Face gated 모델이다. Native 운영은 host의 Hugging Face token 파일을
직접 읽는다. 기본 token source는 `${HOME}/.cache/huggingface/token`이며, 필요하면
`.env`의 `OPEN_ALM_INFERENCE_GATEWAY_HF_TOKEN_FILE`로 다른 경로를 지정한다. 토큰 원문은
문서와 git diff에 남기지 않는다.

## DGX Spark 배치

102/103 양쪽에 inference-gateway API 호환 백엔드를 실행하고, 103 HAProxy가 두 replica를
묶는다. 아래 표는 상태 스냅샷이 아니라 고정 topology 계약이다.

| Endpoint | Role |
| --- | --- |
| `http://128.1.253.103:18080` | Open ALM application용 internal LB endpoint |
| `http://128.1.253.102:18080` | 운영 진단·replica 전용 102 endpoint |
| `http://128.1.253.103:18081` | 운영 진단·replica 전용 103 endpoint |

배치 계약:

```text
102: /etc/systemd/system/open-alm-local-ai-backend.service, vllm-qwen36-docker.service
103: /etc/systemd/system/open-alm-local-ai-backend.service, vllm-qwen36-docker.service
103 HAProxy: local_ai_api :18080 -> 127.0.0.1:18081, 192.168.100.102:18080
Required tasks: embedding, reranker, docling, asr
```

운영 unit 이름은 현재 `open-alm-local-ai-backend.service`이고 working directory는
`/srv/local-ai-backend`다. repository의 신규 설치 helper가 만드는
`open-alm-inference-gateway.service`와 이름이 다르므로 서버 상태 확인과 장애 대응에는 실제
운영 unit 이름을 사용한다. unit 이름 통합은 별도 롤링 변경으로 수행한다.

실제 상태는 문서의 `active` 문자열이 아니라 각 host의 `systemctl is-system-running`,
`systemctl --failed`, unit 상태와 `/health` 응답으로 판정한다. 세 Gateway endpoint는
`ready=true`이고 네 required task가 모두 loaded여야 한다.

Qwen vLLM도 같은 DGX Spark GPU에 올라가므로 inference-gateway 모델 수를 조정해야 할 때는
아래 flag를 사용한다.

| env | 기본값 | disabled 시 |
| --- | --- | --- |
| `OPEN_ALM_INFERENCE_GATEWAY_EMBEDDING_ENABLED` | `true` | `/v1/embeddings` 503 |
| `OPEN_ALM_INFERENCE_GATEWAY_RERANKER_ENABLED` | `true` | `/v1/rerank`, `/v2/rerank` 503 |
| `OPEN_ALM_INFERENCE_GATEWAY_DOCLING_ENABLED` | `true` | `/v1/convert/source` 503 |
| `OPEN_ALM_INFERENCE_GATEWAY_ASR_ENABLED` | `true` | `/v1/audio/transcriptions` 503 |

이 endpoint는 별도 인증 API가 아니므로 인터넷에 공개하지 않는다. 로컬 개발 PC가 공유 GPU
인프라를 직접 사용할 수 있도록 103의 application LB TCP `8000`과 `18080`은 관리 LAN에서
접근 가능하다. replica 직접 진단 포트 `8001`과 `18081`은 계속 다음 source만 허용하고
나머지는 deny한다.

- Open ALM portal server `128.1.253.101`
- replica 전용망 `192.168.100.0/24`

UFW의 다른 ingress는 기존 운영을 보존하기 위해 기본 allow를 유지한다. 2026-07-23 제한
변경 전 설정 backup은 각 DGX의 `/etc/ufw.pre-p0-inference-20260723`에 있고, 로컬 개발
접근 복구 전 103 규칙 snapshot은 `/etc/ufw.pre-open-local-dev-*`에 있다. Open ALM 운영
Nginx의 `/inference-gateway/`는 공개 HTTP 경로가 아니므로 계속 404를 반환한다. 방화벽을
변경할 때는 portal server와 관리 LAN 개발 PC에서 application endpoint가 200인지,
102/103 전용망의 peer health가 200인지 확인한다. replica 직접 진단 포트는 관리 LAN의
다른 source에서 계속 거부되어야 한다.

portal server에서 재확인:

```bash
curl http://128.1.253.103:18080/health
curl http://128.1.253.102:18080/health
curl http://128.1.253.103:18081/health
```

관리 LAN 개발 PC에서 application endpoint 재확인:

```bash
curl http://128.1.253.103:8000/v1/models
curl http://128.1.253.103:18080/health
```

## 실행

게이트웨이 repo checkout에서 직접 실행할 때는 `uv`가 만든 native Python runtime과
systemd user service가 정본 실행 방식이다. 먼저 host에 `uv`, `ffmpeg`, NVIDIA driver,
Hugging Face token 파일이 준비돼 있어야 한다.

```bash
cd /projects/open-alm/open-alm-inference-gateway
bash scripts/inference-gateway-service.sh sync
bash scripts/inference-gateway-service.sh install-user-service
bash scripts/inference-gateway-service.sh enable
bash scripts/inference-gateway-service.sh start
bash scripts/inference-gateway-service.sh status
bash scripts/inference-gateway-smoke.sh
bash scripts/inference-gateway-service.sh logs
```

Open ALM repo 루트에서는 wrapper script로 같은 작업을 호출할 수 있다.

```bash
pnpm inference-gateway:sync
pnpm inference-gateway:install
pnpm inference-gateway:enable
pnpm inference-gateway:start
pnpm inference-gateway:status
pnpm inference-gateway:smoke
pnpm inference-gateway:logs
```

중지:

```bash
cd /projects/open-alm/open-alm-inference-gateway
bash scripts/inference-gateway-service.sh stop

# Open ALM repo wrapper
pnpm inference-gateway:stop
```

systemd user service로 상시 유지할 때:

```bash
cd /projects/open-alm/open-alm-inference-gateway
bash scripts/inference-gateway-service.sh install-user-service
bash scripts/inference-gateway-service.sh enable
bash scripts/inference-gateway-service.sh start
```

DGX Spark 102/103의 현재 운영은 system-level native service다. 서버별 포트는
102가 `18080`, 103이 `18081`이고, 103 HAProxy가 allowlisted internal LB endpoint
`:18080`을 제공한다.

```bash
ssh dgx-spark-102 'systemctl is-enabled open-alm-local-ai-backend.service; systemctl is-active open-alm-local-ai-backend.service'
ssh dgx-spark-103 'systemctl is-enabled open-alm-local-ai-backend.service; systemctl is-active open-alm-local-ai-backend.service'
ssh dgx-spark-103 'systemctl is-enabled haproxy; systemctl is-active haproxy'
```

## API

기본 URL:

```text
http://127.0.0.1:18080
```

엔드포인트:

| endpoint | 용도 |
|---|---|
| `GET /health` | 모든 모델 풀로드 상태 확인 |
| `GET /v1/models` | 로드된 모델과 runtime 정보 확인 |
| `POST /v1/embeddings` | OpenAI-compatible embedding |
| `POST /v1/rerank` | 단순 rerank |
| `POST /v2/rerank` | Cohere-compatible rerank endpoint |
| `POST /v1/audio/transcriptions` | OpenAI-compatible ASR multipart |
| `POST /v1/convert/source` | Docling 문서 변환 |
| `GET /metrics` | Prometheus text metrics |

요청 제한 기본값:

| 항목 | 기본값 |
|---|---:|
| upload max bytes | 104,857,600 |
| embedding input count | 128 |
| rerank document count | 128 |
| text chars per item | 8,192 |
| embedding concurrency | 1 |
| rerank concurrency | 1 |
| ASR concurrency | 1 |
| Docling concurrency | 1 |

요청 `model`은 실제 로드된 모델과 일치해야 한다. 다른 모델명을 보내면 400으로 거절한다.
Embedding 요청은 `input_type="query"`일 때만 `prompt_name`을 적용한다. `prompt_name`을
직접 주지 않으면 `OPEN_ALM_INFERENCE_GATEWAY_EMBEDDING_QUERY_PROMPT_NAME` 기본값 `query`를 사용한다.
문서 chunk 색인 요청은 기본 `input_type="document"`라 query prompt를 붙이지 않는다.

예시:

```bash
curl http://127.0.0.1:18080/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"dragonkue/snowflake-arctic-embed-l-v2.0-ko","input":["테스트 문장"]}'
```

```bash
curl http://127.0.0.1:18080/v1/audio/transcriptions \
  -F "file=@sample.wav" \
  -F "model=transcribe-v1" \
  -F "language=ko"
```

오디오 디코딩에 실패한 업로드는 422 `Unable to decode audio upload.`로 반환한다.

## 장애 복구 및 요청 보호

PID가 남은 active-hang은 `Restart=`만으로 복구되지 않는다. 102/103에는
`open-alm-local-ai-backend-watchdog.timer`를 함께 설치하고 20초마다 localhost `/health`를
검사한다. 시작 후 240초는 모델 load를 위해 유예하고, 8초 timeout이 3회 연속 발생할 때만
unit을 재시작한다. 재시작 직전 peer `/health`가 serving인지 확인한다. 두 replica가 모두
실패하면 우선 노드 102만 먼저 재시작하고 103은 102가 복구될 때까지 재시작을 미뤄 동시
cold start를 막는다. 배포 파일은 `ops/systemd/system/open-alm-local-ai-backend-*`가 정본이다.

계획 점검 중에는 먼저 `/etc/open-alm/inference-gateway-watchdog.disabled`를 만들고 watchdog
service 실행이 no-op인지 확인한 뒤 backend를 중지한다. 점검 종료 후 sentinel을 제거하고
watchdog service를 한 번 실행한다. sentinel 없이 backend만 중지하면 watchdog이 장애로
판단해 다시 시작하는 것이 정상이다.

API `/readyz`는 같은 gateway의 embedding/rerank/Docling 상태를 각각 판정하되 `/health`
payload는 2초 TTL로 공유한다. active-hang 때 세 provider가 직렬로 5초씩 대기하지 않도록
gateway probe는 한 번만 수행한다.

103 HAProxy의 `local_ai_replicas`는 backend별 `maxconn 4`, `maxqueue 16`,
`timeout queue 30s`를 적용한다. 초과 부하는 backend 프로세스의 shared thread pool에
무한 적체시키지 않고 LB queue에서 제한한다.

vLLM 상태 확인은 [DGX Spark 운영 계약](dgx-spark-servers.md#점검)을 따른다.

watchdog 재확인:

```bash
ops/systemd/install-local-ai-backend-guard.sh --host dgx-spark-102 --profile dgx-spark-102
ops/systemd/install-local-ai-backend-guard.sh --host dgx-spark-103 --profile dgx-spark-103 --verify-haproxy
ssh dgx-spark-102 'systemctl is-enabled open-alm-local-ai-backend-watchdog.timer; systemctl list-timers open-alm-local-ai-backend-watchdog.timer --no-pager'
ssh dgx-spark-103 'systemctl is-enabled open-alm-local-ai-backend-watchdog.timer; systemctl list-timers open-alm-local-ai-backend-watchdog.timer --no-pager'
ssh dgx-spark-102 'systemctl show open-alm-local-ai-backend.service -p Restart -p RestartUSec -p TimeoutStopUSec'
ssh dgx-spark-103 'systemctl show open-alm-local-ai-backend.service -p Restart -p RestartUSec -p TimeoutStopUSec'
```

## ASR 구현 기준

`CohereLabs/cohere-transcribe-03-2026`은 transformers native 구현으로 로드한다.
즉 `AutoProcessor`와 `AutoModelForSpeechSeq2Seq`를 사용하되 `trust_remote_code=True`를
쓰지 않는다.

공개 API 모델명은 `transcribe-v1`이다. 운영자는 실제 HF 모델명과 공개 API
모델명을 분리해서 본다.

`trust_remote_code=True` 또는 remote `model.transcribe()` 경로는 운영 기준으로 쓰지 않는다.
ASR 경로를 바꿀 때는 샘플 음성과 한국어 업무 음성으로 smoke를 다시 확인한다.

## 주의

- 이 백엔드는 Open ALM 메인 API/worker와 독립된 범용 inference service다.
- Open ALM 메인 API/worker는 RAG embedding/rerank/OCR과 ASR provider adapter를 통해
  이 백엔드를 호출한다. 메인 API/worker 프로세스에 GPU 모델 로딩을 다시 추가하지 않는다.
- MCP/tool interface는 현재 범위가 아니다.
- Native runtime이므로 host에 `ffmpeg`와 NVIDIA driver가 설치되어 있어야 한다.
- DGX Spark 운영에서 task를 disabled로 둘 때는 caller가 503을 정상적인 capacity/config
  상태로 처리해야 한다.
