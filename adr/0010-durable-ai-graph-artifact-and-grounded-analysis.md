# ADR 0010: Durable AI Graphs, First-Class Artifacts, and Grounded Analysis

- Status: Accepted
- Date: 2026-07-26

## Context

AI-DO의 과거차 문제점 분석은 대화 요청 안에서 정형 분석, 의미 검색, 고정 보고서
렌더링을 순차 실행했다. 이 구조는 브라우저 연결 수명에 작업 수명이 결합되고, 보고서와
근거 SQL·결과가 대화 turn의 JSON에 섞이며, 쿼리 종류가 늘수록 앱 전용 planner와
compiler 분기가 함께 증가한다.

사용자는 전체 건수, 분포, 기간·권역·차종 비교, 추세, 원인·대책 사례, 차량 체크리스트를
자연어로 함께 요청한다. 모든 질문에 SQL을 새로 생성하면 안전성과 재현성이 낮고, 모든
질문을 고정 쿼리로 만들면 확장성이 낮다. 보고서는 질문에 맞는 자유로운 구조가 필요하지만
표시 수치와 인용은 저장된 근거에서만 나와야 한다.

## Decision

### 1. LangGraph가 AI 장기 실행의 유일한 graph runtime이다

- `LangGraph`가 node 실행, 분기, 병렬 wave, checkpoint, 재시작의 정본이다.
- PostgreSQL checkpointer의 `thread_id`는 `ai_graph_runs.id`와 같다.
- `ai_graph_runs`는 workspace/user ACL, 진행률, 현재 단계, 오류, 대화 연결을 위한
  projection이다. node state machine을 별도로 구현하지 않는다.
- 실행은 전용 Celery `ai_graph` queue에서 이루어지며 브라우저 SSE, route, tab 수명과
  독립적이다.
- 공통 executor registry는 `(graph_id, graph_version)`을 정확히 일치시킨다. 배포 시
  drain되지 않은 실행의 Adapter 버전은 해당 실행이 끝날 때까지 함께 등록한다.
- 실행 lease는 공통 runtime heartbeat가 갱신하고, active lease를 만난 broker 재전달은
  ACK하지 않고 다시 시도한다. 앱 node는 자체 lease 갱신을 구현하지 않는다.
- API는 user turn, assistant placeholder, graph run, pending artifact, dispatch outbox를
  먼저 영속화한다. 재진입한 UI는 DB projection과 대화를 다시 읽고 SSE는 보조 신호로만
  사용한다.

### 2. 모든 LLM 단계는 AI Gateway에 등록된 workload다

- LangGraph node와 LangChain Adapter는 provider SDK를 직접 호출하지 않고 공통
  `execute_llm`/`stream_llm`만 사용한다.
- 요청 해석, SQL agent, 보고서 양식, 정량·사례·체크리스트 분석, 초안, grounding 검토,
  최종화, 1회 교정은 서로 다른 stable workload로 등록한다.
- node별 workload, 입력 source, graph run, conversation, actor는 기존 audit와 tracing
  계약을 따른다.

### 3. SQL은 recipe-first이고 생성 SQL은 제한된 fallback이다

- 버전이 있는 YAML recipe와 Pydantic parameter/result schema가 일반 분석의 정본이다.
- recipe는 count, distinct, distribution, ranking, crosstab, time series, comparison,
  change, share/rate, Pareto, duration, completeness, detail, issue/cause/countermeasure,
  checklist coverage/status를 제공한다.
- LangChain SQL agent는 LlamaIndex metadata 검색으로 관련 view, dimension, metric,
  recipe를 찾고 먼저 recipe를 선택한다.
- compatible recipe가 없다고 명시적으로 판정된 경우에만 자유 SQL을 한 번 생성할 수 있다.
  DB 오류나 빈 결과는 자유 SQL 권한이 아니다.
- 실행 대상은 security-barrier read-only analysis view뿐이다. SQLGlot allowlist,
  single SELECT, parameter binding, read-only transaction, statement timeout, row/byte limit를
  모두 통과해야 한다.

### 4. 의미 검색과 SQL metadata 검색은 LlamaIndex를 사용한다

- 과거차 AI 의미 검색과 공통 Retrieval의 `legacy_issues` source는 같은 LlamaIndex
  retriever를 사용한다.
- vector store는 PostgreSQL pgvector이며 binary attachment를 저장하지 않는다. record
  summary와 추출된 attachment text만 node가 된다.
- `retrieval_partition_id`는 ADR 0009의 candidate envelope일 뿐 ACL 정본이 아니다.
  모든 candidate는 source-owned workspace/module/effective-revision ACL을 최종 확인한 뒤
  LLM, rerank, citation에 들어간다.
- index schema와 embedding 변경은 새 `ai_index_generations`에서 backfill·평가 후
  active generation을 원자 교체한다.

### 5. AI 산출물과 근거는 대화 JSON이 아닌 공통 테이블의 1급 데이터다

- `ai_artifacts`는 보고서와 분석 답변을 소유하고 완료 뒤 불변이다.
- `ai_artifact_sources`는 semantic evidence, checklist evidence, source grid를 소유한다.
- `ai_artifact_queries`는 parameterized SQL, typed params, 실행 상태, schema, rows,
  duration, row count, truncation을 소유한다.
- 보고서는 `AIR-YYYYMMDD-##########`, 분석은 `AIA-YYYYMMDD-##########` 번호로
  식별하며 재생성은 기존 row 변경이 아니라 `supersedes` 관계로 만든다.
- 과거 데이터에 SQL/result가 없으면 `not_captured`로 이관하고 근거를 만들어 내지 않는다.
- 보고서 히스토리는 완료된 `report` artifact만 조회한다. 정형 집계와 사례 JSON은 별도
  top-level report가 아니라 보고서의 사용 데이터 tab과 grid로 표시한다.
- persistence node는 같은 graph run의 완료 artifact를 먼저 확인해 멱등적으로 재진입한다.
  대화 turn에는 보고서 본문을 복제하지 않고 artifact reference만 둔다.

### 6. 보고서는 동적이지만 grounding은 결정론적으로 검증한다

- 1차 wave에서 보고서 양식 설계와 적용 가능한 정량·사례·체크리스트 specialist를
  병렬 실행한다.
- 2차 초안, 3차 grounding review, 4차 finalizer를 실행한다.
- 최종 Markdown의 수치와 단위(건수·비율·퍼센트포인트), 인용 ID, 금지된 내부 처리
  표현을 서버가 저장 source와 대조한다.
- 실패하면 별도 correction workload를 한 번만 호출한다. 다시 실패하면 질문과 실제
  source를 바탕으로 한 일반 source-to-Markdown fallback을 사용하고 검증되지 않은
  수치나 인용은 제거한다.

## Consequences

### Positive

- 화면 이동, 새로고침, 네트워크 단절, worker 재시작 뒤에도 같은 실행을 복구할 수 있다.
- 보고서, SQL, 파라미터, 결과, 사례, 체크리스트의 lineage와 재현성이 생긴다.
- 질문 종류는 recipe YAML과 metadata index를 추가해 확장하며 앱 전용 분기 증가를
  억제한다.
- 공통 Retrieval과 과거차 assistant가 한 semantic projection과 ACL 경계를 사용한다.

### Negative

- LangGraph checkpoint, artifact schema, index generation, 전용 worker 운영이 추가된다.
- 새 index generation과 이전 실행 데이터 이관 동안 추가 PostgreSQL 용량이 필요하다.
- 모델 출력 이후 deterministic 검증과 최대 한 번의 교정 때문에 보고서 지연이 늘어난다.

## Migration

1. 공통 graph/artifact schema와 read-only analysis view를 expand한다.
2. recipe와 새 pgvector generation을 backfill하고 ACL/quality corpus를 검증한다.
3. 기존 conversation turn에서 명시적으로 `document` 보고서로 저장된 항목만 common
   report artifact로 이관한다. 보고서 여부가 기록되지 않은 standalone assistant run은
   임의 변환하지 않는다.
4. worker queue를 drain하고 새 graph/retrieval generation을 원자 활성화한다.
5. row count, hash, ACL, report history를 확인한 뒤 기존 assistant execution table과
   고정 planner/compiler/report renderer를 제거한다.
6. rollback window가 끝난 뒤 legacy AI chunk와 호환 table을 drop한다.

## Non-Goals

- 일반 master/checklist grid 검색의 교체
- 모델에게 base table 또는 write SQL 권한 부여
- vector payload를 최종 ACL 정본으로 사용
- 질문별 prompt branch 또는 개별 질문 정답 튜닝
