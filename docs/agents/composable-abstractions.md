# 조합형 추상화 개발 가이드

## 목적

비슷해 보이는 화면이나 기능을 구현할 때 너무 이른 공통 모델화로 거대한 설정 렌더러를 만들지
않도록 한다. AI 에이전트와 사람이 필요한 파일 몇 개만 읽어도 맥락을 이해할 수 있게 공통 모듈,
작은 엘리먼트와 라이브러리를 조합하는 방향을 기본값으로 둔다.

이 문서는 `llm-friendly-development.md`의 얇은 추상화 원칙을 화면·기능 공통화 판단에 적용한
보조 지침이다. 코드 구조 판단이 충돌하면 `llm-friendly-development.md`를 우선한다. 특정 앱
전용 문서가 아니며 여러 화면, CRUD, import/export, 상세 패널, revision, workflow처럼 비슷하지만
완전히 같지는 않은 기능을 설계할 때 적용한다.

## 기본 원칙

- 공통화할 것은 UI 모양 자체가 아니라 변경 이유, 정책, 상태 전이, 검증, 권한과 데이터 흐름이다.
- 화면별 의미가 다르면 화면별 조립을 유지하고 반복되는 작은 단위를 재사용한다.
- 세 번째 이상 반복되고 예외보다 규칙이 많아졌을 때 더 깊은 모델로 승격한다.
- 공통 모델은 이 설정이 어떤 화면에 영향을 주는지 바로 추적할 수 있어야 한다.
- 이름, public entrypoint와 소유 경계를 명시해 AI가 좁은 파일 집합으로 변경 범위를 이해하게 한다.

## 3단계 전략

### 1단계: 공통 엘리먼트

거의 항상 먼저 확인하고 재사용할 수 있는 영역이다.

```txt
Button
IconButton
DataTable
FormField
Dialog
ConfirmDialog
SearchField
PageHeader
EmptyState
```

이 단계의 목표는 화면을 하나로 합치는 것이 아니라 반복되는 UI 단위를 안정화하는 것이다.
구체적인 기존 구현은 [UI 컴포넌트 지침](ui-components.md)에서 찾는다.

### 2단계: 공통 use-case 모듈

여러 화면이 같은 행위를 반복할 때 hook, model, helper 또는 service 단위로 공통화한다.

```txt
usePagination
useSearchParams
useTableSelection
useInlineEdit
useSubmitWithToast
useImportMapping
useRevisionWorkflow
```

상태 전이와 사용자 흐름이 실제로 같을 때만 진행한다. 화면별 비즈니스 규칙이 다르면 hook의
option을 늘리기보다 화면별 조립을 유지한다. React component가 아닌 state projection과
transition은 가능한 한 독립 model로 분리해 focused test를 둔다.

### 3단계: 검증된 도메인 모델

반복되는 기능의 변경 이유가 같고 데이터 차이가 설정값 수준으로 안정되었을 때만 공통 모델로
승격한다.

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

이 단계는 생산성을 높일 수 있지만 잘못 만들면 저장소 내부 프레임워크가 된다. config가 분기를
숨기기 시작하면 한 단계 낮은 조합 방식으로 되돌린다.

## 판단 기준

공통 모델화가 맞는 신호:

- lifecycle, loading/error, submit, validation, permission 흐름이 같다.
- 화면별 차이가 field, label, column, button 노출 정도다.
- 새 화면이 schema/config 추가만으로 대부분 완성된다.
- 한 정책 변경이 여러 화면에 동일하게 적용되어야 한다.
- 공통 contract test를 만들 수 있다.

화면별 조립이 맞는 신호:

- 비슷한 것은 레이아웃뿐이고 도메인 의미가 다르다.
- 한 화면만의 승인, 복원, import 또는 검증 예외가 많다.
- 공통 컴포넌트에 특정 화면을 위한 boolean option이 계속 추가된다.
- `type === 'x'` 같은 분기가 공통 렌더러 안에 늘어난다.
- 제품·디자인 실험이 화면별로 다르게 진행된다.
- 공통 렌더러 하나를 수정했을 때 영향 범위를 넓게 추론해야 한다.

## 권장 파일 구조

Frontend 앱·feature는 사용자가 보는 진입점과 내부 구현 방식을 분리한다.

```txt
apps/web/src/app-modules/<moduleId>/
  manifest.ts
  routes.ts
  public-api.ts        # 다른 앱이 실제로 소비할 때만
  index.ts
  api/
    <module>-api.ts
  views/
    <Module>View.tsx
    <module>-view-model.ts
```

상위 AppBar 앱 아래 붙는 독립 도구라면 full app module로 끌어올리기보다 feature module로 둔다.
feature module도 자기 manifest, API, route와 view를 소유하고 상위 앱은 registration과 route/nav
조립만 한다. 현재 `web-search`가 `ai` 아래 노출되면서도
`apps/web/src/app-modules/web-search/`에서 manifest, API와 view를 소유하는 방식이 이 경계의
예다.

여러 화면 변형을 가진 앱은 다음처럼 app-local 경계를 추가할 수 있다. 모든 앱에 이 구조를
강제하지 않는다.

```txt
app-modules/<appId>/
  manifest.ts
  routes.ts
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
    <FeatureDataTable>.tsx
    <FeatureImportDialog>.tsx
```

Backend는 frontend module과 1:1 파일명을 맞추기보다 domain 책임으로 나눈다.

```txt
apps/api/src/open_work_hub_api/domains/<domain>/
  router.py
  schemas.py
  application.py       # 필요한 경우
  service.py
  <domain-specific-helper>.py
```

Router는 HTTP/SSE envelope, dependency와 localized error mapping을 맡고 service/helper가 상태
전이, 검색, LLM orchestration과 projection을 맡는다. Router, AI tool과 worker가 같은 domain
service를 우회해 각자 권한·DB 로직을 다시 구현하지 않는다.

기능 내부 API를 여러 방식으로 나눌 때는 다음 원칙을 따른다.

- `<feature>-api.ts`: 화면이 import하는 단일 app-local 진입점이다.
- `<feature>-common-api.ts`: 여러 구현이 공유하는 request/response/type 계약이다.
- `<feature>-definitions.ts`: dataset key, route, nav id, storage key 같은 식별 문자열의 정본이다.
- 구현 방식이 다르면 파일명은 카테고리명이 아니라 `fixed-schema`, `configured`, `workflow` 같은
  방식 이름을 쓴다.
- 화면별 카테고리명이 필요하면 모든 카테고리를 같은 계층에 둔다. 하나만 top-level에 두고
  나머지를 `module`, `misc`, `etc`로 묶지 않는다.
- AI 앱 아래의 Web Search 같은 독립 도구는 자기 feature module을 유지한다. 상위 `ai` 앱은
  child view/API를 소유하지 않는다.

다른 앱이 특정 앱 기능을 소비할 때는 app-local deep import 대신 public API를 만든다. 현재
`apps/web/src/app-modules/docs/public-api.ts`가 picker/viewer를 지연 로딩하고 Meeting, PMS,
Recording과 Home이 그 진입점을 소비한다. 반대로 PMS의 tree/reorder처럼 한 앱의 업무 규칙에
묶인 구현은 PMS 안에 유지하며 일반 tree framework로 성급히 승격하지 않는다.

## 이름 규칙

이름은 AI가 맥락을 추론하는 가장 싼 단서다.

- 특정 카테고리만 대표처럼 보이는 이름을 피한다.
- `module`, `misc`, `etc`, `common2`처럼 소유권이나 방식이 드러나지 않는 이름을 피한다.
- 구현 방식 이름과 도메인 이름을 섞지 않는다.
- 공통 진입점은 도메인 이름을 쓰고 내부 구현은 방식 이름을 쓴다.
- route, nav, dataset와 storage 식별 문자열은 소유 파일 한 곳에서만 정의한다.

나쁜 예:

```txt
special-api.ts
misc-module-api.ts
CommonScreenWithOptions.tsx
```

좋은 예:

```txt
document-api.ts
document-fixed-schema-api.ts
document-configured-api.ts
document-datasets.ts
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
- 파일 하나를 고쳤을 때 관련 없는 여러 화면이 함께 깨질 수 있다.

## AI/RAG 파이프라인 추상화

AI 검색, RAG, 리포트 생성과 분석 pipeline은 특정 질문을 맞추기 위한 코드를 넣지 않는다.
질문별 조건문은 당장 품질이 좋아 보여도 다음 질문에서 시스템을 깨뜨린다.

금지:

- 사용자 문장·키워드·언어를 코드에서 직접 판정하는 `if question contains ...` 분기.
- 특정 질문을 위해 만든 synonym dict, suffix mapping, hardcoded expansion.
- 특정 고객, 필드, source, dataset 또는 사례 전용 boolean option.
- 특정 결과 품질을 만들기 위해 evidence 순위를 임의 보정하는 후처리.

허용되는 형태:

- LLM planner가 `intent`, `keywords`, `field_hints`, `operators` 같은 일반 계획을 만든다.
- 서버는 plan schema와 source/dataset schema로 검증 가능한 generic operator만 실행한다.
- `semantic_search`, `full_text_search`, `related_by_field`, `group_by_field`,
  `aggregate_by_field`처럼 필드명과 값이 data/plan에서 오는 연산자.
- operator가 필요하면 특정 질문 이름이 아니라 재사용 가능한 데이터 흐름 이름으로 만든다.
- 특정 질문에서 발견한 품질 문제는 prompt contract, planner schema, generic scoring과
  evaluation fixture로 환원한다.

## AI 에이전트 작업 규칙

비슷한 화면을 추가하거나 리팩터링할 때는 다음 순서로 판단한다.

1. 현재 코드에서 같은 변경 이유가 반복되는지 확인한다.
2. 먼저 기존 공통 엘리먼트와 app-local 컴포넌트를 재사용한다.
3. 반복되는 상태 전이가 확인되면 model/hook/service로 공통화한다.
4. schema/config로 표현 가능한 안정된 패턴만 공통 모델로 승격한다.
5. 새 추상화를 만들 때 이름, 파일 위치, 변경 영향 범위와 테스트 기준을 함께 남긴다.
6. 공통화로 특정 화면만의 조건문이 늘어나면 중단하고 화면별 조립을 유지한다.
7. AI/RAG 품질 튜닝 중 특정 질문 전용 코드가 생기면 generic planner/operator 설계로 되돌린다.

## 완료 기준

- 화면 import 경로가 public/app-local 진입점과 구현 파일을 명확히 구분한다.
- route, nav id, storage key, dataset key 같은 식별 문자열이 중복 정의되지 않는다.
- 공통 컴포넌트에 특정 화면 전용 분기가 없다.
- AI/RAG pipeline에 특정 질문, 고객, 필드, source 또는 사례 전용 분기가 없다.
- 새 화면이나 dataset 추가 절차가 문서, type 또는 registration으로 드러난다.
- typecheck와 관련 focused test가 통과한다.
- 추상화가 줄인 중복보다 늘린 설정 복잡도가 크지 않다.
