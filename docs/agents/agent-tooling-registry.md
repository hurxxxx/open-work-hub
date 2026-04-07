# 에이전트 명령 및 역할 카탈로그

## 목적

이 문서는 이 저장소에서 사용할 수 있는 에이전트용 명령, 역할, 스킬을 한눈에 보여주는 카탈로그다. `gstack`의 역할형 워크플로 아이디어를 차용했지만, 이 프로젝트에서는 하네스와 시나리오 규약을 중심으로 축소 적용한다.

## 핵심 워크플로

`탐색 -> 시나리오 선택 -> 구현/갱신 -> 평가 -> 문서 동기화 -> 릴리즈 판단 -> 회고/학습`

## Claude Code 명령

| 명령 | 역할 | 사용 시점 |
| --- | --- | --- |
| `/select-scenario` | 시나리오 라우터 | 작업 시작 전 |
| `/run-regression` | 회귀 체크리스트 생성 | 구현 전/후 |
| `/prepare-scorecard` | scorecard 초안 정리 | eval 후 |
| `/update-eval-case` | eval case 갱신 | prompt/workflow 변경 시 |
| `/document-release` | 문서 최신화 점검 | 기능/정책 변경 후 |
| `/checkpoint` | 작업 중간 상태 기록 | 큰 변경 전/중 |
| `/learn` | durable learning 정리 | 비직관적 인사이트 발견 시 |
| `/retro` | 회고 정리 | 큰 작업 종료 후 |

## Claude Code 서브에이전트

| 에이전트 | 역할 |
| --- | --- |
| `rag-evaluator` | `documents-rag` 품질/인용/ACL 리뷰 |
| `plm-safety-reviewer` | `plm-query` SQL 안전성과 권한 리뷰 |
| `ui-conformance-reviewer` | 대표 화면과 공통 컴포넌트 기준의 UI 일관성 리뷰 |
| `doc-architect` | 문서 원본과 어댑터 정합성 리뷰 |

## Codex skill

| 스킬 | 역할 |
| --- | --- |
| `doowon-harness-engineering` | 시나리오 매핑, 문서 우선 탐색, eval 영향 분석, 표준 응답 형식 강제 |

## Helper 스크립트

| 스크립트 | 역할 |
| --- | --- |
| `select_scenario.py` | 경로 힌트와 요청을 사용해 `scenario_id` 와 기본 문서 세트를 고른다 |
| `select_context_docs.py` | `scenario_id`, `domain_id`, 파일 경로를 바탕으로 `must_read_docs` 를 계산한다 |
| `required_regressions.py` | `EvalSuite` 기준으로 dataset, gate metric, `promptfoo` 설정을 출력한다 |

## 참조 문서

- 운영 규약: [agent-operating-standard.md](/Users/edward/projects/doowon/docs/agents/agent-operating-standard.md)
- 컨텍스트 선택 기준: [context-loading-policy.md](/Users/edward/projects/doowon/docs/agents/context-loading-policy.md)
- 도메인 매핑: [domain-context-mapping.md](/Users/edward/projects/doowon/docs/agents/domain-context-mapping.md)
- 하네스 개요: [harness-overview.md](/Users/edward/projects/doowon/docs/harness/harness-overview.md)
- 운영 워크플로: [sprint-workflow.md](/Users/edward/projects/doowon/docs/ops/sprint-workflow.md)
- 학습/체크포인트: [learnings-and-checkpoints.md](/Users/edward/projects/doowon/docs/ops/learnings-and-checkpoints.md)
