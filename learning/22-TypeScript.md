# 22. TypeScript — 타입이라는 안전망

> **한 줄 요약.** TypeScript는 JavaScript에 **"이 값이 어떤 형태여야 한다"는 약속(타입)**을 더한 언어다. 이 약속이 **코드 편집기가 실시간으로 틀린 곳을 알려주는 마법**을 가능하게 한다.

---

## 1. JavaScript의 태생적 고민

JavaScript는 1995년 10일 만에 만들어진 언어입니다(놀랍게도 사실). 당시에는 "웹 페이지에 뭔가 반짝이는 기능 넣는 용도"였기에 **타입을 엄격히 검사할 이유가 없었습니다.**

```js
let x = 3;
x = 'hello';     // 에러 없음
x = [1, 2, 3];   // 에러 없음
```

이런 유연함은 작은 스크립트엔 편리했지만, **수십만 줄짜리 앱** 으로 자라자 악몽이 됐습니다. 함수가 어떤 값을 받을지, 어떤 값을 반환할지 **실행하기 전에 알 수 없기** 때문에 런타임 오류가 폭발합니다.

---

## 2. TypeScript의 등장

2012년 Microsoft가 발표했습니다. 철학은 명료합니다.

> **"자바스크립트에 타입 주석을 붙이고, 그것을 컴파일 시점에 검사한다."**

TypeScript는 결국 **JavaScript로 번역(트랜스파일)** 되어 브라우저에서 실행됩니다. 타입 정보는 빌드 시점에만 사용되고, 런타임에는 사라집니다.

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

## 4. 이 프로젝트의 TypeScript 설정

루트 `tsconfig.base.json`이 전 프로젝트의 공통 기준이고, 각 앱이 자기 `tsconfig.json`에서 이를 상속합니다.

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

"타입을 인자처럼 받는" 도구. 재사용 가능한 코드에 필수.

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
// apps/web/src/domains/auth/api/auth-api.ts
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
// apps/web/src/domains/pms/types.ts (가상)
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

TypeScript의 에러 메시지는 초보에게 **암호** 처럼 보입니다. 팁:

- 에러의 **첫 줄**만 읽고, 거기에 나오는 두 타입의 이름을 살핀다.
- `Type 'X' is not assignable to type 'Y'.` → "X는 Y가 요구하는 형태가 아니다."
- `Property 'z' does not exist on type 'X'.` → "X에는 z라는 필드가 없다."
- `Argument of type 'X' is not assignable to parameter of type 'Y'.` → "인자 X를 넣었는데 매개변수 Y를 기대했다."

해결이 막히면 **에러 메시지 + 관련 코드 스니펫**을 AI에게 통째로 복사해 붙여넣으면 90%는 해결됩니다.

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

| 언어/도구 | 특징 | 우리와의 비교 |
|---|---|---|
| **TypeScript** | JS의 정적 타입 확장 | 우리 선택 |
| **Flow** (Meta) | TS와 비슷. 생태계 작음. | 2015년엔 라이벌, 지금은 밀림. |
| **JSDoc + tsc** | JS 파일에 주석으로 타입 | 작은 프로젝트나 라이브러리에 유효. |
| **JavaScript(순수)** | 타입 없음 | 대규모엔 비추. |
| **ReScript, Elm** | 함수형, 강한 타입 | 생태계 작음. |

TypeScript는 2025년 기준 **웹 생태계의 사실상 표준**. 학습 투자 가치가 가장 큽니다.

---

## 11. 핵심 요약

- TypeScript = JS + 타입. 런타임엔 사라지지만 **개발 경험·안정성**을 극대화.
- `strict: true` 하나가 대부분의 엄격 검사를 켠다.
- 기본 문법 6가지: 타입/객체/유니온/함수/제네릭/유틸리티.
- 이 프로젝트는 **프런트 전반 + 일부 노드 도구** 에 TS를 사용. 백엔드(Python)는 Pydantic이 같은 역할.
- 에러 메시지 읽기 + AI 질문이 초보의 가장 강력한 조합.

---

## 12. 이해도 체크

1. TypeScript가 "런타임에는 사라진다"는 말의 뜻은?
2. `any`를 쓰면 왜 위험한지, 그리고 `unknown`과의 차이는?
3. 제네릭이 없다면 `first` 함수를 어떻게 써야 했을지 상상해 보세요.
4. `strictNullChecks`가 잡아주는 전형적 버그 예를 하나 들어 보세요.
5. 프런트(TS)와 백(Python)이 타입을 **공유** 하게 만드려면 어떤 방법이 있을까요? (힌트: OpenAPI)
