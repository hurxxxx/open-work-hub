# 시스템 기준 구조

## 목적

이 문서는 신규 AI 포털의 구현 기준 구조를 고정한다. 레거시 프로토타입의 기능 흐름만 참고하고, 새 구현은 `문서 RAG`, `PLM 조회`, `문서 작성 지원`, `관리자/RBAC`, `최소 PMS/Wiki`를 중심으로 설계한다.

## 기준 기술 스택

- 모노레포: `Nx + pnpm`
- 프론트엔드: `React 19`, `TypeScript`, `Vite`, `TanStack Router`, `TanStack Query`, `React Hook Form`, `Zod`, `Tailwind CSS`, `Radix UI`, `Milkdown`
- 백엔드: `Python 3.12`, `FastAPI`, `Pydantic v2`, `SQLAlchemy 2`, `Alembic`
- 작업 워커: `Celery + Redis`
- 데이터: `PostgreSQL 18`, `MinIO`
- 검색/RAG: `OpenSearch`, `Qdrant`
- 추론: 온프레미스 `vLLM`, `Qwen3-Embedding-8B`, `Qwen3-Reranker-8B`
- OCR 비교 대상: `Qwen3-VL-8B-Thinking`, `DeepSeek-OCR`, `PaddleOCR-VL-1.5`

## 구성 원칙

- 사용자 인터페이스, API, 비동기 작업, 운영성 도구는 서로 다른 책임 단위로 분리한다.
- 조립 계층과 도메인 계층을 구분한다. 조립 계층은 wiring만 담당하고, 도메인 계층은 비즈니스 규칙을 소유한다.
- 공유 계약은 최소화하고, 구현 공유보다 명시적 계약과 facade를 우선한다.
- 프롬프트, workflow, eval, guardrail은 코드 구현보다 먼저 문서와 구조화 자산으로 정의한다.

## 컨텍스트 및 하네스 자산

- 시나리오 계약은 `docs/harness/manifests/scenarios/*.json` 에 둔다.
- stage prompt는 `docs/harness/prompt-bundles/<scenario>/` 에 둔다.
- eval runner와 dataset 계약은 `docs/harness/manifests/eval-suites/*.json` 및 `docs/harness/evals/` 에 둔다.
- trace/span grading 계약은 `docs/harness/manifests/trace-grade-specs/*.json` 에 둔다.
- 경로 기반 도메인 선택 계약은 `docs/agents/manifests/domain-rule-manifests/*.json` 에 둔다.
- 실제 코드 스캐폴드가 생기면 도메인 루트에 local `AGENTS.md` 를 두되, 현재 디렉터리 트리 스냅샷은 기록하지 않는다.

## 책임 단위

- `auth`: 로그인, 세션, 사용자/역할, 기능 노출
- `documents`: 문서 동기화, 메타데이터, 원문 조회
- `search`: 검색, RAG, 인용, 리랭크
- `plm`: 질의 템플릿, SQL 안전성, 결과 요약
- `drafts`: 템플릿, 초안, 내보내기
- `admin`: 감사로그, 기능 토글, 운영 제어
- `pms`: 작업, 이슈, 상태 흐름
- `wiki`: 문서 편집, 버전, 참조 링크

이 책임 단위는 유지하되, 실제 디렉토리 이름과 파일 배치는 구현 단계에서 달라질 수 있다. 문서는 현재 트리 스냅샷이 아니라 책임과 경계를 표현한다.

## 경계 규칙

- 조립 계층은 비즈니스 로직을 소유하지 않는다.
- 프론트와 백엔드가 함께 쓰는 것은 최소 공용 계약만 허용한다.
- 각 도메인은 다른 도메인의 내부 구현을 직접 import하지 않는다.
- 교차 도메인 의존은 공용 계약, 이벤트, 명시적 facade만 허용한다.
- FastAPI `APIRouter`는 각 도메인이 소유하고, 상위 조립 계층은 등록만 수행한다.
- Alembic migration은 도메인별 version directory를 사용한다.
- Prompt, workflow, eval 규약은 코드 안에 흩뿌리지 않고 `docs/harness`와 시나리오 문서에서 먼저 정의한다.

## 충돌 최소화 규칙

- 한 작업은 가능한 한 하나의 도메인 경계와 하나의 시나리오를 중심으로 수행한다.
- 새 엔드포인트 추가 시 `contracts -> domain router -> domain UI` 순서로만 확장한다.
- 공용 유틸은 바로 `shared`로 올리지 않는다. 최소 두 도메인에서 반복될 때만 승격한다.
- 라우트 등록, 데이터 모델, 마이그레이션, 화면 엔트리는 해당 도메인 소유자가 관리한다.
- 다른 개발자가 이미 수정 중인 도메인 내부 파일 대신 facade, contracts, composition layer를 먼저 검토한다.

## 데이터 흐름

### 문서 RAG

`mcloudoc -> 수집/증분 동기화 -> 원문 저장(MinIO) -> 텍스트 추출/OCR -> 청킹 -> 임베딩(Qdrant) + 색인(OpenSearch) -> 리랭크 -> 인용 포함 응답`

### PLM 조회

`사용자 요청 -> 시나리오 선택 -> 질의 템플릿 매칭 또는 SQL 계획 -> 안전성 검증 -> 읽기 전용 실행 -> 결과 요약/표현`

### 문서 작성

`사용자 주제/템플릿 선택 -> 관련 근거 수집 -> 초안 생성 -> citation block 조립 -> 검토/편집 -> docx/pdf 내보내기`

## UI 기준

- 홈은 카드형 포털이 아니라 `전역 검색`, `최근 작업`, `즐겨찾기 워크플로`, `할당 작업` 중심으로 구성한다.
- 기본 레이아웃은 `좌측 조건`, `중앙 결과`, `우측 근거/액션`의 3패널 구조를 우선한다.
- 검색/권한/근거 표현은 `Glean` 스타일을 참고하고, 리스트/상태/작업 밀도는 `Linear` 스타일을 참고한다.
- 카드형 섹션은 최소화하고 표, 리스트, 슬라이드오버, 인라인 상태 전환을 우선한다.

## 문서 원본 위치

- 시스템 구조 기준: [docs/architecture/system-blueprint.md](/Users/edward/projects/doowon/docs/architecture/system-blueprint.md)
- 하네스 기준: [docs/harness/harness-overview.md](/Users/edward/projects/doowon/docs/harness/harness-overview.md)
- 에이전트 실행 규약: [docs/agents/agent-operating-standard.md](/Users/edward/projects/doowon/docs/agents/agent-operating-standard.md)
- 운영 게이트: [docs/ops/release-gates-and-alerts.md](/Users/edward/projects/doowon/docs/ops/release-gates-and-alerts.md)
