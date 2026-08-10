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

Python 백엔드 선택지는 크게 다섯 — 각각 철학·규모·비동기 지원 방식이 다릅니다.

### 1.1 Django (2005)

- **철학**: "배터리 포함(batteries included)". ORM · Admin · 인증 · 폼 · 템플릿까지 웹 앱에 자주 필요한 모든 것을 프레임워크 본체에 내장. "Django가 정한 방식"을 따르는 대가로 의사 결정이 크게 줄어듭니다.
- **강점**: 15년 이상 축적된 성숙도, 관리자 UI 자동 생성, CSRF·XSS·SQL 인젝션 등 보안 기본기 탄탄, 대규모 팀에서 컨벤션을 강제하기 쉬움, 에코시스템·학습 자료 풍부.
- **약점**: 무겁고 "Django 방식" 의존적이라 프레임워크 밖으로 나가려면 저항이 큼. 비동기는 3.1(2020)부터 공식 지원이지만 ORM·미들웨어 곳곳에 동기 가정이 남아 실전 성능은 제약적.
- **적합**: 콘텐츠 중심 CMS, 사내 관리 도구, 관리자 UI 비중이 큰 전통적 CRUD 앱, 팀 규모가 크고 컨벤션 통일이 중요한 조직.

### 1.2 Flask (2010)

- **철학**: 마이크로 프레임워크. 핵심(라우팅·요청/응답·템플릿 후킹)만 제공하고 나머지는 확장(Flask-SQLAlchemy, Flask-Login, Flask-Smorest 등)으로 조립. "필요한 만큼만 쓴다"가 모토.
- **강점**: 입문 장벽 매우 낮음, 코드 양이 적어 학습에 좋음, WSGI 호환 생태계가 넓어 배포 선택지 많음, 작은 프로젝트에서는 Django보다 빠른 개발.
- **약점**: 타입 검증·문서화·비동기가 전부 수동 또는 확장 의존적. 프로젝트가 커지면 구조 표준 부재로 팀마다 패턴이 제각각이 되고 유지보수 부담이 늘어남. Flask 2.0(2021)에서 async 지원이 들어왔지만 WSGI 기반이라 제약이 큼.
- **적합**: 프로토타입, 특정 용도의 단일 목적 API, 학습·교육용 프로젝트, 레거시 WSGI 환경 유지.

### 1.3 FastAPI (2018)

- **철학**: Starlette(비동기 ASGI 툴킷) + Pydantic(타입 검증)을 결합해 **"타입 선언이 곧 API 계약"**이 되게 설계. Python의 최신 타입 힌트 문법을 적극 활용해 요청·응답·문서를 동시에 얻음.
- **강점**: 비동기가 기본, Pydantic 기반 자동 입력 검증, OpenAPI/Swagger 자동 생성, `Depends` 기반 의존성 주입이 강력, AI/LLM 생태계와 궁합 최상(LangChain·OpenAI·Anthropic SDK 예제가 대부분 FastAPI 기준).
- **약점**: Django 수준의 "배터리"가 없어 Admin·ORM·마이그레이션 등을 각자 선택·조립해야 함. 자유도가 높은 만큼 팀 전체가 지키는 구조 규약(계층 분리·에러 처리·인증 패턴)을 따로 확립하지 않으면 프로젝트가 빠르게 산발적이 됨.
- **적합**: 현대적 API 서버, SPA/모바일의 백엔드, AI 에이전트·LLM 앱, 타입 안전을 중시하는 Python 팀. **본 프로젝트가 여기에 해당.**

### 1.4 Litestar (2022, 구 Starlite)

- **철학**: FastAPI를 사용하며 느낀 성능 · 의존성 주입 · 계층화 한계를 개선하려 처음부터 재설계한 신흥 ASGI 프레임워크. Pydantic 없이도 동작하도록 자체 msgspec 경로 제공.
- **강점**: msgspec 기반 직렬화로 FastAPI 대비 직렬화 성능이 수 배 빠름, DI 시스템이 FastAPI보다 구조화돼 대형 앱 유지에 유리, 플러그인 아키텍처가 체계적, 공식 ORM/CLI/Admin 스캐폴딩 제공.
- **약점**: 생태계·커뮤니티가 FastAPI의 1/10 수준. AI·LLM 관련 예제·블로그·튜토리얼은 거의 FastAPI 위주라 문제 해결 시 참고 자료가 적음. 채용 풀이 좁아 팀 온보딩 비용이 큼.
- **적합**: 성능 · 구조 측면에서 FastAPI로 부족함을 느끼는 대형 서비스, 기술 선도 여력이 있는 팀, 마이크로서비스 집합에서 스키마·DI의 일관성이 중요한 경우.

### 1.5 Starlette (2018)

- **철학**: ASGI 위에 얹은 얇은 **웹 툴킷**. 단독 "프레임워크"라기보다 빌딩 블록에 가깝습니다. FastAPI와 Litestar 모두 Starlette 위에 구현되어 있습니다.
- **강점**: 매우 가볍고 빠름, ASGI 표준을 충실히 따름, 미들웨어·라우팅·WebSocket 같은 저수준 도구가 깔끔하게 제공되어 "필요한 만큼만" 쓰기 좋음.
- **약점**: Pydantic 검증 · 의존성 주입 · OpenAPI 자동 생성 같은 **프레임워크 수준의 편의 기능이 없음**. 이를 원하면 직접 조립하거나 FastAPI/Litestar 같은 상위 프레임워크를 써야 함.
- **적합**: 초경량 마이크로서비스, FastAPI가 과하다고 느끼는 특수 엔드포인트, 프레임워크 자체를 커스텀 설계하는 경우, ASGI 학습 목적.

### 1.6 기타 언급

- **Tornado** (2009) — 초기 비동기 서버의 상징. 최근엔 레거시 성격이 강하나 long-polling·WebSocket 헤비 유스케이스에서 아직 쓰임.
- **Bottle** (2009) — 파일 한 개로 된 초소형 프레임워크. 임베디드·스크립트성 용도.
- **Sanic** (2016) — 비동기 중심의 경량 프레임워크. FastAPI와 시기적 경쟁자였으나 타입·문서 자동화 측면에서 밀림.
- **Robyn / BlackSheep** — Rust·.NET 스타일 영향을 받은 실험적 신흥들. 성능 실측에서 선두권이나 생태계는 아직 초기.

---

**우리는 FastAPI 0.115+** 를 씁니다(Python 3.12 — 3.13 호환 전 안정 버전대로 묶어 사용). 이유:

1. **비동기(async/await)** 기본 지원 — 동시 요청을 효율적으로 처리.
2. **Pydantic 기반 타입 검증** — 입력·출력이 자동으로 검사됨.
3. **OpenAPI(API 명세 표준) 자동 생성** — `/docs` 에서 바로 테스트 가능.
4. **FastAPI + Uvicorn[standard] 0.34 조합의 성능** — 실측 성능이 Node.js와 대등.
5. **학습 곡선** — Flask처럼 단순하지만 Django처럼 안전함.
6. **AI 앱과 잘 맞는 선택지** — Python 생태계에는 LLM SDK와 데이터 처리 도구가 많고, FastAPI는 그 위에 API를 얹기 좋습니다.

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

`pydantic-settings 2.8` (Pydantic과 동일한 v2 계열)은 환경 변수를 Pydantic 모델로 읽는 도구. 우리 프로젝트의 `apps/api/src/ai_do_api/core/settings.py` 같은 곳에서 이런 식으로 쓰입니다.

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

- **Uvicorn**: 경량·빠름. 우리 선택.
- Hypercorn: HTTP/2·QUIC 지원.
- Daphne: Django Channels 중심.

운영 배포 시에는 Uvicorn 앞에 **Gunicorn + Uvicorn worker** 또는 **Uvicorn multi-process** 로 프로세스를 여러 개 띄울 수 있습니다. 개발 환경에서는 `scripts/dev-api.sh` 로 API 인스턴스를 포트별로 나눠 띄웁니다(8001, 8002 등).

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
├── src/ai_do_api/
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
│       │   ├── schemas.py   Pydantic 입출력 스키마(도메인에 따라 router.py에 둘 수도 있음)
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
- **Schema** (`schemas.py` 또는 `router.py`): Pydantic 모델(외부 입출력).

이 4-파일 패턴은 **이해하기 쉽고, 테스트하기 쉽고, AI가 잘 생성합니다**.

### 7.2 예시 흐름 (가상)

```python
# apps/api/src/ai_do_api/domains/pms/router.py
class IssueCreate(BaseModel):
    title: str
    board_id: str
    assignee_id: str | None = None

class IssueRead(BaseModel):
    id: str
    title: str
    status: IssueStatus
    # ...

# apps/api/src/ai_do_api/domains/pms/service.py
async def create_issue(db, workspace_id: str, data: IssueCreate) -> Issue:
    issue = Issue(
        workspace_id=workspace_id,
        title=data.title,
        ...
    )
    db.add(issue)
    await db.commit()
    return issue

# apps/api/src/ai_do_api/domains/pms/router.py
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
- Service는 LLM provider 호출을 비동기 제너레이터로 받아 이벤트를 쏩니다.
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

비슷한 역할을 할 수 있는 다른 기술들과, 본 프로젝트에서 각각 선택되지 않은 이유를 정리합니다.

### 11.1 Django REST Framework (DRF)

- **성격**: Django 위에 얹는 성숙한 REST API 툴킷. Serializer · ViewSet · Permission · Authentication이 잘 짜여 있고 대규모 레퍼런스가 수없이 많음.
- **강점**: Django의 Admin · ORM · 마이그레이션을 그대로 활용 가능. 팀이 이미 Django 기반이면 진입 비용이 사실상 0.
- **왜 FastAPI?**: 본 프로젝트는 Django Admin이 핵심 용도가 아니라 Django 본체 무게를 통째로 짊어지는 것이 오히려 오버헤드. 비동기 지원이 여전히 2등 시민이어서 SSE · WebSocket · LLM 스트리밍 구현이 복잡해집니다. Pydantic처럼 Python 타입 힌트와 직결된 검증 경험도 부재(Serializer는 별도 DSL)여서 "타입 = 계약"의 장점을 못 누립니다.

### 11.2 Flask + Marshmallow

- **성격**: Flask 마이크로 프레임워크에 Marshmallow(또는 Pydantic)를 직접 얹어 API·검증을 구성하는 전통적 조합.
- **강점**: 자유도 극대, 시작 빠름, WSGI 호환으로 레거시 인프라에서도 무리 없이 돕니다.
- **왜 FastAPI?**: 검증 스키마 · 문서화 · 비동기가 전부 수동 조립. Flask 2.0+ 의 async 지원은 WSGI 기반이라 FastAPI 수준의 동시성 효율을 내기 어렵습니다. 프로젝트 규모가 커지면서 팀 전체가 반복해 만드는 보일러플레이트(라우팅 표준화·에러 처리·OpenAPI 스키마 정의)가 누적되어 유지보수 부담이 큽니다.

### 11.3 Litestar (구 Starlite)

- **성격**: FastAPI 경험을 토대로 성능 · DI · 계층화를 개선해 2022년에 재설계된 신흥 ASGI 프레임워크.
- **강점**: msgspec 기반으로 직렬화 성능이 FastAPI 대비 수 배 빠름. DI 시스템이 더 구조화되어 대형 앱 유지에 유리. 공식 ORM · CLI · 플러그인 스캐폴딩 제공.
- **왜 FastAPI?**: 생태계 · 커뮤니티 · 자료 양이 FastAPI보다 작습니다. 기술 선택은 팀 채용 · 온보딩 · 외부 인력 영입 속도에 직결되므로 "약간 빠름"의 이득이 "생태계 결핍"의 손실을 보상하지 못합니다.

### 11.4 Express.js (Node.js)

- **성격**: Node.js 생태계의 사실상 표준 웹 프레임워크. 프런트와 언어 통일(JS/TS) 가능.
- **강점**: 프런트 팀 스킬셋을 그대로 백엔드로 확장 가능. npm 생태계 거대, 자유도 높고 유연.
- **왜 FastAPI?**: 본 프로젝트는 **AI/LLM이 핵심 워크로드**. OpenAI · Anthropic · LangChain · LlamaIndex · pgvector · 임베딩 라이브러리 모두 Python이 **1등 시민**이고 Node 버전은 항상 6개월~1년 지연되거나 기능 서브셋입니다. 데이터 전처리 · 임베딩 · 벡터 연산에 쓰이는 numpy · pandas · scikit-learn 같은 과학 생태계도 Python이 압도적. "언어 통일" 이점보다 AI 개발 속도·참고 자료 측면 손실이 훨씬 큽니다.

### 11.5 NestJS (Node.js + TypeScript)

- **성격**: Angular 스타일의 구조적 TypeScript 프레임워크. 데코레이터 · 모듈 · Guard · Pipe · Interceptor 등 엔터프라이즈 설계 패턴을 문법화.
- **강점**: 대규모 팀에서 체계적인 유지보수가 가능. TypeScript 타입 안전을 백엔드까지 확장. 테스트 구조가 잘 정의돼 있습니다.
- **왜 FastAPI?**: 구조 자체는 훌륭하지만 Express와 동일한 **AI 생태계 한계**를 공유합니다. 또한 NestJS의 학습 곡선이 FastAPI보다 가파르고(Guard · Interceptor · Pipe · Module 등 개념이 다수) Python 기반 팀에 도입 시 온보딩 비용이 큽니다. 타입 안전만 놓고 보면 FastAPI + Pydantic v2도 "선언이 곧 검증"이라 실질 체감 차이가 크지 않습니다.

### 11.6 Go (Gin, Echo, Chi 등)

- **성격**: 정적 타입·컴파일형 언어의 고성능 웹 프레임워크 계열. 단일 바이너리 배포가 간단.
- **강점**: 런타임 성능과 동시성(goroutine) 모델 최상. 메모리 풋프린트 작고 운영 단순.
- **왜 FastAPI?**: 본 프로젝트의 병목은 **DB 쿼리와 외부 API(OpenAI) 호출 같은 I/O 대기**이지 CPU 연산이 아닙니다. Go의 CPU 성능 이점이 실익으로 거의 환산되지 않습니다. 반면 ORM · 인증 · 타입 자동 검증 · OpenAPI 자동 생성이 Go 생태계에는 부재하거나 수동이라 개발 생산성 손실이 큽니다. LangChain · LLM SDK 공식 지원도 Python 대비 얕음. 성능이 진짜 병목이 되는 특정 엔드포인트(예: 이미지·영상 처리)는 별도 Go 마이크로서비스로 빼는 편이 합리적입니다.

---

**FastAPI가 맞는 팀**: Python 생태계(LLM SDK · LangChain · pgvector · numpy 등) 활용 + 타입 안전 + 문서화 자동화를 원함.

### 11.7 🛠️ 5분 실습 — `/docs`에서 엔드포인트 한 번 호출해 보기

1. 로컬에서 `pnpm dev:api`(또는 `scripts/dev-api.sh`)로 API를 띄웁니다.
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
