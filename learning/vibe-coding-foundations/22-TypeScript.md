# 22. TypeScript — 타입이라는 안전망

> **한 줄 요약.** TypeScript는 JavaScript에 **데이터 형태 계약(타입)**을 추가한 언어다. 이 계약 덕분에 편집기와 CI가 실행 전에 오류를 조기에 발견한다.

> 🔑 **한 마디로.** 함수와 데이터의 입력/출력 형식을 코드로 명시해, 규격이 맞지 않는 값을 작성 단계에서 차단하는 방식이다.

### 타입 시스템 핵심 포인트

- 타입 시스템은 코드 실행 전에 데이터 형식 불일치를 검출합니다.
- 타입 선언은 함수 입력·출력 범위를 명확히 해 호출 실수를 줄입니다.
- 호환되지 않는 타입은 컴파일 단계에서 차단되어 런타임 오류로 넘어가기 전에 수정할 수 있습니다.
- 필드 규격을 코드에 명시하면 데이터 계약 위반을 조기에 감지할 수 있습니다.

이 프로젝트는 **TypeScript 5.9.3** 버전을 사용하며 `strict: true` 모드를 켜 놓았습니다.

---

## 1. JavaScript의 태생적 고민

JavaScript는 1995년 10일 만에 만들어진 언어입니다. 당시에는 "웹 페이지에 간단한 동작을 추가하는 용도"였기에 **타입을 엄격히 검사할 이유가 없었습니다.**

```js
let x = 3;
x = 'hello';     // 에러 없음
x = [1, 2, 3];   // 에러 없음
```

이런 유연함은 작은 스크립트에는 편리했지만, **수십만 줄 규모의 앱**에서는 유지보수 부담을 크게 늘렸습니다. 함수가 어떤 값을 받을지, 어떤 값을 반환할지 **실행 전에 알기 어렵기** 때문에 런타임 오류가 증가합니다.

---

## 2. TypeScript의 등장

2012년 Microsoft가 발표했습니다. 철학은 명료합니다.

> **"자바스크립트에 타입 주석을 붙이고, 그것을 컴파일 시점에 검사한다."**

TypeScript는 결국 **JavaScript로 번역(트랜스파일, transpile — 언어 A 소스를 언어 B 소스로 변환)** 되어 브라우저에서 실행됩니다. 타입 정보는 **빌드 시점(build time — 배포용 파일을 만들어 내는 단계)** 에만 사용되고, **런타임(runtime — 실제 사용자 브라우저에서 돌아가는 시점)** 에는 사라집니다.

```ts
let x: number = 3;
x = 'hello';   // ❌ 컴파일 오류: Type 'string' is not assignable to type 'number'
```

---

## 3. 왜 타입이 안전망인가

### 3.1 자동 완성

IDE가 "이 객체에 어떤 필드가 있는지" 정확히 알고 제안해 줍니다. 이것만으로도 개발 속도가 2~3배 빨라진다는 연구가 많습니다.

### 3.2 리팩토링

"이 함수 이름을 바꾸고 싶다"를 IDE가 **안전하게 전 프로젝트에 적용** 합니다. 타입이 없으면 텍스트 치환에 가까워 실수가 납니다.

### 3.3 문서화 효과

타입 선언 자체가 문서입니다. 코드 리뷰에서 타입만 봐도 "이 함수가 뭘 받아 뭘 반환하는지" 명확합니다.

### 3.4 버그 조기 발견

Microsoft 연구에 따르면 JS→TS 전환 시 **전체 버그의 약 15%가 타입 시스템만으로** 발견됩니다.

---

## 3.5 ⚠️ 타입에서 자주 하는 오해

- **"TypeScript는 JavaScript보다 느리다"** — 브라우저가 실행하는 것은 **트랜스파일된 JavaScript**다. 타입은 빌드 때 사라지므로 **런타임 성능은 동일**하다.
- **"타입 선언이 코드량을 2배로 늘린다"** — 대부분은 **자동 추론**된다. 명시가 필요한 곳은 함수 경계·외부 데이터 정도다.
- **"타입이 있으면 버그가 안 난다"** — 타입은 **"형태(shape)가 맞는지"** 만 검사한다. "값이 비즈니스 규칙상 맞는지"(예: 결제 금액이 음수인지)는 별도 검증이 필요하다. 타입은 **안전망**이지 **만능 방패**가 아니다.
- **"TypeScript를 배우려면 JavaScript부터 다 마스터해야 한다"** — AI 시대에는 둘을 같이 배우는 편이 빠르다. 에러 메시지·예제는 대부분 TS 맥락이다.
- **"타입만 고치면 버그가 고쳐진다"** — 타입 오류를 억지로 `any`로 덮으면 **버그를 숨기는 꼴**이다. 원인을 먼저 이해해야 한다.

---

## 3.6 🏢 AI 채팅 응답 포맷이 바뀔 때

**상황:** 백엔드에서 AI 채팅 응답 구조를 `{ text }` 에서 `{ text, citations: Source[] }` 로 바꾸기로 했다.

- 변경 파일: `apps/web/src/app-modules/ai/api/ai-api.ts` 의 응답 타입.
- TypeScript가 **즉시** 이 타입을 참조하는 **모든 컴포넌트·훅에 빨간 밑줄**을 긋는다. "이 자리에서 `citations`를 안 쓰고 있는데?"
- 개발자는 **"빨간 줄이 난 곳만 한 바퀴 돌며"** 수정한다. 타입이 없었다면 **실제 배포 후 사용자가 기능 깨진 걸 발견**하는 시나리오가 흔하다.
- AI 도구에게 "ChatResponse 바꿨으니 영향 받는 파일 전부 수정" 이라고만 지시해도, 타입이 명확할수록 AI가 정확히 해 준다.

---

## 4. 이 프로젝트의 TypeScript 설정

이 프로젝트는 **TypeScript 5.9.3** 을 쓰고, 루트 `tsconfig.base.json`이 전 프로젝트의 공통 기준이고, 각 앱이 자기 `tsconfig.json`에서 이를 상속합니다.

주요 설정(대략):

```jsonc
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "strict": true,             // 엄격 모드
    "jsx": "react-jsx",
    "moduleResolution": "bundler",
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true
  }
}
```

가장 중요한 것은 `"strict": true`. 이 하나로 TypeScript의 거의 모든 엄격 검사가 켜집니다. **"null 체크, 암묵적 any 금지, 함수 인자 엄격 검사"** 등.

> 📝 **비개발자용 용어 정리**  
> - **컴파일 옵션(compiler options)**: "TS를 JS로 번역할 때의 규칙들"을 담은 설정.  
> - **target**: "변환 결과물의 JavaScript 버전" — `ES2022`면 2022년 브라우저 표준.  
> - **module**: "파일들이 서로를 불러오는 방식(import 문법)" 규격.  
> - **jsx**: "`<h1>` 같은 JSX 문법을 어떻게 번역할지" 규칙.

---

## 5. 타입의 기초 문법 (최소 생존 키트)

### 5.1 기본 타입

```ts
let n: number = 1;
let s: string = 'hi';
let b: boolean = true;
let arr: number[] = [1, 2, 3];
let pair: [string, number] = ['age', 30];    // 튜플
let nothing: null = null;
let missing: undefined = undefined;
```

### 5.2 객체 타입과 인터페이스

```ts
type User = {
  id: string;
  email: string;
  displayName: string;
  createdAt: Date;
};

// 또는 interface
interface User {
  id: string;
  email: string;
}
```

`type`과 `interface`는 거의 같지만 `interface`는 상속·병합이 가능하고, `type`은 유니온/인터섹션이 자유롭다는 차이가 있습니다. 실무에서는 **둘 다 섞어 써도 무방**.

### 5.3 유니온과 인터섹션

```ts
type Status = 'pending' | 'success' | 'error';   // 유니온
type AdminUser = User & { role: 'admin' };       // 인터섹션
```

### 5.4 함수 타입

```ts
function add(a: number, b: number): number {
  return a + b;
}

const greet = (name: string): string => `Hello, ${name}`;
```

### 5.5 제네릭(Generics)

"타입을 인자로 받는" 도구. 재사용 가능한 코드에 필수.

```ts
function first<T>(arr: T[]): T | undefined {
  return arr[0];
}

first([1, 2, 3]);        // T = number, 반환 number | undefined
first(['a', 'b']);       // T = string, 반환 string | undefined
```

React에서 자주 만납니다: `useState<User | null>(null)`.

### 5.6 유틸리티 타입

TypeScript 표준에 내장된 변형 도구들.

```ts
Partial<User>       // 모든 필드 옵션
Required<User>      // 모든 필드 필수
Pick<User, 'id'>    // id 필드만
Omit<User, 'id'>    // id 빼고
Readonly<User>      // 수정 금지
Record<string, number>  // {key: value} 맵
```

모르면 AI가 추천해 줄 것입니다. 감만 알아두면 됩니다.

---

## 6. 이 프로젝트의 타입 사용 패턴

### 6.1 API 응답 타입

백엔드가 반환하는 JSON을 프런트가 타입으로 받습니다. 현재는 수작업으로 정의하지만, 장기적으로는 `packages/contracts`에서 **OpenAPI 스키마로 자동 생성** 하는 것이 목표입니다.

```ts
// apps/web/src/platform/auth/auth-api.ts
interface LoginResponse {
  userId: string;
  sessionId: string;
  displayName: string;
}

async function login(email: string, password: string): Promise<LoginResponse> {
  // ...
}
```

### 6.2 컴포넌트 Props

React 컴포넌트가 받는 속성을 타입으로 선언.

```tsx
interface ButtonProps {
  label: string;
  variant?: 'primary' | 'secondary';
  onClick: () => void;
}

function Button({ label, variant = 'primary', onClick }: ButtonProps) {
  return <button className={variant} onClick={onClick}>{label}</button>;
}
```

이 타입 덕분에 **잘못된 prop을 주면 빨간 줄이 뜹니다**.

### 6.3 도메인 엔티티

```ts
// apps/web/src/app-modules/pms/api/pms-api.ts (가상)
export type IssueStatus = 'todo' | 'doing' | 'review' | 'done';

export interface Issue {
  id: string;
  title: string;
  status: IssueStatus;
  assigneeId: string | null;
  milestoneId: string | null;
  createdAt: string;
}
```

---

## 7. 엄격 모드의 핵심 규칙 3가지

초보자가 가장 자주 부딪히는 것들.

### 7.1 `strictNullChecks`

```ts
const user: User | null = findUser(id);
console.log(user.email);          // ❌ user가 null일 수도
console.log(user?.email);         // ✅ 옵셔널 체이닝
if (user) console.log(user.email); // ✅ 내로잉
```

### 7.2 `noImplicitAny`

```ts
function process(data) { ... }      // ❌ data의 타입이 없다
function process(data: unknown) { ... }  // ✅
```

`any`는 "타입 검사를 끄는 탈출구"이지만, 쓰는 순간 이 위치의 안전망이 사라집니다. 꼭 써야 한다면 **`unknown`** 을 대신 쓰고 필요한 곳에서 좁혀 내려갑니다.

### 7.3 함수 호환성

```ts
type Handler = (e: Event) => void;
const h: Handler = (e: MouseEvent) => { ... };  // ❌ MouseEvent는 Event보다 좁다
```

이런 규칙들은 당황스럽지만 **언젠가 터질 버그를 미리 잡는** 것입니다. AI에게 에러 메시지를 그대로 보여주면 바로 해법이 옵니다.

---

## 8. 에러 메시지 읽는 법

TypeScript의 에러 메시지는 초보에게 **난해하게** 보일 수 있습니다. 팁:

- 에러의 **첫 줄**만 읽고, 거기에 나오는 두 타입의 이름을 살핀다.
- `Type 'X' is not assignable to type 'Y'.` → "X는 Y가 요구하는 형태가 아니다."
- `Property 'z' does not exist on type 'X'.` → "X에는 z라는 필드가 없다."
- `Argument of type 'X' is not assignable to parameter of type 'Y'.` → "인자 X를 넣었는데 매개변수 Y를 기대했다."

해결이 막히면 **에러 메시지 + 관련 코드 스니펫**을 AI에게 통째로 복사해 붙여넣으면 90%는 해결됩니다.

---

## 8.5 🛠️ 5분 실습 — 타입 실수를 눈으로 보기

1. 사용 중인 코드 에디터에서 `apps/web/src/app-modules/` 아무 `.ts` 파일을 연다.
2. 임의의 변수 선언 아래에 `const x: number = "hello";` 을 한 줄 적어 본다.
3. **저장도 하기 전에** 편집기가 빨간 밑줄을 그어 "Type 'string' is not assignable to type 'number'" 메시지를 띄우는 것 확인.
4. 같은 줄의 타입 주석을 지우고 `const x = "hello";` 로 바꾸면 에러가 사라진다 — 이것이 **타입 추론(type inference — 문맥에서 자동으로 타입을 유추)**.
5. 원복.

이 실습으로 "**타입은 실행 전 단계에서 잡힌다**" 는 감각을 얻을 수 있습니다.

---

## 9. TypeScript 너머 — 파이프라인에서의 위치

우리 프로젝트에서 TypeScript가 실행되는 지점들:

1. **에디터(IDE)**: 쓰는 중에 실시간 검사.
2. **Vite 개발 서버**: 빠른 리로드, 타입은 `vite-plugin-dts` 혹은 `tsc --noEmit`로 백그라운드 검사.
3. **빌드**: `vite build` 시 트랜스파일(속도 우선, 타입 오류는 별도 단계로).
4. **CI**: PR 체크 시 `tsc --noEmit` 로 엄격 검사.
5. **런타임**: 타입은 사라지고 순수 JavaScript만 브라우저에서 실행.

---

## 10. 대안과 비교

| 언어/도구 | 비개발자도 알 만한 특징 | 우리와의 비교 |
|---|---|---|
| **TypeScript** | 문법은 JS와 거의 같고 타입만 얹음. **업계 사실상 표준**. | 우리 선택 |
| **Flow** (Meta) | TS와 유사하지만 **생태계가 작고 도구 지원이 약함**. | 2015년엔 라이벌, 지금은 사실상 밀려남. |
| **JSDoc + tsc** | JS 파일 **주석으로만 타입** 표기. 컴파일 단계 불필요. | 작은 라이브러리나 레거시 JS 점진 전환에 유효. |
| **JavaScript(순수)** | 아예 타입이 없음 — **자유롭지만 대규모엔 위험**. | 스크립트·프로토타입에는 적합하지만, 우리 규모에는 권장하지 않음. |
| **ReScript, Elm** | 함수형 전통 언어. **문법이 낯설고 학습 곡선이 가파름**. | 생태계 작아 AI 지원도 약함. |

TypeScript는 현대 웹 생태계에서 매우 널리 쓰입니다. 학습 투자 가치가 크고, 타입이 명확할수록 사람과 AI 도구 모두 코드를 더 안전하게 수정할 수 있습니다.

---

## 10.5 "이 기술을 고른 이유와 대안" — 비개발자 관점 보강

**고른 이유 (비개발자 언어로)**:

1. **"타자 치는 중에 실수가 발견된다"** — 컴파일/배포까지 안 가고 편집기 단계에서 즉시 안내.
2. **"문서를 따로 쓸 일이 절반으로 준다"** — 타입 선언이 곧 명세. 신규 입사자가 파일만 봐도 함수 사용법을 이해.
3. **"AI 코딩 도구 정확도가 가장 높다"** — LLM이 타입을 힌트로 써서 올바른 호출을 생성.
4. **"리팩터링(Refactoring, 동작을 유지하며 구조를 개선)의 두려움이 줄어든다"** — 이름 바꾸기·경로 이동을 안전하게 자동화.

**대안을 비개발자 언어로 재진술**:

- Flow: "페이스북이 밀었지만 업계가 따라주지 않음" — 생태계 축소로 장기 유지보수 리스크가 커진다.
- JSDoc + tsc: "주석으로만 타입 표기" — **경량이라 도구 의존을 피하고 싶을 때** 유용. 대규모엔 한계.
- 순수 JS: "타입 검증 없이 개발한다" — **소규모 스크립트·프로토타입**에는 여전히 적합.
- ReScript/Elm: "함수형 중심 생태계" — **학습 곡선과 팀 전파 비용**이 높아 AX TF 같은 업무 도메인 팀엔 부담.

---

## 10.7 🏢 신규 입사자의 첫 PR 풍경

**상황:** AX TF에 합류한 신규 인턴이 "회의실 목록 화면의 정렬 기능" 수정을 맡았다.

1. 인턴은 `apps/web/src/app-modules/meeting/`의 API 함수 시그니처만 봐도 **반환 타입(`RoomListResponse`)** 에서 정렬 가능 필드를 바로 파악한다.
2. 정렬 파라미터를 추가하려고 해당 함수에 `sort: 'name' | 'capacity'` 인자를 넣자마자 **호출하는 모든 화면에서 빨간 밑줄** — "어, sort 인자가 필요한데 안 넣었네?"
3. 인턴은 그 곳들을 돌며 필수 인자를 채우고, 전체 타입이 맞춰진 순간 **앱은 컴파일 성공**.
4. 리뷰어는 타입 선언만 봐도 **변경 의도**를 이해. 문서 없이도 의사소통이 됨.

이 시나리오는 **"타입 = 최신 계약 문서 + 실수 방지 도구"** 라는 개념을 보여 줍니다.

---

## 11. 핵심 요약

- TypeScript = JS + 타입. 런타임엔 사라지지만 **개발 경험·안정성**을 극대화.
- `strict: true` 하나가 대부분의 엄격 검사를 켠다.
- 기본 문법 6가지: 타입/객체/유니온/함수/제네릭/유틸리티.
- 이 프로젝트는 **프런트 전반 + 일부 노드 도구** 에 TS를 사용. 백엔드(Python)는 Pydantic이 같은 역할.
- 에러 메시지 읽기 + AI 질문이 초보의 가장 강력한 조합.
