# AI Gateway Contract and Roadmap

상태: 현재 정본

이 문서는 Open ALM의 AI Gateway 현재 계약, 구현 상태, 남은 로드맵을 설명하는 단일 정본이다.
AI Gateway 관련 역할 경계, LLM 호출 표준, 사용량/비용 집계 계획, throttling 계획은
다른 문서에 중복 작성하지 않고 이 문서로 링크한다.

## 범위

AI Gateway는 Open ALM 메인 API 안에서 확정된 LLM 실행 계획을 검증·실행·감사하는
실행 Module이다.
모델을 직접 서빙하는 GPU 추론 백엔드가 아니다.

| 영역 | 소유 |
| --- | --- |
| provider 활성화, endpoint, API key, 모델 discovery, 기본 모델 | LLM Provider control plane |
| discovery inventory의 서비스 사용 승인과 capability 확정 | Model Catalog control plane |
| LLM workload 등록과 workload별 route/provider/model/output cap | LLM Routing control plane |
| 이미지 provider, API key, supervisor/generation 모델, 실행 profile | Image Model Settings control plane |
| 선택 route가 external일 때 payload 판정·마스킹·차단·예외 | AI Security |
| 확정 실행 계획 검증, Adapter 실행, audit/usage | AI Gateway |
| domain context pack, task profile, prompt/message 조립 계약 | AI Gateway + 각 도메인 |
| LLM 호출 audit, token usage, latency, status, model 기록 | AI Gateway |
| 사용자/조직/워크스페이스/앱/기능별 비용 귀속, 비용 예측, throttling | AI Gateway 계획 범위 |
| embedding, rerank, Docling, ASR 모델 로딩/REST 서빙 | Inference Gateway |
| Qwen vLLM chat endpoint 운영 | Local LLM service |
| AI tool discovery/execution/approval | AI capability platform |

Inference Gateway는 `docs/domains/inference-gateway/`의 운영 문서를 따른다. 메인 API는
RAG embedding/rerank/OCR과 ASR provider adapter를 통해 그 백엔드를 호출하고, GPU 모델을
메인 API 프로세스에 다시 로드하지 않는다.

## 설계 기준

- AI capability와 LLM workload는 도메인이 `register_ai_capabilities(registry)`로 등록한다.
- `domains/ai/*`는 공통 실행 파이프라인, registry, tool/capability 계약, gateway 계약만 소유한다.
- `RegisteredLlmWorkload.workload_id`는 신규 LLM 호출의 관리·발견 정본이다.
  `mail.summarize`처럼 앱/기능별 namespaced 상수를 사용하고 사용자 입력을 받지 않는다.
- workload는 route, model, output-token cap을 독립 설정하는 실제 실행 기능
  단위다. 다단계 앱은 각 단계를 별도 workload와 task kind로 등록한다. 여러 app이
  같은 workload를 공유하는 것은 실행·예산 의미가 완전히 같을 때만 허용한다.
- 도메인 service와 worker는 공통 `execute_llm`/`stream_llm` Interface만 호출한다.
  호출자는 provider/model/pool을 선택하지 않고 서버가 확정한 workload/app/context를 제공한다.
- workload descriptor는 owner domain, app, legacy task kind, default/allowed route, allowed provider,
  execution kind, required model capability/role, i18n key, external-data behavior를 공통 발견
  계약으로 제공한다. execution kind를 지원하는 Adapter는 공통 실행 Module이 해석한다.
- Common workload 호출은 서버가 확정한 `workload_id`와 사용자-facing
  `app_id`를 필수로 전달한다. `AiGatewayRequest.app`에서 검증해
  `LlmTaskContext.app_id`와 audit `app_id`로 기록하며 빈 값이나 `unknown` fallback을
  허용하지 않는다. 이전되지 않은 provider 고유 호출의
  `AiExternalCapabilityRequest` envelope는 호환 보안/audit 경계로만 유지한다.
- 미등록 workload와 app/workload 불일치는 fail-closed다. `task_kind`는 예산·audit
  호환 키이며 route를 선택하지 않는다.
- workload route override가 local/external 선택의 유일한 정본이다. registry의
  `allowed_routes`를 위반하거나 provider/model이 준비되지 않은 route는 실행하지 않는다.
- provider 오류와 보안 차단은 실패로 반환하며 local/external 간 자동 fallback하지 않는다.
- 일반 workload의 기본 route는 local이지만 승인된 external Adapter를 제거하는
  의미가 아니다. 관리자가 workload별로 local/external을 선택할 수 있다.
  이미지 생성은 별도 Image Model Settings에서 활성 provider와 두 모델을 명시적으로
  선택하며 일반 LLM route에 섞지 않는다.
- 관리 가능한 provider 목록은 등록된 Provider Module에서 projection한다. provider를
  추가할 때 관리자 API/UI의 고정 enum을 함께 수정하지 않는다. 실제 endpoint, credential,
  기본 모델은 DB 설정이 정본이며 미설정 상태에서는 fail-closed한다.
- LLM Providers 화면은 provider 연결·자격증명·기본 endpoint·기본 모델과 서버측 모델
  discovery를 관리한다. 외부 provider discovery는 저장된 API key가 있어야 하며 key는
  browser로 반환하지 않는다. 모델 catalog는 발견된 inventory 중 서비스에서 사용할 모델과
  capability를 승인하고, LLM Routing은 승인된 모델만 앱/기능별 route·output cap에 연결한다.
  discovery 실패나 일시적인 모델 누락은 기존 승인과 route를 자동 변경하지 않는다.
- 관리자 콘솔의 `LLM 관리` section은 LLM Routing, LLM Providers, 모델 catalog,
  별도 Image Model Settings를 함께 소유한다. 이미지 API key·endpoint·supervisor 모델·
  generation 모델은 이미지 설정에만 저장하며 LLM catalog나 환경변수에 중복하지 않는다.
  `AI 보안` section은 외부 전송 보안만 소유하고 별도 감사 목록을
  복제하지 않는다. 보안 이력은 전역 `감사 로그`의 AI Security 필터로 조회한다.
- workload별 최대 출력 토큰 기본값은 local 32K/external 64K다. 관리자 override가
  실행 상한이며 호출부가 요청한 값은 선택 경로 상한으로 clamp된다.
- 선택 route가 external이고 AI security enforcement가 켜진 경우 payload safety 결과를
  scoped rule, data-protection action, 외부 앱 action, 외부 전송 예외와 함께 평가한다.
  development에서 enforcement가 꺼져 있으면 provider allowlist는 유지하지만
  scan/rule/masking은 우회한다. preview/production에서는 enforcement가 꺼진 external LLM과
  provider-native capability를 provider 호출 전에 fail-closed하고
  `ai_security_enforcement_required` 사유로 감사한다. 이 설정 오류는 security pipeline
  exemption보다 먼저 판정한다. provider-native 실행이 AI security DB context를 전달하지
  않은 경우도 preview/production에서는 enforcement 상태를 검증할 수 없으므로 같은 사유로
  fail-closed한다.
- 회사 민감정보, PII, 내부 URL, 보안 문서는 설정에 따라 `block_external` 또는
  `mask_and_send`로 처리한다. 보안 판정은 route를 변경하지 않는다.
- 내부 context, 민감도 라벨, 회사 민감정보, PII, 내부 URL, 보안 문서는 scope·사유·만료일이
  일치하는 승인 예외 대상이다.
- `credential`, 사용자 지정 차단 단어, 알 수 없는 민감 엔티티는 hard blocker이며 마스킹이나
  외부 전송 예외로 우회할 수 없다.
- AI security rule scope는 `user`, `org_unit`, `workspace`, `app`, `task`, `capability`, `provider`
  기준이다. 팀 scope는 사용하지 않는다.
- raw prompt/content는 audit/usage ledger에 저장하지 않는다. 사용자가 다시 열어야 하는 업무 대화
  본문은 `conversation_turns`에 저장한다.
- Web의 conversation stream runtime은 사용자·워크스페이스·앱 route·scope 단위로 browser tab
  안에서 공유한다. SPA route unmount는 실행을 중단하지 않으며 같은 AI 화면으로 돌아오면 진행
  상태나 저장된 완료 대화를 이어서 표시한다. 명시적 Stop만 현재 request를 취소한다. Browser
  reload, tab close, network-disconnect 이후 복구는 이 in-memory 계약에 포함되지 않으며 별도의
  persisted background-job protocol이 필요하다. 한 scope에서 실행 중인 동안에는 다른 대화
  선택·새 대화·현재 대화 삭제를 막아 단일 active run을 유지한다.
- 등록된 conversation scope의 `direct_response`는 검증된 서버 계산 결과나 고정된
  fail-closed 안내처럼 응답 문구가 서버에서 완전히 확정된 경우에만 사용한다. 생성형 답변,
  모델 재작성, provider fallback, 비용 회피를 위해 LLM/provider 실행을 우회하는 일반
  통로로 사용하지 않는다.
- `max_tokens`, provider, timeout을 service에서 임의 하드코딩해 workload/설정 누락을 숨기지 않는다.
- Provider SDK/HTTP, `core.llm`, 저수준 gateway는 승인된 Adapter와 공통 실행 Module
  밖에서 직접 호출하지 않는다. 새 Adapter가 필요하면 Core Enablement로 추가한다.
- write capability는 별도 write policy를 따른다. 기본 AI 동작은 read/search/summary이고 실제 write는 approval/ACL/audit/rollout gate가 필요하다.

## 이미지 모델 설정 전환 순서

이미지 provider 설정을 환경변수에서 DB 제어면으로 전환할 때는 다음 순서를 지킨다.
API와 worker가 같은 암호화 키와 DB 설정을 사용해야 하므로 일부 단계만 먼저 적용하지 않는다.

1. 새 이미지 승인 요청을 잠시 막고 기존 `queued`/`running` 작업을 비운다. 새 실행기는
   `image_execution_profile.v2`만 허용하고, 저장된 provider·Adapter 참조가 현재 활성 설정과
   다르면 fail-closed한다.
2. API와 worker 양쪽에 동일한 비어 있지 않은
   `OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`를 설정한다. 이 키는 provider API key 자체가
   아니며, DB credential 암복호화용 배포 secret이다.
3. 승인된 배포 절차에서 `cd apps/api && uv run --python 3.12 alembic upgrade head`를 실행한다.
4. legacy provider 값은 runtime `.env`에 남기지 않고 권한을 제한한 일회성 dotenv 파일로
   옮긴다. `import_legacy_llm_provider_settings.py --env-file <path>`와
   `import_legacy_image_model_settings.py --env-file <path>`로 preview한 뒤 각각 `--apply`를
   실행한다. importer는 명시한 파일의 allowlist key만 읽고, 이미 채워진 DB 값을 덮어쓰거나
   비밀값을 출력하지 않는다.
5. 관리자 `LLM 관리 > 이미지 모델`에서 활성 provider, endpoint, supervisor 모델,
   generation 모델과 readiness를 확인한다. 실행 시 endpoint·API key·두 모델은 작업 payload가
   아니라 이 DB 설정에서 다시 해석된다.
6. 운영 배포에서는 `llm_provider_settings_cutover,image_model_settings_cutover` pre-activation
   gate를 사용한다. gate는 worker를 quiesce한 뒤 preview/apply/idempotency, 이미지 broker/DB
   작업 0건, 활성 이미지 설정과 credential 복호화를 확인하고 나서만 restart를 허용한다.
7. smoke가 끝나면 일회성 dotenv 파일을 제거한다. `OPEN_ALM_IMAGE_ENABLED`와 파일 크기·reference 수·
   timeout 같은 배포 한도만 runtime 환경변수에 유지한다.

## 현재 구현

상태 분류:

- 완료: 현재 코드 경로가 있고, 해당 기능을 운영 기준으로 사용할 수 있다.
- 부분 구현: 코드 경로는 있으나 AI Gateway의 단일 정책/감사/비용/운영 요구를 아직 완성하지 못했다.
- 미구현: 현재 코드 경로가 없거나 문서/계획 수준이다.

| 항목 | 상태 | 근거와 남은 일 |
| --- | --- | --- |
| Gateway request/decision/context pack wrapper | 완료 | `AiGatewayRequest`, `AiGatewayContextPack`, `AiGatewayDecision`, sync/text/stream wrapper가 있다. |
| Unknown workload fail-closed | 완료 | registry에 없거나 app identity가 맞지 않는 workload는 Adapter 실행 전에 거부한다. |
| Allowed route validation | 완료 | registry가 허용하지 않은 local/external route는 실행하지 않는다. |
| Domain-owned LLM task registry | 완료 | 각 도메인이 `register_ai_capabilities(registry)`로 task/tool capability를 등록한다. |
| Registered LLM workload discovery | 완료 | `RegisteredLlmWorkload`, `register_llm_workload(...)`, `llm_workloads`, `get_llm_workload(...)`가 있다. legacy task 등록은 `workload_id=task_kind`인 호환 workload를 materialize한다. |
| Single workload route resolution | 완료 | registry default와 workload route override가 route/provider/model/output cap을 한 번만 결정한다. 별도 task policy는 없다. |
| External payload safety | 완료 | external route에만 enforcement를 적용한다. mask-eligible blocker는 scoped rule·global action·외부 앱 action에 따라 마스킹할 수 있고 승인 예외도 평가한다. 차단은 요청 실패이며 local로 바꾸지 않는다. |
| Local/external pool config | 완료 | local pool과 등록된 external Provider Module을 DB 설정으로 해석한다. 외부 provider 선택과 credential은 환경변수로 fallback하지 않는다. |
| Workload output cap | 완료 | workload registry와 관리자 route override가 local/external 최대 출력 토큰의 정본이다. 호출부 요청은 선택 경로 상한으로 clamp된다. |
| Gateway audit | 부분 구현 | `llm_call` audit에 app/task/pool/model/status/latency/usage/context metadata가 남고, external provider SDK/HTTP capability는 `ai_external_call` audit에 app/provider/capability/status/policy/usage metadata가 남는다. 별도 `ai_interactions` ledger에도 raw-free operational usage row를 저장한다. `app_id`는 interaction metadata에도 기록되지만 정규화된 app 비용 차원, `feature_id`, `cost_center_id`, 가격·비용 필드는 없다. |
| Raw prompt audit 미저장 | 완료 | audit helper와 `ai_interactions`는 raw prompt/content 대신 identity, decision, counters, error summary만 저장한다. 디버깅/업무 재열람이 필요한 대화 본문은 `conversation_turns`에 저장한다. |
| LLM 대화 DB 저장 | 부분 구현 | Web Search, Research Trends, Standards Monitor, Q&A assistant, Patent search/detail agent, PPT job chat-edit은 browser storage가 아니라 `conversations`/`conversation_turns`를 사용한다. 아직 모든 LLM UX가 이 패턴으로 검증된 것은 아니다. |
| Conversation scope direct response | 완료 | scope가 서버에서 확정한 고정 응답은 sync/stream 공통 transport와 대화 저장을 재사용하되 LLM/provider는 실행하지 않는다. assistant turn에는 server provenance를 남기고 LLM usage/audit은 만들지 않는다. |
| Token usage 집계 | 부분 구현 | admin usage dashboard가 prompt/completion/total token, user ranking, task/model breakdown을 보여준다. `ai_interactions`는 audit payload보다 조회하기 쉬운 사용량 ledger로 남는다. provider가 usage를 반환하지 않는 stream/call은 usage가 비어 있을 수 있고 비용 환산은 없다. |
| Admin usage UI | 부분 구현 | 관리자 콘솔에 LLM token/call/task/model 정보가 노출된다. 조직/워크스페이스/앱/비용별 화면은 없다. |
| Common workload execution adoption | 완료 | 생성형 LLM domain/worker 호출은 `execute_llm(...)`/`stream_llm(...)`와 registered workload를 사용한다. Web Search/PPT의 Anthropic native search와 Images/OpenAI Agents 같은 provider-native 동작은 등록된 Adapter 경계에 보존한다. API/worker direct-call guard가 신규 우회를 차단한다. |
| Context pack 표준화 | 부분 구현 | RAG/Q&A/legacy issues는 context pack을 사용한다. context pack에는 source kind, sensitivity label, content origin을 붙일 수 있고, provenance가 없는 context pack은 fail-closed로 internal context 취급한다. 다수 domain은 raw messages를 직접 구성한다. |
| External provider 선택 | 부분 구현 | external provider allowlist와 explicit provider 선택은 있다. per-user/per-org/per-workspace/per-app provider 권한, budget, fallback/canary 운영은 없다. |
| Registry-projected model settings | 완료 | `GET /api/v1/admin/ai-model-settings`가 provider/model, registry workload, route override, orphaned override를 하나의 snapshot으로 반환한다. LLM Providers는 기본 endpoint·연결·자격증명·모델 discovery를, 모델 카탈로그는 발견 inventory의 서비스 승인과 capability를, LLM Routing은 승인된 workload route/model/cap을 나눠 표시한다. 외부 discovery는 저장된 key를 서버에서만 사용하고 새 모델을 자동 승인하지 않으며 `registry_digest`/row version으로 stale mutation을 차단한다. |
| Image Model Settings | 완료 | `GET /api/v1/admin/image-model-settings`가 등록 image provider와 별도 실행 profile을 projection한다. endpoint/API key/supervisor 모델/generation 모델은 DB에 저장하고 API key는 암호화하며 browser와 execution profile에 반환하지 않는다. API와 worker는 동일 DB resolver를 사용하고 legacy image env로 fallback하지 않는다. worker는 v2 profile의 provider·Adapter·credential 참조만 검증하고 실제 endpoint·credential·모델은 현재 DB 설정에서 다시 해석한다. |
| AI security policy rules | 완료 | 전역 data protection 설정, 사용자/조직/워크스페이스/앱/task/capability/provider scope rule, custom block term, simulator가 있다. `block_external`, `mask_and_send`, `audit_only`, `inherit` effect를 지원한다. development에서는 전역 enforcement switch가 off일 때 pipeline을 우회하지만, preview/production의 external 실행은 off 상태를 설정 오류로 보고 provider 호출 전에 차단·감사한다. |
| AI security external transfer exceptions | 완료 | Platform Admin AI 보안 화면에서 외부 전송 예외를 생성/수정/삭제할 수 있다. 예외는 user/org/workspace/app/task/capability/provider scope, 허용 blocker, 만료일, 승인 사유를 갖는다. credential, 사용자 지정 차단 단어, 알 수 없는 민감 엔티티는 예외로 우회하지 않는다. |
| Cost attribution | 미구현 | workspace와 `app_id` identity는 기록되지만 app별 LLM 비용 집계, org unit/feature/cost center 차원과 가격·비용 계산이 없다. |
| Cost projection | 미구현 | 모델별 가격표, 환율, 월 누적/예상 비용 계산이 없다. |
| Quota/throttling | 미구현 | Redis 기반 RPM/TPM/daily/monthly cap, 차단 audit, 관리자 화면이 없다. |
| Direct LLM call guard | 부분 구현 | `tests/test_ai_gateway_direct_call_guard.py`가 gateway wrapper 외부의 신규 `core.llm.complete_chat*`/`resolve_chat_execution` 직접 호출을 막는다. API/worker provider SDK·HTTP와 저수준 gateway까지 승인된 Adapter 외 예외 없이 막는 확장이 남아 있다. |
| LiteLLM integration | 미구현 | 현재 판단은 미도입이다. 재검토 조건을 만족할 때 별도 결정한다. |

## 일반 AI Gateway 기능 대비 커버리지

현재 구현은 "AI Gateway phase 1 foundation"이다. workload routing, external payload
masking/block enforcement, audit의 기반은 있지만, 일반적인 enterprise AI Gateway가 제공하는 보안/비용/운영
기능이 모두 들어간 상태는 아니다.

| 일반 기능 | 현재 상태 | 판단 |
| --- | --- | --- |
| 내/외부 LLM 라우팅 | 부분 구현 | workload route override가 local/external과 provider/model을 선택한다. 사용자/조직/워크스페이스별 동적 route나 비용 기반 운영 룰은 없다. |
| 보안 정책 기반 외부 API/도구 egress 판별 | 부분 구현 | AI runtime의 planning/search/quality 일부는 `external_egress.v1`로 provider allowlist, PII, 민감 엔티티, 사용자 외부검색 금지 의사를 평가한다. `AiGatewayRequest`와 외부 provider SDK/HTTP capability envelope는 공통 `boundary_safety` scanner와 masking policy를 적용하고 raw-free decision metadata를 남긴다. 아직 모든 tool/일반 외부 HTTP 호출에 적용되는 outbound proxy는 아니다. |
| PII 탐지 | 부분 구현 | 주민등록번호, 이메일, 국내 전화번호 정규식 탐지가 있다. 일반 DLP 수준의 이름/주소/계좌/카드/여권/사업자번호/파일 내 개인정보 탐지는 없다. |
| PII 마스킹/토큰화 | 부분 구현 | `mask_and_send`가 지원되는 text payload의 PII를 마스킹한 뒤 외부 provider로 보낸다. unsupported content, privacy-filter 실패, hard blocker가 있으면 전송하지 않는다. 범용 문서/바이너리 토큰화 계층은 없다. |
| 기업 민감정보 sanitization | 부분 구현 | external egress sanitizer와 `mask_and_send`가 회사 민감정보, PII, 내부 URL, 보안 문서를 감지·제거하거나 차단한다. credential과 custom block term은 항상 차단한다. gateway 전체의 모든 도구/응답에 적용되는 DLP 계층은 아니다. |
| Prompt guard/jailbreak 방어 | 미구현 | allow/deny prompt rule, semantic guard, prompt-injection classifier, policy violation 차단 계층이 없다. |
| Output moderation/응답 검열 | 미구현 | 모델 응답의 개인정보/민감정보/정책 위반을 후처리 차단하거나 마스킹하는 공통 계층이 없다. |
| Provider/model access control | 부분 구현 | global external provider allowlist와 explicit provider 검증은 있다. AI security rule의 provider scope로 외부 호출 정책을 조정할 수 있지만, model별 세부 권한은 없다. |
| 사용량/비용 관측 | 부분 구현 | `llm_call` audit와 admin token 집계가 있다. provider/model 단가, 조직/워크스페이스/앱/기능별 비용 귀속, 비용 예측은 없다. |
| Quota/throttling/rate limit | 미구현 | 조직/워크스페이스/앱/사용자/task/model별 RPM/TPM/daily/monthly cap과 pre-call 차단이 없다. |
| Retry/fallback/circuit breaker | 미구현 | core LLM 경로는 의도적으로 cross-pool fallback을 하지 않는다. provider fallback/canary/circuit breaker 운영 계층은 없다. |
| Cache/semantic cache | 미구현 | 동일/유사 prompt 응답 캐시나 semantic cache가 없다. |
| Virtual key/tenant key isolation | 미구현 | gateway virtual key, per-key budget, partner-facing gateway API key가 없다. |
| Admin policy UI/API | 부분 구현 | `LLM 관리`에서 Provider 연결·자격증명·기본 모델/catalog와 workload route/model/cap을, `AI 보안`에서 external data protection, scoped security rule, external transfer exception, simulator를 관리한다. 감사 이벤트는 전역 `감사 로그`의 AI Security 필터로 조회한다. 세부 provider 권한, 비용 한도, throttle은 아직 없다. |

구현된 핵심 경로:

- `apps/api/src/open_alm_api/domains/ai/gateway.py`
  - `AiGatewayRequest`
  - `AiGatewayContextPack`
  - `AiGatewayDecision`
  - `complete_gateway_chat`
  - `complete_gateway_chat_text`
  - `complete_gateway_chat_stream`
  - `complete_resolved_gateway_chat_stream`
- `apps/api/src/open_alm_api/domains/ai/boundary_safety.py`
  - 외부 LLM/API 전송 전 PII, 내부 context, 민감 라벨, 보안/credential/기업 민감 엔티티 판정
  - gateway와 external capability envelope가 공유하는 raw-free safety decision
- `apps/api/src/open_alm_api/domains/ai/masking.py`, `privacy_filter.py`
  - mask-eligible text span 치환, privacy-filter 연동, post-mask 재검사와 fail-closed 처리
- `apps/api/src/open_alm_api/domains/ai/external_gateway.py`
  - `AiExternalCapabilityRequest`
  - provider SDK/HTTP 호출 전 allowlist, PII, 내부 context, 민감 라벨, 민감 엔티티 검사
  - SDK 고유 기능을 유지하는 sync/async execution envelope
  - raw input을 저장하지 않는 `ai_external_call` audit 기록
- `apps/api/src/open_alm_api/domains/ai/interactions.py`
  - `ai_interactions` raw-free usage ledger
  - audit보다 조회가 쉬운 token/usage/source/task/provider/conversation metadata 저장
- `apps/api/src/open_alm_api/core/llm.py`
  - resolved workload execution의 provider-neutral completion/stream transport
  - external provider allowlist와 pool health
  - local/external pool health
  - provider-neutral completion/stream result
  - `llm_call` audit 기록
- `apps/api/src/open_alm_api/domains/ai/registry.py`
  - domain-owned registered LLM workload/task/tool/capability registry
  - stable workload discovery snapshot과 legacy task compatibility materialization
  - gateway tool adapter registry
  - discoverability predicate와 approval-required tool guard
- `apps/api/src/open_alm_api/core/llm_model_profiles.py`
  - provider/model별 payload shaping, reasoning effort, prompt truncation profile
- `apps/api/src/open_alm_api/domains/images/model_settings_service.py`
  - 이미지 provider/credential/model/profile의 DB-only resolution과 readiness
- `apps/api/src/open_alm_api/domains/admin/router.py`
  - audit payload 기반 LLM call/token/user/task/model 집계
- `apps/web/src/platform/admin/admin-console.tsx`
  - 관리자 사용량 화면의 LLM token, task/model breakdown 표시
- `apps/api/src/open_alm_api/domains/conversations/app_scope_adapters.py`
  - 앱별 대화 scope ref와 서버 소유 `ConversationExperience` 중앙 등록
  - 공용 대화 CRUD의 owner app entitlement와 선택적 generic chat workload 선언
  - Web Search/Q&A/Patent/PPT처럼 앞으로 늘어나는 LLM UX가 동일 conversation 저장 계약을 사용하도록 함
- `apps/api/src/open_alm_api/domains/conversations/app_persistence.py`
  - 앱 대화 생성/재사용, user/assistant turn append, 최근 turn prompt 재사용 helper

현재 gateway wrapper 사용처:

- RAG grounded answer
- Q&A assistant answer generation
- legacy issues assistant/search/conversation
- Mail summary/reply
- Meeting insights
- Document translate
- Patent analysis
- Patent automation invoice extraction
- Spec compare extraction/comparison/reporting
- FMEA compare AI analysis
- News/industry report curation
- Writing assistant
- worker meeting summary, recording local agent, PPT local generation
- AI chat/router sync and stream path
- AI agent loop and final-answer recovery path
- Web Search Anthropic Messages SDK stream
- Images OpenAI Agents SDK brief/image generation
- PPT worker Claude raw HTTP design/research/image prompt calls

아직 core LLM을 직접 호출하는 주요 사용처:

- gateway wrapper 내부의 low-level delegation

provider SDK/HTTP 직접 호출의 이전 원칙:

- Provider 고유 tool, stream, trace, result object가 필요하면 workload `execution_kind`를
  지원하는 Adapter 내부에서만 다룬다.
- Adapter는 공통 resolved execution의 정책 판정 후 input만 받고 raw secret/content를
  audit에 남기지 않는다.
- 이전되지 않은 기존 `AiExternalCapabilityRequest` 경로는 호환 부채로만 유지하고
  신규 앱이나 기능에서 복제하지 않는다.

## 대화 본문 저장 정책

운영 원칙:

- `audit_logs`와 `ai_interactions`에는 raw prompt/output을 저장하지 않는다.
- 사용자가 업무 화면에서 다시 열어야 하는 대화 본문은 `conversation_turns.content`에 저장한다.
- `conversation_turns.meta`에는 렌더링/디버깅에 필요한 제한된 metadata만 저장한다.
- scope가 서버에서 만든 artifact는 live 응답과 history replay에 같은 ID를 사용하고,
  assistant turn의 `meta.artifacts`에 `id`, `type`, `title`, 선택적 `language`, `content`,
  `status`를 저장한다. 서버 소유 artifact type은 모델이 생성한 markup으로 대체할 수 없으며,
  예약 타입과 세부 payload 계약은 해당 앱 문서를 정본으로 본다.
- 브라우저 localStorage/sessionStorage는 LLM 대화 본문 저장소로 사용하지 않는다.
- 제품 검색 최근 기록, 패널 폭 같은 비-LLM UX 편의 상태는 브라우저 저장을 허용할 수 있다.

### Scope direct response

`ConversationScopeTurnContext.direct_response`는 scope adapter가 데이터 검증과 정책 판정을
끝낸 뒤 응답 본문을 완전히 확정한 경우에만 사용한다. 현재 대표 사용처는 과거차 문제점의
exact-analysis fail-closed 응답이다. 이 계약은 임의의 생성형 응답을 Gateway 밖에서
실행하거나 provider/model 정책을 건너뛰는 확장 지점이 아니다.

- `direct_response`가 있으면 sync와 stream transport는 Gateway resolution과
  LLM/provider 호출을 실행하지 않고 같은 서버 본문과 scope artifact를 반환한다.
- user/assistant turn은 일반 scope 대화와 같은 `conversations`와
  `conversation_turns`에 저장한다. assistant turn의 provenance는
  `policy=scope_direct_response`, `provider=server`, `chosen_pool=null`,
  `decision_reason=scope_direct_response`로 남긴다.
- direct transport에서는 추가 LLM 호출이 없으므로 token usage나 `llm_call` audit,
  `ai_interactions` usage row를 합성하지 않는다. scope adapter가 direct response를
  결정하기 전에 수행한 등록 workload의 intent/planner 호출은 정상 사용 기록으로 남는다.
  위 provenance meta는 history와 운영 디버깅을 위한 서버 응답 출처이며 LLM 사용 기록이
  아니다.
- scope adapter는 사용자 입력이나 모델 출력을 그대로 `direct_response`로 전달하지 않는다.
  서버 계산으로 확정된 짧은 응답 또는 고정된 fail-closed 문구만 허용하며, 생성·요약·번역이
  필요하면 등록된 workload와 공통 execution Interface를 사용한다.

현재 DB-backed conversation scope:

| scope_ref | 용도 | owner app | generic chat workload | scope_resource_id |
| --- | --- | --- | --- | --- |
| `web_search` | 일반 Web Search assistant | `web-search` | 없음 | `default` |
| `research_trends` | Research Trends assistant | `research-trends` | 없음 | `default` |
| `standards_monitor` | Standards Monitor assistant | `standards-monitor` | 없음 | `default` |
| `qna_assistant` | 회사 Q&A assistant | `qa-assistant` | 없음 | `company` |
| `patent_agent` | 특허 검색 agent | `patent-compose` | 없음 | 검색 context hash |
| `patent_brainy` | 특허 상세 Brainy agent | `patent-compose` | 없음 | 상세 context hash |
| `ppt_job` | PPT job chat-edit | `ppt-assistant` | 없음 | `ppt_jobs.id` |
| `meeting` | Chatbot의 회의 handoff | `chatbot` | `chatbot` | `meetings.id` |
| `legacy_issues` | 과거차 문제점 AI 분석 | `legacy-issues` | `legacy_issues.conversation_answer` | `workspace` |

공용 `/chatbot/conversations*` transport는 URL의 `chatbot` 문자열이 아니라 등록된
`ConversationExperience.owner_app_id`를 실행 시점에 검사한다. 신규 대화는 요청 scope,
후속 대화는 DB에 저장된 scope가 정본이다. scope 없는 대화는 standalone `chatbot`으로
해석한다. `chat_workload_id`가 없는 scope는 공용 conversation 저장만 재사용하며 generic
`/chatbot/chat*` 실행은 fail-closed한다. 등록된 owner app이나 workload가 없거나 서로
불일치하면 플랫폼 extension bootstrap이 실패한다.

신규 LLM UX 추가 기준:

1. 실제 실행 기능 단위 namespaced `workload_id`를 정의하고 `register_llm_workload(...)`로 descriptor를 등록한다.
2. local/external 최대 출력 토큰(기본 32K/64K), audit/external-data 정책, execution kind/capability를 검증한다.
3. scope adapter에 `ConversationExperience(owner_app_id, chat_workload_id)`를 등록한다.
   자체 send router만 사용하는 앱은 `chat_workload_id=None`으로 두고, 공용 chat runtime을
   재사용하는 앱만 자기 앱에 등록된 workload를 지정한다.
4. API request/response에 선택적 `conversation_id`를 추가한다.
5. workspace 화면에서 실행되는 앱은 현재 workspace key를 request에 포함해 history 저장 workspace와
   conversation list 조회 workspace가 어긋나지 않게 한다.
6. 첫 요청은 conversation을 생성하고 `conversation_attached` 또는 response field로 id를 반환한다.
7. user turn은 LLM 호출 전에 저장하고, assistant/error turn은 응답 확정 후 저장한다.
8. common execution/audit context에 같은 `conversation_id`, `workload_id`, 서버가 확정한
   `app_id`를 전달한다.

## 사용량과 비용

현재 구현된 것:

- `llm_call` audit payload에 `workspace_id`, `app_id`, `actor_user_id`, `principal_kind`,
  `task_kind`, `policy`, `chosen_pool`, `model`, `status`, `latency_ms`, `usage`,
  `max_tokens`, `context_strategy`, `finish_reason`이 남는다.
- 관리자 사용량 대시보드가 LLM call 수, 성공/오류/취소 수, prompt/completion/total token,
  사용자별 token ranking, task/model breakdown을 집계한다.

아직 없는 것:

- 조직/워크스페이스/앱/기능별 LLM 비용 집계
- 명시적 `feature_id`/`cost_center_id` gateway audit field
- 모델별 단가와 환율 기준
- 원화/달러 비용 환산
- 월별 예측 비용
- 조직/워크스페이스/앱/사용자 기준 quota/throttling

비용 기능의 세부 schema와 집계 차원은 승인된 설계가 없다. 구현 전 별도 결정으로 확정한다.

## Throttling

현재 LLM quota/throttling은 구현되어 있지 않다.

throttling key, counter 방식, 차단 audit shape는 승인된 설계가 없으므로 구현 전에 별도 결정한다.

## LiteLLM 판단

현재 범위에서는 LiteLLM을 기본 구성에 넣지 않는다.

현재 provider 범위는 내부 LLM, 직접 운영 vLLM, OpenAI, Anthropic, Gemini다.
이 범위에서는 Open ALM 내부 gateway에 audit, 비용 집계, 간단한 throttling을 추가하는
편이 운영 복잡도가 낮다.

LiteLLM 재검토 조건:

- provider 수가 크게 늘어난다.
- virtual key, per-key budget, provider별 fallback/canary가 운영 요구가 된다.
- 외부 조직/파트너가 Open ALM 밖에서 gateway API를 직접 소비한다.
- 모델 라우팅 정책을 코드 배포 없이 운영자가 자주 바꿔야 한다.
- 여러 앱/서비스가 같은 외부 LLM proxy를 공유해야 한다.

## 남은 리스크

### LLM 호출 진입점 분산

신규 LLM 호출은 registered workload와 공통 execution Interface를 통해야 한다.
provider-native 기능은 승인된 Adapter 안에서만 SDK/HTTP를 사용할 수 있다. API/worker
direct-call guard는 domain/worker의 provider SDK/HTTP, `core.llm`, 저수준 gateway 우회를
차단하며 예외 allowlist 변경은 독립 플랫폼 정책 검토가 필요하다.

AI Gateway는 현재 LLM/provider capability 경계다. ASR, embedding/rerank/OCR, Inference Gateway
백엔드 호출, 일반 비-LLM 외부 HTTP 호출까지 모두 대체하는 outbound proxy는 아니다.

Inference Gateway 운영 상태와 서비스 이름은 `docs/domains/inference-gateway/`를 정본으로 본다.

## 검증 기준

AI Gateway 또는 LLM task/capability 변경 시 최소 검증:

```bash
cd apps/api
uv run --python 3.12 --group dev python -m pytest tests/test_ai_gateway.py -q
uv run --python 3.12 --group dev python -m pytest tests/test_ai_external_gateway.py -q
uv run --python 3.12 --group dev python -m pytest tests/test_platform_adapter_registries.py -q
uv run --python 3.12 --group dev python -m pytest tests/test_ai_gateway_direct_call_guard.py -q
uv run --python 3.12 --group dev python -m pytest tests/test_admin_usage.py::test_admin_usage_dashboard_aggregates_user_content_and_llm_usage -q
python -c "from open_alm_api.platform_extensions import initialize_platform_extensions; initialize_platform_extensions()"
```

문서만 바꿀 때:

```bash
git diff --check
```

## 관련 문서

- [AI write policy](write-policy.md)
- [Legacy Issues AI Search](../../apps/legacy-issues/README.md)
- [Inference Gateway 운영 문서](../inference-gateway/backend-operations.md)
- [AI HUB 전략 색인](../../current/ai-hub-transition-index.md)
- [현재 구현 상태](../../current/project-status.md)
- [ADR 0001: AI Platform Extensibility Contracts](../../../adr/0001-ai-platform-extensibility.md)
- [ADR 0002: MCP-First AI Capability Platform Contracts](../../../adr/0002-mcp-capability-platform.md)
- [ADR 0005: Registered LLM Workload and Common Execution Interface](../../../adr/0005-registered-llm-workload.md)
