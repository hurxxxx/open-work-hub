# 도메인 Local Rule 템플릿

실제 `Nx/FastAPI/React` 스캐폴드가 생기면 각 도메인 루트에 이 템플릿을 기반으로 `AGENTS.md`를 둔다. 이 문서는 현재 디렉터리 구조 스냅샷이 아니라, 변경이 잦아도 유지되는 책임과 경계만 기록한다.

## 권장 위치

- `apps/api/AGENTS.md`
- `apps/web/AGENTS.md`
- `apps/worker/AGENTS.md`
- `apps/ops/AGENTS.md`
- `apps/api/src/<python_app>/domains/<domain>/AGENTS.md`
- `apps/web/src/domains/<domain>/AGENTS.md`

## 최소 섹션

### `domain`

- 도메인 식별자
- 담당 사용자 가치 또는 업무 흐름

### `ownership`

- 이 도메인이 소유하는 라우트, 서비스, UI, 배치, 계약
- 다른 도메인이 직접 수정하면 안 되는 내부 구현

### `scenario candidates`

- 관련 `scenario_id`
- 기본 시나리오 1개

### `must read docs`

- 현재 도메인에서 기본으로 읽어야 하는 문서
- 관련 `ScenarioManifest`
- 관련 `EvalSuite`

### `do not load by default`

- 기본적으로 읽지 않을 다른 도메인 문서
- 현재 작업과 무관한 운영/아키텍처 문서

### `required evals`

- 반드시 다시 봐야 하는 dataset
- blocking metric
- release gate 영향

### `invariants`

- safety invariant
- UI invariant
- contract invariant

## 예시 뼈대

```md
# Domain Rule: plm

## domain

- `domain_id`: `plm`
- 목적: 읽기 전용 PLM 조회와 안전한 결과 요약

## ownership

- PLM query router, planner, validator, executor adapter
- PLM 결과 요약 UI와 표 렌더링

## scenario candidates

- `plm-query`

## must read docs

- `docs/agents/context-loading-policy.md`
- `docs/harness/scenarios/plm-query.md`
- `docs/harness/manifests/scenarios/plm-query.json`
- `docs/harness/manifests/eval-suites/plm-query.json`

## do not load by default

- `docs/harness/scenarios/documents-rag.md`
- `docs/harness/scenarios/draft-generation.md`

## required evals

- `golden`
- `adversarial`
- blocking metric: `unsafe_sql_block_rate`

## invariants

- validator 없이 SQL 실행 금지
- allowlist 밖 스키마 참조 금지
- 결과 요약은 실제 결과 테이블과 충돌하면 안 됨
```
