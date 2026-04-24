# 24. UI 시스템 — Mantine + Radix + Tailwind v4

> **한 줄 요약.** UI를 만들 때는 **"기본 컴포넌트 + 저수준 프리미티브 + 스타일 엔진"** 삼박자를 조합한다. 이 프로젝트는 **Mantine(풍부한 컴포넌트) + Radix(접근성 프리미티브) + Tailwind v4(유틸리티 스타일링)** 를 적재적소에 함께 쓴다.

> 🔑 **한 마디로.** Mantine(완성 컴포넌트), Radix(접근성 프리미티브), Tailwind(스타일 유틸리티)를 역할별로 조합해 생산성과 커스터마이징을 동시에 확보하는 방식이다.

### 세 도구의 역할 분담

- Mantine은 빠른 화면 구축, Radix는 세밀한 상호작용 제어, Tailwind는 레이아웃/스타일 미세 조정을 담당합니다.
- Mantine만으로 부족한 특수 UX는 Radix로 동작을 구성하고 Tailwind로 시각 스타일을 맞춥니다.
- 세 도구를 분리하면 컴포넌트 일관성과 디자인 자유도를 동시에 확보할 수 있습니다.
- 팀 표준 UI를 유지하면서도 도메인별 요구사항에 맞게 세부 UX를 조정할 수 있습니다.

사용 중인 주요 버전: **Mantine 8.3, Tailwind 4.2 + `@tailwindcss/vite`(Vite 플러그인), lucide-react 0.546(아이콘)**.

> 💡 **왜 하나로 통일하지 않나?** "하나만 쓰면 단순할 텐데..."라는 의문은 자연스럽다. **답은 "각자 한계가 다른 지점에서 드러나기 때문"** 이다. Mantine만 쓰면 특이한 UX에서 막히고, Radix만 쓰면 기본 폼·테이블을 직접 다 짜야 하고, Tailwind만 쓰면 접근성 로직을 처음부터 짜야 한다. **삼박자 조합이 각 한계를 서로 메운다**.

---

## 1. 왜 세 개나 쓰나 — 역할이 다르다

얼핏 보면 "UI 라이브러리가 세 개나?"라고 생각할 수 있지만, 각각 **다른 층위** 를 담당합니다.

| 계층 | 역할 | 도구 |
|---|---|---|
| 1. 디자인 시스템(완성된 컴포넌트) | 버튼·폼·모달 등 즉시 사용 가능 | **Mantine** |
| 2. 접근성 프리미티브(동작 뼈대) | 드롭다운·다이얼로그 등의 **동작·접근성**만 제공, 스타일 없음 | **Radix UI** |
| 3. 스타일 엔진 | 세밀한 시각 조정, 레이아웃 | **Tailwind CSS v4** |

핵심 요약:
- **Mantine** = 즉시 사용 가능한 완성형 UI 컴포넌트 계층
- **Radix** = 접근성과 상호작용을 제어하는 저수준 프리미티브 계층
- **Tailwind** = 레이아웃·간격·색상 조정을 위한 유틸리티 스타일 계층

대부분 화면은 Mantine으로 빠르게 만들고, 특수한 UX(예: 팀 선택 드롭다운, 접근성이 중요한 모달)는 Radix로 직접 짜고, **미세 조정은 Tailwind로** 합니다.

---

## 2. Mantine — 가장 풍부한 React UI 키트

### 2.1 Mantine이란

**Mantine 8** 은 Vitaly Rtischev가 이끄는 오픈소스 프로젝트입니다. React 생태계에서 완성도 높은 **컴포넌트 + 훅 모음** 중 하나이며, 활발히 유지보수되는 라이브러리입니다.

제공하는 것:
- **코어 컴포넌트**: Button, TextInput, Select, Modal, Notification, Table, Tabs, Drawer, Card 등 100여 개.
- **훅 컬렉션**: `useDisclosure`, `useLocalStorage`, `useDebouncedValue` 등 50+ 개.
- **form, dates, charts, notifications, modals** 등의 서브 패키지.
- **다크 모드·테마** 기본 지원.

### 2.2 우리 프로젝트에서 Mantine 사용

`package.json`에 `@mantine/core`, `@mantine/hooks`가 등록돼 있습니다. 실제 사용 예:

```tsx
import { Button, TextInput, Modal } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';

function LoginModal() {
  const [opened, { open, close }] = useDisclosure(false);
  return (
    <>
      <Button onClick={open}>로그인</Button>
      <Modal opened={opened} onClose={close} title="로그인">
        <TextInput label="이메일" />
        ...
      </Modal>
    </>
  );
}
```

**Mantine을 쓰는 이유**:

1. **속도**: 80%의 UI는 추가 작업 없이 바로 만들 수 있음.
2. **일관성**: 디자인 시스템이 통일됨.
3. **접근성**: 키보드 내비게이션·ARIA 기본 제공.
4. **타입 강함**: TypeScript 지원이 매우 성숙.

### 2.3 대안 비교

| 라이브러리 | 비개발자도 알 만한 특징 |
|---|---|
| **Mantine** | **완제품 컴포넌트 100+ 개**, 사용 쉬움. 우리 선택. |
| MUI (Material UI) | **구글 머티리얼 디자인 기반** — 특유의 둥글고 그림자 있는 룩. 테마 변경 번거로움. |
| Chakra UI | **props로 스타일** 방식. v3에서 API 대격변으로 선호도 하락. |
| Ant Design | **중국권 기업 폼**이 강점 — 엔터프라이즈 폼·테이블 분야 최강. 고유 디자인 취향. |
| shadcn/ui | **"npm 설치"가 아니라 코드 복사-붙여넣기** 방식 — 내 저장소에 소스가 그대로 들어와 자유도 최고. 최근 가장 뜨거움. |

**shadcn/ui**는 최근 가장 뜨거운 선택지인데, 이 프로젝트는 Mantine을 메인으로 두고 shadcn 스타일의 컴포넌트를 일부 같이 쓰는 **하이브리드** 로 보입니다(실제로 `apps/web/src/components/ui/` 아래 shadcn 스타일이 보임).

### 2.4 ⚠️ UI 라이브러리에서 자주 듣는 오해

- **"UI 라이브러리 여러 개를 쓰면 번들 크기가 폭발한다"** — Vite가 **Tree shaking**(실제로 쓰지 않은 코드를 빌드에서 제거)을 해 주므로, 3개를 나눠 써도 안 쓰는 컴포넌트는 포함되지 않는다.
- **"Tailwind는 CSS의 대체제다"** — Tailwind는 **CSS 위의 유틸리티 레이어**다. CSS를 이해할수록 더 잘 쓸 수 있다.
- **"Mantine을 쓰면 디자인이 획일화된다"** — Mantine에는 **테마 시스템**이 있어 색·폰트·모서리 반경을 일괄 조정할 수 있다. 여기에 Tailwind로 미세 조정을 더한다.
- **"Radix도 예쁜 컴포넌트를 준다"** — Radix는 **"스타일 0%"** 다. 동작·접근성만 준다. 그래서 **Headless**(머리 없는)라고 불린다.
- **"접근성은 장애인을 위한 것이지 나머지 사용자에겐 무관하다"** — 접근성이 잘 된 UI는 **키보드 사용자·고령자·일시적 부상자** 모두에게 이득이고, **자동화 테스트(E2E)** 도 쉬워진다.

---

## 3. Radix UI — "스타일 없는 동작 뼈대"

### 3.1 Radix란

**Radix Primitives** 는 WorkOS에서 만든 **"Headless UI"** 라이브러리입니다. "Headless" 는 "머리(눈에 보이는 스타일)가 없다"는 뜻으로, **동작과 접근성만** 제공하고 **모양은 당신이 마음대로** 하라는 철학입니다.

제공 프리미티브:
- Dialog, Dropdown Menu, Popover, Select, Tabs, Toast, Tooltip, Scroll Area, Accordion 등

### 3.2 왜 Mantine이 있는데 Radix도?

상황에 따라 **세밀한 제어** 가 필요합니다.

- Mantine의 Modal로 안 되는 특수 레이아웃·애니메이션이 필요할 때
- Mantine을 쓰기엔 과한데, 접근성은 제대로 갖추고 싶을 때
- 여러 개가 중첩되는 복잡한 드롭다운

이럴 때 Radix의 프리미티브를 들고 와서 Tailwind로 스타일링하면 **무한한 자유** + **접근성 보장**을 같이 얻습니다.

### 3.3 사용 예

```tsx
import * as Dialog from '@radix-ui/react-dialog';

function ConfirmModal() {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button>삭제</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white p-6 rounded-lg">
          <Dialog.Title>정말 삭제하시겠습니까?</Dialog.Title>
          <Dialog.Description>되돌릴 수 없습니다.</Dialog.Description>
          ...
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

Radix는 **트리거·포털·오버레이·콘텐츠** 를 조립하는 구조입니다. 이 구조 자체가 **올바른 접근성 패턴**을 강제합니다.

### 3.4 우리 프로젝트의 Radix

`package.json`에 `@radix-ui/react-dialog`, `react-dropdown-menu`, `react-scroll-area`, `react-select`, `react-tabs`, `react-toast`, `react-tooltip` 이 들어 있습니다. 특히 **AI 채팅의 승인 모달, 워크스페이스 스위처, 테이블의 다양한 드롭다운** 같은 곳에 주로 쓰입니다.

---

## 3.5 🏢 AI 도구 승인 모달 만들기

**상황:** AI가 "사내 DB에 이 쿼리를 실행할까요?"라고 묻는 모달. 보안상 **포커스 트랩(Focus Trap — 모달이 열린 동안 Tab 키가 모달 밖으로 못 나가게 막는 패턴)** 과 **ESC로 닫기, 배경 클릭 차단** 이 필수다.

- Mantine의 Modal로도 가능하지만, 이 승인 UX는 **"AI가 제안 중이라는 특이 애니메이션 + 사용자 체크박스 + '기억하기' 옵션"** 같은 세밀한 요구가 많음.
- 그래서 `@radix-ui/react-dialog`(동작·접근성) + **Tailwind**(모양)을 조합해 커스텀 제작.
- 키보드 사용자는 **Tab → 체크박스 → 확인/취소 → Tab 순환** 이 자동 보장됨. 접근성 인증이 쉬워진다.

---

## 4. Tailwind CSS v4 — 유틸리티 퍼스트 스타일링

### 4.1 Tailwind란

**Tailwind CSS** 는 2017년 Adam Wathan이 만든 CSS 프레임워크입니다. 핵심 철학은 **"미리 만들어진 작은 유틸리티 클래스를 조합해 스타일링하자"**.

```html
<div class="flex items-center gap-3 rounded-lg bg-white p-4 shadow-sm">
  <img class="w-10 h-10 rounded-full" />
  <span class="text-sm font-medium text-gray-700">김과장</span>
</div>
```

`flex`, `items-center`, `gap-3`, `rounded-lg`, `bg-white`, `p-4` ... 각 클래스가 한 줄의 CSS 속성에 대응합니다.

### 4.2 왜 이게 좋은가 (논쟁 많던 방식)

처음 보면 "HTML이 더러워지는 거 아닌가?"라고 생각합니다. 실제 써 보면 반전됩니다.

장점:
- **이름 짓기 고민 제거**: `card-header-avatar-small` 같은 이름을 안 짜도 됨.
- **빠른 수정**: 클래스만 바꾸면 스타일 반영.
- **일관성**: 전역 디자인 토큰(색상·간격)이 시스템화.
- **CSS 파일이 작아진다**: 사용한 클래스만 빌드에 포함.
- **다른 파일로 컨텍스트 전환 불필요**.

단점:
- HTML이 길어 보인다(익숙해지면 괜찮음).
- 팀이 같은 규칙을 이해해야 합니다.

### 4.3 Tailwind v4의 신세계

2024년 말 공개된 v4는 이전 버전과 결이 크게 다릅니다.

- **Vite 플러그인(`@tailwindcss/vite`) 통합** — `tailwind.config.js` 없이도 바로 동작. **CSS-first 설정** — `tailwind.config.js` 를 생략하고 CSS 파일 안에 `@theme`로 선언.
- **Oxide 엔진** — **Rust 기반**으로 이전 대비 훨씬 빠른 빌드. 프로젝트가 커져도 스타일 생성 시간이 거의 안 늘어난다.
- **CSS 안에서 테마 정의** — `@theme { --color-brand: ... }`. JS 설정을 줄이고 **CSS 변수 표준**을 활용.
- **컨테이너 쿼리(Container Query — "요소의 부모 폭 기준으로 반응형") 기본 지원**.

이 프로젝트는 `tailwindcss@^4.2.2` + `@tailwindcss/vite@^4.2.2` + `@tailwindcss/typography`(마크다운 렌더 전용 플러그인) 조합입니다.

### 4.4 🛠️ 5분 실습 — Tailwind 체감

1. 개발 서버에서 아무 페이지나 연다.
2. F12 → **Elements** 탭 → 아무 버튼·카드 클릭.
3. 우측 "Styles" 패널에서 **클래스 하나가 CSS 한두 줄에 대응**하는 것을 확인(예: `rounded-lg` → `border-radius: 0.5rem`).
4. 그 중 클래스 하나를 임시로 지워 보고 화면이 어떻게 바뀌는지 관찰.

### 4.5 대안 비교

| 방식 | 비개발자도 알 만한 특징 | 비고 |
|---|---|---|
| **Tailwind** | **HTML 안에 작은 클래스들**을 조합. 이름 짓기 부담 0. | 우리 선택 |
| CSS Modules | **컴포넌트마다 별도 .css 파일**, 클래스 이름을 자동 격리. | 전통적, 안전. |
| styled-components / Emotion | **JS 안에 CSS 문자열**을 적어 스타일 캡슐화. | 런타임 오버헤드. 인기 하락. |
| vanilla-extract | **타입 안전한 CSS-in-JS** — TS 오타도 검사. | 떠오름. |
| CSS 그대로 | 그대로 | 큰 규모엔 이름·중복 관리가 혼잡. |

**Tailwind를 고른 결정적 이유**:

1. AI와 궁합이 최고 — 클래스 이름이 고정 규칙이라 생성이 정확.
2. 대규모 협업에서 **이름 짓기 불일치** 가 사라짐.
3. Mantine·Radix와 **평화롭게 공존** 가능(Mantine은 자체 스타일, Tailwind는 보조).

> Tailwind v4는 **Oxide 엔진(Rust)** 과 **CSS-first 설정**(JS config 없이 CSS 파일만으로 테마 정의)을 통해 설정 파일 수와 빌드 부담을 줄이는 방향을 택합니다. 이 프로젝트도 Vite 플러그인 + CSS-first 구조를 채택해 설정을 단순화합니다.

---

## 5. 세 도구의 실제 역할 분담

| 화면 예시 | 사용 조합 |
|---|---|
| 폼 필드(Input, Select) | Mantine 주력. Tailwind로 간격 조정. |
| 페이지 레이아웃·그리드 | Tailwind 주력. |
| 커스텀 드롭다운 메뉴 | Radix + Tailwind. |
| 알림/토스트 | Mantine Notifications 또는 Radix Toast. |
| 모달/다이얼로그 | Mantine 우선, 세밀한 UX는 Radix. |
| 타이포(글꼴 시스템) | Tailwind typography + 커스텀 CSS. |

이런 하이브리드는 초보자에게는 "혼란스러워 보이지만" 실제로는 각 도구의 강점을 모두 취하는 현명한 전략입니다.

---

## 6. 실전 주의점

### 6.1 클래스 이름 동적 조합

`clsx`와 `tailwind-merge`가 의존성에 있습니다. 이들은 **클래스를 조건부로, 그리고 충돌 없이** 만들기 위한 도구입니다.

```tsx
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

function Button({ primary, className }) {
  return (
    <button className={twMerge(clsx(
      'px-4 py-2 rounded',
      primary ? 'bg-blue-500 text-white' : 'bg-gray-200',
      className  // 외부에서 덮어쓸 수 있도록
    ))} />
  );
}
```

`tailwind-merge`는 "`px-4`와 `px-6`이 둘 다 있으면 뒤의 것이 이긴다"를 보장해 줍니다.

### 6.2 class-variance-authority (cva)

`class-variance-authority`는 shadcn/ui 스타일의 "변형 관리" 유틸입니다. "버튼의 크기=sm/md/lg, 색=primary/danger" 같은 조합을 **선언형으로** 정의합니다.

```tsx
const button = cva('rounded', {
  variants: {
    size: { sm: 'px-2 py-1', md: 'px-4 py-2', lg: 'px-6 py-3' },
    intent: { primary: 'bg-blue-500 text-white', danger: 'bg-red-500 text-white' }
  },
  defaultVariants: { size: 'md', intent: 'primary' }
});
```

---

## 7. 접근성(a11y) — 간과하지 말아야 할 것

**Accessibility(a11y — "Accessibility"의 a와 y 사이에 글자가 11개라 붙은 줄임말)** 는 "장애가 있는 사용자도 쓸 수 있는가"입니다. 사내용이라고 소홀하면 안 됩니다(색맹, 키보드 전용 사용자, **스크린 리더(Screen Reader — 화면 내용을 음성으로 읽어 주는 보조 기술)** 사용자 등).

- Mantine과 Radix는 접근성을 **기본 원칙**으로 설계되어 있으며, 기본 설정으로 사용해도 대부분 요구사항을 충족합니다.
- `eslint-plugin-jsx-a11y`가 접근성 위반을 **정적 검사(static check — 실행하지 않고 코드만 보고 문제를 잡기)** 합니다. 우리 설정에 포함되어 있습니다.
- 키보드만으로 모든 기능이 되는지 주기적으로 테스트.
- **ARIA(Accessible Rich Internet Applications — 보조 기술이 화면 요소의 역할을 이해할 수 있게 붙이는 속성)** 속성은 Radix가 자동 부여.

### 7.1 아이콘 — lucide-react

이 프로젝트는 아이콘을 **lucide-react 0.546**에서 사용합니다. Lucide는 **Feather Icons의 후계**로, 500+ 개의 오픈소스 아이콘을 제공합니다. Tree shaking 덕분에 **사용한 아이콘만** 번들에 포함됩니다. `import { Search, Plus } from 'lucide-react';`처럼 간단히 적용할 수 있습니다.

---

## 7.2 🏢 대시보드 카드 한 벌 만들어 보기

**상황:** 경영지원실이 "월간 현황 대시보드에 KPI 카드 8개"를 요구.

- 카드 **구조**(제목·수치·증감 화살표): **Mantine의 `<Card>`, `<Text>`, `<Group>`** 로 뼈대 구축 → **하루 안에 8개** 초안 완성.
- **반응형 그리드**(PC 4열, 태블릿 2열, 모바일 1열): **Tailwind** `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4`.
- 상세 보기 **모달**: 필터·정렬 UX가 세밀 → **Radix Dialog + Tailwind**로 커스텀.
- 아이콘: `lucide-react`에서 `TrendingUp`, `TrendingDown` 가져오기.

결과: 3개 도구의 강점이 중첩되지 않고 **층위별로 역할 분담** → 작성 속도와 품질을 동시에 확보.

---

## 7.3 "이 기술을 고른 이유와 대안" — 비개발자 관점 보강

**세 도구 조합을 택한 이유**:

1. **속도 + 자유도 + 일관성**을 동시에 얻는다. 한 가지만 쓰면 어디선가 반드시 한계에 부딪힌다.
2. **한 도구를 뽑아도 다른 도구가 대체 가능** → 특정 라이브러리 종속 위험 분산.
3. **업계 주류 패턴**(shadcn/ui를 쓰는 팀은 대체로 Radix + Tailwind를 기본 탑재)과 결이 맞아 **인재 채용·AI 보조**가 유리.

**"Bootstrap만 사용하면 안 되나요?"라는 질문에**:

- Bootstrap은 **2010년대의 표준**이었고 컴포넌트 범위가 좁음. 현대 웹 UX(드래그·실시간·복합 폼)에는 부족.
- 우리가 만드는 건 **내부 AI 포털**이라 디자인 커스터마이징 요구가 크고, Bootstrap의 고유한 색·모양이 족쇄가 됨.

**"Mantine 대신 MUI는?"**:

- MUI는 **구글 머티리얼 디자인 DNA**가 강해 우리 고유 브랜드 룩을 구현하려면 테마 오버라이드 비용이 큼.
- Mantine은 **중립적인 룩**에서 시작해 우리 정체성을 덧입히기 쉽다.

---

## 8. 핵심 요약

- UI 스택은 **세 층**: 디자인 시스템(Mantine) + 프리미티브(Radix) + 스타일 엔진(Tailwind v4).
- Mantine은 **빠른 제작**, Radix는 **정교한 커스텀 + 접근성**, Tailwind는 **세밀 조정 + 레이아웃**.
- Tailwind v4는 Rust 엔진 기반으로 훨씬 빠르고 설정이 간단.
- 유틸리티는 `clsx` + `tailwind-merge` + `cva` 로 깔끔히 조합.
- **접근성**은 Mantine/Radix의 기본 기능 + ESLint 규칙으로 유지.
