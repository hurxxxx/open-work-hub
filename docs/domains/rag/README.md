# RAG Domain

Open ALM RAG domain은 문서 chunking, embedding, vector indexing, rerank, grounded answer synthesis, source adapter policy를 소유한다. 여러 검색 표면을 얇게 묶는 공개 진입점은 [Retrieval 서비스 레이어](../retrieval/README.md)를 정본으로 본다.

## 현재 구현

주요 코드:

- `apps/api/src/open_alm_api/domains/rag/`
- `apps/api/src/open_alm_api/backfill_rag.py`
- `apps/worker/src/open_alm_worker/tasks/rag_sync.py`
- `apps/api/src/open_alm_api/domains/search/`
- `apps/api/src/open_alm_api/domains/legacy_issues/ai_search.py`

핵심 backend:

| 영역                   | Backend                                 | 역할                                     |
| ---------------------- | --------------------------------------- | ---------------------------------------- |
| Generic RAG            | Qdrant dense vector + hashed TF sparse  | RAG compatibility query                  |
| Keyword Search         | OpenSearch                              | workspace keyword/full-text style search |
| Evidence Search        | OpenSearch + Qdrant + reranker          | keyword/semantic 후보 통합 evidence      |
| Legacy Issue AI Search | PostgreSQL FTS/trigram/JSONB + pgvector | legacy issue 전용 evidence search        |

Canonical retrieval에서 keyword는 OpenSearch BM25, semantic은 Qdrant dense vector를
사용한다. Hybrid는 두 backend의 raw score를 섞지 않고 RRF로 결합한 뒤 전역 rerank한다.
Generic RAG 호환 endpoint의 hashed term-frequency sparse vector는 BM25가 아니다.

## Source Scope

Generic RAG의 현재 active workspace 대상:

- Docs native official documents

현재 active company 대상:

- QNA documents and notices through company scope visibility

현재 adapter/projection은 있으나 기본 RAG reindex/query 대상으로 보지 않는 후보:

- Meeting
- PMS
- Planner
- Learning Notes personal docs

`meeting/rag_sync.py`, `pms/rag_sync.py`, `planner/rag_sync.py`라는 파일명은 OpenSearch keyword index hook을 포함한다. 이 이름만 보고 Generic RAG ingestion이 활성이라고 판단하지 않는다.

## Parser/OCR

RAG 관련 parser/OCR 경로는 하나가 아니다.

- Generic RAG OCR/parser provider: Docling/EasyOCR/RapidOCR/Tesseract 또는 Inference Gateway.
- QNA upload parser: fast parser와 fallback 경로.
- Legacy Issue attachment OCR: legacy issue evidence ingestion용 OCR artifact.
- Files retrieval parser: server-observed type detection, HTML active-content 제거를 포함한 bounded
  structured locator extraction과 provenance를 기록하는 OCR enrichment.

`document_translate`, `documents-demo` fixture, patent/fmea document extraction은 텍스트 추출을 하지만 Generic RAG index ingestion surface가 아니다.

Parser와 OCR은 input, ACL과 실패 처리가 실제로 같아지기 전에는 하나의 범용 parser로 합치지 않는다.
공통 utility 재사용은 허용하지만 pipeline 소유권은 source domain에 남긴다. 각 source는 가능한
parser/provider provenance를 기록하고 fallback 실패가 해당 source만 degraded시키도록 격리한다.
새 OCR provider는 먼저 기존 domain provider boundary 뒤에 연결한다.

Files 업로드 소스의 staged 구현과 활성화 순서는
[Files Retrieval Source Activation](files-source-activation.md)을 따른다.
Physical generation 준비·품질 평가·최초 alias 전환의 운영 명령은
[Files Retrieval Generation Cutover Runbook](files-generation-cutover-runbook.md)을 따른다.

## Qdrant와 embedding generation 변경

Embedding model·dimension, Qdrant collection prefix, sparse vector, payload index 또는 point schema가
바뀌면 기존 collection을 제자리에서 수정하거나 legacy lookup fallback으로 전환하지 않는다.
[ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md)의 fresh physical
generation 계약을 사용한다.

현재 Files partitioned Qdrant schema는 v1이다. metadata/date filter는 payload 조건과
PostgreSQL 최종 재검증으로 정확성을 보장한다. 선택적 metadata/date payload index는 실제 연계
corpus의 성능 근거와 후속 rollback 절차가 준비된 v2 fresh generation에서만 도입한다.

1. 새 physical collection과 vector/payload index를 ingest 전에 만든다.
2. [source matrix](source-matrix.md)의 대상 active source를 명시하고 고정 watermark까지 baseline을
   materialize한다.
3. Watermark 이후 event를 replay하고 key set, count, checksum, ACL matrix와 retrieval quality를
   검증한다.
4. `/retrieval/query`, `/rag/query`, source listing과 grounded answer를 실제 허용·거부 principal로
   smoke한다.
5. 검증된 alias만 전환하고 generation/checkpoint/compensation 상태를 PostgreSQL control plane에
   기록한다.
6. 이전 generation은 rollback window 동안 read-disabled로 보존하며 old/new point를 같은
   collection에 섞지 않는다.

Files v3의 정확한 build·quality·cutover 명령은 일반 절차 대신 Files 전용 generation runbook을
사용한다.

## 관리자 문서 처리 현황

플랫폼 관리자의 `/admin/document-processing`은 OCR, Vision 문서 추출, embedding,
rerank, vector/keyword index와 기본 chunking의 **읽기 전용 projection**이다. 현재 API
프로세스에 적용된 환경변수와 RAG runtime health를 합성하며 별도 DB 설정을 만들지 않는다.
Worker health는 별도 관측 계약이 없으므로 API readiness와 혼동하지 않고 미관측으로 표시한다.

일반 OCR, embedding, rerank, vector index는 생성형 LLM 라우팅 대상이 아니다. Vision
모델을 사용하는 문서 추출은 생성형 호출이므로 workload 등록·공통 실행·감사 계약은
유지하되 `management_surface='document_processing'`으로 분류해 LLM 라우팅 편집 화면이
아닌 문서 처리 현황에서 readiness를 확인한다. 단, 생성형 Vision workload의 모델 override는
LLM 관리 라우팅 화면에도 노출해 전용 Vision 모델로 전환할 수 있게 한다.

현재 `legacy_issues.attachment_vision`과 `meal_invoice_ocr_extract`는 별도 Vision 서버나
전용 model endpoint를 직접 호출하지 않는다. 두 workload 모두 공통 local LLM 라우팅과
관리자가 선택한 `vision` capability 모델을 사용한다. `OPEN_ALM_RAG_VISION_OCR_ENABLED`는 레거시
첨부 Vision 추출의 실행 gate일 뿐, 별도 모델 선택 설정이 아니다.

Vision 모델 선택 자체는 `/admin/llm?tab=routing`의 workload override로 관리한다. 따라서
향후 Vision 전용 모델을 모델 카탈로그에 `vision` capability로 등록하고 활성화하면 두 workload를
서로 독립적으로 전환할 수 있다. 물리적으로 endpoint가 분리된 모델은 local provider 앞의
OpenAI-compatible inference router가 하나의 모델 목록과 endpoint로 노출하는 것을 전제로 한다.

이 화면은 여러 pipeline을 하나로 합치는 Interface가 아니다. Generic RAG는 Qdrant를,
Legacy Issue AI Search는 PostgreSQL/pgvector를 계속 소유한다. 모델 dimension이나 collection
변경이 필요해지면 단순 설정 저장이 아니라 위 generation migration 계약을 먼저 적용한다.

## Query Surfaces

| Surface                                          | 응답 계약                   | 현재 역할                                                |
| ------------------------------------------------ | --------------------------- | -------------------------------------------------------- |
| `/api/v1/workspaces/{workspace}/retrieval/query` | `RetrievalQueryResponse`    | 통합 검색/RAG 진입점                                     |
| `/api/v1/workspaces/{workspace}/rag/query`       | `RagQueryResponse`          | RAG 호환 endpoint, retrieval wrapper 통과                |
| `/api/v1/workspaces/{workspace}/rag/sources`     | RAG source-kind 목록        | RAG source listing 호환 endpoint, retrieval wrapper 통과 |
| `retrieval.search`                               | normalized retrieval result | AI/MCP 통합 검색 tool                                    |
| `rag.query`                                      | `RagQueryResponse` JSON     | legacy RAG AI tool fallback                              |

Local gateway 기본 검색 도구는 `retrieval.search` 우선이다. `retrieval.search`가 hidden인 상황을 위해 `rag.query` fallback allowlist는 유지한다.

`/rag/query` compatibility path는 기존 dense + hashed-TF sparse fusion 및 backend rerank
계약을 보존한다. `/retrieval/query`는 Qdrant dense 후보와 OpenSearch BM25 후보를 각각
가져와 Retrieval Module에서 RRF, 전역 rerank, 최종 grounding을 수행한다. 이 분리는
기존 소비자의 응답 호환성을 지키면서 canonical pipeline의 순위 의미를 명확하게 한다.

## Graph/Rerank Boundary

`graph_hybrid`는 현재 persistent graph store를 쓰는 Graph RAG가 아니다. 현재는 keyword + Generic RAG query-time fusion profile이다.

AI graph runtime의 `EvidencePacket`은 이미 모인 tool/node/external search 결과를 grounded writing prompt로 포장한다. 직접 Qdrant/OpenSearch/PostgreSQL query나 rerank provider 호출을 수행하는 RAG engine이 아니다.

## 결정된 정책

- 경계 정책은 [ADR 0004](../../../adr/0004-retrieval-rag-boundary-policy.md)를 따른다.
- Candidate partition, source-owned final ACL, versioned projection stream, fresh backend generation은
  [ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md)를 따른다. Backend ACL
  payload는 후보 힌트이며 실제 grant가 아니다.
- source별 active/inactive 상태는 [RAG Source Matrix](source-matrix.md)를 정본으로 보고 테스트로 검증한다.
- Qdrant collection/model 변경은 위 fresh physical generation 계약과 ADR 0009를 따른다.
- Qdrant server/client는 검증된 동일 minor version으로 고정한다. 새 collection은 vector ingest 전에
  `retrieval_partition_id` payload index를 만들고, watermark replay와 검증 뒤 alias로 전환한다.
- partition-aware point/filter는 source별 physical generation capability다. Files는 fail-closed
  source다. Development는 baseline replay/validation/alias cutover와 60-query v3 품질 gate를
  통과한 pair를 사용한다. Production은 validated empty pair로 gate만 열려 있으며
  `quality_status=deferred_until_nonempty`다. 최초 non-empty corpus에는 `attest-active`의
  60-query evidence와 운영 승인이 필요하다.
- `rag.query`, `rag.list_sources`, `/rag/query`, `/rag/sources`는 호환 surface로 유지한다.
- Meeting, PMS, Planner와 Learning Notes personal documents는 active RAG source가 아니다.
- Legacy Issue AI Search는 [Legacy Issues AI Search](../../apps/legacy-issues/README.md) 문서가 소유한다.
