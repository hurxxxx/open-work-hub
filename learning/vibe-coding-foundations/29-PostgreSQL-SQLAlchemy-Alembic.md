# 29. PostgreSQL · SQLAlchemy · Alembic — 데이터 계층의 삼총사

> **한 줄 요약.** 데이터는 **PostgreSQL**에 안전하게 저장하고, 파이썬에서는 **SQLAlchemy** 라는 ORM으로 SQL을 직접 쓰지 않고 접근하며, 테이블 구조를 바꿀 때는 **Alembic**으로 이력을 남기며 마이그레이션한다.

> **🔑 한 마디로.** PostgreSQL(저장 엔진), SQLAlchemy(ORM), Alembic(스키마 버전 관리)을 함께 사용해 데이터 저장·접근·변경 이력을 일관되게 관리하는 구성입니다.

### 데이터 계층 3요소 역할 정리

- PostgreSQL은 영속 저장을 담당하고, SQLAlchemy는 Python 객체와 SQL 간 매핑을 담당하며, Alembic은 스키마 변경 이력을 파일로 관리합니다.
- ACID는 트랜잭션의 원자성·일관성·격리성·지속성을 보장해 데이터 무결성을 유지합니다.
- Alembic 마이그레이션은 스키마 변경 절차를 단계별로 기록해 환경 간 불일치와 데이터 유실 위험을 줄입니다.

### ⚠️ 데이터 계층에서 자주 하는 오해

- **"ORM을 쓰면 SQL을 아예 몰라도 된다"** — 성능 문제(N+1, 인덱스 미사용)를 잡으려면 ORM이 생성한 SQL을 읽을 줄 알아야 합니다. ORM은 **SQL을 가리는 게 아니라 다듬어 주는 것**입니다.
- **"PostgreSQL은 MySQL과 거의 똑같다"** — JSONB 1급 지원, 트랜잭션 격리의 일관성, `pgvector` 같은 확장 생태계에서 구조적으로 다릅니다.
- **"Alembic `upgrade head`만 돌리면 안전하다"** — `autogenerate`가 만든 파일을 **사람이 반드시 검토**해야 합니다. 컬럼 이름 변경을 "삭제 후 추가"로 잘못 추론하면 데이터가 유실됩니다.
- **"DB 스키마는 한 번 잘 설계하면 바꿀 일 없다"** — 제품이 살아 있는 한 계속 바뀝니다. 그래서 마이그레이션이 **핵심 인프라**입니다.
- **"SQLAlchemy 1.x와 2.0은 사소한 차이"** — 2.0은 `Mapped[...]` 타입 힌트, 새 `select()` 스타일, 세션 패턴이 크게 달라졌습니다. 우리 프로젝트는 2.0 신문법을 씁니다.

---

## 1. 왜 이 세 가지가 함께 다니는가

8장에서 데이터베이스를 개괄했다면, 이번 장은 **이 프로젝트가 실제로 쓰는 도구** 이야기입니다.

- **PostgreSQL**(일반적으로 16/17 공식 Docker 이미지) — 저장소 엔진. 실제 데이터가 사는 집.
- **SQLAlchemy 2.0** — 파이썬 코드에서 DB를 다루는 **ORM(Object-Relational Mapper, 객체-관계 매퍼)**. 이 프로젝트는 2.x 스타일을 기준으로 설명합니다.
- **Alembic 1.16** — DB 스키마를 바꿀 때 쓰는 **마이그레이션(스키마 변경 이력 관리) 도구**. SQLAlchemy 팀이 함께 만든 공식 보조 도구.
- 드라이버는 **psycopg 3.2**(binary extras 포함) 사용 — 과거의 `psycopg2`가 아님. 동기/비동기 모두 한 드라이버에서 지원.

세 도구는 서로 맞물려 설계됐기에 궁합이 매우 좋습니다.

---

## 2. PostgreSQL — "가장 정통한" 오픈소스 RDBMS

### 2.1 역사

- 1986년 UC 버클리의 Postgres 프로젝트 → 1996년 SQL 추가로 PostgreSQL.
- 30년 넘는 역사. "세상에서 가장 발전된 오픈소스 관계형 DB"가 공식 슬로건.
- Oracle·SQL Server 같은 상용 RDBMS에 기능적으로 필적하며, 완전 오픈소스.

### 2.2 특징

- **ACID 완벽 지원** — 금전 등 강한 일관성이 필요한 데이터도 안심.
- **강력한 타입 시스템** — `JSONB`, `ARRAY`, `UUID`, `INET`, `TSVECTOR`(전문검색) 등 실용 타입.
- **확장(Extension) 생태계** — `pgvector`(벡터 검색, RAG에 유용), `postgis`(지리), `pg_trgm`(유사 검색).
- **윈도우 함수, CTE, 부분 인덱스** 등 고급 SQL 기능.
- **복제·백업** 도구들(WAL, 스트리밍 복제, Point-in-Time Recovery).

### 2.3 왜 MySQL이 아니고 PostgreSQL인가

| 기준 | MySQL | PostgreSQL |
|---|---|---|
| 역사 | 1995, 읽기 성능 명성 | 1996, 표준 준수·기능 풍부 |
| JSON | 보조적 | `JSONB` 1급 지원 |
| 제약조건 | 역사적으로 약함(개선 중) | 엄격 |
| 트랜잭션 격리 | 구현이 엔진별(InnoDB 등) | 일관된 MVCC |
| AI 확장 | — | `pgvector`(벡터 검색) |

**AI 허브**에는 **pgvector**가 큰 이점입니다. 문서 임베딩을 저장해 RAG 검색을 할 때, 별도의 벡터 DB 없이 PostgreSQL 하나로 해결할 수 있습니다.

### 2.4 이 프로젝트에서의 용도

- 사용자, 워크스페이스, 문서 메타데이터, 이슈, 회의, 캘린더 이벤트 등 **모든 영속 데이터**.
- Celery 결과 저장(부분적)·감사 로그.
- 필요 시 `pgvector`로 임베딩 저장.

`docker-compose.yml` 에는 공식 `postgres` 이미지(통상 16 또는 17 태그)로 뜨며, `POSTGRES_USER`, `POSTGRES_DB` 환경변수로 초기화됩니다.

### 2.5 대안

- **MySQL / MariaDB** — 여전히 많이 쓰이나, 기능 균형은 PG가 우세.
- **SQLite** — 파일 한 개 DB. 로컬 개발·모바일에 훌륭. 서버 앱엔 부적합.
- **CockroachDB / YugabyteDB** — 분산 RDBMS. PG 호환. 대규모에서 유용.
- **MongoDB(NoSQL)** — 스키마가 자주 바뀌는 문서 저장엔 좋음. 관계·트랜잭션 약점.
- **Supabase / Neon / Aurora Postgres** — 관리형 PostgreSQL. 우리는 사내 운영이 필요해 자체 Docker 이미지를 사용하지만, 장기적으로 이중화 옵션으로 고려 가능.

### 2.6 🏢 업무 시나리오

**케이스 — 관리자 콘솔 "감사 로그(audit log) 검색"**
- 로그 행에 "누가·언제·어떤 IP로·무엇을 했는지"를 JSONB 컬럼(`details`)에 저장.
- `SELECT * FROM audit_logs WHERE details @> '{"action":"doc.delete"}'` 한 줄로 특정 행위만 조회. JSON 안의 키-값을 **인덱스**로 빠르게 찾는 것은 PostgreSQL의 GIN 인덱스 덕분.
- MySQL에서는 동일 기능을 우회적으로 구현해야 하는 경우가 많고 성능도 열세입니다.

---

## 3. ORM — "SQL을 객체로 쓴다"

### 3.1 ORM이 없을 때

```python
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
row = cur.fetchone()
user = {"id": row[0], "email": row[1]}
```

- SQL을 문자열로 쓰고
- 결과를 수동으로 꺼내 객체로 변환
- 수십 개 테이블을 이렇게 쓰면 반복이 엄청남
- SQL 문자열 조립은 **SQL 인젝션** 위험의 원흉

### 3.2 ORM이 있을 때 (SQLAlchemy)

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)

user = session.get(User, user_id)
print(user.email)
```

- 테이블이 파이썬 **클래스**
- 행이 파이썬 **객체**
- 쿼리가 파이썬 식

### 3.3 ORM의 장단점

**장점**:
- 반복 감소, 타입 안정, IDE 자동완성.
- 여러 DB 엔진 이식성.
- 파라미터 바인딩으로 **SQL 인젝션 방어** 자동.

**단점**:
- 생성되는 SQL이 가려져 성능 튜닝이 까다로울 때 있음(N+1 문제 등).
- 매우 복잡한 쿼리는 결국 raw SQL이 더 깔끔.

**결론**: 기본은 ORM, 필요 시 raw SQL을 섞는 하이브리드가 현실적입니다. SQLAlchemy는 이 혼합을 잘 지원합니다.

---

## 4. SQLAlchemy 2.0 — 파이썬 ORM의 표준

### 4.1 특징

- 파이썬 DB 생태계의 사실상 표준.
- **Core**(SQL Expression Language) + **ORM** 두 층.
- 2.0부터 **타입 힌트 친화**로 대대적 개편. `Mapped[...]` 문법.
- 비동기(async) 지원 성숙.

### 4.2 이 프로젝트의 모델 (개념 예시)

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, ForeignKey
from datetime import datetime
from .base import Base

class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str]
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
```

### 4.3 쿼리 — 기본

```python
# 단건
user = session.get(User, 1)

# 조건
from sqlalchemy import select
stmt = select(User).where(User.email == "a@x.com")
user = session.scalars(stmt).first()

# 조인
stmt = (
  select(User, Workspace)
  .join(Workspace, User.workspace_id == Workspace.id)
  .where(Workspace.slug == "doowon-hq")
)
rows = session.execute(stmt).all()
```

### 4.4 세션과 트랜잭션

- `Session`은 "작업 단위(Unit of Work)". 변경을 모아 `commit()` 시점에 SQL로 내보냅니다.
- 요청당 한 개 세션을 생성해 주입 → FastAPI의 `Depends`와 조합.

```python
def get_session():
    with SessionLocal() as session:
        yield session

@router.get("/users/{id}")
def get_user(id: int, session: Session = Depends(get_session)):
    return session.get(User, id)
```

### 4.5 N+1 문제와 해결

"사용자 100명을 가져온 뒤 각자의 워크스페이스 이름을 100번 조회" → 100+1번의 SQL.

해결: `selectinload`·`joinedload` 등의 **eager loading**.

```python
stmt = select(User).options(selectinload(User.workspace))
```

실무에서 N+1은 가장 흔한 ORM 성능 문제이니 기억해 두면 좋습니다.

### 4.6 레포지토리 패턴과 함께

7장의 DDD처럼, 이 프로젝트에서는 **Router → Service → Repository → Model** 흐름으로 분리하는 패턴을 씁니다. Router는 HTTP만, Service는 비즈니스 로직, Repository는 DB 접근을 담당합니다. SQLAlchemy 세션은 Repository 안에서만 쓰고 Service 계층엔 드러내지 않는 편이 깔끔합니다.

### 4.7 🏢 업무 시나리오

**케이스 — PMS "이슈 목록 + 담당자 + 코멘트 수" 한 번에 조회**
- 순진한 구현: 이슈 50건 → 각각 담당자 조회(50 쿼리) + 각각 코멘트 수 COUNT(50 쿼리) = 101회. 이것이 **N+1 문제**.
- 개선: `selectinload(Issue.assignee)` + 집계 서브쿼리 한 방으로 3회 이내. 응답 시간이 2~3초 → 200ms.
- 체감 효과가 큰 대표 사례. 실제 운영에서 "왜 느릴까?"의 80%는 N+1입니다.

---

## 5. Alembic — 스키마 변경 이력 관리

### 5.1 왜 마이그레이션 도구가 필요한가

앱이 발전하면 테이블 구조가 바뀝니다.

- "users에 `avatar_url` 컬럼 추가"
- "documents 테이블에 `deleted_at` 소프트 삭제 컬럼 추가"
- "index 추가/제거"

이 변경을 **코드 변경과 함께 기록**하지 않으면, 개발/스테이징/운영 DB가 점점 달라져 사고가 납니다.

Alembic은 그 이력을 **파일로 버전 관리**합니다. Git과 유사하게 DB 변경을 커밋 단위로 관리합니다.

### 5.2 작동 방식

1. `alembic revision --autogenerate -m "add avatar_url"` 로 모델과 DB의 차이를 감지해 **마이그레이션 파일** 생성.
2. 파일 안에 `upgrade()`/`downgrade()` 함수로 변경을 표현.
3. `alembic upgrade head` 로 DB에 적용. `alembic downgrade -1` 로 되돌리기도 가능.
4. 적용된 버전은 DB의 `alembic_version` 테이블에 기록.

### 5.3 마이그레이션 파일 예시

```python
"""add avatar_url to users
Revision ID: 3a1e2b...
Revises: 0cd4f9...
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))

def downgrade():
    op.drop_column("users", "avatar_url")
```

### 5.4 이 프로젝트의 마이그레이션

`apps/api/alembic/` 밑에 `env.py`, `versions/` 폴더가 있고, 각 버전은 파일 하나. 배포 파이프라인은 앱을 띄우기 전 `alembic upgrade head` 를 실행해 DB를 최신 상태로 만듭니다.

### 5.5 마이그레이션 팁

- **autogenerate 결과를 반드시 눈으로 검토** — 누락이나 과잉 변경 있을 수 있음.
- **파괴적 변경**(컬럼 삭제·이름 변경)은 두 단계로: 추가 → 코드 이전 → 삭제.
- **데이터 변환**이 필요한 경우 마이그레이션 파일 안에서 수행.
- 여러 개발자가 동시에 revision을 만들면 **브랜치**가 생김. `alembic merge`로 합칩니다.

### 5.6 대안

- **Django ORM + migrations** — 장고 프레임워크에 내장. 장고 안에서만.
- **Prisma Migrate** — 노드 생태계 중심. 선언형.
- **Flyway / Liquibase** — JVM 생태계 표준. 언어 독립적이며 Python 프로젝트에서도 쓸 수 있음.
- **수동 SQL 파일 버전 관리** — 초소형엔 가능하지만 금방 한계.

Python 생태계에서 Alembic은 사실상 표준입니다.

### 5.7 🏢 업무 시나리오

**케이스 — "채팅 메시지에 reaction(이모지) 기능 추가"**
1. `chat_messages` 모델에 `reactions: Mapped[dict] = mapped_column(JSONB, default=dict)` 추가.
2. `alembic revision --autogenerate -m "add reactions to chat_messages"` 실행.
3. 생성된 버전 파일의 `upgrade()` 검토 — "add_column" 한 줄인지 확인.
4. 개발 DB에서 `alembic upgrade head`, 이상 없으면 PR.
5. 스테이징·운영 배포 파이프라인이 자동으로 동일 명령을 실행 → 모든 환경의 스키마가 동기화.

실수로 revision을 만들지 않고 모델만 고치면, 운영 배포 시 "ProgrammingError: column reactions does not exist"가 터집니다. Alembic이 "모델 변경 = 스키마 변경 = 버전 파일"을 강제해 이 사고를 예방합니다.

### 5.8 🛠️ 5분 실습

1. `apps/api/alembic/versions/` 폴더를 열어 최근 마이그레이션 파일 하나를 읽어 봅니다.
2. `upgrade()`와 `downgrade()` 두 함수가 대칭을 이루는지, 어떤 SQL 명령으로 번역될지 상상해 봅니다.
3. `alembic history` 명령으로 체인을 확인. 각 revision이 앞 revision을 가리키는 **링크드 리스트** 구조임을 체감.

---

## 6. 연결·풀·환경

### 6.1 연결 문자열 (DSN, Data Source Name)

```
postgresql+psycopg://user:pass@host:5432/dbname
```

- `psycopg`는 Python용 PostgreSQL 드라이버. 우리는 v3(psycopg 3.2, binary extras). v2(`psycopg2`)와 이름이 비슷하지만 별개 패키지.
- 비동기: `postgresql+asyncpg://...` 또는 psycopg3의 비동기 모드.

### 6.2 커넥션 풀

DB 연결을 매 요청마다 새로 만들지 않고 **풀(pool)에서 재사용** 합니다. SQLAlchemy의 기본 `QueuePool`이 자동으로 처리.

### 6.3 환경 변수

`.env` 에 DSN, DB 비밀번호 같은 민감 값을 저장. 앱은 Pydantic `Settings`로 이를 읽습니다(28장).

---

## 7. 인덱스와 성능의 기초

### 7.1 인덱스란

특정 컬럼 조건 조회를 빠르게 수행하기 위한 별도 자료구조입니다. `B-Tree`가 기본입니다.

- 자주 `WHERE` 되는 컬럼에 인덱스.
- 너무 많으면 쓰기가 느려짐.

### 7.2 쿼리 실행계획

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'x@y.com';
```

`Seq Scan`(전체 스캔) 대신 `Index Scan`이 나오는지 확인. 대규모에서는 이 습관이 곧 성능.

### 7.3 PostgreSQL만의 강력 인덱스

- **GIN** — JSONB, 전문검색.
- **GiST / SP-GiST** — 기하·범위.
- **pgvector(HNSW)** — 벡터 유사도.

---

## 8. 백업 · 복구의 개념

### 8.1 논리 백업

`pg_dump`로 SQL 파일 생성. 소규모·이식성에 유리.

### 8.2 물리 백업

`pg_basebackup` + WAL(Write-Ahead Log). 대규모·정확 시점 복구(PITR)에 유리.

### 8.3 운영 권장

- **매일 덤프** + **WAL 아카이빙**.
- 복구 연습(restore test)을 주기적으로 — "백업은 해 봤는데 복구는 안 해 봤다"가 가장 큰 함정.

---

## 9. 핵심 요약

- **PostgreSQL** — 기능·표준 준수가 우수한 오픈소스 RDBMS. AI 시대엔 `pgvector`도 큰 이점.
- **SQLAlchemy 2.0** — 파이썬 ORM의 표준. `Mapped` 기반 타입 친화 API.
- **Alembic** — 스키마 변경을 버전 관리해 주는 마이그레이션 도구.
- 이 프로젝트는 **Router → Service → Repository → Model** 흐름으로 DB 접근을 분리.
- N+1, 인덱스, 백업·복구는 "ORM을 써도" 항상 신경 써야 할 기본.
