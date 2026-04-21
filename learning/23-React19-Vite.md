# 23. React 19 + Vite — 프런트엔드의 심장

> **한 줄 요약.** React는 **"화면을 데이터의 함수로 그리는"** 라이브러리이고, Vite는 그 React 앱을 **놀랍게 빠르게 개발·빌드해 주는 도구**이다. 이 조합이 2025년 프런트엔드의 사실상 표준이다.

---

## 1. 웹 프런트엔드의 짧은 역사 (왜 React가 표준이 됐나)

- **~2000년대 중반**: HTML + CSS + 약간의 JavaScript. 페이지 이동마다 서버가 전체 HTML을 돌려줌.
- **2005년 이후**: AJAX로 "페이지 안 바뀌고 서버와 대화" 가능해짐. 화면이 복잡해지기 시작.
- **2010년대 초**: 거대한 프런트 코드가 jQuery로 관리 불가능해짐. 프레임워크 전쟁.
- **2013년**: Facebook이 **React**를 공개. "화면을 컴포넌트로 쪼개라"라는 철학.
- **2015~**: React + Redux, Vue, Angular의 삼국지.
- **2020~**: React가 점유율 1위 고착. Next.js, Vite, React Server Components 등 생태계 성숙.
- **2024~**: **React 19** 공개. 새 기능: Actions, `use` hook, Server Components 성숙화.

우리 프로젝트는 **React 19.0.0** + **React Router v7 (data router 스타일)** + **Vite 7.3.1** 의 최신 조합을 씁니다.

---

## 2. React의 핵심 아이디어

### 2.1 "UI는 데이터의 함수"

React의 가장 근본 철학입니다.

```
UI = f(state)
```

"같은 상태(state)에서는 항상 같은 화면이 나온다." 상태가 바뀌면 자동으로 화면이 업데이트됩니다. 우리는 **"어떻게 바꿀지"** 를 명령하지 않고 **"어떻게 생겼는지"** 만 선언합니다. 이를 **선언형(declarative) 프로그래밍** 이라 합니다.

### 2.2 컴포넌트(Component)

UI의 **재사용 가능한 조각**. 버튼, 카드, 폼, 페이지 모두 컴포넌트입니다.

```tsx
function Greeting({ name }: { name: string }) {
  return <h1>안녕하세요, {name}님</h1>;
}

// 사용
<Greeting name="김과장" />
```

이 JSX 문법(`<h1>...</h1>`)은 HTML처럼 보이지만 실제로는 JavaScript 함수 호출로 번역됩니다.

### 2.3 상태(state)와 훅(hook)

컴포넌트가 기억할 값을 `useState` 훅으로 선언합니다.

```tsx
import { useState } from 'react';

function Counter() {
  const [count, setCount] = useState(0);

  return (
    <>
      <p>카운트: {count}</p>
      <button onClick={() => setCount(count + 1)}>+1</button>
    </>
  );
}
```

`setCount`가 호출되면 React가 **이 컴포넌트만 다시 그립니다**. 이 자동 업데이트가 React의 마법입니다.

### 2.4 다른 핵심 훅

- **`useEffect`** — 외부 세계와의 상호작용(서버 요청, 구독, 타이머)을 처리.
- **`useMemo` / `useCallback`** — 비싼 계산·함수를 캐시.
- **`useContext`** — 컴포넌트 트리 깊은 곳으로 값을 전달.
- **`useRef`** — DOM 참조나 렌더링 간 유지 값.

훅은 반드시 **함수 컴포넌트 최상위** 에서만 호출. 조건문 안이나 반복문 안에서 호출하면 안 됩니다(Rules of Hooks).

### 2.5 React 19의 새로움

- **Actions** — 폼 제출을 서버와 연결하는 새 개념.
- **`use()` 훅** — Promise와 Context를 동시 처리.
- **ref as prop** — `forwardRef` 없이도 자식에 ref 전달.
- **더 안정적인 Suspense + concurrent rendering**.

이 프로젝트에서 본격적으로 새 기능을 많이 쓰고 있지는 않지만, 앞으로 활용 폭이 넓어질 영역입니다.

---

## 3. 왜 React인가 — 대안과 비교

| 프레임워크 | 철학 | 우리와의 비교 |
|---|---|---|
| **React** | 라이브러리, 컴포넌트 기반 | 우리 선택. 생태계 최강. |
| **Vue 3** | 간단한 템플릿 문법, 반응성 자동 추적 | 초보에 친숙. 생태계 중상. |
| **Angular** | 전체 프레임워크, TS 우선 | 대기업 백오피스에 강세. 무거움. |
| **Svelte / SvelteKit** | 컴파일 타임에 반응성 제거. 매우 가벼움 | 떠오르는 다크호스. |
| **Solid / Qwik** | 최신 대안. 성능 중심 | 얼리어답터 영역. |

**React를 고른 결정적 이유**:

1. **인재 풀**: 전 세계에서 가장 많이 쓰는 프런트 기술. AI(Claude/GPT)도 React 코드에 제일 강하다.
2. **생태계**: BlockNote, FullCalendar, TanStack Table 등 거의 모든 UX 라이브러리가 React 우선.
3. **Next.js 등으로의 진화 경로**가 열려 있다. 추후 SSR이 필요해지면 옮길 수 있다.
4. **AI 코딩 지원**: LLM 학습 데이터에 가장 많이 들어 있는 프런트 프레임워크.

---

## 4. Vite — "빌드가 이렇게 빠르다니"

Vite(빛)는 2020년 Evan You(Vue 창시자)가 공개한 빌드 도구입니다. 이름 뜻은 프랑스어 "빠르다"입니다.

### 4.1 이전의 문제 — Webpack의 느림

2010년대 후반의 표준이었던 **Webpack** 은 개발 서버를 띄울 때 **전체 코드를 번들**했습니다. 작은 프로젝트는 괜찮지만 커지면 수 분이 걸렸습니다. 한 번 고치고 F5 누를 때마다 몇 초.

### 4.2 Vite의 혁신

- **개발 중에는 번들하지 않는다.** 브라우저가 요청한 모듈만 **네이티브 ES 모듈** 로 즉시 제공. 시작이 1초 안 걸림.
- **esbuild** (Go로 작성된 초고속 번들러)로 의존성 사전 번들.
- **HMR(Hot Module Replacement)** 이 번개같이 빠름. 코드 저장하면 화면이 즉시 반영됨.
- 빌드 시에는 **Rollup** (검증된 번들러)을 사용해 최적화.

### 4.3 이 프로젝트의 Vite 설정

`apps/web/vite.config.mts` 에는 대략:

- `@vitejs/plugin-react` — JSX 변환.
- `@tailwindcss/vite` — Tailwind v4 통합.
- Nx 플러그인 연계.
- 개발 서버 포트 4200.

개발자는 거의 건드릴 일이 없습니다. 문제가 생기면 AI에게 "Vite 설정에서 X를 추가해 줘"로 시킵니다.

### 4.4 대안

| 도구 | 비고 |
|---|---|
| **Vite** | 우리 선택 |
| Webpack | 전통적, 여전히 대형 프로젝트에서 사용 |
| Parcel | 설정 없는 간편함. 커뮤니티 약해짐. |
| esbuild 직접 | 매우 빠르지만 플러그인 빈약 |
| Turbopack | Next.js 차세대 번들러 |
| Rspack | Rust로 만든 Webpack 호환 |

---

## 5. 빌드 결과물의 모양

`pnpm build:web` 실행하면 `dist/apps/web/` 아래에 다음이 생깁니다.

```
dist/apps/web/
├── index.html           ← 진입점 (아주 작음)
├── assets/
│   ├── index-a3f1b2.js  ← 메인 번들
│   ├── vendor-xxx.js    ← React, Mantine 등 라이브러리
│   ├── index-yyy.css    ← Tailwind 생성된 스타일
│   └── ...              ← 폰트·이미지 등
```

파일 이름에 붙는 해시(`a3f1b2`)는 내용이 바뀌면 달라집니다. 이 덕분에 브라우저 캐시를 **안전하게** 쓸 수 있습니다.

Nginx는 이 `dist/` 폴더를 그대로 사용자에게 서빙합니다. 즉 **운영 서버에서는 Node.js가 돌지 않습니다**. 정적 파일 + API 서버 두 가지뿐입니다.

---

## 6. SPA(Single Page Application)의 이해

우리 포털은 SPA입니다. 한 번 `index.html`이 로드되면, 이후 페이지 이동은 서버에 새 HTML을 요청하지 않고 **JavaScript가 화면을 갈아 끼웁니다**.

- 장점: 빠른 전환, 네이티브 앱 같은 체감.
- 단점: 첫 로딩이 살짝 무거움(번들을 받아야 함), SEO 취약(사내 포털이라 무관).

우리는 사내 포털이라 SPA의 단점이 문제되지 않고 장점만 취합니다.

---

## 7. 렌더링의 작동 원리 (정말 얕게)

React가 어떻게 빠른지 궁금하면 한 문단만:

1. JSX는 `React.createElement(...)` 호출로 번역됨.
2. 이 호출들이 **가상 DOM(Virtual DOM)** 이라는 가벼운 JS 트리를 만듦.
3. 상태가 바뀌면 React는 **이전 가상 DOM과 새 가상 DOM을 비교(diff)**.
4. **달라진 부분만** 실제 브라우저 DOM에 반영.

이 "필요한 곳만 업데이트" 전략이 React의 성능 비결입니다. 다만 최근에는 Svelte·Solid 같은 대안들이 "애초에 가상 DOM 없이" 더 빠르게 하자고 도전하고 있습니다.

---

## 8. 실전 팁

### 8.1 키(key)의 중요성

리스트를 렌더링할 때 각 항목에 **고유한 `key`** 를 줘야 React가 추적할 수 있습니다.

```tsx
{users.map(u => <UserCard key={u.id} user={u} />)}
```

`key={index}`는 피하세요. 순서가 바뀌면 버그가 납니다.

### 8.2 상태는 필요한 곳에 가까이

상위 컴포넌트에서 상태를 들고 아래로 내려주는 것은 자연스럽지만, **너무 위에서 들고 있으면** 전 컴포넌트가 다시 그려질 수 있습니다. 상태는 **쓰는 곳에 가장 가까이** 두는 것이 원칙.

### 8.3 사이드 이펙트는 `useEffect`에

HTTP 호출, 타이머, 구독은 **렌더 함수 안에서 바로 하지 말고** `useEffect` 안에서. 이유: 렌더는 순수해야 하기 때문.

### 8.4 Strict Mode

React는 개발 중 `<StrictMode>` 안에서 컴포넌트를 **두 번 렌더링** 합니다. "사이드 이펙트를 감지"하기 위한 트릭입니다. 당황하지 마세요.

---

## 9. 이 프로젝트에서 React가 쓰이는 지점

- `apps/web/src/main.tsx` — 앱의 진입점. `<App />` 을 렌더.
- `apps/web/src/App.tsx` — 최상위 라우터 구성.
- `apps/web/src/domains/**` — 도메인별 페이지와 컴포넌트.
- `apps/web/src/components/**` — 공용 UI 컴포넌트.
- `packages/ui` — 여러 앱이 공유하는 UI.

---

## 10. 핵심 요약

- React는 "UI = f(state)" 라는 선언형 모델.
- **컴포넌트 + 훅** 이 두 축. 특히 `useState`, `useEffect`.
- React 19의 핵심: Actions, `use()`, ref-as-prop, 안정된 Suspense.
- **Vite** 는 네이티브 ESM + esbuild 로 "미친 듯이 빠른" DX 제공.
- 빌드 결과는 **정적 파일** → Nginx가 서빙. 운영에 Node 필요 없음.
- 대안(Vue, Svelte 등)도 훌륭하지만 React의 **생태계 + AI 지원** 이 이 프로젝트 선택의 결정타.

---

## 11. 이해도 체크

1. "UI = f(state)"라는 식의 의미를 일상 예로 설명해 보세요.
2. `useState`와 `useEffect`의 역할을 각각 한 문장으로 요약하세요.
3. Webpack과 Vite의 결정적 차이는 무엇인가요?
4. 리스트 렌더링에서 `key`를 **인덱스**로 주는 것이 왜 위험한가요?
5. SPA의 장점 두 가지와 단점 하나를 들어 보세요.
6. React 19에서 새로 추가된 기능 중 하나 이름을 대고, 어떤 용도에 쓸 수 있을지 짐작해 보세요.
