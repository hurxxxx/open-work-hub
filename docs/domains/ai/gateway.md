# AI Gateway

Open Work Hub의 생성형 모델 호출은 등록된 workload와 공용 실행 게이트웨이를 사용한다.
앱 코드는 provider SDK나 외부 HTTP endpoint를 직접 선택하지 않는다.

## 계약

- workload는 안정적인 ID, 소유 도메인, 허용 route, capability와 출력 토큰 한도를 등록한다.
- 관리자가 활성 provider와 모델을 선택하며 로컬 장애를 외부 provider로 자동 전환하지 않는다.
- 외부 전송은 데이터 분류, 마스킹, 승인 정책과 감사 이벤트를 통과해야 한다.
- 도구 실행은 workspace/app 권한과 discoverability를 검사하고 쓰기 작업은 승인 게이트를 사용한다.
- 모델 호출과 결과에는 actor, workspace, workload, provider/model, token 사용량과 trace ID를 남긴다.
- 자율 툴 루프는 `AgentRuntimeAdapter`로 등록하고 one-shot chat execution adapter와 분리한다.
  runtime 선택도 workload override의 일부이며 route 간 자동 fallback은 없다.

구현 정본은 `apps/api/src/open_work_hub_api/domains/ai/`와 등록 bootstrap이다.

## 로컬 OpenAI 호환 런타임

로컬 route의 전송 주소는 `OPEN_WORK_HUB_LLM_LOCAL_BASE_URL`, 요청 profile은
`OPEN_WORK_HUB_LLM_LOCAL_PROVIDER`가 정한다. 모델 선택은 환경 변수가 아니라 관리자 모델
카탈로그와 workload route 설정에 저장한다. `docker-model-runner` profile은 Docker Model
Runner의 OpenAI 호환 API를 사용한다. Qwen에서 `reasoning_effort=none`인 workload는
`chat_template_kwargs.enable_thinking=false`로 변환해 결과 본문에 출력 토큰을 집중시킨다.

개발 기본 예시는 `http://127.0.0.1:12434/engines/v1`이다. 모델 설치와 런타임 smoke는
`scripts/dev-local-qwen.sh`를 사용한다. 모델을 바꾸더라도 앱 코드는 수정하지 않고 관리자
카탈로그의 local 기본 모델 또는 workload 역할 매핑만 변경한다.

비스트리밍 호출의 `LlmCompletionResult`는 본문뿐 아니라 provider-neutral
`tool_calls`(`id`, `name`, `arguments`)도 전달한다. 앱은 provider 원본 응답을 직접 읽지 않고
등록 workload의 이 계약을 사용해 함수 인자를 파싱하고 자체 도메인 검증을 수행한다.
