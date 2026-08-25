# LLM-Friendly Development

이 문서는 Open Work Hub를 LLM/agent와 함께 변경할 때 코드가 잘 검색되고, 좁게 이해되며,
안전하게 수정되도록 유지하는 개발 구조·추상화·진입점 판단의 정본이다. 루트 `AGENTS.md`에는
핵심 규칙만 두고 구현 판단이 필요하면 이 문서를 참조한다.
`vibe-coding-harness.md`, `composable-abstractions.md`, `ui-components.md`는 각각 검증,
추상화 세부 판단, UI 재사용을 위한 보조 문서이며 코드 구조 판단이 충돌하면 이 문서를 우선한다.

## 핵심 원칙

- 진입점은 적게, 책임은 명확하게 둔다. 한 도메인의 주요 orchestration은
  `application.py`, `service.py`, `router.py`처럼 예측 가능한 이름에 둔다.
- 추상화는 얇게 둔다. registry, adapter, plugin loader는 런타임 확장성이 실제 요구될 때만
  추가한다.
- LLM이 검색할 수 있는 이름을 쓴다. `retrieval`, `rag`, `keyword`, `rerank`,
  `source_catalog`처럼 도메인 용어와 코드 용어를 맞춘다.
- 호환 경로는 유지한다. 새 진입점을 만들더라도 기존 REST/MCP/tool 응답 모양은 wrapper로
  보존하고 명시적인 폐기 절차 없이 제거하지 않는다.
- 복잡한 동작은 데이터 구조로 노출한다. profile, source descriptor, method list,
  degraded reason처럼 실행 결과를 관찰 가능한 필드로 남긴다.
- 특정 사용자 질문을 맞추는 분기는 금지한다. intent, operator, filter, source 같은 일반
  schema로 표현한다.

## 생성형 LLM 호출 진입점

- 신규 앱과 기존 기능의 모든 생성형 LLM 호출은 도메인의
  `register_ai_capabilities(registry)`에서 `RegisteredLlmWorkload`를 먼저 등록한다.
- `workload_id`는 `mail.summarize`, `meeting.summary`처럼 앱/기능 의미가 유지되는 namespaced
  서버 상수다. 사용자 입력이나 provider/model명으로 동적 생성하지 않는다.
- workload는 실제 실행 기능 단위다. 한 앱의 추출·비교·생성 단계가 route, model 또는
  output-token budget을 따로 가져갈 수 있으면 각각 등록한다. 범용 generation workload로
  서로 다른 앱 기능을 묶지 않는다.
- 도메인 service와 worker는 `apps/api/src/open_work_hub_api/domains/ai/gateway.py`의 공통
  `execute_llm`/`stream_llm` 인터페이스만 호출한다. provider, model, pool, endpoint,
  credential, retry/fallback은 호출자의 선택 인자가 아니다.
- Provider SDK/HTTP와 저수준 `core.llm`/gateway 호출은 승인된 Adapter와 공통 실행 모듈 뒤로
  격리한다. 앱 로컬 wrapper, 별도 registry, direct-call guard 예외를 추가하지 않는다.
- 기존 외부 LLM의 provider-native tool/stream/trace는 승인된 Adapter 안에 보존한다. 관리자가
  workload별 route와 model을 선택하며 route 사이에 자동 fallback을 추가하지 않는다.
- workload descriptor는 `task_kind`, 허용 route, execution kind, model capability,
  local/external 출력 상한, audit/tracing metadata, 외부 전송 정책과 관리자 표시용 i18n key를
  하나의 발견 계약으로 노출한다. 관리자 화면은 registry snapshot을 사용하고 호출부 목록을
  따로 하드코딩하지 않는다.
- 최대 출력 토큰 플랫폼 기본값은 local 32K, external 64K다. 호출부는 관리자 상한보다 작은
  값만 요청할 수 있다.
- local/external 선택은 workload route override에서만 관리한다. AI security는 이미 선택된
  external payload를 allow/mask/block/audit할 뿐 route를 바꾸지 않으며 block 시 호출이 실패한다.
- `execution_kind="agent"`는 허용된 `AgentRuntimeAdapter`를 사용한다. one-shot chat adapter와
  agent runtime을 호출부에서 섞지 않는다.
- embedding, rerank, OCR, ASR은 생성형 LLM workload가 아니며
  `docs/domains/inference-gateway/`와 각 registry/Adapter 계약을 따른다.

새 LLM 기능의 최소 변경 단위는 안정적인 `workload_id`, registry descriptor, local/external 출력
상한, 공통 인터페이스 호출, audit/external-data 정책과 등록/direct-call guard 테스트다. 필요한
Adapter나 실행 종류가 없으면 기능 코드에서 우회하지 말고 공통 AI 실행 경계에 먼저 추가한다.

Web Search는 external-only 등록 workload다. 현재 `web_search.answer`가 승인된 Anthropic native
`web_search` Adapter를 사용하며 local route나 오류 시 local fallback을 추가하지 않는다. 자세한
계약은 [AI Gateway](../domains/ai/gateway.md)와
[ADR 0005](../../adr/0005-registered-llm-workload.md)를 따른다.

## 좋은 구조

- `router.py`: HTTP dependency, response model, localized error mapping.
- `application.py` 또는 `service.py`: use case orchestration과 기존 domain service 호출.
- `contracts.py` 또는 `schemas.py`: REST/AI/tool별 DTO. AI tool DTO는 human REST DTO를 그대로
  재사용하지 않는다.
- `source_catalog.py`, `registry.py`: 정적 발견·등록이 필요한 경우에만 사용하고 실행 로직은
  넣지 않는다.
- `tests/`: 핵심 contract, registry wiring, 권한·가용성·실패 모드 중심의 focused test.

Backend 도메인은 `apps/api/src/open_work_hub_api/domains/<domain>/` 아래에서 소유하고,
Frontend 앱은 `apps/web/src/app-modules/<moduleId>/`가 identity와 app-local UI/API를 소유한다.
플랫폼 composition root는 명시적으로 registration 객체를 조합하되 앱 ID 문자열 allowlist를
복제하지 않는다. 앱 등록 세부 계약은
[앱 플랫폼 문서](../domains/app-platform/README.md)를 따른다.

## 피해야 할 구조

- 모든 백엔드를 상속 hierarchy로 감싸는 추상 adapter framework.
- 실제 확장 포인트가 없는데 만드는 DB registry/plugin loader 또는 런타임 파일 스캔.
- router/service/worker에서 provider SDK, 저수준 LLM gateway, RAG query, LLM retry, rerank를
  직접 호출하는 구조.
- LLM이 따라가기 어려운 pass-through 모듈, local alias, deep import chain.
- shell/auth/검색 코드에 app ID를 다시 나열한 allowlist나 도메인별 특례.
- 문서와 코드 용어가 다른 상태. 예를 들어 문서는 `BM25`라고 쓰고 코드는 `keyword`만 쓴다면
  두 용어의 역할 차이를 명시한다.

## MCP와 AI 도구 기준

- 내부 capability 정본은 `AiCapabilityDescriptor`이며 도메인의
  `register_ai_capabilities(registry)`를 통해 등록한다.
- MCP manifest, OpenAI strict schema와 derived OpenAPI는 descriptor에서 파생한다.
- AI tool은 AI 전용 Pydantic DTO를 사용하고 router가 아니라 application/domain service를
  호출한다.
- discovery에서 workspace/platform app availability와 discoverability predicate를 검사하고,
  invoke 시점에 같은 predicate와 source domain ACL을 다시 검사한다.
- write tool은 기본 비노출이며 기능 플래그, approval preview, 사용자 승인, 실행 시점 ACL과
  audit 계약을 모두 만족해야 한다. 자세한 기준은
  [AI Write Policy](../domains/ai/write-policy.md)와
  [ADR 0002](../../adr/0002-mcp-capability-platform.md)를 따른다.

## RAG/Retrieval 기준

- 신규 caller의 공개 검색 진입점은 Retrieval REST/AI surface로 통합하되 ingestion, indexing과
  source ACL 소유권은 기존 domain에 남긴다.
- 현재 caller-facing source는 Qdrant 기반 `generic_rag`와 OpenSearch 기반 `keyword`이며, 서로
  다른 backend와 score 체계임을 profile에 남긴다. raw score를 직접 비교하지 않는다.
- Workspace keyword search 참여는 app-owned `SearchEntityAdapter` 한 곳에서 선언하고 backend가
  bootstrap, query scope와 availability를 파생한다. Frontend source flag나 app-ID allowlist를
  만들지 않는다.
- `graph_hybrid`는 persistent graph store가 생기기 전까지 query-time keyword/RAG fusion일 뿐
  실제 graph 저장소 사용을 암시하지 않는다.
- Rerank, chunking, OCR/parser, embedding provider는 registry 또는 runtime settings 이름을
  그대로 문서화한다.
- `/retrieval`은 기존 `/rag` compatibility route를 무조건 제거하는 근거가 아니다. 새 코드는
  Retrieval을 선호하고 기존 소비자는 wrapper와 contract test를 통해 단계적으로 전환한다.
- `retrieval_partition_id`는 candidate envelope이지 ACL이 아니다. 모든 evidence, summary,
  external LLM payload와 citation은 source-owned 최종 ACL을 통과해야 한다.
- projection identity, version fence와 generation cutover는
  [ADR 0009](../../adr/0009-retrieval-partition-projection-generations.md)를 따른다.

현재 source와 동작은 [Retrieval](../domains/retrieval/README.md),
[RAG](../domains/rag/README.md),
[ADR 0004](../../adr/0004-retrieval-rag-boundary-policy.md)가 소유한다.

## 검증 기준

- 새 AI capability는 registry compile, duplicate guard, MCP schema/discovery, direct invoke와 hidden
  tool 차단 중 관련 focused test를 갱신한다.
- 새 LLM 기능은 workload registry duplicate/budget/Adapter/default-route 검증, 미등록 workload
  fail-closed와 provider/direct-call guard를 통과해야 한다.
- 새 workspace API는 router 등록, server-side app gate와 `pnpm check:api-contract` 영향을 같이 본다.
- 통합 레이어는 source catalog, DTO validation, capability schema compile과 기존 compatibility
  route를 검증한다.
- 문서 업데이트는 마지막에 실제 diff, 존재하는 경로와 `package.json` 명령을 기준으로 다시 맞춘다.

구체적인 명령 선택은 [구현 검증 하네스](vibe-coding-harness.md)를 따른다.
