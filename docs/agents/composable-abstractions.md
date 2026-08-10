# 조합형 추상화 개발 가이드

## 목적

비슷해 보이는 화면이나 기능을 구현할 때, 너무 이른 공통 모델화로 거대한 설정 렌더러를
만들지 않도록 한다. AI 에이전트와 사람이 모두 맥락을 쉽게 이해할 수 있게, 공통 모듈,
공통 엘리먼트, 공통 라이브러리를 조합하는 방향을 기본값으로 둔다.
이 문서는 `llm-friendly-development.md`의 얇은 추상화 원칙을 화면/기능 공통화 판단에 적용한 보조 지침이다. 코드 구조 판단이 충돌하면 `llm-friendly-development.md`를 우선한다.

이 문서는 특정 앱 전용 문서가 아니다. 여러 화면, 데이터셋, CRUD, import/export, 상세
패널, revision, workflow 처럼 비슷하지만 완전히 같지는 않은 기능을 설계할 때 적용한다.

## 기본 원칙

기본값은 `llm-friendly-development.md`의 얇은 추상화 원칙을 따르는 얕은 공통화다.

- 공통화할 것은 UI 모양이 아니라 변경 이유, 정책, 상태 전이, 검증, 권한, 데이터 흐름이다.
- 화면별 의미가 다르면 화면별 조립을 유지하고, 반복되는 작은 단위를 재사용한다.
- 세 번째 이상 반복되고 예외보다 규칙이 많아졌을 때 더 깊은 모델로 승격한다.
- 공통 모델은 읽는 사람이 "이 설정이 어떤 화면에 영향을 주는지" 바로 추적할 수 있어야 한다.
- AI가 필요한 파일 몇 개만 읽어도 변경 범위를 이해할 수 있게 이름과 경계를 명시한다.

## 3단계 전략

### 1단계: 공통 엘리먼트

거의 항상 먼저 확인하고 재사용할 수 있는 영역이다.

```txt
Button
IconButton
DataGrid
FormField
Modal
ConfirmDialog
SearchToolbar
PageHeader
EmptyState
```

이 단계의 목표는 화면을 하나로 합치는 것이 아니라 반복되는 UI 단위를 안정화하는 것이다.

### 2단계: 공통 use-case 모듈

여러 화면이 같은 행위를 반복할 때 hook, helper, service 단위로 공통화한다.

```txt
usePagination
useSearchParams
useTableSelection
useInlineEdit
useSubmitWithToast
useImportMapping
useRevisionWorkflow
```

이 단계는 상태 전이와 사용자 흐름이 실제로 같을 때만 진행한다. 화면별 비즈니스 규칙이
다르면 hook의 option을 늘리기보다 화면별 조립을 유지한다.

### 3단계: 검증된 도메인 모델

반복되는 기능의 변경 이유가 같고, 데이터 차이가 설정값 수준으로 안정되었을 때만 공통
모델로 승격한다.

```ts
type DatasetPageDefinition = {
  key: string;
  route: string;
  title: string;
  fields: FieldDefinition[];
  actions: ActionDefinition[];
  permissions: PermissionDefinition[];
};
```

이 단계는 생산성을 크게 높일 수 있지만, 잘못 만들면 사내 프레임워크가 된다. config가
분기를 숨기기 시작하면 한 단계 낮은 조합 방식으로 되돌린다.

## 판단 기준

공통 모델화가 맞는 신호:

- lifecycle, loading/error, submit, validation, permission 흐름이 같다.
- 화면별 차이가 field, label, column, button 노출 정도다.
- 새 화면이 schema/config 추가만으로 대부분 완성된다.
- 한 정책 변경이 여러 화면에 동일하게 적용되어야 한다.
- 공통 contract test를 만들 수 있다.

화면별 조립이 맞는 신호:

- 비슷한 것은 레이아웃뿐이고 도메인 의미가 다르다.
- 한 화면만의 승인, 결재, 복원, import, 검증 예외가 많다.
- 공통 컴포넌트에 특정 화면을 위한 boolean option이 계속 추가된다.
- `type === 'x'` 같은 분기가 공통 렌더러 안에 늘어난다.
- PM/디자인 실험이 화면별로 다르게 진행된다.
- AI가 공통 렌더러를 수정하면 영향 범위를 넓게 추론해야 한다.

## 권장 파일 구조

기능이 여러 데이터셋이나 화면 변형을 가진다면, 화면에서 보는 진입점과 내부 구현 방식을
분리한다.

```txt
apps/web/src/app-modules/<moduleId>/
  manifest.ts
  routes.ts
  public-api.ts
  index.ts
  api/
    <module>-api.ts
  views/
    <Module>View.tsx
```

상위 AppBar 앱 아래 붙는 독립 도구라면 full app module 로 끌어올리기보다 feature module 로
둔다. feature module 도 자기 manifest/API/routes/views 를 갖고, 상위 앱은 route rewrite 나
launcher gate 같은 조립만 한다.

여러 데이터셋이나 화면 변형을 가진 앱 내부에서는 다음처럼 app-local core 를 추가로 나눌 수
있다.

```txt
app-modules/<appId>/
  manifest.ts
  routes.ts
  core/
    public-api.ts
    <feature>-definitions.ts
    api/
      <feature>-api.ts
      <feature>-common-api.ts
      <feature>-fixed-schema-api.ts
      <feature>-configured-api.ts
    views/
      <FeaturePage>.tsx
      <FeatureConfiguredPage>.tsx
      <FeatureDataGrid>.tsx
      <FeatureImportDialog>.tsx
```

Backend 는 frontend module 과 1:1 파일명을 맞추기보다 domain 책임으로 나눈다.

```txt
apps/api/src/open_alm_api/domains/<domain>/
  router.py
  schemas.py
  service.py
  <domain-specific-helper>.py
```

Router 는 HTTP/SSE envelope 와 dependency/error mapping 을 맡고, service/helper 가 상태 전이,
검색, LLM/provider orchestration, projection 을 맡는다.

기존 feature 내부 구조 예시는 다음 원칙을 따른다.

```txt
feature/
  feature-definitions.ts
  api/
    feature-api.ts
    feature-common-api.ts
    feature-fixed-schema-api.ts
    feature-configured-api.ts
  views/
    FeaturePage.tsx
    FeatureConfiguredPage.tsx
    FeatureDataGrid.tsx
    FeatureImportDialog.tsx
```

- `feature-api.ts`: 화면이 import 하는 단일 진입점이다.
- `feature-common-api.ts`: 여러 구현이 공유하는 request/response/type 계약이다.
- `feature-definitions.ts`: dataset key, route, nav id, storage key 같은 식별 문자열의 정본이다.
- 구현 방식이 다르면 파일명은 카테고리명이 아니라 방식 이름을 쓴다. 예: `fixed-schema`, `configured`, `workflow`.
- 화면별 카테고리명이 필요하면 모든 카테고리를 같은 계층에 둔다. 한 카테고리만 top-level이고 나머지는 `module`이나 `etc`로 묶지 않는다.
- 현재 과거차 문제점 구조는 이 패턴의 기준 사례다. `legacy-issues/core/public-api.ts` 가 외부 노출면이고, `legacy-issue-datasets.ts` 가 dataset/route/nav/storage key 정본이며, backend `domains/legacy_issues` 는 router, revisioning, dataset_records, AI planner/search helper 로 책임을 나눈다.
- 과거차 문제점은 backend dataset 을 전체 원장(`common-master`) 하나로 유지하고, 에어컨/의장/쿨링모듈/전장 3종 메뉴는 같은 원장의 부서 필터 view 로 노출한다. RAG/SQL 검색에 필요한 공통 필드는 SQL projection 컬럼과 `search_text`로 승격하고, 모듈별 전용 컬럼 정의는 `legacy_issue_module_fields`에 두며 값은 `legacy_issue_records.field_values` JSONB에 보존한다. 모듈별 전용 컬럼 관리는 별도 설정 화면으로 노출하고, `legacy_issue_module_access_rules`는 향후 사용자/조직/팀 단위 권한 분리를 위한 확장 지점으로 유지한다.
- Q&A와 웹 검색처럼 AI 앱 아래 노출되는 도구도 자기 feature module 을 가진다. `app-modules/ai` 는 그 route 를 자기 경로 아래로 rewrite 해서 조립할 뿐, child view/API 를 소유하지 않는다.

## 이름 규칙

이름은 AI가 맥락을 추론하는 가장 싼 단서다.

- 특정 카테고리만 대표처럼 보이는 이름을 피한다.
- "나머지" 느낌의 `module`, `misc`, `etc`, `common2` 이름을 피한다.
- 구현 방식 이름과 도메인 이름을 섞지 않는다.
- 공통 진입점은 도메인 이름을 쓰고, 내부 구현은 방식 이름을 쓴다.
- 데이터셋 식별 문자열은 한 파일에서만 정의한다.

나쁜 예:

```txt
aircon-api.ts
legacy-module-api.ts
CommonScreenWithOptions.tsx
```

좋은 예:

```txt
legacy-issue-api.ts
legacy-issue-fixed-schema-api.ts
legacy-issue-configured-api.ts
legacy-issue-datasets.ts
```

## 피해야 할 패턴

다음 형태가 보이면 추상화가 너무 빨라졌을 가능성이 높다.

```tsx
<CommonScreen
  type="user"
  mode="edit"
  showAdvanced={true}
  enableBulkAction={false}
  customValidation={validate}
  overrideHeader={renderHeader}
  renderExtraSection={renderExtra}
  disableDefaultFooter={true}
  useLegacyPermission={condition}
/>
```

문제 신호:

- option이 화면 수보다 빠르게 늘어난다.
- 공통 컴포넌트 내부에 특정 화면 이름이 등장한다.
- 새 화면을 만들기보다 기존 config 조합을 해석하는 시간이 더 길다.
- 한 화면 수정의 영향 범위를 테스트 없이는 알기 어렵다.
- AI가 파일 하나를 고쳤을 때 여러 화면이 깨질 수 있다.

## AI/RAG 파이프라인 추상화

AI 검색, RAG, 리포트 생성, 분석 pipeline은 특정 질문을 맞추기 위한 코드를 넣지 않는다.
질문별로 맞춘 조건문은 당장 품질이 좋아 보여도 다음 질문에서 시스템을 깨뜨린다.

금지:

- 사용자 문장/키워드/언어를 코드에서 직접 판정하는 `if question contains ...` 분기.
- 특정 질문을 위해 만든 synonym dict, suffix mapping, hardcoded expansion.
- 특정 차종, 특정 필드, 특정 데이터셋, 특정 사례 전용 boolean option.
- 특정 결과 품질을 만들기 위해 evidence 순위를 코드에서 임의 보정하는 후처리.

허용되는 형태:

- LLM planner가 `intent`, `keywords`, `field_hints`, `operators` 같은 일반 계획을 만든다.
- 서버는 plan schema와 dataset schema로 검증 가능한 generic operator만 실행한다.
- 예: `semantic_search`, `full_text_search`, `related_by_field`, `group_by_field`,
  `aggregate_by_field` 처럼 필드명과 값이 데이터/plan에서 오는 연산자.
- operator가 필요하면 특정 질문 이름이 아니라 재사용 가능한 데이터 흐름 이름으로 만든다.
- 특정 질문에서 발견한 품질 문제는 prompt contract, planner schema, generic scoring,
  evaluation fixture로 환원한다.

## AI 에이전트 작업 규칙

비슷한 화면을 추가하거나 리팩터링할 때는 다음 순서로 판단한다.

1. 현재 코드에서 같은 변경 이유가 반복되는지 확인한다.
2. 먼저 기존 공통 엘리먼트와 app-local 컴포넌트를 재사용한다.
3. 반복되는 상태 전이가 확인되면 hook/service로 공통화한다.
4. schema/config로 표현 가능한 안정된 패턴만 공통 모델로 승격한다.
5. 새 추상화를 만들 때는 이름, 파일 위치, 변경 영향 범위, 테스트 기준을 함께 남긴다.
6. 공통화로 인해 특정 화면만의 조건문이 늘어나면 중단하고 화면별 조립을 유지한다.
7. AI/RAG 품질 튜닝 중 특정 질문 전용 코드가 생기면 즉시 중단하고 generic planner/operator
   설계로 되돌린다.

## 완료 기준

조합형 추상화 작업은 다음을 만족해야 완료로 본다.

- 화면 import 경로가 공통 진입점과 구현 파일을 명확히 구분한다.
- route, nav id, storage key, dataset key 같은 식별 문자열이 중복 정의되지 않는다.
- 공통 컴포넌트에 특정 화면 전용 분기가 없다.
- AI/RAG pipeline에 특정 질문, 키워드, 차종, 필드, 사례 전용 분기가 없다.
- 새 화면이나 데이터셋 추가 절차가 문서 또는 타입으로 드러난다.
- typecheck와 관련 focused test가 통과한다.
- 추상화가 줄인 중복보다 늘린 설정 복잡도가 크지 않다.
