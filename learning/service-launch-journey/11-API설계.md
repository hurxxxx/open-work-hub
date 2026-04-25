# 11. API 설계 — 프론트와 백을 잇는 계약

> **한 줄 요약.** API 는 **프론트와 백 사이의 계약서**다. 이 계약이 명확하면 양쪽이 병렬로 작업하고, 흐리면 양쪽 다 멈춘다.

---

## 들어가며

화면이 그려지고 데이터 모델이 잡혔다면, 이제 **그 데이터를 화면이 어떻게 가져갈지**를 결정합니다. 프론트엔드는 사용자에게 보이는 화면을, 백엔드는 데이터를 다루는 서버를 만듭니다. 두 영역이 서로 데이터를 주고받는 통로가 **API(Application Programming Interface)** 입니다.

API 설계가 흐리면 자주 일어나는 일:

- 프론트가 백에 "이런 데이터 줄 수 있어요?" 라고 묻고 답을 기다린다. 그 사이 작업 멈춤.
- 백이 만든 응답 형태가 프론트가 기대한 것과 달라서 양쪽 다 다시 작업.
- 인증·에러 처리 같은 공통 규칙이 엔드포인트마다 달라서 디버깅 지옥.

API 설계의 진짜 목적은 **양쪽이 합의한 계약을 문서로 남기는 것** 입니다. 계약이 명시되면 프론트·백이 병렬로 일하고, 한쪽이 변경되어도 다른 쪽이 안전합니다.

이 레슨을 다 읽으면:

- REST API 의 기본 원칙(자원·메서드·상태 코드)을 안다.
- 화면·데이터 모델로부터 엔드포인트 목록을 도출할 수 있다.
- 요청·응답의 표준 모양을 잡을 수 있다.
- 인증·에러·페이지네이션의 공통 규칙을 정한다.
- OpenAPI(Swagger) 로 문서화하는 가벼운 방법을 안다.

---

## 1. 핵심 개념 — REST API 의 기본

### 1.1 자원 (Resource)

REST 의 핵심은 **자원(resource) 중심 사고** 입니다. 모든 것을 자원으로 보고, URL 로 그 자원을 가리킵니다.

| 자원 | URL |
|---|---|
| 사용자 모음 | `/users` |
| 특정 사용자 | `/users/123` |
| 그 사용자의 글 모음 | `/users/123/posts` |
| 특정 글 | `/posts/456` |

자원은 **명사** 입니다. 동사가 아닙니다. ❌ `/getUsers` ❌ `/createPost` ✅ `/users` ✅ `/posts`.

### 1.2 HTTP 메서드 — 동사는 메서드가 표현

자원에 무엇을 할지는 HTTP 메서드로 표현합니다.

| 메서드 | 의미 | 예시 |
|---|---|---|
| **GET** | 조회 | `GET /users/123` (123번 사용자 조회) |
| **POST** | 생성 | `POST /users` (새 사용자 생성) |
| **PUT** | 전체 교체 | `PUT /users/123` (123번 사용자 전체 교체) |
| **PATCH** | 부분 수정 | `PATCH /users/123` (일부 필드만 수정) |
| **DELETE** | 삭제 | `DELETE /users/123` |

URL + 메서드 조합으로 거의 모든 동작이 표현됩니다.

### 1.3 상태 코드 (Status Code)

응답에는 HTTP 상태 코드가 붙습니다. 자주 쓰는 것들:

| 코드 | 의미 | 언제 |
|---|---|---|
| **200 OK** | 성공 | GET·PATCH·PUT·DELETE 성공 |
| **201 Created** | 생성됨 | POST 로 자원 생성 성공 |
| **204 No Content** | 성공, 응답 본문 없음 | DELETE 성공 |
| **400 Bad Request** | 잘못된 요청 | 입력 검증 실패 |
| **401 Unauthorized** | 인증 안됨 | 로그인 필요 |
| **403 Forbidden** | 권한 없음 | 로그인했지만 권한 부족 |
| **404 Not Found** | 자원 없음 | 존재하지 않는 ID |
| **409 Conflict** | 충돌 | 중복 이메일 가입 |
| **422 Unprocessable Entity** | 의미적 검증 실패 | 형식은 맞지만 비즈니스 규칙 위반 |
| **429 Too Many Requests** | 과도한 요청 | rate limit 초과 |
| **500 Internal Server Error** | 서버 에러 | 백엔드의 버그 |

상태 코드를 정확히 쓰면 프론트가 응답 본문을 보지 않고도 결과를 판단할 수 있습니다.

### 1.4 요청·응답 본문 — JSON

REST API의 본문은 거의 항상 **JSON** 입니다.

요청 예시:

```http
POST /transactions HTTP/1.1
Content-Type: application/json
Authorization: Bearer eyJhbGc...

{
  "card_id": 12,
  "amount": 4500,
  "merchant": "스타벅스 강남점",
  "transacted_at": "2026-04-25T14:32:00Z"
}
```

응답 예시:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": 789,
  "card_id": 12,
  "amount": 4500,
  "merchant": "스타벅스 강남점",
  "category_id": null,
  "transacted_at": "2026-04-25T14:32:00Z",
  "created_at": "2026-04-25T14:32:15Z"
}
```

---

## 2. 실무 흐름 — 엔드포인트 도출 4단계

### 단계 1. 화면별로 필요한 데이터 정리 (15분)

각 화면에서 **무엇을 보여주고 무엇을 받아야 하는지** 정리합니다.

예시 — 부부 가계부 앱:

| 화면 | 보여줄 데이터 | 받을 입력 |
|---|---|---|
| 정산 화면 | 월별 거래 합계 + 카테고리별 분류 | 조회 월 |
| 거래 상세 | 한 거래의 모든 필드 | 거래 id |
| 카드 등록 | (없음) | 카드 정보 |
| 초대 보내기 | 초대 코드 | (없음) |
| 초대 수락 | 부부 그룹 정보 | 초대 코드 |

### 단계 2. 자원 후보 식별 (10분)

위 표에서 명사를 뽑아 자원 후보를 만듭니다.

```
users
couples
couple_members
invitations
cards
transactions
categories
```

레슨 10에서 도출한 테이블과 거의 같습니다 (의도된 것). 각 자원에 대해 표준 CRUD를 적용.

### 단계 3. 엔드포인트 카탈로그 작성 (30분)

각 자원에 대해 필요한 엔드포인트를 적습니다.

**users**

| 메서드 | URL | 설명 |
|---|---|---|
| POST | `/auth/signup` | 회원가입 |
| POST | `/auth/login` | 로그인 |
| GET | `/users/me` | 내 정보 |
| PATCH | `/users/me` | 내 정보 수정 |

**couples**

| 메서드 | URL | 설명 |
|---|---|---|
| POST | `/couples` | 부부 그룹 생성 |
| GET | `/couples/me` | 내가 속한 그룹 |

**invitations**

| 메서드 | URL | 설명 |
|---|---|---|
| POST | `/invitations` | 초대 코드 생성 |
| POST | `/invitations/accept` | 초대 수락 |

**cards**

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/cards` | 내 카드 목록 |
| POST | `/cards` | 카드 등록 |
| DELETE | `/cards/:id` | 카드 삭제 |

**transactions**

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/transactions` | 거래 목록 (필터 가능) |
| GET | `/transactions/:id` | 거래 상세 |
| PATCH | `/transactions/:id` | 거래 카테고리 수정 |

**categories**

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/categories` | 카테고리 목록 |
| POST | `/categories` | 새 카테고리 생성 |
| PATCH | `/categories/:id` | 수정 |
| DELETE | `/categories/:id` | 삭제 |

**dashboard / 정산**

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/dashboard/summary?month=2026-04` | 월별 요약 |

### 단계 4. 요청·응답 스키마 작성 (30분 ~ 1시간)

각 엔드포인트의 요청·응답 모양을 구체적으로 적습니다.

예시 — `POST /transactions/:id` 의 PATCH:

**요청:**
```json
PATCH /transactions/789
{
  "category_id": 5
}
```

**응답 (성공):**
```json
HTTP/1.1 200 OK
{
  "id": 789,
  "card_id": 12,
  "amount": 4500,
  "merchant": "스타벅스 강남점",
  "category_id": 5,
  "transacted_at": "2026-04-25T14:32:00Z",
  "created_at": "2026-04-25T14:32:15Z"
}
```

**응답 (실패):**
```json
HTTP/1.1 404 Not Found
{
  "error": {
    "code": "TRANSACTION_NOT_FOUND",
    "message": "해당 거래를 찾을 수 없습니다."
  }
}
```

이 스키마가 **계약** 입니다. 프론트는 이 모양으로 요청을 보내고, 백은 이 모양으로 응답을 보냅니다.

---

## 3. 공통 규칙 — 한 번 정해 모든 엔드포인트에 적용

각 엔드포인트마다 다른 규칙을 쓰면 양쪽 다 혼란스럽습니다. 다음 항목들을 **출시 전에 한 번 정해 두면** 이후의 모든 엔드포인트가 일관됩니다.

### 3.1 인증 (Authentication)

대부분의 엔드포인트는 로그인된 사용자만 호출 가능. 인증 방식 선택:

| 방식 | 적합한 상황 |
|---|---|
| **Session Cookie** | 웹만 쓰는 단순 서비스 |
| **JWT Bearer Token** | 모바일·SPA·다중 플랫폼 |
| **OAuth (소셜 로그인)** | 카카오·구글·애플 로그인 |

JWT 라면 모든 요청에 다음 헤더가 붙습니다.

```http
Authorization: Bearer <token>
```

자세한 내용은 레슨 17 (인증).

### 3.2 에러 응답 형식

모든 에러 응답은 같은 모양으로:

```json
{
  "error": {
    "code": "ERROR_CODE_IN_SCREAMING_SNAKE",
    "message": "사용자에게 보여줄 메시지",
    "details": { "field": "specific_info" }
  }
}
```

`code` 는 프론트가 분기하는 데 쓰고, `message` 는 사용자에게 보여줍니다.

### 3.3 페이지네이션 (Pagination)

리스트 응답은 거의 항상 페이지네이션이 필요합니다.

**오프셋 기반:**
```
GET /transactions?page=1&per_page=20
```

**커서 기반 (대규모 서비스에 유리):**
```
GET /transactions?cursor=eyJ...&limit=20
```

응답:
```json
{
  "data": [ ... 20개 거래 ... ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 153,
    "has_next": true
  }
}
```

### 3.4 필터·정렬

쿼리 파라미터로 표현:

```
GET /transactions?card_id=12&category_id=5&from=2026-04-01&to=2026-04-30&sort=-transacted_at
```

`sort=-transacted_at` 의 `-` 는 내림차순 표시.

### 3.5 시간 형식

날짜·시간은 항상 **ISO 8601 + UTC**:

```
2026-04-25T14:32:00Z
```

### 3.6 명명 규칙

JSON 키는 한 가지로 통일:

| 컨벤션 | 예시 |
|---|---|
| `snake_case` | `user_id`, `created_at` |
| `camelCase` | `userId`, `createdAt` |

처음 정한 것을 끝까지 유지. 섞이면 디버깅이 괴롭습니다.

### 3.7 버전 관리

API는 시간이 지나며 변합니다. 버전을 URL 또는 헤더에 표시:

```
/v1/users/123     ← URL 버전
/v2/users/123
```

처음에는 `/v1` 만 있어도 됩니다. 깨는 변경(breaking change) 이 생기면 `/v2` 추가.

---

## 4. API 문서화 — OpenAPI(Swagger)

API 설계서를 **OpenAPI** 명세로 적으면 다음을 자동으로 얻습니다.

- **상호작용 가능한 문서** (Swagger UI 로 직접 호출 테스트).
- **클라이언트 코드 자동 생성** (TypeScript·Dart 등).
- **서버 코드 자동 생성** 또는 검증.

### 4.1 OpenAPI 의 모양

YAML 형식 예시:

```yaml
openapi: 3.0.0
info:
  title: Couple Budget API
  version: 1.0.0

paths:
  /transactions:
    get:
      summary: 거래 목록
      parameters:
        - name: card_id
          in: query
          schema: { type: integer }
        - name: from
          in: query
          schema: { type: string, format: date }
      responses:
        '200':
          description: 성공
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TransactionList'

components:
  schemas:
    Transaction:
      type: object
      properties:
        id: { type: integer }
        amount: { type: number }
        merchant: { type: string }
        transacted_at: { type: string, format: date-time }
```

### 4.2 무료 도구

- **Swagger UI** — 명세 파일을 인터랙티브 문서로.
- **Redoc** — 더 정리된 문서 디자인.
- **Postman / Insomnia** — API 테스트 도구. 명세 임포트 가능.
- **Stoplight, Apiary** — GUI로 OpenAPI 작성.

### 4.3 가볍게 시작하기

처음에는 위 같은 정식 OpenAPI YAML 까지 안 가도 됩니다. **마크다운 한 페이지에 엔드포인트 카탈로그 + 요청·응답 예시**만 적어도 충분합니다. 출시 후 안정화되면 OpenAPI 로 옮겨도 늦지 않습니다.

---

## 5. REST 가 아닌 선택지

REST 외에 다른 API 스타일도 있습니다. 처음 만드는 분에게는 REST 가 거의 항상 정답이지만, 알아 두면 도움이 됩니다.

| 스타일 | 무엇 | 적합한 상황 |
|---|---|---|
| **REST** | URL = 자원, 메서드 = 동작 | 거의 모든 경우 |
| **GraphQL** | 클라이언트가 원하는 필드만 선언적 조회 | 복잡한 화면, 여러 자원 한 번에 |
| **RPC / gRPC** | 함수 호출 형태 | 내부 서비스 간 통신, 고성능 |
| **WebSocket** | 양방향 실시간 통신 | 채팅, 알림, 협업 |
| **Server-Sent Events (SSE)** | 서버 → 클라이언트 단방향 스트림 | 실시간 알림, AI 응답 스트리밍 |

처음 출시할 서비스라면 **REST + 필요한 부분만 WebSocket/SSE** 가 단순합니다.

---

## 6. 자주 빠지는 함정

### 함정 1. URL 에 동사를 쓴다

`/getUsers`, `/deletePost` 같은 URL. REST 의 핵심을 놓침. 명사 + 메서드로 표현하세요.

### 함정 2. 모든 응답을 200 으로

성공·실패 모두 200으로 보내고 본문에서 구분하는 패턴. 프론트가 매번 본문을 검사해야 합니다. **상태 코드를 정확히** 쓰세요.

### 함정 3. 에러 메시지에 기술 용어

"SQLException at line 42 of UserRepository" — 사용자에게 보일 수 있는 에러는 **사람이 읽을 수 있는 메시지** 로. 자세한 내용은 로그로.

### 함정 4. 페이지네이션 없는 리스트

"일단 처음에는 사용자가 적으니까" 라고 페이지네이션을 빼면, 나중에 추가하기가 어색해집니다. **처음부터** 표준 페이지네이션을 적용하세요.

### 함정 5. 같은 데이터를 여러 형태로

`/users/123` 의 응답과 `/users` 의 응답에 들어가는 사용자 객체의 모양이 다른 경우. 양쪽이 같은 스키마(`User`)를 공유하도록.

### 함정 6. N+1 호출 강요

리스트 화면에서 각 항목마다 별도 호출이 필요한 설계. 100개 항목이면 100번 호출. **리스트 응답에 필요한 필드를 한 번에 포함** 시키거나, 관련 자원을 같이 가져오는 옵션 (`?include=card,category`) 제공.

### 함정 7. 응답 스키마를 마구 변경

한번 출시된 API의 응답 스키마는 함부로 바꾸면 안 됩니다 (앱 사용자는 업데이트 안 한 구버전을 쓰고 있을 수 있음). 변경 시 **버전 분리** 또는 **하위 호환성 유지**.

### 함정 8. 인증·CORS 를 나중에 챙긴다

처음 개발 환경에서는 인증·CORS 없이 잘 돌아가다가 운영 환경에서 깨지는 일. **첫 엔드포인트부터** 인증·CORS 를 적용한 채로 만드세요.

---

## 7. 한 셜 더

### 7.1 GraphQL 한 줄 설명

REST 가 "자원마다 정해진 응답" 이라면, GraphQL 은 "클라이언트가 원하는 필드만 골라서 가져가기" 입니다.

```graphql
query {
  user(id: 123) {
    name
    email
    posts(limit: 5) {
      title
      created_at
    }
  }
}
```

화면이 매우 다양하거나, 한 화면에 여러 자원의 일부 필드만 필요할 때 유리합니다. 단, 학습 곡선이 있고 캐싱·보안 처리가 더 까다롭습니다.

### 7.2 Idempotency — 같은 요청은 같은 결과

POST 요청은 보통 매번 다른 자원을 만듭니다 (멱등성 없음). 하지만 결제 같이 중복되면 안 되는 작업은 **Idempotency-Key** 헤더로 멱등성을 보장합니다.

```http
POST /payments
Idempotency-Key: a1b2c3d4-...

{ "amount": 10000 }
```

같은 키로 두 번 호출되면 한 번만 처리. 결제 시스템에서는 거의 필수.

### 7.3 Rate Limiting

악의적·실수로 인한 과도한 호출을 막기 위해 **rate limit** 을 적용. 응답 헤더에 표시:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1714050000
```

초과 시 `429 Too Many Requests`.

### 7.4 추가 키워드

- **HATEOAS** — 응답에 다음 행동 링크를 포함하는 REST 의 고급 형태.
- **JSON:API** — 표준화된 JSON 응답 명세.
- **gRPC + Protobuf** — 고성능 내부 통신.
- **WebHook** — 서버 → 사용자 서버로 이벤트 알림 (반대 방향 API).

---

## 마치며

오늘 한 일:

- REST 의 **자원·메서드·상태 코드** 기본.
- **엔드포인트 도출 4단계** (화면 데이터 → 자원 후보 → 카탈로그 → 스키마).
- **공통 규칙 7가지** (인증·에러·페이지네이션·필터·시간·명명·버전).
- **OpenAPI** 로 가볍게 문서화 시작하는 법.
- 함정 8가지를 미리 점검.

다음 레슨 [`12. 디자인 시스템과 비주얼 설계`](./12-디자인시스템.md) 에서는 회색 와이어프레임에 색·타이포·컴포넌트를 입혀 **실제 사용자가 보는 화면**으로 옮기는 작업을 살핍니다. Part 3 (설계) 의 마지막 레슨입니다.

다음 페이지에서 만나요.
