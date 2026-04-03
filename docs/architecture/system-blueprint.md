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

## 배포 단위

- `apps/web`: SPA 셸, 페이지 엔트리, 라우터 조립
- `apps/api`: FastAPI 엔트리, 인증/미들웨어, 도메인 라우터 조립, OpenAPI 노출
- `apps/worker`: 비동기 작업 등록, 스케줄링, 배치
- `apps/ops`: 벤치마크 CLI, 회귀 평가, 샘플 적재, scorecard 생성

## 저장소 구조

```text
apps/
  web/
  api/
  worker/
  ops/
packages/
  contracts/
  ui/
  testing/
  config-web/
  config-api/
  web/
    auth/
    documents/
    plm/
    drafts/
    admin/
    pms/
    wiki/
  api/
    auth/
    documents/
    plm/
    search/
    drafts/
    admin/
    pms/
    wiki/
docs/
  architecture/
  harness/
  agents/
  ops/
```

## 도메인 소유권

| 도메인 | 주요 책임 | 프론트 소유 패키지 | 백엔드 소유 패키지 |
| --- | --- | --- | --- |
| `auth` | 로그인, 세션, 사용자/역할, 기능 노출 | `packages/web/auth` | `packages/api/auth` |
| `documents` | 문서 동기화, 메타데이터, 원문 조회 | `packages/web/documents` | `packages/api/documents` |
| `search` | 검색, RAG, 인용, 리랭크 | `packages/web/documents` | `packages/api/search` |
| `plm` | PLM 질의 템플릿, SQL 안전성, 결과 요약 | `packages/web/plm` | `packages/api/plm` |
| `drafts` | 템플릿, 초안, 내보내기 | `packages/web/drafts` | `packages/api/drafts` |
| `admin` | 감사로그, 기능 토글, 운영 제어 | `packages/web/admin` | `packages/api/admin` |
| `pms` | 작업, 이슈, 상태 흐름 | `packages/web/pms` | `packages/api/pms` |
| `wiki` | 문서 편집, 버전, 참조 링크 | `packages/web/wiki` | `packages/api/wiki` |

## 경계 규칙

- `apps/*`는 조립만 하고 비즈니스 로직을 소유하지 않는다.
- `packages/contracts`만 프론트와 백엔드가 공통으로 참조할 수 있다.
- `packages/web/<domain>`은 다른 도메인의 내부 구현을 직접 import하지 않는다.
- `packages/api/<domain>`은 다른 도메인의 내부 서비스나 ORM 모델을 직접 import하지 않는다.
- 교차 도메인 의존은 `contracts`, 이벤트, 명시적 facade만 허용한다.
- FastAPI `APIRouter`는 각 도메인이 소유하고 `apps/api`에서는 `include_router()`만 수행한다.
- Alembic migration은 도메인별 version directory를 사용한다.
- Prompt, workflow, eval 규약은 코드 안에 흩뿌리지 않고 `docs/harness`와 시나리오 문서에서 먼저 정의한다.

## 충돌 최소화 규칙

- 한 작업은 가능한 한 하나의 도메인 패키지와 하나의 시나리오를 중심으로 수행한다.
- 새 엔드포인트 추가 시 `contracts -> domain router -> domain UI` 순서로만 확장한다.
- 공용 유틸은 바로 `shared`로 올리지 않는다. 최소 두 도메인에서 반복될 때만 승격한다.
- 라우트 등록, 데이터 모델, 마이그레이션, 화면 엔트리는 도메인 소유자가 관리한다.
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
