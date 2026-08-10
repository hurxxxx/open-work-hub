# DGX Spark Local LLM 운영 계약

상태: 운영 참고 문서
운영 변경 전에는 반드시 live endpoint와 배포 대상 환경 파일을 다시 확인한다.

이 문서는 DGX Spark replica와 load balancer를 Open ALM local LLM으로 연결하는 계약만
설명한다. 일시적인 메모리 사용량, 하드웨어 상태, SSH 키·지문, 현재 로드된 특정 모델명은
문서에 보관하지 않는다.

## 정본

- 애플리케이션의 기본 모델과 workload별 선택: 관리자 `LLM 관리`
- provider endpoint와 연결 설정: 관리자 `LLM 관리 > Provider`
- 각 vLLM 프로세스가 실제로 로드하는 모델: 서버의 `/srv/vllm/qwen36-docker.env`
- vLLM 시작 동작: `ops/vllm/start-qwen36-docker.sh`
- 관리 화면의 replica 진단 대상: `OPEN_ALM_MODEL_STATUS_DIAGNOSTIC_TARGETS_JSON`

관리자 설정은 이미 실행 중인 vLLM 프로세스의 모델을 교체하지 않는다. 먼저 서버 runtime을
변경하고 `/v1/models`를 확인한 다음, 관리자가 탐색·승인·기본 모델 선택을 수행한다.

## Topology

운영 구성은 두 개의 독립 vLLM replica와 하나의 load balancer endpoint다.

| Endpoint | 용도 |
| --- | --- |
| `http://128.1.253.103:8000/v1` | 애플리케이션용 local LLM endpoint |
| `http://128.1.253.102:8000/v1` | replica 직접 진단 |
| `http://128.1.253.103:8001/v1` | replica 직접 진단 |
| `http://128.1.253.103:18080` | inference gateway |

직접 endpoint는 장애 진단과 benchmark에만 사용한다. 애플리케이션 workload는 관리자에게
설정된 provider endpoint를 사용한다.

## 모델 변경 계약

서버 환경 파일에는 `MODEL_ID`를 반드시 명시한다. 시작 스크립트는 기본 모델명을 내장하지
않으며, served name의 기본값을 `MODEL_ID`와 동일하게 설정한다.

```env
MODEL_ID=<runtime-model-id>
SERVED_MODEL_NAME=<same-runtime-model-id>
REASONING_PARSER=<parser-if-required>
TOOL_CALL_PARSER=<parser-if-required>
VLLM_IMAGE=<validated-runtime-image>
```

호환 alias가 꼭 필요한 경우에만 `ALLOW_SERVED_MODEL_ALIASES=1`과
`SERVED_MODEL_NAMES`를 명시한다. 일반 모델 전환에서는 이전 모델명 alias를 남기지 않는다.
따라서 이전 FP8 모델명이 `/v1/models`에 계속 보이면 정상적인 호환 유지로 간주하지 말고
서버 환경의 served alias를 점검한다.

모델 변경 순서:

1. 한 replica의 runtime 환경에서 `MODEL_ID`와 모델별 parser 옵션을 변경한다.
2. 해당 replica를 재시작하고 `/v1/models`와 chat smoke를 확인한다.
3. 다른 replica도 같은 방식으로 변경한다.
4. load balancer `/v1/models`가 새 실제 모델명만 반환하는지 확인한다.
5. 관리자 `LLM 관리`에서 local provider 모델 탐색을 실행한다.
6. 새 모델을 승인하고 기본 모델을 명시적으로 선택한다.

탐색에서 더 이상 발견되지 않은 모델은 감사 이력으로만 보존된다. 일반 모델 목록에서는
숨겨지며, 기본 모델이나 workload가 이를 계속 참조하면 실행은 자동 전환되지 않고 실패한다.

## 진단 대상 선언

관리자 모델 상태 화면의 serving target은 local provider 설정에서 자동으로 만들어진다.
replica 직접 진단은 코드의 고정 102/103 목록이 아니라 다음 JSON 배열로 선언한다.

```env
OPEN_ALM_MODEL_STATUS_DIAGNOSTIC_TARGETS_JSON='[
  {"id":"dgx-spark-102","display_name":"DGX Spark 102","endpoint_url":"http://128.1.253.102:8000/v1","provider_id":"local","role":"redundancy"},
  {"id":"dgx-spark-103","display_name":"DGX Spark 103","endpoint_url":"http://128.1.253.103:8001/v1","provider_id":"local","role":"redundancy"}
]'
```

새 replica는 같은 구조의 항목을 추가한다. `role=redundancy`는 전체 상태에 반영되고,
`role=diagnostic`은 정보만 표시하며 전체 serving 상태에는 영향을 주지 않는다. API key는 이
JSON에 넣지 않고 provider 자격증명 설정을 재사용한다.

## 점검

```bash
curl http://128.1.253.103:8000/v1/models
curl http://128.1.253.102:8000/v1/models
curl http://128.1.253.103:8001/v1/models
curl http://128.1.253.103:18080/health
```

응답에서 다음만 확인한다.

- 각 replica와 load balancer가 동일한 실제 모델명을 제공한다.
- 이전 모델명이나 의도하지 않은 compatibility alias가 없다.
- 관리자 local provider 기본 모델이 그 실제 served name을 선택한다.
- 등록된 local workload readiness가 모두 정상이다.

서비스 재시작·rollback·watchdog 절차는
[Inference Gateway 운영 문서](backend-operations.md)를 따른다.
