# 러닝 DB 전환 + 글로벌 컨텐츠 스코프 + 공유 주석

## Context

현재 러닝 앱은 `/learning/**/*.md` 파일을 Vite glob으로 번들해 `react-markdown`으로 렌더한다. 백엔드·DB 없음, 순수 정적 컨텐츠. 공유 주석(워크스페이스/전사 전원이 볼 수 있는 하이라이트/메모) 기능이 필요해졌고, 본문 편집에도 주석이 안정적으로 붙어 있어야 한다.

마크다운 + 여러 앵커 전략을 검토했으나 트레이드오프가 커서, **DB + BlockNote 전환**으로 확정. git 리뷰 워크플로는 포기.

추가로 중요한 요구사항이 드러남: 러닝은 "전사 공용 영역" 패턴의 첫 사례이며, 뒤따라 **공지사항 / 업무 가이드 / 지식베이스** 같은 워크스페이스 경계를 넘는 컨텐츠도 필요. 따라서 러닝을 러닝만을 위한 도메인으로 좁게 짓지 말고, **"글로벌 가시성(visibility=global)"을 docs 도메인에 일반 추상화**로 도입한다.

## Architecture

### 전사 공용 영역 = docs 확장

기존 docs 도메인(`NativeDoc`/`NativeDocPage`)을 확장해 워크스페이스 경계를 넘는 컨텐츠를 표현:

```
NativeDoc:
  + visibility: enum('workspace', 'global')   # 신규
  workspace_id: nullable                       # visibility='global'일 때 NULL
  source_app: str                              # 'learning', 'announcement', 'knowledge', ...
  source_kind: str                             # 'course', 'notice', 'article', ...
```

**권한 규칙 확장**:
- `visibility='workspace'` — 기존 로직 그대로 (워크스페이스 멤버 + per-doc ACL)
- `visibility='global'` — 인증된 전 사용자 조회 가능. 편집은 `global_editor` 역할 또는 시스템 admin만 (신규 역할 또는 user.is_staff 플래그 재사용)

**장점**:
- BlockNote 에디터·뷰어·Yjs·트리·공유 인프라 **모두 그대로 재사용**
- 러닝 = `source_app="learning", visibility="global"`인 NativeDoc 1개 + 하위 페이지 트리
- 공지사항/업무 가이드/지식베이스는 동일 메커니즘으로 나중에 추가
- 주석도 `doc_annotations`가 page_id FK만으로 global/workspace 양쪽에서 동작

### 러닝 매핑

- 1 Course = 1 `NativeDoc` (source_app="learning", source_kind="course", visibility="global")
- 1 Part = 최상위 `NativeDocPage` (parent_id=null)
- 1 Lesson = 자식 `NativeDocPage` (parent_id=part.id, content_blocks = BlockNote JSON)

### 주석 앵커

- BlockNote가 JSON 내부에 부여하는 블록 id(opaque stable string) 사용. 블록 편집에도 id 유지(BlockNote 내장 보장). 블록 삭제 시에만 orphan.
- 블록 내부 텍스트 범위: `anchor_text` + `offset_start/end` (블록 평문 기준). 리라이팅으로 offset drift 시 `anchor_text` fuzzy 복원 시도. 실패 시 `orphaned=true` 마킹하되 데이터 보존.

### 주석 스코프 (v1)

**글로벌 단일 공유**. 전 사용자가 같은 주석 세트를 본다. 필요 시 나중에 `workspace_id nullable` 필드 한 줄로 team 스코프 확장 가능 — v1에 미리 짓지 않음.

### 권한 (주석)

- 조회: 페이지 접근 권한 있으면 전원 조회
- 수정/삭제: 작성자 본인 + 워크스페이스/시스템 admin (타인 주석 삭제)

## Implementation Steps

> 프로젝트 로드맵의 "Phase N"과 혼동 방지를 위해 이 플랜 내부 단계는 "Step"으로 표기.

### Step 1 — docs 도메인에 global visibility 도입

**백엔드**:
- `apps/api/src/aidoo_api/domains/docs/models.py` — `NativeDoc`에 `visibility` enum 추가, `workspace_id` nullable 전환
- `apps/api/src/aidoo_api/domains/docs/service.py` — `check_doc_access()` 확장: visibility='global'일 때 인증된 사용자 모두 read 허용, 편집은 admin 역할 체크
- `apps/api/src/aidoo_api/domains/docs/router.py` — 기존 엔드포인트에 global docs 라우팅 경로 추가 (`/api/v1/docs/global/...`) 또는 workspace_id optional 처리
- Alembic: `NativeDoc.visibility` 컬럼 추가, 기존 레코드는 default='workspace'로 백필

**프론트엔드**:
- `apps/web/src/domains/docs/docs-api.ts` — global docs 조회 함수 추가
- 기존 DocsView는 변경 최소. 러닝은 별도 view에서 global docs API 호출

### Step 2 — MD→BlockNote 컨버터 보강

현재 `_markdown_to_blocks()`는 H1-3 + 문단만 지원. 실제 러닝 레슨에 필요한:
- 헤딩 H1-6
- 순서·비순서 리스트 (중첩)
- 펜스 코드 블록 (언어 힌트 보존)
- GFM 표
- 인라인 bold/italic/code/link
- blockquote, hr

**대상 파일**: `apps/api/src/aidoo_api/domains/docs/markdown_import.py` (신규 유틸로 분리)
**도구**: Python `marko` (CommonMark + GFM) 파서로 AST → BlockNote 블록 스키마(`packages/ui/src/lib/editor/schema.ts` 참조) 매핑. 샘플 레슨 `01-오리엔테이션.md`로 라운드트립 단위 테스트.

### Step 3 — 러닝 seed 마이그레이션

**신규 파일**: `apps/api/scripts/seed_learning.py`

흐름:
1. `apps/web/src/domains/learning/manifest.ts`의 course/part/lesson 구조를 Python으로 포팅 (또는 JSON export)
2. 각 Course에 대해 `NativeDoc` 생성 (`source_app="learning"`, `source_kind="course"`, `visibility="global"`, `workspace_id=NULL`)
3. Part → top-level `NativeDocPage`, Lesson → child `NativeDocPage` (sort_order 보존)
4. `.md` 본문을 Step 2 컨버터로 BlockNote JSON 변환 후 저장
5. Idempotent: 동일 source_ref(`course:{slug}`)의 NativeDoc이 이미 있으면 skip, `--overwrite` 플래그로 재생성

### Step 4 — Annotations 도메인

범용 설계. 러닝 + 모든 docs 페이지에서 동작.

**백엔드** `apps/api/src/aidoo_api/domains/annotations/`:
- `models.py` — `DocAnnotation`:
  ```
  id (PK), page_id (FK→docs_native_doc_pages),
  author_id (FK→users),
  block_id (str, indexed with page_id),
  anchor_text (str),
  anchor_offset_start (int), anchor_offset_end (int),
  body (text),
  color (enum: yellow|green|pink|blue),
  orphaned (bool, default false),
  created_at, updated_at, trashed_at
  ```
- `schemas.py` — `AnnotationCreate/Update/Read` (author join 필드 포함)
- `service.py` — CRUD + 권한 체크 (docs의 page access 재사용, global 페이지 포함)
- `router.py` — `GET/POST /api/v1/docs/pages/{page_id}/annotations`, `PATCH/DELETE /api/v1/annotations/{id}`
- Alembic: `doc_annotations` 테이블 신규

**프론트엔드**:
- `apps/web/src/domains/annotations/` — API 클라이언트, React Query 훅, types
- `apps/web/src/components/views/annotations/`:
  - `AnnotationPopover.tsx` — 드래그 선택 시 floating 툴바 (색상 4개 + 메모 input)
  - `MarginaliaPanel.tsx` — 우측 마진 주석 카드 리스트 (데스크톱)
  - `AnnotationCard.tsx` — 작성자 아바타·시간·메모·수정삭제
  - `OrphansPanel.tsx` — orphaned 주석 모아보기, 원본 anchor_text 표시 + 수동 재앵커
  - `AnnotationLayer.tsx` — BlockNote 뷰어 위에 overlay (block_id 매치 → 해당 범위 하이라이트)

### Step 5 — LearningCourseView DB 전환

**제거**:
- `apps/web/src/domains/learning/content.ts` (Vite glob 로더)

**수정**:
- `apps/web/src/domains/learning/manifest.ts` → API 기반 `useLearningCourse(courseSlug)` 훅 (global docs API 호출, course + page tree fetch). 기존 `findCourse/findLesson/getAllLessons` API 형태는 유지해 호출자 최소 수정.
- `apps/web/src/components/views/LearningCourseView.tsx`:
  - `react-markdown` 제거
  - `@aidoo/ui`의 `block-viewer.tsx` 재사용해 BlockNote JSON 렌더
  - `AnnotationLayer` + `MarginaliaPanel` 통합
  - 기존 sticky TOC / 넓게-좁게 토글 유지
- URL 경로 `/w/:workspaceSlug/learning/:courseSlug/:lessonSlug` 유지. 슬러그→doc/page 해석은 프론트에서 API 응답 기반.

### Step 6 — Admin 편집 모드 (v1 포함)

사용자가 git 리뷰 포기 대신 UI 편집을 얻어야 DX가 유지됨. v1에 포함.

- `LearningCourseView`에 admin만 보이는 "편집 모드" 토글 (아이콘 버튼)
- 토글 ON: `collaborative-block-editor.tsx` 재사용 (Yjs 실시간 협업 포함, NativeDocPage는 이미 docs_collab_documents와 연결됨)
- admin 판단: `user.is_staff` 또는 새로운 `global_editor` 역할 — 기존 인증 모듈 확인 후 결정
- 저장은 Yjs 자동. 명시적 "publish" 단계는 v2 이후

## Critical Files

**수정**
- `apps/api/src/aidoo_api/domains/docs/models.py` — visibility 컬럼
- `apps/api/src/aidoo_api/domains/docs/service.py` — visibility 권한 로직
- `apps/api/src/aidoo_api/domains/docs/router.py` — global docs 엔드포인트
- `apps/web/src/components/views/LearningCourseView.tsx` — 전면 재작성 (레이아웃/토글 유지)
- `apps/web/src/domains/learning/manifest.ts` — API 훅으로 교체
- `apps/web/src/App.tsx` — 라우팅 동일, import 정리

**신규**
- `apps/api/src/aidoo_api/domains/docs/markdown_import.py`
- `apps/api/src/aidoo_api/domains/annotations/` (models, schemas, service, router)
- `apps/api/alembic/versions/XXXX_add_doc_visibility.py`
- `apps/api/alembic/versions/XXXX_add_doc_annotations.py`
- `apps/api/scripts/seed_learning.py`
- `apps/web/src/domains/annotations/` (api.ts, hooks.ts, types.ts)
- `apps/web/src/components/views/annotations/` (5개 컴포넌트)

**제거**
- `apps/web/src/domains/learning/content.ts`
- `/learning/vibe-coding-foundations/*.md` (seed 이후. git history에서 복원 가능)

## Reuse (새로 만들지 않음)

- **BlockNote 에디터·뷰어**: `packages/ui/src/lib/editor/block-viewer.tsx`, `collaborative-block-editor.tsx`
- **Docs 트리 구조/API**: `NativeDoc` + `NativeDocPage`의 self-referential parent_id + sort_order
- **Yjs collab**: `apps/api/src/aidoo_api/domains/docs/collab.py` (NativeDocPage 기반이라 global doc에도 그대로 동작)
- **Docs 권한 프레임**: `check_doc_access` 확장 기반
- **BlockNote 스키마**: `packages/ui/src/lib/editor/schema.ts`

## Verification

1. **마이그레이션**: `alembic upgrade head` 성공, `NativeDoc.visibility` 기본값 'workspace'로 백필 확인. `alembic downgrade -1` 역방향 무결
2. **seed 실행**: Course 1개(global), Part 4 + Lesson 33이 DB에 생성됨. 재실행 시 skip
3. **기존 URL 호환**: `/w/hq/learning/vibe-coding-foundations/01-orientation` 접근 → 기존 마크다운 렌더와 시각적 동등 (헤딩·표·코드블록·리스트 모두)
4. **글로벌 가시성**: 워크스페이스 A 사용자 / 워크스페이스 B 사용자 모두 동일한 러닝 컨텐츠 조회 가능
5. **주석 생성/영속**: 텍스트 드래그 → popover → 저장 → 새로고침 후에도 같은 블록 같은 범위에 마커/메모
6. **주석 공유**: 다른 사용자로 로그인 → 같은 주석 조회
7. **주석 권한**: 작성자로 메모 수정·삭제 가능, 타인은 자기 것만. admin은 타인 것도 삭제 가능
8. **Orphan 처리**: 편집 모드에서 블록 삭제 → 그 주석 `orphaned=true`로 전환, "위치 유실" 탭 표시, 원본 anchor_text 보존
9. **편집 모드**: admin 로그인 → "편집" 토글 → BlockNote 편집기 활성 → 저장 후 다른 뷰에도 반영
10. **Yjs 실시간**: admin 두 명 동시 편집 → 실시간 동기화
11. **레이아웃 유지**: sticky TOC, 넓게/좁게 토글, 이전/다음 네비 정상
12. **백엔드 테스트**: `apps/api/src/aidoo_api/tests/` — visibility 권한 매트릭스 + annotations CRUD/권한
13. **프론트 테스트**: `LearningCourseView.spec.tsx` 업데이트 (mock API), `AnnotationPopover.spec.tsx` 신규

## 확정 사항 (Open Questions 정리)

1. **`.md` 파일**: seed 완료 후 삭제 (git history로 복원 가능) ✅
2. **편집 권한**: 워크스페이스/시스템 admin만 ✅
3. **주석 삭제 권한**: 작성자 + admin ✅
4. **편집 UI**: v1에 포함 (Step 6) ✅
5. **스코프**: 러닝 컨텐츠 글로벌, 주석도 글로벌 단일 공유로 시작. team 스코프는 추후 필드 추가로 확장 ✅

## 향후 확장 (이 플랜 범위 밖, 같은 기반 재사용)

- **공지사항**: `source_app="announcement"`, `visibility="global"`
- **업무 가이드 / 지식베이스**: `source_app="knowledge"`, `visibility="global"`
- **전사 검색**: global docs 인덱스에 걸면 워크스페이스 경계 없이 검색 가능
- **주석 team 스코프**: `doc_annotations.workspace_id nullable` 추가, NULL=글로벌, 값 있으면 team 전용

## 롤백 계획

Step 단위로 독립 롤백 가능하게 구성.

- **Step 1 (visibility 컬럼)**: `alembic downgrade` 1단계. 기존 workspace docs는 영향 없음 (기본값 'workspace'로 백필했기 때문).
- **Step 2 (MD 컨버터)**: 신규 유틸 파일만 추가 — 제거해도 기존 동작 영향 없음.
- **Step 3 (seed 데이터)**: seed 스크립트에 `--rollback` 옵션 제공(`source_ref='course:{slug}'`로 조회해 soft-delete). `.md` 파일은 git history에서 복원 가능.
- **Step 4 (annotations 테이블)**: 데이터 유실 우려가 가장 큼 → downgrade 전 DB 덤프 필수. 롤백 시 테이블 drop.
- **Step 5 (LearningCourseView 전환)**: 순수 프론트 변경. git revert 1개 커밋 + Vite glob 로더 파일 복원.
- **Step 6 (편집 모드)**: 토글만 숨기면 기능 비활성. 코드 제거는 별도.

최악의 경우 전체 롤백: Step 6 → 1 순서 역순으로. 주석 DB 데이터는 덤프 보존 필수.
