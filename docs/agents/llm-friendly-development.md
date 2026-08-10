# LLM-Friendly Development

이 문서는 AI-DO를 LLM/agent와 함께 변경할 때 코드가 잘 검색되고, 좁게 이해되며, 안전하게 수정되도록 유지하는 개발 구조/추상화/진입점 판단의 정본이다. 루트 `agents.md`에는 핵심 규칙만 두고, 구현 판단이 필요하면 이 문서를 참조한다. `vibe-coding-harness.md`, `composable-abstractions.md`, `ui-components.md`는 각각 검증, 추상화 세부 판단, UI 재사용을 위한 보조 문서이며, 코드 구조 판단이 충돌하면 이 문서를 우선한다.

## 핵심 원칙

- 진입점은 적게, 책임은 명확하게 둔다. 한 도메인의 주요 orchestration은 `application.py`, `service.py`, `router.py`처럼 예측 가능한 이름에 둔다.
- 추상화는 얇게 둔다. registry, adapter, plugin loader는 런타임 확장성이 실제 요구될 때만 추가한다.
- LLM이 검색할 수 있는 이름을 쓴다. `retrieval`, `rag`, `keyword`, `rerank`, `source_catalog`처럼 도메인 용어와 코드 용어를 맞춘다.
- 호환 경로는 유지한다. 새 진입점을 만들더라도 기존 REST/MCP/tool 응답 모양은 wrapper로 보존한다.
- 복잡한 동작은 데이터 구조로 노출한다. profile, source descriptor, method list, degraded reason처럼 실행 결과를 관찰 가능한 필드로 남긴다.
- 특정 사용자 질문을 맞추는 분기는 금지한다. intent, operator, filter, source 같은 일반 schema로 표현한다.

## 생성형 LLM 호출 진입점

- 신규 앱과 기존 기능의 모든 생성형 LLM 호출은 도메인의
  `register_ai_capabilities(registry)`에 `RegisteredLlmWorkload`를 먼저 등록한다.
- `workload_id`는 `mail.summarize`, `meeting.summary`처럼 앱/기능 의미가 유지되는
  namespaced 상수다. 사용자 입력이나 provider/model명으로 동적 생성하지 않는다.
- workload는 실제 실행 기능 단위다. 한 앱의 추출·비교·리서치·생성 단계가
  route/model/output-token을 따로 가져갈 수 있으면 각각 등록한다. 범용
  generation workload로 서로 다른 앱 기능을 묶지 않는다.
- 도메인 service/worker는 공통 `execute_llm`/`stream_llm` Interface만 호출한다.
  provider, model, pool, endpoint, credential, retry/fallback은 호출자의 인자가 아니다.
- Provider SDK/HTTP와 저수준 `core.llm`/gateway 호출은 승인된 Adapter와 공통 실행
  Module 뒤로 격리한다. 앱 로컬 wrapper, 별도 registry, direct-call guard 예외를
  추가하지 않는다.
- 기존 외부 LLM 구현은 제거하지 않는다. provider-native tool/stream/trace를 승인된
  Adapter 안에 보존하고, 관리자가 workload별로 local/external과 model을 선택한다.
  일반 workload의 기본은 local, image workload는 external-only며 route 간 자동 fallback은 없다.
- workload descriptor는 양쪽 예산과 연결된 `task_kind`, 기본값과 허용 route,
  execution kind/model capability, audit/tracing metadata, 외부 전송 정책, 관리자
  표시용 i18n key를 하나의 발견 계약으로 노출한다. 공통 실행 Module이
  execution kind를 지원하는 Adapter를 해석한다. 관리자 화면은 이 registry snapshot을 사용하고 호출부
  목록을 따로 하드코딩하지 않는다.
- 최대 출력 토큰 기본값은 local 32K/external 64K다. 관리자가 workload별로
  변경하며 호출부는 더 작은 값을 요청할 수만 있고 상한을 넘길 수 없다.
- local/external 선택은 workload route override에서만 관리한다. AI security는 선택된
  external payload를 allow/mask/block/audit할 뿐 route를 바꾸지 않으며 block 시 호출이
  실패한다.
- embedding, rerank, OCR, ASR은 생성형 LLM workload가 아니며 각 Inference Gateway
  registry/Adapter 계약을 따른다.

새 LLM 기능의 최소 변경 단위는 `workload_id` 상수, registry descriptor, local/external
양쪽 최대 출력 토큰, 공통 Interface 호출, 등록/direct-call guard 테스트다. 필요한 Adapter나
실행 종류가 없으면 기능 코드에서 우회하지 말고 Core Enablement로 먼저 추가한다.

Web Search, Research Trends, Standards Monitor는 external-only 등록 workload다.
기존 Anthropic native `web_search` tool Adapter를 사용하며 local route나 오류 시
local fallback을 추가하지 않는다. 관리자는 승인된 외부 provider/model만 선택한다.

## 좋은 구조

- `router.py`: HTTP dependency, response model, localized error mapping.
- `application.py` 또는 `service.py`: use case orchestration과 기존 domain service 호출.
- `contracts.py` 또는 `schemas.py`: REST/AI/tool별 DTO. AI tool DTO는 human REST DTO를 그대로 재사용하지 않는다.
- `source_catalog.py`, `registry.py`: 정적 발견/등록이 필요한 경우에만 사용하고, 실행 로직은 넣지 않는다.
- `tests/`: 핵심 contract, registry wiring, 권한/가용성/실패 모드 중심의 focused test.

## 피해야 할 구조

- 모든 백엔드를 상속 hierarchy로 감싸는 추상 adapter framework.
- 실제 확장 포인트가 없는데 만드는 DB registry/plugin loader.
- router/service/worker에서 provider SDK, 저수준 LLM gateway, RAG query, LLM retry,
  rerank를 직접 호출하는 구조.
- LLM이 따라가기 어려운 pass-through 모듈, local alias, deep import chain.
- 문서와 코드 용어가 다른 상태. 예: 문서는 `BM25`라 쓰고 코드는 `keyword`만 쓰는 경우는 역할 차이를 명시한다.

## RAG/Retrieval 기준

- 검색의 공개 진입점은 통합하되, ingestion/indexing 소유권은 기존 domain에 남긴다.
- Generic RAG(Qdrant), keyword search(OpenSearch), legacy issue search(PostgreSQL/pgvector), QNA(company RAG)는 서로 다른 backend임을 profile에 남긴다.
- Workspace keyword search 참여는 app-owned `SearchEntityAdapter` 한 곳에서 선언하고 Backend가
  bootstrap, query scope, retrieval availability를 파생한다. Frontend source flag나 별도 app-ID
  allowlist를 만들지 않는다.
- Graph RAG는 persistent graph store가 생기기 전까지 `graph_hybrid`라는 이름으로 실제 graph 저장소 사용을 암시하지 않는다. query-time fusion이면 그렇게 기록한다.
- Rerank, chunking, OCR/parser, embedding provider는 provider registry나 runtime settings 이름을 그대로 문서화한다.
- `/retrieval` 같은 새 API는 기존 `/rag`, `/search`, domain assistant 흐름을 한 번에 대체하지 않는다. 먼저 wrapper를 통해 관찰 가능한 통합 surface를 만든다.

## 검증 기준

- 새 AI capability는 `AiCapabilityRegistry` 컴파일이 통과해야 한다.
- 새 LLM 기능은 workload registry compile과 duplicate/budget/Adapter/default-route
  검증, 미등록 workload fail-closed, provider/direct-call guard가 통과해야 한다.
- 새 workspace API는 router 등록과 OpenAPI contract 영향을 같이 본다.
- 통합 레이어는 최소한 source catalog, DTO validation, capability schema compile, 기존 compatibility route를 검증한다.
- 문서 업데이트는 마지막에 실제 diff 기준으로 다시 맞춘다.
