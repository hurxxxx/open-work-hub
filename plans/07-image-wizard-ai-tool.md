# 07. Image Wizard — AI 앱의 새 어시스턴트 도구

## Context

기존 **AI 앱**(`apps/web/src/app-modules/ai/`) 안에 인포그래픽 / 업무용 문서
이미지를 만들어 주는 위저드 도구를 추가한다. 새 앱이 아니라 AI 앱의 nav
아이템(tool)으로 들어가서 chatbot, search, drafting, ppt-assistant 등과 같은
줄에 위치한다.

사용자는 자유 프롬프트를 쓰지 않는다. 위저드가 다음을 단계별로 묻는다:

1. 이 이미지를 어디에 쓸 것인지 (사용처)
2. 원하는 스타일
3. 적합한 레이아웃
4. (선택) 참고 이미지 업로드
5. (선택) 참고 컨텍스트 첨부 — 회의록 / PMS 태스크 / Docs
6. LLM이 합성한 **이미지 브리프**(텍스트)를 확인하고 자연어로 수정 요청
7. 승인 — 이때 비로소 실제 이미지 생성 API가 호출됨

이미지 생성은 **OpenAI Codex / Agents SDK** (raw Images REST API가 아님) 로
위임해서 에이전트가 내부적으로 프롬프트 구성, 참고 이미지 결합,
재생성/리파인을 알아서 처리하도록 한다.

OpenAI API 키는 서버에만 보관. 스택은 기존 FastAPI + Celery worker + MinIO
그대로 활용.

**Why now**: 회의록/태스크 요약/기획 문서를 정리해 한 장짜리 인포그래픽으로
만들고 싶을 때, 지금은 사용자가 외부 도구로 나가야 한다. 위저드 + 컨텍스트
인식 브리프로 5분 걸리던 프롬프트 엔지니어링을 클릭 몇 번으로 줄이면서도,
최종 브리프는 사람이 검토/승인하는 단계를 유지한다.

## Architecture / Principles

### AI 앱과의 결합 방식

AI 앱은 기능을 **nav 아이템 = "tool"** 단위로 노출한다. 각 tool은
`/tool/<navItemId>`로 접근하고, `tool-view-wrapper.tsx`가 toolId를 보고
적절한 element를 렌더링한다. 이번 작업에서는 새 nav 아이템 하나를 추가한다.

- nav id: `image-wizard`
- title key: `image-wizard`
- icon: `ImageIcon` (lucide-react)
- category: `Assistants` (`ppt-assistant` 옆자리)
- 진입 URL: `/tool/image-wizard?workspace=<slug>`
- 내부 URL state: `?step=1..7`, `?gen=<generationId>` (새로고침 시 재개)
- `AppModuleId` union 변경 없음. 새 manifest 없음. 새 top-level route 없음.

### 백엔드 원칙

- 새 도메인 `domains/images` 추가, 기존 도메인 패턴(models / schemas / router /
  service / prompt) 그대로 따른다.
- **브리프 생성**(step 6의 인터랙션)은 기존 `core/llm.py`의 chat LLM 풀을
  사용한다. 인터랙티브하고 저렴, 컨텍스트 하이드레이션을 우리가 통제.
- **이미지 생성**(승인 후)만 OpenAI Codex/Agents SDK로 실행. Celery worker
  안에서 `Runner.run` 호출 → 에이전트가 내부 image_generation tool로
  반복/리파인 → 결과 이미지를 MinIO에 저장.
- 기능 플래그 `DOOWON_IMAGE_ENABLED` 도입. 비활성 시 라우터 503.
- 이미지 모델 기본값 `gpt-image-2` (env로 override 가능). 슈퍼바이저 모델
  기본값 `gpt-5` (env override).

### UX 원칙

- **브리프는 직접 편집 불가**. 모든 수정은 채팅창 같은 자연어 지시로 입력하고
  LLM이 반영. `brief_versions`에 의도가 함께 기록되어 회귀/되돌리기 가능.
- **승인 게이트가 명시적**. 승인 전엔 절대 이미지 생성 API를 부르지 않는다.
- **위저드 상태는 항상 서버에 자동 저장**. 새로고침이나 이탈 후 재개 가능.
- 결과 이미지는 v1 단계에서는 AI 앱 내부 갤러리에서만 보인다 (NativeDoc 자동
  저장 안 함).

## 위저드 플로우 (UX)

각 단계는 vertical card stack의 카드. 진입 시점에 `ImageGeneration` 행을
생성하고 단계마다 PATCH로 자동 저장. 이전 단계는 언제든 펴서 수정 가능.

1. **사용처 (Use-case)** — 단일 선택 + 썸네일 예시:
   meeting deck slide / report cover / docs hero / status one-pager /
   process flow / comparison / timeline / quote-card / social header /
   기타(자유 입력).

2. **스타일 (Style)** — 다중 칩: clean-corporate / editorial / hand-drawn /
   data-viz / flat-illustration / photo-real / minimal-mono. 그리고 팔레트
   (auto / brand / warm / cool / monochrome / vivid)와 배경(transparent /
   white / dark).

3. **레이아웃 (Layout)** — 와이어프레임 미리보기가 들어간 라디오 카드:
   single-focus / left-text-right-visual / top-title-grid / 3-column /
   2-row-comparison / timeline-horizontal / freeform. 종횡비
   (`1024x1024` / `1792x1024` / `1024x1792`) 같이 선택.

4. **참고 이미지 (선택)** — drag & drop 업로드, 기본 최대 4장. 썸네일마다
   역할 칩(**style ref / composition ref / content ref**) 지정. MinIO에 저장
   후 에이전트에 인라인 멀티모달 입력으로 전달.

5. **참고 컨텍스트 (선택)** — 워크스페이스 안에서 다중 첨부. recording 모듈의
   picker 패턴 그대로 재사용:
   - 회의록: 기존 `MeetingPickerModal` 재사용
   - PMS 태스크: 기존 `TaskPickerModal` 재사용
   - Docs: `DocPickerModal` 새로 작성 (`MeetingPickerModal`의 near-copy)
   추가로 "audience / tone / 기타 메모" 자유 입력 박스.
   (워크스페이스 파일 첨부는 v2로 미룸.)

6. **브리프 검토 (Review brief)** — 백엔드가 LLM으로 합성한 이미지 브리프
   (~200단어, 섹션: TITLE / LAYOUT / KEY ELEMENTS / COLORS / TYPOGRAPHY /
   NOTES)를 보여준다.
   - 브리프 본문은 **읽기 전용**.
   - 아래의 **채팅창**에 자연어로 수정 요청. 예: "팔레트를 더 따뜻하게",
     "두 번째 항목을 'Q3 ARR +18%'로 바꿔줘". 백엔드가 prior brief + edit
     instruction으로 LLM 재호출 → 새 버전 append → `brief_versions` 히스토리
     유지(되돌리기 가능).
   - **Regenerate**(처음부터 다시) / **Approve** 버튼.

7. **생성 (Generate)** — Approve를 누르면 `image_status`가 `queued` →
   `running` → `succeeded`/`failed`. 클라이언트는 2초 간격 폴링. 성공 시
   미리보기 + 다운로드 + "복제해서 수정" + "버리기" 액션. 결과는 AI 앱
   안의 image-wizard 갤러리(`/tool/image-wizard?view=gallery`)에서만 조회.

## 구현 단계

### 1단계 — 백엔드 도메인 + 마이그레이션

**파일 (신규):**

- `apps/api/src/aidoo_api/domains/images/__init__.py`
- `apps/api/src/aidoo_api/domains/images/models.py` — SQLAlchemy
  `ImageGeneration` 정의:
  - `id`, `workspace_id`, `owner_id`
  - `use_case` (string)
  - `style` (JSONB — chips + palette + background)
  - `layout` (JSONB — layout id + aspect ratio)
  - `details` (JSONB — audience/tone notes + free text)
  - `context_refs` (JSONB array — `{kind: "meeting"|"task"|"doc", id, snapshot}`)
  - `reference_image_keys` (JSONB array — `{storage_key, role: "style"|"composition"|"content"}`)
  - `brief_versions` (JSONB array — `[{text, created_at, edit_instruction|null}]`; current = last)
  - `brief_status` (enum: drafting, ready, approved)
  - `image_status` (enum: idle, queued, running, succeeded, failed)
  - `image_storage_key` (nullable)
  - `image_model` (사용된 OpenAI 이미지 모델 id)
  - `agent_trace_id` (nullable — Codex/Agents SDK run id, 디버깅용)
  - `failure_reason` (nullable)
  - `created_at`, `updated_at`, `deleted_at` (soft delete)
- `apps/api/src/aidoo_api/domains/images/schemas.py` — Pydantic, camelCase
  alias generator (다른 도메인 컨벤션 따름)
- `apps/api/src/aidoo_api/domains/images/router.py` — 아래 endpoint들
- `apps/api/src/aidoo_api/domains/images/service.py` — DB 접근 + LLM 브리프
  생성 호출 + Celery dispatch
- `apps/api/src/aidoo_api/domains/images/prompt.py` — 순수 함수 헬퍼:
  - `build_brief_messages(state, hydrated_context, prior_brief=None, edit_instruction=None)`
  - `ILLUSTRATOR_SYSTEM_PROMPT` 상수 (worker가 import해서 씀)
  - `build_agent_input(brief_text, style, layout, ref_image_bytes_with_roles)`
- `apps/api/migrations/versions/<rev>_image_generations.py`

**Endpoints**(prefix `/workspaces/{workspace_slug}/images`):

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/generations` | 위저드 시작 시 row 생성 (LLM 호출 없음) |
| `PATCH` | `/generations/{id}` | 단계별 자동 저장 (use_case / style / layout / details / context_refs / reference_image_keys) |
| `POST` | `/generations/{id}/reference-images` | multipart 업로드, MinIO 저장 후 metadata 반환 |
| `DELETE` | `/generations/{id}/reference-images/{storage_key}` | 첨부 제거 |
| `POST` | `/generations/{id}/brief` | 브리프 생성/리파인. `{ edit_instruction?: string }` |
| `POST` | `/generations/{id}/approve` | brief_status=approved, Celery dispatch, image_status=queued |
| `GET` | `/generations/{id}` | 폴링/재개용 |
| `GET` | `/generations` | 갤러리용 페이지네이션 (filter by image_status, use_case) |
| `DELETE` | `/generations/{id}` | soft delete + MinIO cleanup |
| `GET` | `/generations/{id}/download` | MinIO presigned URL |

**파일 (수정):**

- `apps/api/src/aidoo_api/api_registry.py` — 새 router 등록
- `apps/api/src/aidoo_api/core/settings.py` — 다음 필드 추가:

  ```python
  image_enabled: bool = Field(default=False, validation_alias=AliasChoices('DOOWON_IMAGE_ENABLED'))
  image_api_key: str = Field(default='', validation_alias=AliasChoices('DOOWON_IMAGE_API_KEY'))
  image_base_url: str = Field(default='https://api.openai.com/v1', validation_alias=AliasChoices('DOOWON_IMAGE_BASE_URL'))
  image_model: str = Field(default='gpt-image-2', validation_alias=AliasChoices('DOOWON_IMAGE_MODEL'))
  image_supervisor_model: str = Field(default='gpt-5', validation_alias=AliasChoices('DOOWON_IMAGE_SUPERVISOR_MODEL'))
  image_agent_max_iterations: int = Field(default=2, validation_alias=AliasChoices('DOOWON_IMAGE_AGENT_MAX_ITER'))
  image_max_reference_uploads: int = Field(default=4, validation_alias=AliasChoices('DOOWON_IMAGE_MAX_REFS'))
  ```

  `image_api_key`가 비어있으면 `llm_external_api_key`로 폴백하여 단일 키
  세팅도 동작하도록.

- `apps/api/pyproject.toml` — `openai-agents` 의존성 추가
  (실제 패키지명/버전은 구현 시 확정)

### 2단계 — Worker 태스크 (Codex/Agents SDK)

**파일 (신규):** `apps/worker/src/aidoo_worker/tasks/images.py`

```python
@celery_app.task(name='images.generate_image')
def generate_image(generation_id: str) -> None:
    # 1) row + reference image bytes 로드 (MinIO get)
    # 2) Agents SDK 구성:
    from agents import Agent, Runner
    from agents.tools import image_generation
    agent = Agent(
        name='infographic-illustrator',
        model=settings.image_supervisor_model,
        instructions=ILLUSTRATOR_SYSTEM_PROMPT,
        tools=[image_generation(
            model=settings.image_model,
            size=layout.aspect,
            quality=style.quality,
            background=style.background,
        )],
    )
    result = await Runner.run(
        agent,
        input=build_agent_input(brief_text, style, layout, ref_images),
        max_turns=settings.image_agent_max_iterations + 1,
    )
    # 3) 결과에서 마지막 image part 추출
    # 4) MinIO 업로드: images/results/{workspace_id}/{generation_id}.png
    # 5) row 업데이트: succeeded + storage_key + image_model + agent_trace_id
    # 예외 시: failed + failure_reason
```

**파일 (수정):**

- `apps/worker/src/aidoo_worker/celery_app.py` — `tasks/images` 모듈 include
- `apps/worker/pyproject.toml` — `openai-agents` 의존성 추가

### 3단계 — 프론트엔드 (AI 앱 안)

**디렉터리 트리:**

```
apps/web/src/app-modules/ai/
├── api/
│   └── image-wizard-api.ts             # NEW
├── views/
│   └── ImageWizard/                    # NEW
│       ├── ImageWizardToolView.tsx     # entry; ?view에 따라 wizard | gallery 분기
│       ├── ImageWizardView.tsx         # vertical card stack, generationId 보유
│       ├── ImageWizardGalleryView.tsx  # 과거 generation 목록
│       ├── steps/
│       │   ├── UseCaseStep.tsx
│       │   ├── StyleStep.tsx
│       │   ├── LayoutStep.tsx
│       │   ├── ReferenceImagesStep.tsx
│       │   ├── ContextStep.tsx
│       │   └── ReviewBriefStep.tsx
│       ├── DocPickerModal.tsx          # MeetingPickerModal의 near-copy
│       ├── ContextChipList.tsx
│       ├── ReferenceImageThumb.tsx
│       ├── PresetCard.tsx
│       ├── BriefVersionList.tsx
│       └── GenerationDetailView.tsx
├── manifest.ts                         # EDIT
└── routes.tsx                          # EDIT
```

**API 클라이언트** (`api/image-wizard-api.ts`): `createGeneration`,
`patchGeneration`, `uploadReferenceImage`, `deleteReferenceImage`,
`generateBrief({editInstruction?})`, `approveGeneration`, `getGeneration`,
`listGenerations`, `presignedDownload`.

**Wizard 호스트** (`ImageWizardView.tsx`): URL `?step=N&gen=<id>` 동기화,
각 단계 컴포넌트는 currentRow + onChange 받음. 단계 onChange는
`patchGeneration`을 디바운스(500ms)로 호출. `?gen` 없는 상태에서 첫
변경이 일어나면 `createGeneration` 후 URL replace.

**Review 단계** (`ReviewBriefStep.tsx`): 최신 `brief_versions[-1]` 렌더 +
채팅 입력 + Regenerate / Approve 버튼. Approve 후
`GenerationDetailView`로 라우팅 (URL `?view=detail&gen=<id>`)되어 폴링
시작.

**Wiring (외부 서지컬 편집):**

- `apps/web/src/app-modules/ai/manifest.ts` — `navItems` 배열에 추가:

  ```ts
  { id: 'image-wizard', title: 'image-wizard', icon: ImageIcon,
    category: 'Assistants', appId: 'ai', description: 'image-wizard' }
  ```

- `apps/web/src/app-modules/ai/routes.tsx` — `ragSearchToolElement`처럼:

  ```ts
  const ImageWizardToolView = lazy(() =>
    import('./views/ImageWizard/ImageWizardToolView')
      .then(m => ({ default: m.ImageWizardToolView })),
  );
  export const imageWizardToolElement = lazyRoute(<ImageWizardToolView />);
  ```

- `apps/web/src/app/shell/tool-view-wrapper.tsx` — 기존
  `if (toolId === 'search') { ... return ragSearchToolElement; }` 옆에:

  ```ts
  if (toolId === 'image-wizard') {
    if (!isWorkspaceAppEnabled(enabledBootstrapApps, 'ai')) {
      return <AccessDeniedView description={t('shell:gates.appDisabled')} />;
    }
    return imageWizardToolElement;
  }
  ```

- `apps/web/src/platform/i18n/resources.ts` — 다음 키 추가 (`ko-KR`, `en` 둘 다):
  - `apps.ai.image-wizard` — nav 아이템 짧은 라벨
  - `apps.ai.imageWizard.steps.{useCase|style|layout|referenceImages|context|review}.title|description`
  - `apps.ai.imageWizard.usecase.{...}` (사용처 라벨들)
  - `apps.ai.imageWizard.style.{...}`, `apps.ai.imageWizard.layout.{...}`
  - `apps.ai.imageWizard.review.editPlaceholder|regenerate|approve`
  - `apps.ai.imageWizard.gallery.{empty|title|cloneAction}`
  - `apps.ai.imageWizard.errors.{briefFailed|approveFailed|disabled}`

**재사용 부품:**

- `Dialog`, `Button` (`@aidoo/ui`)
- `MeetingPickerModal`, `TaskPickerModal` (`@/src/app-modules/recording/views/`) — workspace-scoped onPick 그대로 사용
- `listMeetings` (`@/src/app-modules/meeting/public-api`),
  `listPmsTaskLists` + `listTaskListIssues` (PMS), `listDocs` (docs) — 새
  `DocPickerModal`이 `listDocs` 호출
- `RecordingStageRail.tsx` 패턴 — 브리프→승인→생성 진행 표시에 영감

## Verification

### 단위 테스트

1. **API** (`tests/domains/images/test_service.py`):
   - 픽스처 회의록 + doc + task로 `build_brief_messages` 호출, 결과 메시지에
     use_case와 컨텍스트 필드가 포함되는지.
   - `prior_brief` + `edit_instruction` 동시에 줬을 때 둘 다 프롬프트에
     포함되는지.
   - approve 엔드포인트가 Celery task `.delay`를 정확히 한 번 호출하는지
     (mock).
   - `image_enabled=False`일 때 모든 엔드포인트가 503.
   - reference-image 업로드 → MinIO mock 기록 + row의 `reference_image_keys`
     append.

2. **Worker** (`tests/tasks/test_images.py`):
   - Agents SDK `Runner.run`을 mock해 가짜 image part 반환 →
     MinIO put 호출 + row가 `succeeded` + `agent_trace_id` 기록.
   - `Runner.run`이 raise → row가 `failed` + `failure_reason` 채워짐.

3. **Frontend** (`apps/web/src/app-modules/ai/views/ImageWizard/*.spec.tsx`):
   - 위저드 호스트 RTL 테스트: step 진행 시 PATCH 호출, brief가 `ready`
     아닐 때 Approve 비활성, 갤러리 빈 상태 렌더링.

### 수동 e2e (`./dev.sh`)

- env 세팅: `DOOWON_IMAGE_ENABLED=true`, `DOOWON_IMAGE_API_KEY=...`,
  `DOOWON_IMAGE_MODEL=gpt-image-2`, `DOOWON_IMAGE_SUPERVISOR_MODEL=gpt-5`.
- AI 앱 사이드바 (혹은 `/tool/image-wizard?workspace=<slug>`)에서 새 도구 진입.
- step 따라가기:
  사용처 = status report, 스타일 = clean-corporate vivid,
  레이아웃 = top-title-grid 1792x1024, 참고 이미지 1장(style ref) 업로드,
  회의록 1개 + 태스크 리스트 1개 첨부, audience = "exec readout".
- review에서 생성된 브리프가 회의 안건과 액션 아이템을 인용하는지 확인.
- "팔레트를 더 따뜻하게 하고 세 번째 KPI를 매출 성장률로 바꿔줘" 입력 →
  새 버전이 반영되어 등장하는지, v1로 revert 가능한지, 다시 수정되는지.
- Approve → ~30초 안에 이미지 등장, 다운로드 동작 확인.
- 위저드 중간에 새로고침 → 행에서 상태 복원 확인.
- 갤러리 진입 → 결과 클릭 → "복제해서 수정" → 새 draft가 이전 입력
  (참고 이미지 포함) 상속하는지 확인.
- 언어를 ko-KR로 바꿔 step 제목과 preset 라벨이 모두 정상 표시되는지.
- 실패 경로: Agents SDK가 raise하도록 강제 → row가 `failed`로,
  UI에 `failure_reason` 노출, 재시도 버튼이 다시 enqueue.

## 결정 로그

- **표면 (Surface)**: AI 앱 안의 새 tool nav 아이템(`image-wizard`,
  `Assistants` 카테고리). 새 top-level 앱이 아님. (사용자가 명시 요청)
- **이미지 모델 기본값**: `gpt-image-2` (env `DOOWON_IMAGE_MODEL`로 override).
  슈퍼바이저 모델 기본값 `gpt-5` (env `DOOWON_IMAGE_SUPERVISOR_MODEL`).
- **생성 표면**: OpenAI Codex/Agents SDK (`openai-agents`)가 worker에서
  실제 이미지 호출을 담당. 브리프 합성은 기존 chat LLM 풀 그대로 사용.
- **v1 컨텍스트 종류**: 회의록, PMS 태스크, Docs. 워크스페이스 파일은 v2.
- **결과 저장소**: AI 앱 image-wizard 갤러리에만. NativeDoc 자동 저장 v1엔
  없음.
- **브리프 편집 UX**: 채팅 스타일 자연어 지시만. 본문 직접 편집 비허용.
  모든 수정 의도는 `brief_versions`에 함께 기록.
- **차후 결정**: (a) 결과를 NativeDoc으로 저장하는 명시 액션을 v2에서
  추가할지, (b) 워크스페이스 파일 picker를 step 5에 합칠지, (c) 동일
  브리프로 N개 variant를 한 번에 생성하는 옵션이 필요할지.

## 롤백 계획

- 기능 플래그 `DOOWON_IMAGE_ENABLED=false`로 즉시 비활성화 가능. 라우터가
  503 반환, 프론트는 nav 아이템에서 도구를 안 보이게 처리하거나 `comingSoon`
  플래그로 잠금.
- 새 nav 아이템은 기존 사용자에게 영향 없음 (다른 tool 동작에 변경 없음).
- 데이터 영향: `image_generations` 테이블만 추가. 롤백 시 alembic
  `downgrade -1`로 테이블 제거 가능 (사용자 데이터 보전이 필요하면 archive
  덤프 후 drop).
- 의존성: `openai-agents` 패키지를 추가만 함. 다른 코드 경로에서 import하지
  않으면 제거 안전.
- MinIO 객체: `images/refs/` 와 `images/results/` 프리픽스로 격리되어 있어
  벌크 cleanup 단순.
