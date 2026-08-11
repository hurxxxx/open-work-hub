# ADR 0009: Retrieval Candidate Partitions and Versioned Projection Generations

- Status: Accepted
- Date: 2026-07-22

## Context

Open Work Hub는 OpenSearch keyword search와 Qdrant Generic RAG를 공용 Retrieval Module에서 조합한다. 현재 OpenSearch document ID와 Qdrant point ID, query filter, Search/RAG outbox identity에는 workspace 또는 scope가 포함되어 있다.

이 구조에서는 대량 Files corpus의 관리 workspace나 공개 범위를 바꿀 때 다음 비용과 경쟁 조건이 생긴다.

- OpenSearch delete/reindex
- Qdrant delete/re-embedding 또는 중복 point
- workspace가 다른 두 outbox stream 사이에서 늦은 delete가 최신 upsert를 제거하는 경쟁
- backend payload를 권한 정본으로 오인할 위험

한편 Open Work Hub source의 실제 권한 모델은 서로 다르다. Files는 owner/visibility/folder ancestry, Docs는 target/share/grant, Meeting은 organizer/attendee, PMS는 Team, Planner는 owner를 사용한다. 하나의 partition scope를 모든 source의 실제 grant로 사용할 수 없다.

대안은 workspace별 physical index/collection, custom routing, resource별 partition, backend metadata in-place rewrite였다. 이들은 workspace 이동 비용, shard/collection 수, partial move 비용 또는 권한 결합도를 높인다.

## Decision

### 1. Retrieval partition은 candidate envelope다

`retrieval_partition_id`는 backend routing과 coarse candidate filtering을 위한 opaque immutable UUID다. 실제 resource grant가 아니다.

- PostgreSQL `retrieval_partitions`가 partition ID, source namespace, 관리 주체, candidate scope, state, metadata version의 정본이다.
- candidate scope는 `company`, `workspace`, `personal`이다.
- backend query는 server-resolved non-empty partition predicate를 반드시 포함한다.
- backend payload의 partition/workspace/ACL hint는 권한 정본이 아니다.
- source-owned PostgreSQL ACL이 최종 권한 정본이다.
- candidate scope 변경만으로 resource publication이 바뀌지 않는다.
- 실제 publication/ownership 전환은 source-owned row 또는 aggregate와 partition directory를 같은 PostgreSQL transaction에서 변경한다.

권한의 기본 linearization point는 candidate 생성 뒤 실행되는 최종 PostgreSQL batch ACL statement snapshot이다. Raw content, evidence, citation은 반환 직전에 source ACL을 다시 확인한다.

### 2. Source policy는 source Module이 소유한다

Retrieval은 source Adapter에서 지원 candidate scope, transition operation, transition ownership mode만 발견하고 검증한다. Built-in source는 `transition_mode=source_owned`로 등록하며 범용 partition transition 함수가 source ACL transaction을 우회해 candidate metadata만 바꾸는 것을 거부한다. `generic` mode는 source ACL과 별도 정본이 없는 명시적 adapter에만 허용하고, mode 누락은 registration에서 fail-closed한다. 다음 책임은 기존 owner Module에 남긴다.

- mutation principal과 authorization
- storage key 정책
- 실제 final ACL
- source activation
- aggregate-specific transition

Partition binding을 추가해도 inactive source를 활성화하지 않는다. Caller-facing Retrieval query Interface와 raw REST/MCP input에는 partition ID를 추가하지 않는다.

Files의 기본 workspace partition은 mixed private/workspace ACL을 포함할 수 있으므로 실제 company publication 단위가 아니다. 함께 이동·공개할 대량 batch는 업로드 전에 source-owned `files_corpus` security cohort와 non-default partition을 배정한다. Files corpus 전환은 source corpus ownership/publication과 candidate partition metadata를 한 transaction에서 변경한다.

### 3. Physical identity는 scope-neutral하다

- canonical resource identity는 length-delimited `(resource_type, resource_id)`다.
- OpenSearch document ID는 canonical resource identity에서 결정한다.
- Qdrant point UUID는 canonical `(resource_type, resource_id, chunk_id)`의 UUIDv5다.
- workspace와 partition은 physical ID나 custom routing key에 포함하지 않는다.
- deterministic namespace/encoding은 고정 test vector로 관리한다.

Partition ID 자체는 PostgreSQL native UUID로 저장하고 DB trigger로 update를 거부한다.

### 4. Projection ordering은 resource stream version으로 보장한다

PostgreSQL projection head를 `(resource_type, resource_id)`별로 영구 보존한다. Head는 단조 증가 `projection_version`, current partition, desired state/tombstone, checksum을 가진다.

- source mutation, projection head 증가, immutable projection event/outbox insert는 한 transaction이다.
- Search/RAG merge와 supersession identity는 `(backend, resource_type, resource_id)`다.
- workspace는 진단 metadata일 뿐 stream identity가 아니다.
- delete는 versioned tombstone이며 projection head는 source 삭제 후에도 남는다.
- worker는 resource head lock/fence를 확인하고 stale event를 `superseded`로 종료한다.
- OpenSearch mutation은 strict external version을 사용한다.
- Qdrant mutation은 PostgreSQL projection head fence를 필수로 사용한다. Conditional update를 사용할 때는 client/server 최소 버전과 non-existent point 동작을 고정하고 검증한다.

### 5. Backend schema 변경은 generation migration이다

OpenSearch mapping/ID 변경은 새 physical index, Qdrant point/payload 변경은 새 physical collection에서 수행한다.

- Qdrant 같은 collection에 old/new point ID를 함께 저장하지 않는다.
- Qdrant payload index는 vector ingest 전에 생성한다.
- baseline watermark 뒤 변경 event를 replay한다.
- key set, count, checksum, ACL matrix, retrieval quality를 검증한다.
- backend별 alias를 원자적으로 전환한다.
- 두 backend cutover는 하나의 transaction이 아니므로 PostgreSQL control plane에 generation, checkpoint, validation, cutover, compensation, rollback 상태를 기록한다.
- 이전 generation은 rollback window 동안 read-disabled로 보존한다.

Online replay를 구현하지 않는 rollout은 source mutation producer를 모두 freeze하고 queue를 완전히 drain한 maintenance migration만 허용한다.

### 6. Query는 final ACL과 bounded refill을 사용한다

Source-specific owner/visibility/team fields는 scope/ownership 전환 뒤에도 허용 candidate를 제거하지
않는다는 것을 증명할 수 있을 때만 backend coarse hint로 유지한다. 그렇지 않으면 partition predicate와
source-owned final ACL/refill만 사용한다. 모든 candidate는 facet, highlight, rerank, summarization,
external LLM input, grounding, citation 이전에 source ACL을 통과해야 한다.

ACL 탈락으로 요청 개수를 채우지 못하고 backend candidate가 남아 있으면 bounded refill한다. OpenSearch refill은 PIT와 `search_after`를 사용한다. Source Adapter는 batch authorization Interface를 제공하고 ACL rejection/refill 지표를 기록한다.

Backend의 workspace/scope/deep-link payload는 응답 metadata 정본도 아니다. Scope 전환을 지원하는
source는 canonical resource ID로 현재 source metadata를 hydrate하거나 scope-neutral locator를 사용한다.
Signed raw-content capability는 발급 principal과 source ACL version을 bind하고 byte stream 직전에
active principal, workspace membership(필요한 scope), source ACL을 다시 확인하며 cache를 금지한다.

### 7. PostgreSQL rollout은 expand/backfill/contract로 나눈다

- Expand: UUID directory, immutability trigger, nullable source/job binding을 추가한다.
- Backfill: cursor batch, parent-before-child, orphan quarantine, reconciliation을 수행한다.
- Constraint validation: FK를 `NOT VALID`로 추가하고 별도 validate한다. 필요한 index는 `CONCURRENTLY` 생성한다.
- Contract: dual-write와 null audit가 완료된 source만 NOT NULL/check/composite FK를 적용한다.

기존 active PostgreSQL 검색을 유지해야 하는 nullable expand 기간에는 source ACL과 함께
`retrieval_partition_id IS NULL OR retrieval_partition_id IN (server-resolved IDs)`를 사용한다. 비어 있는
server scope는 NULL legacy 행만 허용하며 unfiltered fallback이나 `COALESCE`로 둘을 합치지 않는다. 모든
producer의 dual-write, NULL/orphan/parent-child mismatch 0건, FK validation, composite FK와 `NOT NULL`이
완료된 contract release에서 NULL branch를 제거한다.

Alembic migration 안에서 대형 source table을 한 transaction으로 전체 UPDATE하지 않는다.

### 8. 기존 ADR 관계

- 기존 `workspace_id`/`company_public` backend scope filter mechanism은 이 ADR의 candidate partition mechanism으로 대체한다.
- ADR 0004의 backend별 candidate generation과 Retrieval canonical caller-facing 역할은 유지한다.
- ADR 0004의 backend ACL 문구는 backend coarse ACL hint + source-owned PostgreSQL final authorization으로 구체화한다.
- ADR 0004의 active-source 정책은 유지한다.
- ADR 0007의 company tenant/workspace hierarchy와 `company_id` 비도입 결정을 유지한다.

## Consequences

### Positive

- 전용 corpus/partition의 workspace 이동은 PostgreSQL metadata 변경으로 끝난다.
- scope 변경 때문에 embedding, OCR, object copy를 반복하지 않는다.
- workspace 이동 전후 physical projection ID가 안정적이다.
- source ACL이 실제 권한 정본으로 남아 mixed ACL과 stale backend payload가 권한 누출을 만들지 않는다.
- versioned resource stream이 late delete, duplicate, out-of-order event를 일관되게 처리한다.
- generation별 검증과 rollback이 가능하다.

### Negative

- projection head/event/control plane과 reconciliation worker가 추가된다.
- 모든 active source와 worker가 versioned outbox 계약으로 한 번 이동해야 한다.
- migration 동안 old/new backend 용량이 필요하다.
- final ACL과 refill 때문에 query 비용이 증가할 수 있다.
- Files 대량 batch를 싸게 이동하려면 업로드 전에 corpus/security cohort를 정해야 한다.

## Non-Goals

- workspace별 index/collection
- OpenSearch custom routing
- partition payload를 source grant로 사용
- PostgreSQL RLS나 OpenSearch DLS로 source ACL 대체
- partition binding만으로 inactive source 활성화
- 일반 LLM workload, MCP capability, provider route 변경

## Follow-up

- Retrieval/RAG/Files 소유 문서에 이 계약을 반영한다.
- Files production activation은 partition migration과 별도 quality/ACL/citation gate를 통과해야 한다.
- Qdrant server/client version을 conditional update와 UUID tenant index가 검증된 범위로 고정한다.
- rollback window가 끝난 뒤에만 legacy workspace-based physical ID와 payload를 제거한다.
