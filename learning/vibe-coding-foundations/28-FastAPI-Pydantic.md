# 28. FastAPI + Pydantic — 백엔드의 심장

> **한 줄 요약.** **FastAPI**는 Python으로 API를 만드는 현대적 프레임워크이고, **Pydantic**은 그 안에서 입력·출력 데이터의 **모양을 강제**하는 타입 검사기다. 이 조합이 TypeScript 같은 개발 경험을 Python에 가져온다.

> **🔑 한 마디로.** FastAPI + Pydantic은 요청 JSON 검증, 응답 스키마 강제, OpenAPI 문서 생성을 자동화해 API 계약을 일관되게 유지하는 도구 조합입니다.

### FastAPI + Pydantic 조합의 핵심

- Router는 요청을 받고, Pydantic이 입력 스키마를 검증한 뒤 Service 로직으로 전달합니다. 잘못된 입력은 HTTP 422로 즉시 반환됩니다.
- `async/await`는 I/O 대기 중 다른 요청을 처리해 동시 처리 효율을 높입니다.
- Pydantic 스키마가 요청/응답 계약을 명확히 하므로 서비스 계층은 비즈니스 로직에 집중할 수 있습니다.

### ⚠️ 백엔드 선택에서 자주 듣는 오해

- **"Python은 느려서 백엔드에 부적합하다"** — 대부분의 병목은 DB·네트워크 I/O이며, FastAPI의 `async`는 Node.js에 필적하는 동시성을 냅니다. Pydantic v2는 Rust 코어(Pydantic-core)로 v1 대비 10~100배 빠릅니다.
- **"자동 문서(`/docs`)는 장식이다"** — 프런트 팀이 명세 PDF 없이 바로 API를 이해·테스트할 수 있는 **커뮤니케이션 비용 절감 장치**입니다. 설계 변경이 곧 문서 변경이라 어긋날 일이 없습니다.
- **"FastAPI는 Django의 완전한 대체품"** — Django가 가진 Admin·Auth·CMS 기능은 대부분 직접 구성해야 합니다. 가볍지만 "조립해야 한다"는 책임이 따릅니다.
- **"`async def`만 붙이면 전부 비동기가 된다"** — 내부에서 `time.sleep()`, 동기 DB 드라이버, CPU 연산을 하면 이벤트 루프가 막혀 오히려 **동기보다 느려질 수** 있습니다.
- **"Pydantic은 타입 검사기일 뿐이다"** — 설정(pydantic-settings)·JSON 직렬화·OpenAPI 스키마 자동 생성까지 담당하는 **다목적 데이터 계약 엔진**입니다.

---

## 1. Python 웹 프레임워크의 지형도

Python은 오래전부터 웹 개발에 쓰였습니다. 대표 프레임워크:

| 프레임워크 | 등장 | 특징 |
|---|---|---|
| **Django** | 2005 | "배터리 포함" 풀 프레임워크. ORM·어드민·폼 다 내장. 전통의 강자. |
| **Flask** | 2010 | 마이크로 프레임워크. 최소 기능, 자유도 높음. |
| **FastAPI** | 2018 | 비동기·타입·자동 문서화의 신예. 폭발적 성장. 2024년 이후 Django와 유사 레벨의 인기. |
| Tornado/Bottle/Starlette 등 | 오래 전 | 특정 영역에서만 쓰임. |

**우리는 FastAPI 0.115+** 를 씁니다(Python 3.12 — 3.13 호환 전 안정 버전대로 묶어 사용). 이유:

1. **비동기(async/await)** 기본 지원 — 동시 요청을 효율적으로 처리.
2. **Pydantic 기반 타입 검증** — 입력·출력이 자동으로 검사됨.
3. **OpenAPI(API 명세 표준) 자동 생성** — `/docs` 에서 바로 테스트 가능.
4. **FastAPI + Uvicorn[standard] 0.34 조합의 성능** — 실측 성능이 Node.js와 대등.
5. **학습 곡선** — Flask처럼 단순하지만 Django처럼 안전함.
6. **2026 에이전트/AI 앱 기본 선택지** — OpenAI·Anthropic 등 LLM SDK가 Python에서 가장 먼저 나오며, FastAPI가 그 위 API 프레임워크로 사실상 표준화됨.

---

## 2. FastAPI의 첫 감각

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float
    in_stock: bool = True

@app.post("/items")
async def create_item(item: Item) -> Item:
    # item이 이미 검증된 상태로 들어옴
    # 필요 시 DB에 저장
    return item
```

짧은 이 코드에서 다음이 **자동으로** 제공됩니다.

- `POST /items` 경로 등록
- 요청 본문이 `Item` 형태(name: 문자, price: 숫자)인지 검증. 잘못되면 **자동 422 응답**.
- 응답을 JSON으로 직렬화.
- `/docs` 에 이 엔드포인트가 **Swagger UI**로 노출됨.

TypeScript + Node.js로는 한참 더 써야 할 일이 한 줄에 끝납니다.

---

## 3. Pydantic — 데이터 모델링의 핵심

### 3.1 무엇인가

**Pydantic** 은 Python의 타입 힌트(`: str`, `: int`)를 **런타임 검증기** 로 활용하는 라이브러리입니다. v2(2023)부터 Rust 기반 핵심 엔진을 써서 **매우 빠릅니다**.

### 3.2 기본 사용

```python
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr            # 이메일 형식 강제
    password: str
    display_name: str | None = None

u = UserCreate(email="bad", password="123")
# ValidationError: email is not a valid email address
```

타입이 **선언이 곧 검증 규칙**이 됩니다.

### 3.3 FastAPI와의 통합

FastAPI가 Pydantic을 사용해:

- **요청 본문** (JSON body) 자동 파싱·검증
- **쿼리/패스 파라미터** 검증
- **응답 직렬화** (Pydantic model → JSON)
- **OpenAPI 스키마** 자동 생성

### 3.4 응답 모델

```python
class UserRead(BaseModel):
    id: str
    email: EmailStr
    display_name: str

@app.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: str):
    return fetch_user_from_db(user_id)
```

`response_model`로 지정하면 **불필요한 필드(예: 해시된 비밀번호)가 자동으로 숨겨집니다**. 정보 유출 예방.

### 3.5 Pydantic Settings

`pydantic-settings 2.8` (Pydantic과 동일한 v2 계열)은 환경 변수를 Pydantic 모델로 읽는 도구. 우리 프로젝트의 `apps/api/src/aidoo_api/core/settings.py` 같은 곳에서 이런 식으로 쓰입니다.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_dsn: str
    redis_url: str
    minio_endpoint: str
    openai_api_key: str
    
    class Config:
        env_file = ".env"

settings = Settings()
```

`.env`에 정의된 값이 **타입 검사되어** 들어옵니다. 환경 변수 오타로 인한 사고를 막아줍니다.

---

## 4. 비동기(async/await) — 왜 중요한가

### 4.1 문제

전통적 Python은 "한 요청을 처리하는 동안 다른 요청을 기다리게" 합니다. DB 쿼리가 100ms 걸리면 그 사이 CPU는 놀고 있고 다른 요청은 대기.

### 4.2 asyncio의 해법

```python
@app.get("/items/{id}")
async def get_item(id: str):
    item = await db.fetch_item(id)       # DB 대기 중 다른 요청 처리
    related = await api.fetch_related(item.sku)  # 외부 API 대기 중에도
    return { "item": item, "related": related }
```

`await` 가 걸린 동안 이벤트 루프가 **다른 일**을 합니다. 한 서버 프로세스가 수천 개 동시 요청을 다룰 수 있게 됩니다.

### 4.3 주의

- 동기 블로킹 코드(예: `time.sleep(1)`)를 `async` 함수 안에서 쓰면 이벤트 루프가 막혀 망합니다.
- CPU 집약 작업(이미지 처리 등)은 **워커(Celery)** 로 넘기거나 thread pool을 써야 합니다.

---

## 5. 의존성 주입(Depends) — FastAPI의 독특한 강점

FastAPI는 **Depends** 라는 매커니즘을 언어 레벨로 지원합니다.

```python
from fastapi import Depends

async def get_db():
    async with AsyncSession() as s:
        yield s
        # 요청 끝에 자동 정리

async def current_user(token: str = Header(...), db = Depends(get_db)) -> User:
    user = await verify_token(token, db)
    if not user:
        raise HTTPException(401)
    return user

@app.get("/me")
async def me(user: User = Depends(current_user)):
    return user
```

`Depends()` 안의 함수들은 **재귀적으로 해결**됩니다. 의존성 자체가 의존성을 가질 수 있습니다. 테스트할 때 이 체인을 **대체**하기도 쉽습니다.

우리 프로젝트도 `require_workspace_membership`, `require_legacy_workspace_membership` 같은 의존성으로 **권한 가드**를 걸어 놓습니다.

---

## 6. Uvicorn과 ASGI

FastAPI는 **ASGI(Async Server Gateway Interface, 비동기 서버 게이트웨이 인터페이스)** 표준을 따릅니다. ASGI는 이전 WSGI(Web Server Gateway Interface, 동기형)의 비동기 후계 표준입니다.

FastAPI 자체는 "프레임워크"이고, 실제로 요청을 받는 "서버"는 **Uvicorn** 입니다(현재 `uvicorn[standard] 0.34`).

- **Uvicorn**: 최신·경량·빠름. 우리 선택.
- Hypercorn: HTTP/2·QUIC 지원.
- Daphne: Django Channels 중심.

운영 배포 시에는 Uvicorn 앞에 **Gunicorn + Uvicorn worker** 또는 **Uvicorn multi-process** 로 프로세스를 여러 개 띄웁니다. `scripts/prod-like-api.sh` 가 바로 이 역할을 합니다(포트 8001, 8002 등).

### 6.1 SSE(서버 전송 이벤트)·파일 업로드 관련 패키지

- **sse-starlette 2.1** — AI 응답을 한 글자씩 스트림(SSE, Server-Sent Events) 하는 응답 타입. 채팅 답변을 토큰 단위로 실시간 표시하는 기반.
- **python-multipart 0.0.18** — multipart/form-data 파일 업로드 파싱기. 이미지·첨부 업로드 처리에 필요(없으면 FastAPI가 업로드 파싱을 아예 못 합니다).

---

## 7. 우리 프로젝트 백엔드 구조

```
apps/api/
├── alembic/                 DB 마이그레이션 (29장)
├── alembic.ini
├── pyproject.toml           의존성 선언
├── src/aidoo_api/
│   ├── core/
│   │   ├── settings.py      환경변수 → Pydantic Settings
│   │   ├── security.py      암호화·토큰
│   │   ├── logging.py
│   │   └── ...
│   ├── db/                  SQLAlchemy 세션·엔진
│   ├── main.py              FastAPI app 조립
│   ├── routers.py           라우터 결합
│   └── domains/             도메인별 폴더
│       ├── ai/
│       │   ├── router.py    HTTP 엔드포인트
│       │   ├── service.py   비즈니스 로직
│       │   ├── models.py    DB 모델
│       │   ├── schemas.py   Pydantic 입출력 스키마
│       │   ├── registry.py  AI 능력 레지스트리
│       │   └── ...
│       ├── auth/
│       ├── docs/
│       │   └── collab.py    실시간 협업 허브
│       ├── pms/
│       ├── calendar/
│       ├── meeting/
│       ├── ocr/
│       └── ...
└── tests/
```

### 7.1 패턴: Router → Service → Model

대부분의 도메인이 이 3층을 따릅니다.

- **Router** (`router.py`): HTTP 엔드포인트 정의. 입출력 Pydantic 스키마 연결. 권한 가드.
- **Service** (`service.py`): 비즈니스 로직. DB 접근·외부 호출. 재사용 가능한 단위.
- **Model** (`models.py`): SQLAlchemy ORM 모델(DB 테이블 매핑).
- **Schema** (`schemas.py`): Pydantic 모델(외부 입출력).

이 4-파일 패턴은 **이해하기 쉽고, 테스트하기 쉽고, AI가 잘 생성합니다**.

### 7.2 예시 흐름 (가상)

```python
# apps/api/src/aidoo_api/domains/pms/schemas.py
class IssueCreate(BaseModel):
    title: str
    board_id: str
    assignee_id: str | None = None

class IssueRead(BaseModel):
    id: str
    title: str
    status: IssueStatus
    # ...

# apps/api/src/aidoo_api/domains/pms/service.py
async def create_issue(db, workspace_id: str, data: IssueCreate) -> Issue:
    issue = Issue(
        workspace_id=workspace_id,
        title=data.title,
        ...
    )
    db.add(issue)
    await db.commit()
    return issue

# apps/api/src/aidoo_api/domains/pms/router.py
@router.post("/issues", response_model=IssueRead)
async def post_issue(
    body: IssueCreate,
    ws: Workspace = Depends(require_workspace_membership),
    db = Depends(get_db),
):
    return await create_issue(db, ws.id, body)
```

이 4-파일 패턴에 익숙해지면 **새 기능 추가** 가 10~30분 안에 가능해집니다.

### 7.3 🏢 업무 시나리오

**케이스 — 채팅 답변을 한 글자씩 보여주는 "스트리밍 응답"**
- `POST /ai/chat` 라우터가 `sse-starlette`의 `EventSourceResponse`를 반환.
- Service는 OpenAI 호출을 비동기 제너레이터로 받아 이벤트를 쏩니다.
- 프런트에서는 `eventsource-parser`로 한 청크씩 받아 BlockNote 에디터에 append.
- Pydantic 스키마는 **요청에만** 엄격 적용, 응답은 스트림 청크이므로 `response_model`을 쓰지 않고 SSE 커스텀 포맷을 씁니다(라우터마다 응답 스타일이 다를 수 있음을 보여주는 예).

**케이스 — 첨부 파일 업로드 엔드포인트**
- `@router.post("/docs/attachments")` 가 `file: UploadFile = File(...)`를 받음. `python-multipart`가 실제 파싱을 담당.
- Service에서 MinIO로 `put_object`(31장), DB `files` 테이블에 메타 저장.
- 응답은 `FileRead(id, url)` 같은 Pydantic 모델.

---

## 8. OpenAPI 자동 문서

`http://localhost:8000/docs` — Swagger UI. 브라우저에서 바로 테스트 가능.
`http://localhost:8000/redoc` — ReDoc (더 읽기 좋은 문서 형태).

이 문서는 **코드의 타입 선언으로부터 자동 생성** 됩니다. 별도 유지보수 불필요.

프런트 팀은 이 문서로 API를 파악합니다. 나중에 `openapi-typescript` 등 도구로 **OpenAPI → TypeScript 타입 자동 생성** 도 가능하며, `packages/contracts`에서 이를 관리하는 것이 다음 진화 방향입니다.

---

## 9. 에러 처리 패턴

```python
from fastapi import HTTPException

@router.get("/items/{id}")
async def get_item(id: str):
    item = await service.find_item(id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
```

도메인 에러는 `HTTPException`으로 변환. 복잡한 경우 **커스텀 예외 핸들러** 등록:

```python
@app.exception_handler(PermissionDenied)
async def handle_permission(request, exc):
    return JSONResponse(status_code=403, content={"error": "permission_denied"})
```

---

## 10. 테스트 (pytest)

```python
from fastapi.testclient import TestClient

def test_create_issue(client, auth_header):
    response = client.post("/pms/issues", json={
        "title": "버그 발견", "board_id": "b-1"
    }, headers=auth_header)
    assert response.status_code == 201
    assert response.json()["title"] == "버그 발견"
```

`TestClient` 는 실제 HTTP 없이 Python 레벨에서 FastAPI 앱을 호출합니다. 속도가 빠릅니다.

---

## 11. 대안이 될 수 있었던 것들

| 기술 | 비교 | 왜 FastAPI? |
|---|---|---|
| Django REST Framework | 성숙·풀기능 | 우리 규모엔 무겁고, 비동기 제약. |
| Flask + Marshmallow | 가볍고 자유 | 타입 검증·문서화 수동. |
| Litestar (구 Starlite) | FastAPI 대안, 성능·DI 개선 시도 | 생태계·AI 예제 수에서 FastAPI가 우세. |
| Express.js (Node) | 프런트와 언어 통일 | AI 라이브러리·Python 생태계를 포기해야 합니다. |
| NestJS (Node) | TS + 구조적 | 언어는 좋으나 AI 통합 약점. |
| Go (Gin, Echo) | 성능 최상 | 우리 병목이 네트워크라 실익 낮고, 학습 부담 큼. |

**FastAPI가 맞는 팀**: Python 생태계(LLM SDK·LangChain·pgvector 등) 활용 + 타입 안전 + 문서화 자동화를 원함. 2026년 기준 AI 에이전트 백엔드의 사실상 기본값.

### 11.1 🛠️ 5분 실습 — `/docs`에서 엔드포인트 한 번 호출해 보기

1. 로컬에서 `pnpm api:dev`(또는 `scripts/dev-api.sh`)로 API를 띄웁니다.
2. 브라우저에서 `http://localhost:8000/docs` 열기.
3. 아무 `GET` 엔드포인트의 "Try it out" 누르고, 필요한 파라미터를 채운 뒤 "Execute".
4. 응답 JSON과 curl 명령 예시가 자동 생성되는 걸 확인. 이것이 **Pydantic 스키마가 곧 문서**인 이유.

---

## 12. 핵심 요약

- **FastAPI** = Python + 비동기 + 타입 검증 + 자동 문서화.
- **Pydantic** 이 입출력·설정 검증의 중심.
- **Depends** 로 권한·DB 세션 등 의존성을 깔끔히 주입.
- **Uvicorn**이 ASGI 서버. 운영에서는 여러 프로세스로 확장.
- 도메인별 **Router → Service → Schema/Model** 4-파일 패턴이 개발 기본 흐름.
- `/docs` 자동 OpenAPI가 팀 커뮤니케이션을 크게 가볍게 만든다.

---

## 13. 이해도 체크

1. FastAPI의 "자동 검증"은 무엇을 자동으로 해 주는가? 세 가지를 들어 보세요.
2. Pydantic v2가 왜 빠른지 간단히 설명하세요(키워드: Pydantic-core, Rust).
3. `Depends()`가 의존성 주입과 권한 검증에 어떤 이점을 주는지 설명해 보세요.
4. `async def` 함수 안에서 `time.sleep()` 을 쓰면 안 되는 이유는?
5. 우리 프로젝트의 4-파일 패턴(Router/Service/Model/Schema)을 **회의실 예약 기능**으로 예시해 보세요.
6. `response_model`을 쓰면 "정보 유출 예방"이 된다는 건 구체적으로 어떤 상황을 막는 건가요?
7. `sse-starlette`이 챗봇 UX에서 수행하는 역할을 한 문장으로 설명해 보세요.
