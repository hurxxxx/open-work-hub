# API App

FastAPI 기반의 조립 계층이다. 현재 스캐폴드는 아래를 제공한다.

- 앱 팩토리와 설정 로딩
- health endpoint
- mlx-lm (Apple Silicon) / OpenAI 호환 LLM 연결과 readiness endpoint
- 문서 검색, PLM 조회, 템플릿/초안, 위키 페이지의 최소 placeholder endpoint
- 도메인 루트와 local rule 파일

실행:

```bash
cp .env.example .env
pnpm nx dev api
```

LLM 설정은 **로컬 풀**(Apple Silicon mlx-lm)과 **외부 풀**(OpenRouter)로 완전히 분리되어
있다. 어느 풀을 쓸지는 `task_kind` 별 DB 정책(`LlmPolicy`)이 결정하며, 기본 정책은
`local_only`다. 로컬 장애 시 외부로 자동 폴백하지 않는다 ([`plans/00-ai-platform-roadmap.md`](../../plans/00-ai-platform-roadmap.md) 참조).

로컬 mlx-lm 서버 구동:

```bash
bash scripts/mlx-serve.sh          # foreground
nohup bash scripts/mlx-serve.sh &  # background
```

최초 실행 시 `~/.local/share/mlx-lm-venv`에 venv를 만들고 `mlx-lm`을 설치한다.
모델(약 19GB)은 `~/.cache/huggingface` 로 첫 요청 시 캐시된다.

```env
# Local pool
DOOWON_LLM_LOCAL_PROVIDER=mlx-lm
DOOWON_LLM_LOCAL_BASE_URL=http://127.0.0.1:8080/v1
DOOWON_LLM_LOCAL_API_KEY=mlx
DOOWON_LLM_LOCAL_DEFAULT_MODEL=mlx-community/Qwen3.6-35B-A3B-4bit
DOOWON_LLM_LOCAL_CANONICAL_MODEL=qwen/qwen3.6-35b-a3b
DOOWON_LLM_LOCAL_LONG_GENERATION_TIMEOUT_SECONDS=1200

# External pool
DOOWON_LLM_EXTERNAL_ENABLED=true
DOOWON_LLM_EXTERNAL_PROVIDER=openrouter
DOOWON_LLM_EXTERNAL_BASE_URL=https://openrouter.ai/api/v1
DOOWON_LLM_EXTERNAL_DEFAULT_MODEL=qwen/qwen3.5-35b-a3b
DOOWON_LLM_EXTERNAL_API_KEY=          # OPENROUTER_API_KEY로도 대체 가능
DOOWON_LLM_EXTERNAL_LONG_GENERATION_TIMEOUT_SECONDS=900
```

기존 `DOOWON_LLM_*` / `DOOWON_LLM_FALLBACK_*` 환경변수는 Phase 3 kickoff 전까지
alias로 계속 인식된다. 특히 예전 shared 값이던
`DOOWON_LLM_CANONICAL_MODEL`, `DOOWON_LLM_LONG_GENERATION_TIMEOUT_SECONDS` 는
local/external 양쪽 풀의 fallback alias 로 함께 해석된다.

준비 상태 확인:

```bash
curl http://127.0.0.1:8000/readyz               # 무인증, 현재 정책 기준의 실제 AI readiness
curl http://127.0.0.1:8000/api/v1/ai/health     # 인증 필요, raw local/external pool health
```

`/api/v1/ai/chat` 등 AI 엔드포인트는 app-level dependency 체인으로
`require_current_user` + workspace membership 검증 뒤에만 mount된다.

## 데이터베이스 마이그레이션 (Alembic)

스키마는 Alembic 이 단독 소유한다. `Base.metadata.create_all()` 과 손으로 만든
`_apply_postgres_schema_compat()` SQL 리스트는 `0b843a383b2b_baseline_2026_04_10`
리비전으로 baseline 화 되었다 (PR0).

### 일상 워크플로

```bash
cd apps/api

# 1. 모델 변경 후 마이그레이션 자동 생성
DOOWON_POSTGRES_DSN=postgresql+psycopg://aidoo_db:aidoo_db@127.0.0.1:5432/doowon_ai_portal \
  uv run --python 3.12 alembic revision --autogenerate -m "add_meeting_tables"

# 2. 생성된 alembic/versions/<hash>_*.py 파일을 반드시 손으로 검토
#    autogenerate 가 잡지 못하는 변경 (테이블/컬럼 rename, server_default, CHECK 등) 보강
# 3. 로컬에 적용
uv run --python 3.12 alembic upgrade head

# 4. 직전 리비전 되돌리기 (개발 중에만)
uv run --python 3.12 alembic downgrade -1
```

### 환경별 적용 방법

| 환경 | 방법 |
| --- | --- |
| 로컬 dev / 테스트 | `DOOWON_API_AUTO_MIGRATE=1` 환경변수를 켜면 앱 부팅 시 `init_db()` 가 자동으로 `alembic upgrade head` 를 호출한다. 테스트 fixture (`apps/api/tests/conftest.py`) 가 이 방식을 사용한다. |
| 스테이징 / 프로덕션 | **자동 실행 금지.** 배포 스크립트에서 명시적으로 `alembic upgrade head` 를 실행한 뒤 앱을 기동한다. `DOOWON_API_AUTO_MIGRATE` 는 prod 에서 절대 켜지 말 것. |
| Alembic 도입 이전부터 운영 중인 기존 DB | 한 번만 `alembic stamp head` 로 baseline 적용 표시. 이후부터 일반 워크플로 따르면 된다. baseline 은 새 컬럼/테이블만 다루므로 기존 row 는 손실 없음. 다만 legacy `pms_goals`, `pms_goal_links`, `pms_automations` 는 baseline 이 더 이상 다루지 않으므로 필요하면 수동 DROP. |

### 모델 드리프트 가드

`apps/api/tests/test_alembic_migrations.py` 의 `test_alembic_check_reports_no_model_drift`
가 매 테스트 실행마다 `alembic check` 를 돌려, SQLAlchemy 모델 변경이 마이그레이션
없이 머지되는 것을 막는다. 모델만 바꾸고 마이그레이션을 깜빡하면 CI 가 빨개진다.
