# Retrieval Service Layer

AI-DO retrieval은 RAG, keyword search, QNA, legacy issue AI search의 공개 Interface이자
교차 backend 순위 결합 Module이다. 백엔드별 ingestion, parser, embedding, index, ACL,
native candidate 생성은 기존 domain이 계속 소유한다. Retrieval은 이 경계 위에서 후보를
정규화하고, 결합하고, 전역 rerank하고, 최종 evidence를 한 번 grounding한다.

## 현재 구현

주요 코드:

- `apps/api/src/ai_do_api/domains/retrieval/application.py`
- `apps/api/src/ai_do_api/domains/retrieval/contracts.py`
- `apps/api/src/ai_do_api/domains/retrieval/source_catalog.py`
- `apps/api/src/ai_do_api/domains/retrieval/ranking.py`
- `apps/api/src/ai_do_api/domains/retrieval/grounding.py`
- `apps/api/src/ai_do_api/domains/retrieval/evaluation.py`
- `apps/api/src/ai_do_api/domains/retrieval/router.py`
- `apps/api/src/ai_do_api/domains/retrieval/tools.py`

공개 표면:

- REST: `POST /api/v1/workspaces/{workspace_slug}/retrieval/query`
- REST: `GET /api/v1/workspaces/{workspace_slug}/retrieval/sources`
- MCP/AI tools: `retrieval.search`, `retrieval.list_sources`
- Shared TS contract: `packages/contracts/src/openapi.generated.d.ts`
- Web workspace API route policy: `/api/v1/retrieval`
- Frontend client: `apps/web/src/platform/retrieval/retrieval-api.ts`
- Frontend diagnostics UI: `apps/web/src/app-modules/retrieval-search`
- Feature flag: `AI_DO_RETRIEVAL_UNIFIED_ENABLED` default `true`

## 검색 경계

Retrieval 레이어가 하는 일:

- 요청 strategy와 source를 해석한다.
- 기존 backend service에서 후보를 가져온다.
- 결과를 `RetrievalHit`, `RetrievalProfile`, `RetrievalSourceDescriptor`로 정규화한다.
- canonical resource identity로 dedupe한다.
- 여러 backend 결과는 raw score를 더하지 않고 RRF(`k=60`)로 결합한다.
- semantic/hybrid 결과는 최종 후보 전체를 한 번 rerank한다.
- 최종 top-k evidence를 한 번 grounding한다.
- 기존 `/rag/query`, `/rag/sources`, `rag.query`, `rag.list_sources`, `/search/query`, QNA, legacy issue assistant가 호환 wrapper를 통해 같은 진입점을 지나가게 한다.
- Local gateway 기본 검색 도구를 `retrieval.search` 우선으로 둔다.

Retrieval 레이어가 하지 않는 일:

- parser/OCR/chunking/embedding/vector DB provider를 재구현하지 않는다.
- RAG source adapter registry를 대체하지 않는다.
- OpenSearch, Qdrant, PostgreSQL/pgvector를 하나의 generic Adapter hierarchy로 숨기지 않는다.
- persistent graph store가 없는 상태에서 Graph RAG가 실제 graph DB를 사용한다고 표현하지 않는다.

## Candidate partition과 최종 ACL

[ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md)에 따라 모든
OpenSearch, Qdrant, PostgreSQL FTS/pgvector projection은 공용 backend에 저장하되
`retrieval_partition_id`로 후보 범위를 제한한다. Partition은 실제 권한 grant가 아니라
coarse candidate envelope다.

- `retrieval_partitions`는 immutable UUID, source namespace, 관리 workspace, candidate
  `company`/`workspace`/`personal` 범위와 metadata version을 소유한다.
- 실제 ownership, publication, private/share/team 규칙은 source row 또는 source-owned aggregate가
  정본이다. Candidate는 source-owned PostgreSQL batch ACL을 통과하기 전 facet, highlight, rerank,
  summary, grounding, citation에 들어갈 수 없다.
- Search/RAG/SourceAccess registration은 같은 resource type에 동일 Partition Adapter ID를 선언한다.
  누락, 잘못된 resource claim, ID drift는 platform bootstrap에서 실패한다. Legacy Issues의 native
  PostgreSQL pipeline도 같은 partition binding을 사용하지만 Generic RAG로 중복 등록하지 않는다.
- physical document/point ID와 projection stream key에는 workspace, partition, visibility scope를
  넣지 않는다. Canonical resource/chunk identity와 resource별 단조 증가 projection version,
  영구 tombstone을 사용한다.
- 실제 workspace/publication 전환은 source-owned row 또는 aggregate와 partition directory를 같은
  transaction에서 갱신한다. 정상 전환은 object copy, OCR, embedding, OpenSearch reindex, Qdrant
  point 재생성을 호출하지 않는다.
- Partition Adapter는 `transition_mode`를 명시한다. Built-in source는 `source_owned`이며 범용 partition
  transition API로 candidate metadata만 바꾸는 경로를 거부한다. Source ACL과 별도 정본이 없는 adapter만
  `generic`을 선언할 수 있고, mode 누락·오류는 registration에서 실패한다.
- mapping, stable ID, payload schema 전환은 새 physical index/collection에서 검증·replay한 뒤 alias를
  바꾼다. Qdrant old/new point ID를 같은 collection에 혼합하지 않는다.

Rollout은 source별로 분리한다. Files development runtime은 UUID directory/source binding 위에서
OpenSearch v3/Qdrant v1 physical generation을 materialize·검증·alias cutover한 뒤 live writer/query를
연결했다. Production Files와 다른 source는 owner별 generation 전환이 끝날 때까지 기존
compatibility path와 activation 상태를 유지하며, partition binding만으로 inactive source를
활성화하지 않는다.

기존 active PostgreSQL source의 nullable 행은 expand 기간에 정본 source ACL과
`partition IS NULL OR partition IN server-resolved IDs`를 함께 적용한다. Scope가 비어도 NULL 행만 허용하고
무필터 fallback은 하지 않는다. Legacy Issues exact/FTS/trigram/term/pgvector가 이 규칙을 사용한다. NULL,
orphan, parent-child mismatch가 모두 0이고 producer dual-write와 FK/composite/NOT NULL contract가 검증된
뒤에만 NULL branch를 제거한다.

구현 checkpoint는 다음과 같다.

- 공통 구현: native UUID directory/불변 trigger, source binding/adapter guard, projection
  head/event/tombstone, versioned Search/RAG job fence, partition-aware backend capability, Search PIT
  refill과 source-owned final ACL 재검증.
- Files development 구현: cached-artifact baseline, bounded event replay, exact source/backend/ACL/quality
  reconciliation, 최초 alias cutover/보상, active control-plane selector와 live writer/query, 검색 UI.
- 미완료: 후속 Files generation rollback/replay, source 전체 cursor backfill과
  quarantine/constraint validation/contract migration, personal/workspace-less company caller,
  non-Files source별 physical activation.
- 결과: 비활성 expand release와 development Files의 최초 generation materialize, v3 품질 평가,
  workspace/company/A→B canary를 통과했다. 이는 development capability 증거일 뿐 production
  승인 증거가 아니다.
- production 10,000-file 활성화는 전체 eligible corpus의 data-plane 처리량·비용, 사람이 검토한
  60-query 이상 corpus, 후속 generation rollback/replay, workspace 없는 company principal과
  non-Files source별 physical E2E가 남아 있다. 현재 상태와 재현 경로는
  [Files source activation](../rag/files-source-activation.md),
  [Files generation cutover runbook](../rag/files-generation-cutover-runbook.md)이 소유한다.

## Source Catalog

| source | scope | backend | 상태 |
| --- | --- | --- | --- |
| `generic_rag` | workspace | Qdrant | active |
| `keyword` | workspace | keyword search/OpenSearch | active |
| `qna` | company | Qdrant | active |
| `legacy_issues` | workspace | app-owned LlamaIndex PostgreSQL FTS/pgvector | active |
| `documents_demo` | workspace | fixture | inactive |
| `learning_notes_personal` | user | native doc personal metadata | inactive |

`keyword` availability와 허용 entity는 workspace의 활성 앱 ID와 Backend
`SearchEntityAdapter.owner_app_id` registry의 교집합이다. Retrieval source catalog나 Web manifest에
별도 keyword source ID 목록을 두지 않는다. 활성 keyword source가 없으면 직접 keyword API는
localized 403, 요청 entity가 모두 비활성/미등록이면 200 empty, 물리 index가 없으면 503이다.
문서가 0개인 정상 workspace는 200 empty이며 QNA(company RAG), Generic RAG, legacy issue search와
index/권한 수명주기를 공유하지 않는다.

기본 strategy:

- `semantic`: `generic_rag`
- `keyword`: `keyword`
- `hybrid`: `keyword`, `generic_rag`
- `graph_hybrid`: `keyword`, `generic_rag` with profile marker `persistent_graph_store=false`

실제 후보 생성 및 순위 정책:

| strategy | 후보 backend | 교차 backend fusion | 전역 rerank |
| --- | --- | --- | --- |
| `keyword` | OpenSearch BM25 | 없음 | 없음 |
| `semantic` | Qdrant dense vector | 없음 | 1회 |
| `hybrid` | OpenSearch BM25 + Qdrant dense vector | RRF, `k=60` | 1회 |
| `graph_hybrid` | 현재 `hybrid`와 동일 | RRF, `k=60` | 1회 |

후보 수는 `max(top_k * 4, 80)`으로 넓히되 기존 backend Interface의 최대값을 보존해
100개로 제한한다. Backend raw score는 서로 다른 척도이므로 cross-backend ranking에
직접 사용하지 않는다. 한 backend가 같은 resource를 여러 번 반환해도 backend별 최초
rank만 RRF에 기여한다.

Reranker score는 provider가 의미를 선언한 경우에만 절대값을 해석한다. 현재 inference
gateway reranker는 `normalized_relevance`를 선언하며, 모든 후보가 `0.001` 미만이면
low-confidence로 보고 rerank 전 backend/RRF 순서로 복귀한다. NaN/무한대, 정규화 범위
밖의 값, 후보를 구분하지 못하는 평탄한 score도 degraded fallback 대상이다. 의미를
선언하지 않은 provider의 score에는 임의 threshold를 적용하지 않는다.

Filter는 backend 의미를 섞지 않는다. 공통 `filters` 아래에서 `filters.keyword`와
`filters.rag` namespace를 사용하고, 명시된 source ID가 잘못됐으면 422, 활성화되지
않았으면 403을 반환한다. 기본 source 중 하나만 사용할 수 없으면 사용 가능한 결과를
반환하되 profile에 degraded reason을 기록한다.

명시적으로 선택한 source의 runtime backend가 실패하면 빈 200으로 숨기지 않고 503을
반환한다. Partial result는 기본/암시적 multi-source 요청에만 허용한다. Strategy와 별개로
실제 결과를 둘 이상의 backend가 제공하면 항상 RRF를 적용해 raw score 혼합을 막는다.

### Files 검색 품질 정책

Files의 검색엔진형 `keyword`와 `hybrid` 전략에서 BM25 경로는 사용자가 입력한 분석
token을 모두 포함하는 strict AND 검색을 사용한다. 자연어 질문을 받는 공통 Retrieval
API의 recall 지향 OR/30% 정책은 그대로 유지한다.

Files `semantic`/`hybrid`에서 `normalized_relevance` reranker가 적용되면 `0.001` 미만의
낮은 관련도 tail은 ACL 검사와 pagination 전에 제거한다. 모든 후보가 threshold 미만이면
reranker 순위를 버린다. Semantic은 vector 1위만, hybrid도 semantic 1위를 우선 보존하고
vector 후보가 없을 때만 keyword 1위로 복귀한다.
정확한 어휘 일치 순위는 사용자가 BM25 전략에서 별도로 확인할 수 있다. score 의미가
unknown인 provider에는 이 필터를 적용하지 않는다.

Files 문서 AI는 이 검색 UI fallback을 근거로 직접 사용하지 않고, 정상
`normalized_relevance` cross-encoder 점수를 통과한 Files hit만 증거로 허용한다. 첫 검색이
무근거인 경우에는 등록된 `files.rag_query_rewrite` workload가 문서 발견 요청인지
schema로 판정한다. 발견 요청일 때만 특정 산출물 형식을 중립적인 문서 검색 질의로 일반화해
한 번 재검색한다. 완화 질의는 원 질의의 일반 어휘 앵커를 보존해야 하며, 재검색 결과에도
같은 reranker·source ACL·excerpt 기준을 적용한다. 사실 질문, 의미가 이탈한 완화 결과,
선택적 완화 provider 장애는 기존 fail-closed 응답을 유지하고 보안 정책 차단은 전파한다.

## 품질 및 승격 gate

`evaluation.py`는 Recall@k, MRR, nDCG, p95 latency, ACL 위반, citation 실패를 계산한다.
새 index generation이나 Files source는 versioned corpus 최소 60 query에서 다음 gate를
통과하기 전에는 활성화하지 않는다.

- ACL 위반과 citation 실패 0건
- p95 5초 이하
- Hybrid Recall@10 0.80, MRR@10 0.50, nDCG@10 0.50 이상
- Recall 회귀 없음
- nDCG 또는 MRR 5% 이상 상대 개선

승격 CLI는 이 결과를 versioned quality artifact로 입력받으며, artifact의 corpus SHA-256과
실제 `--quality-corpus` 파일 raw bytes의 SHA-256, corpus ID, index generation이 모두
일치해야 한다. 일반 artifact version 2는 평가한 OpenSearch 전체 문서의 canonical SHA-256도
기록하며 물리 index UUID와 mapping/settings digest도 활성화 직전에 다시 검증한다.
BM25/dense baseline 누락, 세 결과의 query count 불일치, 어느 전략에서든 ACL/citation/p95 위반,
v2 mapping version 불일치, backfill document count 불일치도 모두 fail-closed한다.

`python -m ai_do_api.evaluate_retrieval_quality`는 named staging generation의 BM25와
Qdrant dense를 사용해 keyword/semantic/hybrid를 각각 실행한다. `--prepare-staged-files`는
Files source가 preview/production에서 inactive인 동안 generation 전용 임시 Qdrant collection과
staging OpenSearch generation만 준비하며 live alias를 이동하지 않는다. 이 옵션은 stale vector 재사용을
막기 위해 artifact 생성에 필수다. 임시 collection은 기본적으로
평가 성공·실패 후 삭제된다. 실제 Files corpus는 제품 데이터와 권한
경계를 반영해 별도로 구축해야 하며 합성 fixture를 production quality 근거로 사용하지 않는다.

Files OpenSearch v3/Qdrant v1 승격에는 이 legacy evaluator를 사용하지 않는다. 이미 materialize된
정확한 physical pair를 변경 없이 조회하는 `evaluate_files_partitioned_quality`와 artifact version 3를
사용한다. Version 3는 OpenSearch뿐 아니라 Qdrant physical/config/content와 embedding runtime
identity, disabled 상태와 candidate-k를 포함한 reranker runtime identity, Files source snapshot과
judged principal별 전체 keyword/RAG 허용 집합 SHA-256까지 고정한다. 평가 전후 inventory/source/ACL
집합이 같아야 하며 비회원 context는 거부한다. Files judged corpus의 relevant ID와 최소 한 개의
forbidden ID는 평가 전에 active source row 및 현재 keyword/RAG ACL로 교차 검증한다. Validate와
non-empty cutover는 동일 corpus로 ACL 집합을 다시 계산하며 raw query나 user/resource ID를 generation
validation JSON에 복제하지 않는다. 명령과 cutover 순서는
[Files Retrieval Generation Cutover Runbook](../rag/files-generation-cutover-runbook.md)이 소유한다.

## Compatibility

기존 표면은 응답 모양을 유지한다.

- `/rag/query`와 `rag.query`는 `RagQueryResponse`를 그대로 반환한다.
- `/search/query`는 `KeywordSearchResponse`를 그대로 반환한다.
- QNA service는 `RagQueryResponse`를 그대로 사용한다.
- Legacy Issue Assistant와 공통 Retrieval `legacy_issues` source는 같은 app-owned
  LlamaIndex retriever와 generation을 사용한다. Retrieval은 정규화된 hit/profile
  compatibility shape만 유지하며 LangGraph 실행이나 SQL 분석을 소유하지 않는다.

따라서 신규 호출자는 `/retrieval/*` 또는 `retrieval.*`을 사용한다. 기존 UI/API는 현재 응답 계약을 유지한 채 호환 wrapper를 통해 retrieval service layer를 지난다.

## 결정된 정책

- 신규 REST, OpenAPI, frontend, MCP/AI 소비자는 retrieval surface를 정본으로 사용한다.
- 외부 partner/API-key 소비자도 retrieval contract를 기준으로 설계한다. 단, 실제 service-account/API-key 공개는 ADR 0001의 auth/key lifecycle 구현 뒤에만 가능하다.
- 기존 keyword search UI는 유지한다. retrieval source/profile을 보여주는 화면이 필요하면 기존 UI를 교체하지 않고 별도 UI로 만든다.
- Retrieval source/profile 확인은 별도 diagnostics UI(`/w/{workspace}/retrieval-search`, `/tool/retrieval-search`)에서 한다.
- `rag.query`, `rag.list_sources`, `/rag/query`, `/rag/sources`는 호환 surface로 유지한다. 신규 호출자는 `retrieval.search`와 `/retrieval/*`를 사용한다.
- `graph_hybrid`는 현재 keyword + Generic RAG fusion profile이다. persistent graph store, entity extraction, relationship indexing이 없으면 실제 Graph RAG라고 부르지 않는다.
