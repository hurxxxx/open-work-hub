# 도메인 컨텍스트 매핑

이 문서는 `파일 경로 -> domain_id -> scenario_id` 로 이어지는 선택 규칙을 정의한다. 전역 문서를 모두 읽는 대신, 현재 작업 경로에서 가장 가까운 도메인 규칙과 시나리오 계약만 로드하는 것이 목적이다.

## 선택 순서

1. 변경 대상 파일 경로를 수집한다.
2. `DomainRuleManifest` 의 `path_prefixes` 와 대조해 `domain_id` 를 고른다.
3. 해당 도메인의 `scenario_candidates` 를 확인한다.
4. 요청 의도와 가장 잘 맞는 `scenario_id` 하나를 고른다.
5. `ScenarioManifest` 의 `must_read_docs` 와 `do_not_load_by_default` 를 적용한다.

## 현재 기본 매핑

| domain_id | 주 용도 | 시나리오 후보 |
| --- | --- | --- |
| `documents` | 문서 검색, 근거형 응답, citation | `documents-rag` |
| `plm` | 읽기 전용 PLM 조회, SQL safety | `plm-query` |
| `drafts` | 초안 생성, export, citation block | `draft-generation` |
| `ocr` | OCR 라우팅, 파싱, 품질 판단 | `ocr-pipeline` |
| `wiki-pms` | 위키/작업/이슈 preview 생성 | `wiki-pms` |
| `shared-harness` | docs/harness, eval, scorecard, adapters | 복수 시나리오 |

## 원칙

- 경로만으로 충분히 좁혀지면 다른 도메인 문서는 읽지 않는다.
- 경로가 애매할 때만 요청 텍스트로 시나리오를 보정한다.
- `shared-harness` 작업은 관련 시나리오를 최소 1개 명시하고 시작한다.
- 현재 구조 스냅샷이 바뀌더라도 `path_prefixes` 는 책임 단위 기준으로만 유지한다.

## 참조 자산

- 시나리오 계약: [docs/harness/manifests/scenarios](/Users/edward/projects/doowon/docs/harness/manifests/scenarios)
- 도메인 계약: [docs/agents/manifests/domain-rule-manifests](/Users/edward/projects/doowon/docs/agents/manifests/domain-rule-manifests)
- 컨텍스트 정책: [docs/agents/context-loading-policy.md](/Users/edward/projects/doowon/docs/agents/context-loading-policy.md)
