# 서비스 런타임 하네스 기준

## 적용 대상

서비스에서 LLM을 사용하는 아래 경로는 모두 런타임 하네스 관리 대상이다.

- OCR 선택 및 후처리
- 문서 질의응답 생성
- PLM 질의 계획 및 SQL 생성
- 문서 초안 생성
- 답변 근거 정리
- 품질 판정용 judge/evaluator

## 공통 요청 메타데이터

모든 요청은 아래 메타데이터를 trace 상위 레코드에 남긴다.

- `scenario_id`
- `workflow_version`
- `prompt_version`
- `retrieval_profile`
- `llm_profile`
- `eval_profile`
- `trace_id`
- `user_role`
- `acl_scope`

## 프롬프트 포장 규칙

- system prompt 는 역할, 안전 규칙, 출력 계약만 유지한다.
- retrieved context 는 현재 요청과 직접 관련 있고 ACL 을 통과한 정보만 넣는다.
- 다른 도메인 설명, 전체 서비스 설명, 관련 없는 예시는 기본적으로 넣지 않는다.
- 긴 문서 기반 작업은 `extract/quote -> synthesize` 의 2단 구성으로 나눈다.
- 문서 입력이 길면 문서와 메타데이터를 먼저 두고, 사용자 질의와 출력 지시는 뒤에 둔다.
- 고정 지시는 앞에 두고, 가변 컨텍스트는 뒤에 둔다.
- retrieval 결과가 필요 없는 단계에는 retrieval payload 를 전달하지 않는다.

## 구조화 런타임 자산

서비스 단계는 prose 문서가 아니라 아래 자산으로 조합한다.

- 시나리오 선택: `ScenarioManifest`
- stage prompt: `docs/harness/prompt-bundles/<scenario>/workflow.json`
- offline/CI eval: `EvalSuite` + `promptfoo`
- runtime span grading: `TraceGradeSpec`

서비스 코드는 위 자산을 참조해 stage별 prompt 와 grader 를 조립해야 한다.

## 공통 span

모든 시나리오는 가능한 범위에서 아래 span 키를 사용한다.

- `auth`
- `intent-routing`
- `retrieval`
- `ocr`
- `rerank`
- `generation`
- `policy-check`
- `export`

필요한 span만 선택하되 이름은 변경하지 않는다.

## 동기 가드레일

아래 정책은 online eval보다 먼저 동기적으로 실행한다.

| 정책 | 기본 동작 |
| --- | --- |
| 권한 없는 문서/PLM 결과 | 즉시 제거 후 차단 또는 재질문 |
| citation 누락 | 생성 응답 실패 처리 |
| unsafe SQL | 실행 차단, 감사로그 기록 |
| catastrophic OCR failure | 해당 엔진 결과 폐기, fallback 실행 |

## 비동기 online eval

응답이 사용자에게 전달된 후 아래 평가를 비동기 수행한다.

- `citation_completeness`
- `groundedness`
- `retrieval_relevance`
- `plm_safety`
- `template_field_fill_rate`
- `ocr_parse_quality`
- `user_feedback_outcome`

## 시나리오별 런타임 체인

### `documents-rag`

`query rewrite -> retrieval -> citation attachment -> final answer`

평가 단위:

- rewrite 적합성
- retrieval relevance
- citation completeness
- grounded final answer

### `plm-query`

`intent -> template match or generated SQL -> validator -> executor -> summarizer`

평가 단위:

- template routing precision
- unsafe SQL block
- execution accuracy
- summary fidelity

### `draft-generation`

`template resolution -> evidence gather -> draft generation -> citation block assembly -> export`

평가 단위:

- template resolution accuracy
- evidence coverage
- field fill rate
- export integrity

### `ocr-pipeline`

`native extraction -> OCR 필요 판정 -> engine selection -> parse -> normalization -> quality judge`

평가 단위:

- OCR 필요 판정 정확도
- parse completeness
- layout/table preservation
- catastrophic failure rate

### `pms`

`intent routing -> policy check -> structured generation -> mutation preview -> execution`

평가 단위:

- action classification accuracy
- schema validity
- unauthorized mutation block

## OCR 운영 정책

- 기본 정책은 `native text extractor 우선 -> OCR 필요 판정 -> 품질 우선 엔진 선택 -> failure fallback`이다.
- 배치 기본엔진은 내부 벤치 결과로 최종 고정한다.
- 초기 비교 대상은 `Qwen3-VL-8B-Thinking`, `DeepSeek-OCR`, `PaddleOCR-VL-1.5`다.
- OCR 출력 표준은 `plain_text`, `markdown`, `layout_blocks`, `tables`, `confidence`, `artifacts`다.

## fallback 규칙

- retrieval relevance 저하 시: 필터 완화 후 재검색 또는 재질문
- groundedness 미달 시: 답변 대신 근거 부족 안내와 추가 조건 요청
- template fill rate 미달 시: 빈 필드 목록과 보완 요청 반환
- OCR parse quality 미달 시: 대체 OCR 엔진으로 재시도
- PLM safety 미달 시: 사전 정의 템플릿 결과만 반환

## 운영 구현 원칙

- trace 저장 형식은 OpenTelemetry 친화적으로 유지한다.
- 관찰성 UI는 나중에 `Langfuse` 를 붙일 수 있도록 provider-neutral contract를 유지한다.
- `promptfoo` 는 offline/CI 의 기본 runner 로 사용하고, 고위험 실험만 `Inspect AI` 계열을 보조로 사용한다.

## 운영 큐

- `triage/hard-fail`: ACL, unsafe SQL, catastrophic OCR
- `triage/quality-regression`: groundedness, relevance, fill rate
- `triage/user-feedback`: thumbs down, 재질문 반복, 수동 신고

운영 큐 항목은 다음 근무일 첫 번째 eval triage에서 검토한다.
