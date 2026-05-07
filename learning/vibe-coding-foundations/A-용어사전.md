# 부록 A. 용어 사전

> AI-DO Portal 교육 자료에서 자주 등장하는 IT·개발 용어를 **비개발자 기준**으로 짧게 풀어 둔 사전입니다. 각 항목은 문장 1~3개의 정의 + 이 프로젝트에서의 위치로 구성됩니다. 가나다 순.

---

## ㄱ

**가명화(Pseudonymization)**
개인 식별 정보를 가짜 이름·ID 로 치환해 원본을 추정하기 어렵게 만드는 기법. 외부 AI 도구에 사내 데이터를 넣기 전 필수(15장).

**객체 저장소(Object Storage)**
파일 바이트를 "키 → 데이터" 형태로 보관하는 저장소. S3·MinIO가 대표. 이 프로젝트는 **MinIO**(31장).

**골든 패스(Golden Path)**
사용자가 정상적으로 따라가는 핵심 경로. 테스트·검증 우선순위 1번(10·13장).

**객체 지향(Object-Oriented Programming, OOP)**
데이터와 동작을 "객체"라는 단위로 묶어 다루는 프로그래밍 패러다임. 클래스·상속·다형성이 핵심.

**관측(Observability)**
운영 중인 시스템의 내부 상태를 **로그·지표·트레이스** 로 "밖에서" 볼 수 있게 만드는 것(11·33장).

**컨테이너(Container)**
앱과 그 실행 환경을 함께 포장한 가벼운 "박스". Docker가 가장 유명. 개발·운영 환경 차이를 줄임(11·33장).

**크로스브라우저(Cross-browser)**
크롬·파이어폭스·사파리 등 여러 브라우저에서 동일하게 동작하는 것.

---

## ㄴ

**낙관적 업데이트(Optimistic Update)**
서버 응답을 기다리지 않고 UI를 먼저 바꾸고, 나중에 서버 응답으로 맞추는 UX 패턴. React 19의 `useOptimistic` 훅이 지원(23·25장).

**네임스페이스(Namespace)**
이름 충돌을 피하려고 묶어두는 "구역". 파이썬 모듈, JS 모듈, Docker 네트워크 등에서 쓰임.

**노드(Node.js)**
브라우저 밖에서 JavaScript를 실행하는 런타임. 프런트 빌드 도구·일부 서버가 여기서 돎(3·23장).

---

## ㄷ

**도커(Docker)**
컨테이너를 만들고 실행하는 대표 도구(11·33장).

**도커 컴포즈(Docker Compose)**
여러 컨테이너를 **한 번에** 정의하고 실행하는 도구(33장).

**동기 / 비동기(Sync / Async)**
동기는 "끝날 때까지 기다리는" 호출, 비동기는 "기다리지 않고 다음 일을 하는" 호출. 파이썬의 `async/await`가 대표(30장).

**디버깅(Debugging)**
코드의 버그를 찾아 고치는 과정. 로그 출력, 브레이크포인트, 테스트가 주 도구.

**딥 링크(Deep Link)**
앱의 특정 화면 상태를 URL로 지목할 수 있는 것. SPA에서 라우팅이 책임(25장).

---

## ㄹ

**라우팅(Routing)**
URL을 특정 화면/핸들러와 연결하는 규칙. 프런트는 **React Router**, 백엔드는 **FastAPI Router**가 담당(25·28장).

**런타임(Runtime)**
프로그램이 실제로 실행되는 환경. 파이썬 인터프리터, Node.js, 브라우저 등(3장).

**레포지토리(Repository, DDD 맥락)**
데이터 저장소에 접근하는 코드를 한 곳에 모은 객체. "DB 사용 지점을 한 층으로" 분리(7·29장).

**리버스 프록시(Reverse Proxy)**
바깥 요청을 받아서 내부 여러 서비스로 전달하는 중계 서버. 이 프로젝트는 **Nginx**(33장).

**리팩토링(Refactoring)**
동작을 바꾸지 않고 코드 구조만 개선하는 작업. 테스트가 있을 때 안전(34장).

---

## ㅁ

**마이그레이션(Migration)**
DB 스키마 변경을 코드로 남기고 적용하는 작업. 이 프로젝트는 **Alembic**(8·29장).

**마크다운(Markdown)**
가벼운 서식 텍스트 문법. `# 제목`, `**굵게**` 등. 이 교육 자료도 전부 마크다운.

**멀티 스테이지 빌드(Multi-stage Build)**
Dockerfile에서 빌드 도구를 최종 이미지에서 제외하기 위해 단계를 나누는 기법(33장).

**모노레포(Monorepo)**
여러 프로젝트를 한 저장소에 모아 관리하는 방식. 이 프로젝트는 **pnpm workspace + Nx**(6·21장).

**모놀리식(Monolithic) / 모듈러 모놀리스(Modular Monolith)**
한 덩어리 앱 / 내부를 도메인 모듈로 명확히 나눈 한 덩어리 앱. 이 프로젝트는 후자(6장).

---

## ㅂ

**바이브 코딩(Vibe Coding)**
자연어로 AI 코딩 도우미와 협업해 개발하는 방식. 이 자료에서는 "AI에게 맡기고 끝"이 아니라 **목표를 설명하고, 작게 확인하고, 검증하는 작업 습관**을 뜻합니다(1·12·35장).

**반사·반성(Reflection, Reflexion)**
에이전트가 자기 결과물을 스스로 검토하고 오류를 보정하는 패턴. "방금 답이 요구사항을 모두 만족하는지 다시 확인해 줘" 같은 요청이 대표적입니다(12·13·35장).

**벤치마크(Benchmark)**
모델·도구의 능력을 표준화된 문제로 측정하는 평가. 참고 자료일 뿐, **내 프로젝트에서 통과해야 할 테스트와 리뷰의 대체재는 아닙니다**(12·32장).

**백엔드(Backend)**
사용자 눈에는 보이지 않는 서버 쪽 로직·DB 등. 이 프로젝트는 **FastAPI**(28장).

**버킷(Bucket)**
객체 저장소의 최상위 폴더(실은 평면 컨테이너). MinIO의 `ai-do-uploads` 등(31장).

**브랜치(Branch)**
Git에서 코드 변경을 분리된 줄기로 만드는 것. `main`, `feat/xxx` 등(4장).

**비동기 작업 큐(Task Queue)**
긴 작업을 백그라운드에서 처리하는 구조. 이 프로젝트는 **Celery + Redis**(30장).

---

## ㅅ

**서버(Server)**
요청을 받아 처리하는 프로그램 또는 그 프로그램이 돌아가는 컴퓨터.

**세션(Session)**
로그인 상태 같은 "이 사용자가 지금 쓰는 중" 정보. SQLAlchemy에서는 DB 작업 단위도 세션이라고 부름(29장).

**스키마(Schema)**
데이터 구조의 정의. DB 스키마(테이블 구조), Pydantic 스키마(입력 검증) 등(8·28장).

**스트리밍(Streaming)**
데이터를 덩어리째가 아니라 한 조각씩 보내고 받는 것. **SSE**, WebSocket이 대표(9·32장).

**스트레스 테스트(Stress Test)** / **로드 테스트(Load Test)**
시스템을 많은 트래픽으로 때려서 한계를 확인하는 테스트.

**스펙 드리븐 개발(Spec-Driven Development, SDD)**
"잘 쓴 스펙"을 영구적 프롬프트로 활용해 AI 에이전트를 지휘하는 개발 방식. 이 프로젝트에서는 **이슈 본문 + ADR** 이 스펙 역할을 담당합니다(5·35장).

**서브에이전트(Subagent)**
메인 작업에서 분리된 **격리된 컨텍스트**의 보조 에이전트. 조사·리팩토링·리뷰 같은 작업에 쓰입니다(12·13·35장).

**승인 단계(Approval Step)**
민감·영향 큰 행동(쓰기·삭제·외부 호출 등)을 실행 전 사람이 승인하는 MCP capability 설계 요소. 이 프로젝트 ADR 0002의 핵심(15·32장).

**시크릿(Secret)**
API 키·DB 비밀번호·토큰처럼 노출되면 안 되는 값. `.env`·시크릿 매니저에 보관. 프롬프트·커밋·로그 유출이 가장 흔한 보안 사고(10·15·35장).

---

## ㅇ

**아티팩트(Artifact)**
빌드 결과물. 이 교육 맥락에서는 Cowork의 "재방문 가능한 페이지"를 뜻하기도 합니다.

**어댑터 패턴(Adapter)**
이질적인 인터페이스를 맞춰주는 객체.

**오케스트레이션(Orchestration)**
여러 서비스를 조율해 돌리는 행위. Docker Compose, Nx가 각자 층에서 오케스트레이터.

**원자성(Atomicity)**
트랜잭션의 "다 되거나, 다 안 되거나" 성질. ACID의 A.

**이벤트 루프(Event Loop)**
비동기 처리에서 대기 중인 작업을 차례로 실행하는 큐 구조. Node.js, 파이썬 asyncio의 심장.

**이미지(Image, Docker)**
컨테이너를 만들기 위한 "정적 빌드 정의". Dockerfile로 생성한다.

---

## ㅈ

**자동완성(Autocomplete)**
IDE가 타입 정보·문맥으로 이름·인자를 제안해 주는 기능. TypeScript·파이썬 타입힌트의 큰 효용(22장).

**자동 재시도(Auto Retry)**
일시적 실패를 견디기 위해 요청·작업을 다시 시도하는 패턴. 지수 백오프(exponential backoff)와 같이 씀.

**정규화(Normalization)**
중복을 줄이고 무결성을 높이는 테이블 설계 기법(8장).

**지속적 통합 / 배포(CI/CD)**
코드를 자주 합치고 자동으로 테스트·배포하는 관행(5·11장).

---

## ㅊ

**채널(Channel)**
데이터가 흐르는 길. Redis Pub/Sub, WebSocket 채널 등.

**체인지셋(Changeset)**
변경 단위. PR, 커밋, 마이그레이션 등이 모두 체인지셋의 일종.

---

## ㅋ

**캐시(Cache)**
자주 쓰는 데이터를 빠른 저장소에 잠깐 복사해 두는 것. 이 프로젝트 **Redis**가 담당(30장).

**커밋(Commit)**
Git에서 변경을 저장소에 기록하는 단위(4장).

**컨벤셔널 커밋(Conventional Commits)**
`feat:`, `fix:` 같은 접두로 커밋 메시지 규칙을 잡는 방식(4장).

**컨텍스트 창(Context Window)**
LLM이 한 번에 읽을 수 있는 토큰 수. 관리가 필수(32·35장).

**컨트롤러(Controller)**
MVC 용어. HTTP 요청을 받는 층. FastAPI의 Router가 이 역할.

**커넥션 풀(Connection Pool)**
DB 연결을 재사용해 성능을 올리는 구조(29장).

---

## ㅌ

**타입(Type)**
"이 값은 숫자다", "이 함수는 문자열을 받는다" 같은 정보. TypeScript·파이썬 타입힌트(22·28장).

**테스트 더블(Test Double)**
테스트용으로 실제 객체 대신 쓰는 가짜(Mock, Stub, Fake 등)(34장).

**트랜잭션(Transaction)**
여러 작업을 원자적으로 묶는 단위. DB의 `BEGIN ... COMMIT`(8·29장).

**토큰(Token)**
① 인증 토큰(JWT 등) ② LLM의 최소 단위(글자 조각).

**트리 쉐이킹(Tree Shaking)**
쓰지 않는 코드를 빌드에서 제거하는 최적화. Vite·Webpack이 자동 수행(23·27장).

**타이포스쿼팅(Typosquatting)**
유명 패키지 이름과 비슷한 **오타 패키지명** 으로 악성 라이브러리를 배포하는 공급망 공격. AI가 가상 패키지를 제안할 때도 경계(15장).

---

## ㅍ

**파라미터(Parameter)** / **아규먼트(Argument)**
함수 정의에서의 변수명 / 호출 때 넣는 실제 값.

**패러독스(Deadlock)**
여러 작업이 서로를 기다려 멈춰버리는 상황.

**포매터(Formatter)**
코드 스타일을 자동 정돈하는 도구. JS는 **Prettier**, 파이썬은 **Ruff format**(34장).

**플랜-앤-이그제큐트(Plan-and-Execute)**
작업을 **명시적 계획**으로 먼저 분해한 뒤 단계별로 실행하는 에이전트 패턴. 큰 작업을 안전하게 쪼개는 기본 방식입니다(12·35장).

**프롬프트 인젝션(Prompt Injection)**
사용자 입력·외부 문서가 LLM 시스템 지시를 **덮어쓰는** 공격. 에이전트의 도구 권한이 클수록 피해 큼. 최소 권한 원칙과 approval 단계로 방어(15·32장).

**프런트엔드(Frontend)**
사용자 화면 쪽. 이 프로젝트는 **React 19 + Vite**(23장).

**프리사인드 URL(Presigned URL)**
객체 저장소에 **일시 접근**을 허용하는 서명된 링크(31장).

---

## ㅎ

**헤드리스 UI(Headless UI)**
동작은 제공하고 **스타일은 우리가 붙이는** 라이브러리. 이 프로젝트는 **Radix UI**, **TanStack Table**(24·27장).

**환경 변수(Environment Variable)**
실행 환경마다 바뀌는 값(DB 주소, 비밀번호 등). `.env` 파일에 저장(28·33장).

**환각(Hallucination)**
LLM이 **그럴듯하지만 사실이 아닌 것** 을 만들어 내는 현상. 라이브러리 API·파일 경로에서 특히 자주 발생. 검증 없이 믿지 말 것(12·13장).

**훅(Hook)**
두 의미: ① React에서 상태·생애주기를 함수 안에서 쓰는 API (`useState`, `useEffect` — 23장). ② 특정 이벤트가 발생했을 때 자동 실행되는 스크립트나 콜백(35장).

---

## A–Z

**ACID**
Atomicity, Consistency, Isolation, Durability. 트랜잭션의 4대 보증(8·29장).

**ACP (Agent Client Protocol)**
에이전트를 특정 에디터에 묶지 않고 연결하려는 프로토콜 계열의 개념입니다. 이 자료에서는 세부 표준보다 "도구가 바뀌어도 작업 루프를 유지한다"는 관점이 더 중요합니다(35장).

**ADR (Architecture Decision Record)**
아키텍처 결정의 근거를 짧게 기록한 문서. 이 프로젝트에서는 `adr/` 아래의 결정 문서를 기준으로 삼습니다(7장).

**API (Application Programming Interface)**
프로그램 간 약속된 호출 규격(9·28장).

**ASGI**
Asynchronous Server Gateway Interface. 파이썬 비동기 웹의 표준. FastAPI + Uvicorn이 이 규격(28장).

**CDN (Content Delivery Network)**
정적 파일을 세계 여러 곳 엣지 서버에 복사해 빠르게 전달하는 서비스.

**Context Design (작업 맥락 설계)**
에이전트가 작동하는 **전체 정보 환경**(시스템 프롬프트·맥락 파일·도구·메모리·외부 자료)을 정리하는 개념(12·14·35장).

**CRDT (Conflict-free Replicated Data Type)**
여러 사용자가 동시에 편집해도 자동으로 병합되는 자료구조. **Yjs**가 구현체(26장).

**CSR / SSR**
클라이언트 렌더링 / 서버 렌더링. 이 프로젝트는 CSR(SPA).

**DB (Database)**
데이터 저장소. 이 프로젝트는 **PostgreSQL 18**(29장).

**DDD (Domain-Driven Design)**
비즈니스 도메인을 코드 구조의 중심축으로 두는 설계 방식(7·25장).

**DI (Dependency Injection)**
필요한 부품을 바깥에서 넣어 주는 방식. FastAPI `Depends`, SQLAlchemy 세션 주입(28장).

**DSN (Data Source Name)**
DB 접속 문자열. `postgresql+psycopg://...`(29장).

**E2E (End-to-End)**
처음부터 끝까지 사용자 시나리오를 자동 테스트하는 것. **Playwright**(34장).

**GFM (GitHub Flavored Markdown)**
테이블·체크박스 같은 확장을 포함한 GitHub의 마크다운 변형(27장).

**HTTP / HTTPS**
웹의 통신 규약 / TLS로 암호화된 HTTP(9·33장).

**IDE (Integrated Development Environment)**
VS Code 같은 통합 개발 도구.

**JSON / JSONB**
JavaScript 객체 문자열 포맷 / PostgreSQL의 이진 JSON 타입(29장).

**JWT (JSON Web Token)**
서명된 토큰으로 인증 정보를 담는 형식(9장).

**LLM (Large Language Model)**
대규모 언어 모델. AI 채팅과 코드 생성 도구의 "두뇌" 역할을 합니다(12·32장).

**MCP (Model Context Protocol)**
LLM이 외부 도구·데이터에 일관된 방식으로 접근하기 위한 프로토콜. 권한·미리보기·승인·감사 설계와 함께 써야 안전합니다(12·32장).

**MCP Capability**
이 프로젝트 ADR 0002가 정의한 **MCP-first capability** 단위. human-friendly REST DTO + AI-friendly Pydantic DTO 분리, discoverability·preview·approval 내장(32장).

**MoE (Mixture of Experts)**
여러 특화된 작은 모델(expert) 중 필요한 것만 활성화하는 LLM 아키텍처(12장).

**N+1 문제**
ORM에서 부모 목록을 한 번 가져오고 자식 데이터를 N번 더 가져오는 비효율 패턴(29장).

**NFR (Non-Functional Requirement)**
기능 외 요구사항(성능·보안·가용성 등)(6장).

**ORM (Object-Relational Mapping)**
테이블을 객체처럼 다루게 해 주는 라이브러리. **SQLAlchemy**(8·29장).

**OWASP**
웹 보안 모범 사례를 모은 단체·문서(10장).

**PII (Personally Identifiable Information)**
이메일·전화번호·주민번호 등 개인 식별 정보. 로그·프롬프트·외부 채널 유출 금지(15장).

**Plugin**
여러 기능, 지침, 도구 연결을 묶어 배포하는 확장 단위(35장).

**PR (Pull Request / Merge Request)**
코드 변경을 제안하고 리뷰받아 병합하는 절차(4·35장).

**RAG (Retrieval Augmented Generation)**
검색된 문서를 LLM 프롬프트에 넣어 답변 정확도를 높이는 기법(12·32장).

**RBAC (Role-Based Access Control)**
역할 기반 접근 제어. 사용자 역할(admin, member, viewer 등)에 따라 화면·API 권한을 나누는 방식(15장).

**ReAct (Reason + Act)**
"생각 → 행동 → 관찰 → 재사고"를 반복하는 에이전트의 기본 루프. Reflection·Plan-and-Execute·Multi-Agent의 기반 패턴(12·32장).

**REST (Representational State Transfer)**
HTTP 자원 기반의 API 스타일. `/users/1`, `POST /posts`(9장).

**RPC (Remote Procedure Call)**
원격 함수 호출 스타일. gRPC가 대표(9장).

**SDD (Spec-Driven Development)**
"스펙"을 영구적 프롬프트로 활용하는 개발 방식. 이슈 본문, PR 본문, ADR, 테스트 이름이 스펙 역할을 할 수 있습니다(5·14·35장).

**SDK (Software Development Kit)**
어떤 서비스·플랫폼을 다루기 위한 라이브러리 묶음. OpenAI SDK 등(32장).

**코딩 벤치마크(Coding Benchmark)**
실제 코드 수정 과제를 기반으로 LLM 코딩 능력을 측정하는 벤치마크 계열. 참고 자료일 뿐, 우리 프로젝트의 테스트와 리뷰를 대신하지 않습니다(12·32장).

**Skills**
재사용 가능한 작업 지침이나 절차를 묶어 둔 파일·기능. 반복 작업을 표준화할 때 사용합니다(35장).

**SOLID**
객체 지향 설계의 5원칙(단일 책임·개방-폐쇄·리스코프·인터페이스 분리·의존 역전)(7장).

**SPA (Single Page Application)**
한 HTML 페이지에서 자바스크립트가 화면 전환을 처리하는 앱(23·25장).

**SQL**
관계형 DB의 표준 질의 언어(8·29장).

**SSE (Server-Sent Events)**
서버가 클라이언트로 이벤트를 스트리밍하는 HTTP 기반 방식(9·32장).

**TDD (Test-Driven Development)**
실패 테스트 → 구현 → 리팩토링 순환 개발(10·34장).

**TLS / SSL**
네트워크 전송 암호화. HTTPS의 기반(33장).

**TTL (Time To Live)**
데이터의 유효 기간. Redis 키 만료 등에 사용(30장).

**UUID**
중복 없는 128비트 식별자. `b9d2-...` 같은 문자열.

**UX / UI**
User Experience / User Interface. 경험 / 인터페이스(24장).

**WAL (Write-Ahead Log)**
쓰기를 먼저 로그에 기록해 장애에 대비하는 DB 기법(29장).

**WebSocket**
양방향 지속 연결. 실시간 협업·채팅에 사용(9·26장).

**Y.js / Y-WebSocket**
JavaScript CRDT 구현과 WebSocket 동기화 서버(26장).

---

## 마치며

이 사전은 완전하지 않습니다. 공부하다 모르는 단어를 만나면 이 파일에 직접 추가하세요. 팀이 함께 늘려가는 **살아 있는 사전** 이 되는 것이 이 자료의 궁극적 목표입니다.
