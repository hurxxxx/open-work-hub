# 14. 백엔드 API 개발 — CRUD부터 로직까지

> **한 줄 요약.** 백엔드는 "API 응답을 만드는 일" 이 아니라 **"비즈니스 규칙을 안전하게 데이터에 적용하는 일"** 이다. 라우팅·검증·로직·DB·응답 5단계가 한 흐름으로 흘러야 한다.

---

## 들어가며

프론트엔드가 사용자에게 보이는 화면이라면, 백엔드는 그 화면 뒤에서 **데이터·규칙·외부 시스템**을 다루는 영역입니다. 사용자에게 직접 보이지는 않지만, 서비스의 안정성·보안·정합성이 모두 여기서 결정됩니다.

처음 만드는 분이 백엔드에서 자주 막히는 자리:

- "API 만들기" 가 무엇을 하는 일인지 흐릿함.
- 어떤 언어·프레임워크를 골라야 할지 막막함.
- 데이터 검증·인증·에러 처리가 한 코드에 뒤섞여 복잡.
- 비즈니스 로직을 어디에 두어야 하는지 헷갈림.

이 레슨은 백엔드의 **큰 그림과 한 요청의 흐름**을 잡습니다.

이 레슨을 다 읽으면:

- 한 API 요청이 들어오는 5단계 흐름을 안다.
- 백엔드 언어·프레임워크 옵션을 비교할 수 있다.
- CRUD 와 비즈니스 로직을 분리하는 폴더 구조를 잡을 수 있다.
- 검증·인증·에러 처리를 한 곳으로 모으는 패턴을 안다.
- 자주 빠지는 함정(N+1·시간대·트랜잭션)을 피할 수 있다.

---

## 1. 핵심 개념 — 한 요청의 5단계 흐름

API 요청 한 건이 들어와서 응답이 나가기까지의 흐름은 거의 항상 다음 5단계입니다.

```
요청 ─► [1] 라우팅
       ─► [2] 검증·인증
       ─► [3] 비즈니스 로직
       ─► [4] DB 호출
       ─► [5] 응답 직렬화
       ─► 응답
```

### 단계 1. 라우팅 (Routing)

URL + HTTP 메서드를 보고 **어느 핸들러 함수가 처리할지** 정합니다.

```python
# FastAPI 예시
@router.post("/transactions")
def create_transaction(...):
    ...
```

```ts
// Express 예시
app.post('/transactions', (req, res) => { ... });
```

### 단계 2. 검증·인증 (Validation & Auth)

요청 본문이 기대한 형식인가? 헤더의 토큰이 유효한가? 이 사용자가 이 작업을 할 권한이 있는가?

```python
# FastAPI + Pydantic
class CreateTransactionInput(BaseModel):
    card_id: int
    amount: Decimal
    merchant: str
    transacted_at: datetime

def create_transaction(body: CreateTransactionInput, user: User = Depends(current_user)):
    ...
```

검증과 인증이 통과하지 못하면 비즈니스 로직까지 가지 않고 즉시 4xx 응답.

### 단계 3. 비즈니스 로직 (Business Logic)

도메인 규칙을 적용. "이 거래의 소유자가 현재 사용자인가", "이미 같은 거래가 있는가", "한 달 한도를 초과하지 않았는가" 등.

이 부분이 백엔드의 **진짜 가치** 입니다. 라우팅·DB 호출은 도구이고, 비즈니스 로직은 우리 서비스의 정체성.

### 단계 4. DB 호출 (Persistence)

검증된 데이터를 데이터베이스에 저장하거나, 데이터를 가져옵니다. ORM 또는 raw SQL.

```python
db_transaction = Transaction(
    user_id=user.id,
    card_id=body.card_id,
    amount=body.amount,
    merchant=body.merchant,
)
session.add(db_transaction)
session.commit()
```

### 단계 5. 응답 직렬화 (Serialization)

DB 객체를 JSON 으로 바꿔서 응답.

```python
return TransactionResponse.from_orm(db_transaction)
```

이 5단계가 매끄럽게 흐르도록 코드를 정리하는 것이 백엔드 개발의 큰 부분입니다.

---

## 2. 언어·프레임워크 — 무엇을 고를까

### 2.1 주요 옵션

| 언어 | 프레임워크 | 특징 |
|---|---|---|
| **TypeScript / Node.js** | Express, Fastify, NestJS, Hono | 프론트와 같은 언어, 풀스택 가능 |
| **Python** | FastAPI, Django, Flask | AI·데이터 작업과 잘 어울림 |
| **Go** | Gin, Fiber, Echo | 고성능, 단일 바이너리 |
| **Rust** | Axum, Actix | 매우 빠름, 학습 곡선 |
| **Java / Kotlin** | Spring Boot | 대기업·금융 표준 |
| **Ruby** | Rails | 빠른 개발, Convention 강함 |
| **C# / .NET** | ASP.NET Core | MS 생태계 |

### 2.2 처음 시작에 무난한 선택

| 상황 | 추천 |
|---|---|
| 프론트와 같은 언어 통일 | TypeScript + NestJS / Hono |
| AI·데이터 처리 강함 | Python + FastAPI |
| 작은 팀·빠른 개발 | Python + FastAPI / Ruby + Rails |
| 고성능 필요 | Go + Gin |
| 대기업·B2B | Java + Spring Boot |

이 코스 본문 예시는 **Python + FastAPI** 를 자주 씁니다. 진입 장벽이 낮고 코드가 짧으며, AI 도구가 만들어 주기에도 자연스럽습니다.

### 2.3 ORM — 데이터베이스 추상화

ORM(Object-Relational Mapping) 은 SQL 대신 객체로 DB 를 다루게 합니다.

| 언어 | 인기 ORM |
|---|---|
| Python | SQLAlchemy, Tortoise, Django ORM |
| TypeScript | Prisma, Drizzle, TypeORM |
| Go | GORM, sqlx |
| Java | Hibernate, JOOQ |
| Ruby | ActiveRecord |

처음에는 ORM 사용 권장. 직접 SQL 보다 빠르고 안전. 단, **복잡한 쿼리는 raw SQL** 이 더 명확할 때도.

---

## 3. 폴더 구조 — 책임 분리

처음 만드는 분이 가장 자주 빠지는 함정이 **모든 코드를 한 파일에 넣는 것** 입니다. 라우팅·검증·로직·DB 호출이 한 함수에 뒤섞이면 작은 변경도 위험합니다.

권장 구조 (Python/FastAPI 기준, 다른 언어도 비슷):

```
app/
├── main.py                ← 진입점
├── domains/
│   ├── transactions/
│   │   ├── router.py     ← 엔드포인트 정의
│   │   ├── schemas.py    ← 요청·응답 스키마
│   │   ├── service.py    ← 비즈니스 로직
│   │   ├── models.py     ← DB 모델
│   │   └── repository.py ← DB 쿼리 (선택)
│   └── auth/
├── core/
│   ├── config.py
│   ├── database.py
│   └── security.py
└── tests/
```

각 도메인이 자기만의 라우터·스키마·서비스를 가집니다. **도메인 한 폴더 안에서 거의 모든 변경이 끝나는 구조**가 좋습니다.

### 3.1 계층의 역할

| 계층 | 책임 |
|---|---|
| **Router** | 라우트 등록, 입출력 형식 정의, 검증·인증 의존성 주입 |
| **Schema** | 요청·응답 모양 정의 (Pydantic·Zod·DTO) |
| **Service** | 비즈니스 로직. DB 모델·외부 API 조합 |
| **Model** | DB 테이블 매핑 (ORM 클래스) |
| **Repository** (선택) | DB 쿼리만 담당. Service 와 분리하면 테스트 용이 |

작은 프로젝트에서는 Repository 없이 Service 가 직접 ORM 호출해도 됩니다. 커질 때 분리.

### 3.2 한 엔드포인트의 코드 예시 (FastAPI)

**router.py:**
```python
@router.post("/transactions", response_model=TransactionResponse)
def create_transaction(
    body: CreateTransactionInput,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    return transaction_service.create(session, user, body)
```

**schemas.py:**
```python
class CreateTransactionInput(BaseModel):
    card_id: int
    amount: Decimal
    merchant: str
    transacted_at: datetime

class TransactionResponse(BaseModel):
    id: int
    card_id: int
    amount: Decimal
    merchant: str
    transacted_at: datetime
    created_at: datetime
```

**service.py:**
```python
def create(session: Session, user: User, body: CreateTransactionInput) -> Transaction:
    card = session.get(Card, body.card_id)
    if card is None or card.user_id != user.id:
        raise HTTPException(404, "card not found")

    transaction = Transaction(
        user_id=user.id,
        card_id=card.id,
        amount=body.amount,
        merchant=body.merchant,
        transacted_at=body.transacted_at,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction
```

각 파일이 한 가지에 집중. 라우터는 라우터, 검증은 스키마, 로직은 서비스.

---

## 4. CRUD — 가장 기본 패턴

자원 하나에 대해 거의 항상 다음 5개 작업이 있습니다.

| 작업 | HTTP | 의미 |
|---|---|---|
| Create | POST `/transactions` | 새 거래 생성 |
| Read (list) | GET `/transactions` | 거래 목록 |
| Read (one) | GET `/transactions/:id` | 한 거래 상세 |
| Update | PATCH `/transactions/:id` | 거래 수정 |
| Delete | DELETE `/transactions/:id` | 거래 삭제 |

이 5개 패턴을 한 번 익히면 다른 자원도 거의 같은 구조로 만들 수 있습니다.

### 4.1 List 의 흔한 옵션

목록 엔드포인트는 거의 항상 다음 옵션이 필요합니다.

- **필터** — `?card_id=12&category_id=5`
- **검색** — `?q=스타벅스`
- **정렬** — `?sort=-transacted_at`
- **페이지네이션** — `?page=1&per_page=20`
- **포함 자원** — `?include=card,category`

이 패턴을 라이브러리화하면 모든 List 엔드포인트가 자동으로 같은 모양을 가집니다.

### 4.2 Update — PATCH 의 부분 업데이트

`PATCH` 는 일부 필드만 수정. nullable 처리에 주의.

```python
class UpdateTransactionInput(BaseModel):
    category_id: Optional[int] = None
    merchant: Optional[str] = None

def update(session, transaction_id, body):
    transaction = session.get(Transaction, transaction_id)
    if body.category_id is not None:
        transaction.category_id = body.category_id
    if body.merchant is not None:
        transaction.merchant = body.merchant
    session.commit()
    return transaction
```

---

## 5. 비즈니스 로직 — 어디에 두는가

비즈니스 로직(business logic)은 **우리 서비스만의 규칙**입니다.

- "한 사용자가 같은 부부 그룹에 두 번 가입할 수 없다"
- "결제 금액은 카드 한도를 초과할 수 없다"
- "탈퇴한 사용자는 새 거래를 만들 수 없다"

### 5.1 비즈니스 로직의 자리

| 자리 | 적합한 경우 | 위험 |
|---|---|---|
| **Router** | 매우 단순한 검사 | 라우터가 비대해짐 |
| **Service** | 대부분의 경우 ✓ | — |
| **Model (ORM)** | 데이터 자체의 규칙 | DB 와 결합 |
| **DB constraint** | 절대 어겨선 안 되는 규칙 | 비즈니스 룰을 DB 에 박는 것 |

가장 흔한 권장은 **Service 에 두기**. 라우터는 입출력만, 모델은 데이터만.

### 5.2 로직을 함수로 작게

큰 로직은 작은 함수들로 쪼갭니다. 각 함수는 한 가지 일.

```python
def can_create_transaction(user, card):
    return card.user_id == user.id and not user.is_suspended

def is_duplicate(session, user, body):
    existing = session.query(Transaction).filter_by(
        user_id=user.id,
        card_id=body.card_id,
        amount=body.amount,
        transacted_at=body.transacted_at,
    ).first()
    return existing is not None

def create(session, user, body):
    card = session.get(Card, body.card_id)
    if not can_create_transaction(user, card):
        raise PermissionError()
    if is_duplicate(session, user, body):
        raise ValueError("duplicate transaction")
    # ... 저장
```

이렇게 분리하면 단위 테스트가 쉬워집니다.

---

## 6. 검증·인증·에러 — 한 곳으로

### 6.1 검증 (Validation)

요청 본문이 형식·범위·필수 항목을 만족하는지. 보통 **스키마 라이브러리** 가 담당.

| 언어 | 라이브러리 |
|---|---|
| Python | Pydantic |
| TypeScript | Zod, Joi, class-validator |
| Go | ozzo-validation, validator |

```python
class CreateTransactionInput(BaseModel):
    amount: Decimal = Field(gt=0, le=100_000_000)
    merchant: str = Field(min_length=1, max_length=255)
```

스키마가 잘못된 입력을 자동으로 거르고 422 응답을 보냄.

### 6.2 인증 (Authentication) & 인가 (Authorization)

- **인증** — "이 요청자가 누구인가". 토큰 검증.
- **인가** — "이 사람이 이 작업을 할 수 있는가". 권한 검사.

미들웨어 또는 의존성 주입 패턴으로 모든 엔드포인트에 일관 적용.

```python
def current_user(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    return verify_token(token)
```

자세한 내용은 레슨 17 (인증).

### 6.3 에러 처리 (Error Handling)

모든 에러를 한 곳에서 잡아 일관된 응답으로 변환.

```python
@app.exception_handler(BusinessError)
def handle_business_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```

엔드포인트 코드는 비즈니스 에러를 던지기만 하면 됩니다.

---

## 7. 자주 빠지는 함정

### 함정 1. 라우터에 모든 코드를 몰아넣는다

```python
# 나쁨
@router.post("/transactions")
def create_transaction(...):
    # 100줄의 검증·로직·DB 호출 ...
```

리팩터링이 어려워지고 테스트도 안 됩니다. **계층 분리** 필수.

### 함정 2. N+1 쿼리

리스트를 가져오면서 각 항목마다 별도 쿼리를 추가로 실행. 100개 항목이면 101번 쿼리.

```python
# 나쁨: 각 transaction마다 card를 추가 조회
for t in transactions:
    print(t.card.nickname)  # ← 매번 SELECT

# 좋음: 한 번에 조인
transactions = session.query(Transaction).options(joinedload(Transaction.card)).all()
```

### 함정 3. 트랜잭션 (DB Transaction) 무시

여러 테이블에 걸친 작업이 중간에 실패하면 데이터 정합성이 깨집니다. **트랜잭션으로 감싸세요**.

```python
with session.begin():
    user.balance -= 1000
    transaction = Transaction(...)
    session.add(transaction)
# 한 번에 커밋. 중간 실패 시 롤백.
```

### 함정 4. 시간대 처리 안 함

서버는 UTC, 사용자는 KST. `datetime.now()` 가 서버 시간대로 흘러가면 사용자 시간이 어긋납니다. **항상 UTC** 로 저장, 표시 시점에 변환.

### 함정 5. 비밀번호·시크릿을 코드에 박는다

```python
# 절대 금지
DATABASE_URL = "postgresql://user:password123@db:5432/app"
```

환경 변수·Secret Manager 사용. `.env` 파일은 git 에 안 올림.

### 함정 6. 모든 응답을 200 으로

성공·실패 모두 200 + `{"success": false}` 같은 패턴. 프론트가 status code 를 못 신뢰. 레슨 11 의 상태 코드 표 참고.

### 함정 7. SQL Injection

직접 문자열로 SQL 을 만들면 입력에 따라 임의 쿼리가 실행될 수 있음.

```python
# 나쁨
session.execute(f"SELECT * FROM users WHERE name = '{name}'")

# 좋음
session.execute("SELECT * FROM users WHERE name = :name", {"name": name})
# ORM 사용 시 자동 처리
```

### 함정 8. 로깅 없이 시작

문제가 생기면 로그가 없어 진단 불가. **시작 단계부터** 구조화된 로깅 (JSON 로그) 도입.

---

## 8. 한 셜 더

### 8.1 비동기 (Async)

I/O 가 많은 백엔드는 비동기로 짜면 처리량이 크게 올라갑니다.

```python
# Sync
def list_transactions():
    return session.query(Transaction).all()

# Async
async def list_transactions():
    return await session.execute(select(Transaction))
```

FastAPI·Hono·Express 모두 비동기를 지원. 단, ORM·드라이버도 비동기 호환이어야.

### 8.2 의존성 주입 (Dependency Injection)

테스트 가능성과 확장성을 위해 의존성을 주입 패턴으로 받음.

```python
def transaction_service(repo: TransactionRepository = Depends()):
    return TransactionService(repo)
```

테스트 시 mock repository 주입 가능.

### 8.3 작업 큐 (Job Queue)

응답 시간이 긴 작업(이메일 발송·이미지 처리·외부 API 호출)은 백그라운드 큐로 보냄.

| 도구 | 언어 |
|---|---|
| Celery | Python |
| BullMQ | Node.js |
| Sidekiq | Ruby |
| Resque | Ruby |
| Asynq | Go |

API 는 작업을 큐에 등록하고 즉시 응답, 워커가 백그라운드에서 처리.

### 8.4 캐싱 (Caching)

자주 조회되는 데이터는 메모리에 캐시. **Redis** 가 가장 흔함.

```python
def get_user(user_id):
    cached = redis.get(f"user:{user_id}")
    if cached:
        return User.parse_raw(cached)

    user = session.get(User, user_id)
    redis.set(f"user:{user_id}", user.json(), ex=300)
    return user
```

### 8.5 추가 키워드

- **Idempotency** — 같은 요청을 여러 번 보내도 결과가 같음.
- **Rate Limiting** — 사용자별 요청 빈도 제한.
- **Webhook** — 외부 시스템에 이벤트 발행.
- **GraphQL Resolvers** — GraphQL 의 비즈니스 로직 자리.
- **Event-Driven Architecture** — 이벤트 발행·구독 기반.

---

## 마치며

오늘 한 일:

- 한 API 요청의 **5단계 흐름** (라우팅·검증·로직·DB·응답).
- 언어·프레임워크 선택 가이드 (FastAPI 권장).
- **계층 분리 폴더 구조** (router·schema·service·model).
- **CRUD** 5개 패턴.
- 검증·인증·에러를 **한 곳으로 모으는** 패턴.
- 함정 8가지.

다음 레슨 [`15. 데이터베이스 구축과 운영`](./15-데이터베이스-구축.md) 에서는 백엔드가 호출하는 DB 자체를 어떻게 설치·운영하는지 봅니다.

다음 페이지에서 만나요.
