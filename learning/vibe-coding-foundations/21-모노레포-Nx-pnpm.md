# 21. 모노레포 — Nx와 pnpm

> **한 줄 요약.** 모노레포는 "여러 앱과 라이브러리를 한 저장소에 두는 방식"이다. 이 프로젝트는 **pnpm 워크스페이스**로 패키지를 묶고 **Nx**로 빌드·테스트·캐싱을 최적화한다.

---

## 1. 모노레포의 목적 (복습 + 심화)

6장에서 모노레포 vs 폴리레포의 개념 차이를 봤습니다. 여기서는 우리 프로젝트에서 모노레포가 **실제로 어떤 편의를 주는지** 구체적으로 봅니다.

### 1.1 공통 작업의 단순화

- **타입 공유**: 프런트(TS)와 백엔드 사이의 API 타입을 `packages/contracts` 같은 공용 패키지로 공유 가능.
- **UI 라이브러리 공유**: `packages/ui` 안의 공통 컴포넌트를 `apps/web`과 `apps/ops`가 모두 import 가능.
- **한 PR로 풀스택 변경**: "로그인 API 바꾸면서 프런트 화면도 같이 바꾸는" 일이 한 번의 커밋·리뷰·배포로 끝난다.

### 1.2 일관된 도구

하나의 ESLint 설정, 하나의 TypeScript 설정, 하나의 Prettier 설정으로 팀 전체가 같은 규칙을 따릅니다. 개발자마다 스타일이 엇갈리는 일이 줄어듭니다.

### 1.3 규모의 함정

모노레포는 **잘못 쓰면 저장소가 무거워지고 빌드가 느려질 수 있습니다**. 이 문제를 해결하기 위해 **Nx 같은 빌드 오케스트레이터** 가 필요합니다.

---

## 2. pnpm — 왜 npm/yarn이 아니라 pnpm인가

**pnpm** 은 Node.js 생태계의 **패키지 매니저** 중 하나입니다. 세 가지 대표가 있습니다.

| 구분 | npm | yarn | pnpm |
|---|---|---|---|
| 출시 | 2010 | 2016 (FB) | 2017 |
| 디스크 사용 | 매 프로젝트 복사 | 매 프로젝트 복사 | **전역 저장소 + 하드링크** |
| 설치 속도 | 보통 | 빠름 | 가장 빠름 |
| 모노레포 지원 | 약함 | 워크스페이스 | 워크스페이스 (깔끔) |
| 엄격한 호이스팅 | 약함 | 중간 | **엄격** |

pnpm의 결정적 차이는 **전역 저장소(store)를 두고, 각 프로젝트의 `node_modules`에는 그 저장소로의 "링크"만 남긴다** 는 점입니다. 이로 인해:

- **디스크 절약**: 같은 라이브러리가 10번 복사되지 않는다.
- **속도**: 실제 복사가 아니라 링크라 거의 순간이다.
- **엄격성**: `package.json`에 선언하지 않은 의존성은 못 쓴다. 우연한 의존이 줄어든다.

### 2.1 pnpm-workspace.yaml

우리 프로젝트 루트의 이 파일이 "워크스페이스 구성"을 정합니다.

```yaml
packages:
  - 'apps/*'
  - 'packages/*'
```

이 설정으로 `apps/web`, `apps/api`(※ 파이썬은 제외), `packages/ui` 등이 모두 같은 워크스페이스의 "내부 패키지"가 됩니다. 서로를 `@aidoo/ui` 같은 이름으로 import 할 수 있습니다.

### 2.2 package.json의 `packageManager`

루트 `package.json`에 `"packageManager": "pnpm@10.33.0"` 이 명시돼 있습니다. 이 줄 덕분에 팀원들의 pnpm 버전이 **자동으로 통일** 됩니다(Corepack 기능).

---

## 3. Nx — 모노레포 오케스트레이터

**Nx** 는 Nrwl이 만든 모노레포 도구입니다. Angular 진영에서 출발해 지금은 React/Node/Python까지 지원합니다. 업계에서는 **Turborepo**(Vercel)와 함께 양대 산맥입니다.

### 3.1 Nx가 하는 일

1. **프로젝트 그래프 인식**: "`apps/web`이 `packages/ui`에 의존한다"를 자동 파악.
2. **증분 빌드**: 바뀐 패키지와 그 영향 범위만 다시 빌드·테스트. 전체 모노레포가 커져도 속도가 안 느려진다.
3. **캐싱**: 같은 입력이면 결과를 캐시에서 꺼냄. 같은 테스트를 두 번 돌리지 않음.
4. **태스크 러너**: `nx run-many -t test --all` 같이 여러 프로젝트에 일괄 실행.
5. **플러그인 생태계**: `@nx/react`, `@nx/vite`, `@nx/eslint` 등. 템플릿·제너레이터 지원.

### 3.2 nx.json

이 프로젝트의 `nx.json`에 있는 주요 설정:

- **namedInputs**: 캐시 키 계산 시 포함할 파일 패턴. 테스트 파일은 `production` 입력에서 제외해 "소스 파일 변경 없이는 빌드 캐시 히트"가 됨.
- **targetDefaults**: `build`, `test`, `lint`의 기본 동작. 예: `build`는 `^build`(의존성 빌드 먼저)에 의존.
- **plugins**: `@nx/vite/plugin`, `@nx/eslint/plugin`, `@nx/vitest/plugin` 등이 자동으로 프로젝트의 타겟을 감지.

### 3.3 자주 쓰는 명령

```bash
# 특정 프로젝트만
pnpm nx run web:build
pnpm nx run api:test

# 전체 프로젝트에 일괄
pnpm lint          # nx run-many -t lint --all
pnpm test          # nx run-many -t test --all

# 영향 받는 것만 (Git diff 기반)
pnpm nx affected -t test

# 의존성 그래프 시각화
pnpm nx graph
```

`pnpm nx graph`는 진짜 유용합니다. **어떤 패키지가 어떤 걸 의존하는지** 브라우저로 볼 수 있습니다.

---

## 4. 우리 모노레포의 구성 (최종 상세)

```
apps/web/         React 프런트
  ├── package.json  (name: "web", private)
  ├── vite.config.mts
  ├── project.json  (Nx 타겟 정의)
  ├── playwright.config.ts
  └── src/
      ├── main.tsx
      ├── App.tsx
      ├── domains/
      ├── components/
      └── lib/

apps/api/         Python FastAPI
  ├── pyproject.toml   (Python 의존성)
  ├── project.json     (Nx에서는 Python도 관리 가능)
  ├── alembic/
  └── src/aidoo_api/
      └── domains/...

apps/worker/      Python Celery 워커
  ├── pyproject.toml
  └── src/aidoo_worker/
      └── tasks/

apps/ops/         운영 도구 (초기 단계)

packages/ui/      공통 UI 컴포넌트
  ├── package.json  (name: "@aidoo/ui")
  ├── src/index.tsx
  └── src/styles.css

packages/contracts/  (예정) 공통 타입·스키마
```

Python 앱 두 개는 pnpm-workspace에 넣지 않고(파이썬은 자체 패키지 매니저 `uv` 를 씁니다), **Nx project.json** 으로만 관리합니다. 즉 **Nx는 TypeScript뿐 아니라 Python 프로젝트도 태스크 관리에 포함** 시킵니다.

---

## 5. 내부 패키지 import의 실제

`apps/web/src/App.tsx` 안에서 공통 UI를 쓸 때:

```ts
import { AppShell } from '@aidoo/ui';
```

이렇게 되려면 `packages/ui/package.json`의 `name` 이 `@aidoo/ui`여야 하고, `apps/web/package.json`이 그걸 `dependencies`(or `workspace:*` 참조)로 포함해야 합니다. pnpm 워크스페이스가 이 연결을 자동으로 처리합니다.

---

## 6. 왜 Nx인가 — 대안과 비교

| 도구 | 특징 | 비교 |
|---|---|---|
| **Nx** | 강력한 캐싱·플러그인·제너레이터. Angular 기원. | 우리 선택. Python까지 태스크 관리. |
| **Turborepo** | Vercel. 매우 간단. Next.js에 친숙. | Python 통합이 약함. |
| **Lerna** | 옛 표준. 지금은 Nx가 인수. | 레거시. |
| **Bazel** | Google. 아주 강력. 러닝커브 가파름. | 오버킬. |
| **Rush** | Microsoft. 복잡하지만 강력. | 우리 규모엔 과함. |

**Nx를 고른 결정적 이유**:

1. TypeScript + Python 혼합 모노레포에서 **태스크 관리까지 일원화** 가능.
2. 캐싱·affected 빌드가 훌륭해 모노레포가 커져도 속도를 유지.
3. 플러그인(@nx/react, @nx/vite 등)이 성숙해 설정 부담이 적다.

---

## 7. 모노레포 운영의 규칙

초보자가 흔히 실수하는 것들과 팀 차원의 권장 규칙.

### 7.1 경계 규칙 (module boundaries)

`@nx/eslint-plugin`에는 **"프로젝트 A는 프로젝트 B를 import 못 하게 막는"** 규칙이 있습니다. 예: `apps/ops`가 `apps/web`의 내부 코드를 직접 쓰면 안 됨. `packages/ui`를 통해서만 공유.

이 규칙이 없으면 모노레포가 빠르게 스파게티가 됩니다.

### 7.2 루트에 공통 도구, 각 프로젝트에 특화 도구

- 루트: ESLint, Prettier, TypeScript, Vitest 공통 설정.
- 앱별: Vite 설정, Playwright 설정, Python pyproject 등 특화.

### 7.3 버전 통일

같은 라이브러리(예: React)를 여러 앱이 써야 할 때, pnpm이 **한 버전만 쓰도록** 강제됩니다. 이게 **이중 설치** 로 인한 "두 개의 React" 같은 재앙을 막습니다.

### 7.4 의존성 추가의 기본값

- 앱의 의존성 → 그 앱의 `package.json`에만.
- 여러 앱이 쓰는 것 → `packages/ui` 같은 공용 패키지에 추가.
- 빌드·개발 도구 → 루트 `package.json`의 `devDependencies`.

---

## 8. 핵심 요약

- 모노레포 = **여러 앱·패키지를 한 저장소에**. 장점은 공유·일관성, 단점은 도구 필요.
- **pnpm** 을 패키지 매니저로 쓴다. 디스크·속도·엄격성 모두 우위.
- **Nx** 가 모노레포의 빌드·테스트·캐시를 오케스트레이션. Python도 타겟으로 관리.
- 우리 구조: `apps/{web,api,worker,ops}` + `packages/{ui,contracts}`.
- 규칙: **경계 규칙 + 버전 통일 + 의존성 위치 원칙**.

---

## 9. 이해도 체크

1. pnpm이 "디스크를 절약"하는 메커니즘을 한 줄로 설명하세요.
2. Nx가 "증분 빌드"를 가능하게 하는 이유는?
3. 우리 프로젝트에서 `packages/ui`가 하는 역할은?
4. 모노레포에서 "경계 규칙"이 없으면 생기는 문제를 예로 들어 보세요.
5. `pnpm nx graph`를 실행했을 때 기대되는 출력은 어떤 것일지 설명해 보세요.
