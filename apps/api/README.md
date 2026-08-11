# API App

FastAPI 기반의 조립 계층이다. 현재 API는 아래를 제공한다.

- 앱 팩토리와 설정 로딩
- health endpoint
- vLLM / mlx-lm 등 OpenAI 호환 LLM 연결과 readiness endpoint
- retrieval/search, 템플릿/초안, 문서, PMS 등 범용 도메인 API
- 도메인 루트와 local rule 파일

저장소 루트에서 개발 서버 실행:

```bash
./dev.sh --api-only
```

로컬 개발 환경은 루트 `.env.example`의 안전한 예시를 기준으로 별도의 `.env`를 구성한다.
비밀값과 운영 데이터는 저장소에 커밋하지 않는다.

LLM 설정은 **로컬 풀**(vLLM 또는 Apple Silicon mlx-lm)과
**외부 풀**(OpenAI/Anthropic/Gemini 공식 API)로 분리되어 있다.
어느 풀을 쓸지는 등록된 workload와 관리자의 명시적 override가 결정한다. 로컬 장애 시
외부로 자동 폴백하지 않는다.

local LLM runtime 계약은
[`AI gateway 문서`](../../docs/domains/ai/gateway.md)를 정본으로 본다.
endpoint는 private network와 firewall/ACL로 보호된 운영 전제를 가진다. vLLM 자체는
API key를 검증하지 않으므로 public network에 직접 노출하면 안 된다. 애플리케이션의 local
endpoint와 기본 모델은 관리자가 `LLM 관리 > Provider`에서 탐색·승인 후 명시적으로 선택한다.
`.env.example`에는 기본 모델명을 중복 기록하지 않는다.

개인 장비에서 로컬 mlx-lm 서버를 구동해야 하는 경우 모델을 명시한다.

```bash
MLX_MODEL=org/local-model-id \
bash scripts/mlx-serve.sh
```

최초 실행 시 `~/.local/share/mlx-lm-venv`에 venv를 만들고 `mlx-lm`을 설치한다.
모델은 `~/.cache/huggingface`로 첫 요청 시 캐시된다. 아래 값은 개인 장비용 예시이며
공유 dev 또는 운영 기본값이 아니다. 모델별 chat template option이 필요한 경우에만
`MLX_CHAT_TEMPLATE_ARGS`로 명시한다.

```env
# Local pool (mlx-lm alternative)
OPEN_WORK_HUB_LLM_LOCAL_PROVIDER=mlx-lm
OPEN_WORK_HUB_LLM_LOCAL_BASE_URL=http://127.0.0.1:8080/v1
OPEN_WORK_HUB_LLM_LOCAL_API_KEY=mlx
OPEN_WORK_HUB_LLM_LOCAL_LONG_GENERATION_TIMEOUT_SECONDS=1200

# External pool
OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS=openai,anthropic,gemini
OPEN_WORK_HUB_LLM_EXTERNAL_LONG_GENERATION_TIMEOUT_SECONDS=900
```

외부 LLM provider API key는 환경 변수로 전달하지 않는다. 관리자가 Admin의
AI 모델 설정에서 provider별 credential을 입력하면 DB에 암호화해 저장한다.
환경에는 저장 credential을 암복호화하는
`OPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`만 설정한다.

이미지 생성 provider와 LLM provider는 서로 다른 제어면을 사용한다. 관리자는
Admin의 `LLM 관리 > 이미지 모델`에서 이미지 provider endpoint, API key,
supervisor 모델, generation 모델과 실행 프로필을 명시적으로 설정한다. 이미지
provider API key와 모델명은 환경 변수에 두지 않으며, 같은 credential 암호화 키만
재사용한다. `OPEN_WORK_HUB_IMAGE_ENABLED`는 배포 kill switch이고 파일 크기·reference 수·
timeout은 운영 한도로 유지한다. 모델 설정이 없으면 이미지 실행은 fail-closed 한다.

준비 상태 확인:

```bash
curl http://127.0.0.1:8001/readyz                 # dev, 무인증 AI readiness
```

인증된 pool health endpoint는
`/api/v1/workspaces/{workspace_slug}/chatbot/health`다.

기본 API 포트는 `8000`이며 배포 환경에서는 리버스 프록시와 health check를 별도로 구성한다.

`/api/v1/workspaces/{workspace_slug}/chatbot/chat` 등 AI 엔드포인트는 app-level dependency 체인으로
`require_current_user` + workspace membership 검증 뒤에만 mount된다.

## 데이터베이스 마이그레이션 (Alembic)

스키마는 Alembic 이 단독 소유한다. `Base.metadata.create_all()` 과 손으로 만든
`_apply_postgres_schema_compat()` SQL 리스트는 `0b843a383b2b_baseline_2026_04_10`
리비전으로 baseline 화 되었다.

### 일상 워크플로

```bash
cd apps/api

# 1. 현재 checkout의 typed env가 가리키는 조정된 개발 DB에서만 자동 생성
uv run --python 3.12 alembic revision --autogenerate -m "add_meeting_tables"

# 2. 생성된 alembic/versions/<hash>_*.py 파일을 반드시 손으로 검토
#    autogenerate 가 잡지 못하는 변경 (테이블/컬럼 rename, server_default, CHECK 등) 보강
# 3. 로컬에 적용
uv run --python 3.12 alembic upgrade head

# 4. 직전 리비전 되돌리기 (개발 중에만)
uv run --python 3.12 alembic downgrade -1
```

### 환경별 적용 방법

| 환경                                    | 방법                                                                                                                                                                                                                                                                         |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 서버 dev checkout | `./dev.sh`의 migration 검증과 현재 dev 환경 계약을 따른다. 공유 DB drift를 발견하면 stamp하지 말고 `open-work-hub-development-environment` 절차로 조사한다. |
| 로컬 개발자 머신 | 공유 dev DB에 auto-migrate하지 않는다. 공식 launcher가 `OPEN_WORK_HUB_API_AUTO_MIGRATE=0`을 강제한다. |
| 테스트 | run/worker별 임시 DB에 Alembic과 runtime seed를 한 번 적용하고, 일반 API 테스트는 application-ready baseline과 worker별 앱 조립을 재사용한다. 실제 startup/migration 계약만 전용 테스트에서 다시 실행한다. |
| 스테이징 / 프로덕션 | **자동 실행 금지.** 배포 스크립트에서 명시적으로 `alembic upgrade head`를 실행한 뒤 앱을 기동한다. |
| Alembic 도입 이전 DB | 현재 revision, 실제 schema, migration chain을 비교한 승인된 전환 계획 없이 `alembic stamp`하거나 수동 DROP하지 않는다. |

### 모델 드리프트 가드

`apps/api/tests/test_alembic_migrations.py` 의 `test_alembic_check_reports_no_model_drift`
가 매 테스트 실행마다 `alembic check` 를 돌려, SQLAlchemy 모델 변경이 마이그레이션
없이 머지되는 것을 막는다. 모델만 바꾸고 마이그레이션을 깜빡하면 CI 가 빨개진다.
