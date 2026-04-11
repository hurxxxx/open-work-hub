# PR0 결과 — Alembic 부트스트랩

작업일: 2026-04-10
커밋: `8dd1458` Bootstrap Alembic with baseline migration (origin/main)
관련 plan: [MEETING-APP-PLAN.md](MEETING-APP-PLAN.md) Phase 3 C1 결정 (line 519-523)

## 한 줄 요약

스키마 관리 방식이 `Base.metadata.create_all() + 손제작 compat SQL` → **Alembic** 으로 전환됨. PR1 부터는 마이그레이션 추가가 표준 절차.

## Shipped

| 파일 | 역할 |
|---|---|
| `apps/api/alembic.ini` | Alembic 설정. `prepend_sys_path = src`, DSN 은 env.py 가 동적 주입 |
| `apps/api/alembic/env.py` | `aidoo_api.core.db.Base.metadata` 를 target 으로, DSN 은 `get_settings().postgres_dsn` 에서 해석. `compare_type` / `compare_server_default` 활성화 |
| `apps/api/alembic/versions/0b843a383b2b_baseline_2026_04_10.py` | autogenerate 베이스라인. 36개 테이블 (기존 손제작 11개 포함). 840줄 |
| `apps/api/src/aidoo_api/core/db.py` | `_apply_postgres_schema_compat()` + `create_all()` 호출 완전 제거. `init_db()` 는 `DOOWON_API_AUTO_MIGRATE` 가 truthy 일 때만 `run_migrations()` 호출 |
| `apps/api/src/aidoo_api/reset_dev_db.py` | `drop_all` → `DROP TABLE alembic_version` → `run_migrations()` 흐름으로 전환 |
| `apps/api/tests/conftest.py:82` | 픽스처가 `DOOWON_API_AUTO_MIGRATE=1` 을 monkeypatch 로 켜서 alembic 으로 부트스트랩 |
| `apps/api/tests/test_alembic_migrations.py` | (1) `alembic upgrade head` smoke (2) `alembic check` 드리프트 가드 |
| `apps/api/README.md` | "데이터베이스 마이그레이션 (Alembic)" 섹션 추가 |

삭제: `apps/api/tests/test_db_compat.py` (사라진 함수에 의존하는 obsolete 테스트)

검증: `pytest apps/api/tests/` 42 passed in 25.40s

## 인프라 현재 상태

### 원격 dev DB

- 호스트: `14.39.166.163:37677`
- DB: `doowon_ai_portal_dev`
- DSN: 프로젝트 루트 [.env](.env) 의 `DOOWON_POSTGRES_DSN` 에서 자동 로드 (Settings 가 `WORKSPACE_ROOT/.env` 에서 읽음)
- **Alembic 상태: `alembic_version = 0b843a383b2b` 로 stamp 됨** (2026-04-10 PR0 마무리에서 `alembic stamp head` 적용)
- 모델에 선언된 36개 테이블 전부 존재. 드리프트 0
- App (`pnpm nx dev api`) 은 이 DB 를 사용

### 테스트 DB

- conftest.py 의 `postgres_dsn` 픽스처가 매 세션마다 일회용 `postgres:18` Docker 컨테이너를 띄움 (`aidoo-api-test-<hash>`)
- 테스트는 schema drop/recreate 를 반복하므로 **원격 dev DB 에 절대 붙이면 안 됨**
- Docker Desktop 이 켜져있어야 동작
- 픽스처 종료 시 `--rm` 으로 자동 정리

### AUTO_MIGRATE 플래그

- `DOOWON_API_AUTO_MIGRATE=1` 이면 `init_db()` 가 부팅 시 `alembic upgrade head` 자동 실행
- **사용 환경**:
  - 로컬 dev: 사용자 선택 (수동으로 `alembic upgrade head` 권장)
  - 테스트: conftest 가 자동으로 켬
  - **prod: 절대 켜지 말 것.** 배포 스크립트에서 명시 실행

## 작업 중 결정 기록

### Local Docker 컨테이너를 한 번 띄웠다가 지웠다 (왜?)

`alembic revision --autogenerate` 는 `Base.metadata` 와 **현재 DB introspect 결과**를 diff 함. 원격 DB 는 이미 모든 테이블이 만들어진 상태라 거기에 대고 autogenerate 를 돌리면 빈 migration 이 나옴. CREATE TABLE 36개가 들어간 baseline 을 받으려면 빈 스키마 대상이 필수. 그래서 일회용 `aidoo-alembic-bootstrap` 컨테이너를 띄워 baseline 만 생성하고 즉시 `docker rm -f` 로 정리했음. 지금은 doowon 관련 docker 컨테이너 0개.

### 원격 DB 는 stamp head 만 적용 (upgrade 아님)

원격 dev DB 는 이미 PR0 이전부터 `create_all + compat SQL` 로 모든 테이블이 만들어진 상태. 여기에 `upgrade head` 를 돌리면 CREATE TABLE 충돌이 남. 정답은 `stamp head` — 마이그레이션을 적용하지 않고 "이미 적용된 상태" 로 표시만 함. PR1 부터의 새 마이그레이션은 정상 `upgrade` 로 받음.

## 미해결 / 인계 사항

### legacy `pms_docs` 테이블 — **해결됨 (2026-04-11, PR1 라운드 8)**

- ~~원격 dev DB 에 `pms_docs` 테이블이 남아있음~~
- **제거 방법**: `reset_dev_db.py` 의 `Base.metadata.drop_all()` 을 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` 으로 교체하면서 orphan 테이블까지 한번에 날아감
- 관련 commit: `0321c45 reset_dev_db: drop schema wholesale instead of via metadata graph`
- PR1-STATUS.md §3d 참조

### MEETING-APP-PLAN.md 는 untracked 상태

- 의도적으로 git 에 안 올림 (작업용 임시 문서)
- PR0-RESULT.md, PR1-HANDOFF.md 도 같은 정책 — 작업 끝나면 셋 다 삭제

## 사용법 cheatsheet

```bash
cd apps/api

# 현재 리비전 확인 (원격 DB 에 붙어서 확인)
uv run --python 3.12 alembic current

# 새 마이그레이션 생성 (모델 변경 후)
# 주의: autogenerate 는 현재 DB 와 모델을 diff 함. 원격 DB 가 head 면 새 모델 변경분만 잡힘
uv run --python 3.12 alembic revision --autogenerate -m "add_meeting_tables"

# 생성된 alembic/versions/<hash>_*.py 를 손으로 검토 (필수!)
# - autogenerate 가 잡지 못하는 변경: 컬럼 rename, server_default 변경, CHECK 제약, 데이터 마이그레이션
# - FK 순서, 인덱스 이름, nullable 기본값 등 점검

# 원격 dev DB 에 적용
uv run --python 3.12 alembic upgrade head

# 직전 리비전 되돌리기 (개발 중에만)
uv run --python 3.12 alembic downgrade -1

# 드리프트 확인
uv run --python 3.12 alembic check

# 테스트
uv run --python 3.12 --group dev pytest
```

`DOOWON_POSTGRES_DSN` 은 [.env](.env) 에서 자동 로드. alembic CLI 는 LLM healthcheck 를 트리거하지 않으므로 다른 환경변수 export 불필요.
