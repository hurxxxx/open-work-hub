# Production Deployment Layout

상태: 승인된 전환 계약. 필수 로컬 backup 기본값의 runtime 적용은 후속 배포 구현 MR
병합·배포 시 완료한다. 그 전까지 실제 default는 배포 SHA의 `.env.example`과
`scripts/prod-deploy.sh`로 확인한다.

이 문서는 AI-DO 서버의 운영/개발 checkout 분리, release/rollback, DB migration
원칙을 정리한다.

## 운영/개발 기준

운영 checkout은 `/projects/ai-do/prod`, 개발 checkout은 `/projects/ai-do/dev`를
사용한다.

| 대상                       | 기준                                                     |
| -------------------------- | -------------------------------------------------------- |
| 운영 코드                  | `/projects/ai-do/prod`, `main` branch                    |
| 개발 코드                  | `/projects/ai-do/dev`, `dev` branch                      |
| 운영 배포 rollback DB 백업 | `/projects/ai-do/backups/prod/<timestamp>/postgres.dump` |
| 운영 SysPerf 파일 저장소   | `/data_nas/ai-do-prod/sysperf`                           |
| 개발 SysPerf 파일 저장소   | `/data_nas/ai-do-dev/sysperf`                            |

원칙:

- 개발은 `/projects/ai-do/dev` checkout의 `dev` 브랜치에서 수행한다.
- 운영은 `/projects/ai-do/prod` checkout의 `main` 브랜치를 기준으로 배포한다.
- 개발 완료 후에는 `dev`에서 `main`으로 PR/MR을 만들어 병합한다. 운영 checkout에서
  임의 개발 커밋을 만들지 않는다.
- 이전 checkout 이름을 가리키는 호환 symlink는 두지 않는다.
- Nginx는 checkout 경로를 알지 않고 TLS/reverse proxy만 담당한다.
- 운영 배포의 첫 번째 PostgreSQL rollback dump는 로컬
  `/projects/ai-do/backups/prod`에 필수 생성한다. 디렉터리 `0700`, 파일 `0600`,
  비어 있지 않은 archive, `pg_restore -l`, SHA-256을 확인한다.
- NAS 또는 다른 off-host 저장소는 검증된 로컬 dump의 선택적 2차 사본이다. 장애가
  서비스 readiness나 표준 배포를 중단시키지 않는다.
- 로컬 dump는 동일 호스트 백업이므로 재해복구 사본으로 간주하지 않는다.
- SysPerf 업로드 원본과 변환 CSV는 DB/vector hot path가 아니므로 환경별 NAS 디렉터리에
  분리 보관한다.
- systemd unit을 제외하고 운영 절대 경로를 repo에 하드코딩하지 않는다.

## 런타임 구조

```text
Nginx
  -> /inference-gateway/  404 (unauthenticated backend exposure disabled)
  -> collab websocket     http://127.0.0.1:8009
  -> /                    http://127.0.0.1:8000

ai-do-privacy-filter.service
ai-do-prod-infra.service
ai-do-prod-api.service
  -> FastAPI API
  -> frontend dist static serving
  -> SPA fallback

ai-do-prod-collab.service
ai-do-prod-worker.service
ai-do-prod-worker-realtime.service
ai-do-prod-worker-long.service
ai-do-prod-worker-ppt.service
ai-do-prod-worker-beat.service
```

FastAPI는 `AI_DO_API_SERVE_FRONTEND=1`일 때 `dist/apps/web`을 정적 서빙한다.
Nginx는 `root`나 checkout path를 갖지 않는다.

## 적용된 이름 규칙

| 구성요소                 | 운영                                                      | 개발                                                      |
| ------------------------ | --------------------------------------------------------- | --------------------------------------------------------- |
| Compose project          | `ai-do-prod`                                              | `ai-do-dev`                                               |
| Postgres DB/user         | `ai_do_prod`                                              | `ai_do_dev`                                               |
| Postgres runtime         | native PostgreSQL, shared listener with DB/role isolation | native PostgreSQL, shared listener with DB/role isolation |
| Redis container          | `ai-do-prod-redis`                                        | `ai-do-dev-redis`                                         |
| MinIO container          | `ai-do-prod-minio`                                        | `ai-do-dev-minio`                                         |
| MinIO bucket             | `ai-do-prod`                                              | `ai-do-dev`                                               |
| OpenSearch container     | `ai-do-prod-opensearch`                                   | `ai-do-dev-opensearch`                                    |
| OpenSearch index prefix  | `ai-do-prod`                                              | `ai-do-dev`                                               |
| Qdrant container         | `ai-do-prod-qdrant`                                       | `ai-do-dev-qdrant`                                        |
| Qdrant collection prefix | `ai-do-prod-rag`                                          | `ai-do-dev-rag`                                           |
| draw.io container        | `ai-do-prod-drawio` on `127.0.0.1:18083`                  | `ai-do-dev-drawio` on published `:18082`                  |

운영 인프라는 `ops/compose/ai-do-prod.infra.yml`, 개발 인프라는
`ops/compose/ai-do-dev.infra.yml`이 기준이다. PostgreSQL은 Docker가 아니라 서버 native
service로 실행한다. Portal에서는 loopback과 관리 LAN 주소의 `:5432`를 함께 listen하며,
`pg_hba.conf`가 외부 개발 DB와 승인된 운영 계정을 구분한다. main cluster는
`network-online.target`과 `NetworkManager-wait-online.service` 뒤에 시작해야 하며 정본
drop-in은 `ops/systemd/system/postgresql@18-main.service.d/network-online.conf`다. Redis,
MinIO, OpenSearch, Qdrant는 `AI_DO_INFRA_BIND_HOST`에 바인딩하며 기본값은 `0.0.0.0`이다.
서버 외부 개발 환경은 `.env.local`에 게시된 dev 인프라 포트로 접속한다. container 내부
기본 포트 `6379`와 `9000`을 외부 endpoint로 사용하지 않는다.
draw.io는 다이어그램 앱 전용 컨테이너이며 운영에서는 `drawio.dwdcc.kr` 별도 origin으로
프록시한다. 상세 운영 절차는 [Diagrams 앱 운영](../../apps/diagrams/README.md)을 따른다.

PostgreSQL/pgvector 원칙:

- 운영, 개발, 테스트 모두 PostgreSQL은 Docker container로 띄우지 않고 native PostgreSQL
  service/database를 사용한다.
- `pgvector`는 플랫폼 RAG/AI 검색의 필수 DB 확장이다. 확장이 없으면 Qdrant나 비벡터 검색으로
  기능 계획을 바꾸지 말고 native PostgreSQL에 `vector` extension을 설치한 뒤 진행한다.
- Alembic migration은 `CREATE EXTENSION IF NOT EXISTS vector`와 pgvector index 생성을
  기대한다. 확장 package나 권한이 없어 migration이 실패하면 환경 준비 문제로 처리한다.
- 테스트 DB도 native PostgreSQL에서 임시 database를 만들고 `CREATE EXTENSION vector`를
  적용한다. 테스트 편의를 위해 PostgreSQL Docker image를 pull/run하지 않는다.

운영·개발 systemd unit의 정본은 `ops/systemd/user/*.service.template`과 설치 script다.
API/app, collab, infra, beat와 queue group별 worker(default, realtime, long, PPT,
AI graph 등)는 이 template에서 생성한다. 문서의 고정 unit 개수나 목록으로 설치 상태를
판정하지 않는다. 실제 대상과 enablement는 다음 명령으로 확인한다.

```bash
systemctl --user list-unit-files 'ai-do-*.service' --no-pager
systemctl --user list-units 'ai-do-*.service' --all --no-pager
```

## 데이터 배치

로컬 NVMe primary와 배포 rollback 안전장치:

- Postgres
- Redis
- MinIO primary bucket
- Qdrant/OpenSearch primary data
- `/projects/ai-do/backups/prod/<timestamp>/postgres.dump`의 배포 전 PostgreSQL dump

선택적 NAS 2차 archive/off-host copy:

- 검증을 마친 로컬 `pg_dump` 사본
- MinIO mirror/archive
- Qdrant/OpenSearch snapshot
- `.env`, Nginx config, systemd unit snapshot
- release/debug artifact
- SysPerf uploaded workbooks and generated CSV files, separated by runtime
  environment under `/data_nas/ai-do-dev/sysperf` and
  `/data_nas/ai-do-prod/sysperf`

DB와 vector primary를 NFS에 두지 않는다. NFS는 latency와 tail latency 변동이 커서
hot path보다 2차 백업/아카이브에 맞다. NAS mount 부재나 장애는 서비스 기동과 표준
배포를 중단시키지 않으며, 2차 copy의 미완료 상태는 별도 운영 위험으로 기록한다.

## 배포 흐름

```text
1. prod checkout이 main 및 origin/main과 일치하는지 검증
2. pnpm/API/worker locked dependency 동기화
3. Alembic revision graph 사전 검증
4. /projects/ai-do/backups/prod/<timestamp>/postgres.dump에 PostgreSQL 백업 생성
5. 현재 `dist/apps/web`과 분리된 staging 디렉터리에 web production build
6. Vite manifest, `index.html`, 로컬 asset, frontend build ID 무결성 검증
7. API, collab, worker, beat를 quiesce하고 infra/OpenSearch는 유지
8. Alembic migration 및 DB head 일치 검증
9. 새 frontend/API를 활성화하기 전에 pre-activation release gate 실행
10. staging build를 `dist/apps/web`으로 승격하고 prod systemd unit 전체 restart
11. activation 이후 production smoke check
12. post-activation release gate 실행
13. 최종 production smoke 재확인
```

기본 실행 명령은 다음과 같다.

```bash
pnpm prod:deploy
```

실제 배포는 `nohup`, shell background job 또는 분리된 세션으로 넘기지 않는다. 운영자는 같은
콘솔에서 activation 이후 첫 smoke, post-activation gate, 최종 smoke가 차례로 끝날 때까지 로그를
계속 모니터링한다. 첫 smoke나 HTTP 200만으로 배포 완료로 판정하지 않는다.
최종 smoke가 성공한 뒤 `[prod-deploy] deployment flow complete`가 출력되어야 배포가 완료된
것이다. 이 흐름은 별도 관리자
알림을 보내지 않으므로 배포 실행자가 콘솔 확인을 끝까지 책임진다.

사전 확인만 할 때는 실제 백업, build, migration, restart, smoke를 실행하지 않는
dry-run을 먼저 사용한다. dry-run도 release gate 설정을 fail-closed로 검증한다.

```bash
pnpm prod:deploy -- --dry-run
```

기본 preflight와 두 번의 production smoke는 live 인증서가 30일보다 오래 남지 않으면
fail-closed한다. 인증서가 현재 유효하고 신뢰 체인·hostname·필수 SAN이 모두 정상인 상태에서
잔여 기간 경고만 넘겨야 한다는 명시적 운영 승인이 있으면, TLS 운영 정본 문서의 일회성
`--tls-expiry-break-glass` 절차를 사용한다. 이 옵션은 dry-run에서 실제 배포로 유지되지 않으므로
두 명령에 각각 명시해야 하며, 실제 만료나 인증서 신뢰 오류는 우회하지 않는다.

배포 전에 `.env`에서 `AI_DO_PROD_RELEASE_GATE_ADAPTERS` 또는
`AI_DO_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS`를 의도한 운영 gate로 설정한다. gate를 실행하지
않는 배포는 `AI_DO_PROD_SKIP_RELEASE_GATES=1`을 명시한 승인된 우회일 때만 허용한다.
세 값이 모두 비어 있거나 false이면 dry-run과 실제 배포 모두 중단한다.

외부 LLM·이미지 provider를 DB 제어면으로 처음 전환하는 release는
`AI_DO_PROD_RELEASE_GATE_ADAPTERS`에
`llm_provider_settings_cutover,image_model_settings_cutover`를 포함한다. legacy 값은 runtime
`.env`에서 제거하고 `.runtime/` 아래 권한 제한 일회성 dotenv 파일로 옮긴 뒤, 그 경로를 배포
프로세스의 `AI_DO_PROD_MODEL_SETTINGS_CUTOVER_ENV_FILE`로만 전달한다. Image 기능이 활성화된
환경은 `image_model_settings_cutover`를 생략하거나 release gate 전체를 우회할 수 없다. Gate는
migration과 app/worker quiesce 후 preview/apply/재적용을 수행하고, broker queue와 DB의
queued/running 이미지 작업이 모두 0이며 활성 설정·credential 복호화가 유효할 때만 activation을
허용한다. 이후 배포에서는 legacy 입력이 없는 runtime `.env`를 읽어 importer가 no-op하고 DB
readiness만 재검증한다.

Files partitioned retrieval의 full consistency checker는 일반 production deploy gate가 아니다.
새 physical generation을 build·validate·cutover하는 통제된 작업에서 writer를 정지하고
`python scripts/check_files_retrieval_cutover.py`를 명시적으로 한 번 실행한다. 이 checker는 다음을
확인한다.

- PostgreSQL에 OpenSearch와 Qdrant의 active generation이 각각 정확히 하나이고, 두 row가 같은
  `generation_key`/검증 cohort 및 `PASSED` validation timestamp를 가진다.
- OpenSearch schema v3와 Qdrant schema v1이고 alias·physical name이 현재 runtime 설정으로 계산한
  identity와 정확히 일치한다.
- query runtime이 위 두 physical backend에 직접 bind되며 legacy collection/index fallback을 만들지
  않는다.
- bound OpenSearch physical index와 Qdrant physical collection이 실제 backend에 존재한다.

검사기는 alias 전환, index/collection 생성, backfill, OCR, embedding을 수행하지 않지만,
PostgreSQL Files source 전체와 OpenSearch 문서 전체, Qdrant payload·vector 전체를 읽어 checksum을
다시 계산한다. 따라서 corpus 크기에 선형인 이 작업을 일반 deploy나 상시 readiness probe에서
실행하지 않는다. generation cutover, 인덱스 장애 조사, 운영자가 승인한 명시적 감사에만 사용한다.
실패 시 secret, URL, provider 원문 오류를 출력하지 않고 `status=failed reason=<code>`를 남긴다.

Files v3 build·quality·cutover는
[Files generation cutover runbook](../rag/files-generation-cutover-runbook.md)의
`evaluate_files_partitioned_quality`와 Files generation control plane만 사용한다. 아래의
`evaluate_retrieval_quality`, `backfill_keyword_search --activate-existing-generation`,
`--prepare-staged-files`는 Files v3 승인 또는 전환 절차가 아니다.

### Workspace keyword v2 generation

Workspace keyword search 구조 변경 release는 선택 workspace key 목록 대신 명령 범위에서
`--keyword-reindex-all-active`를 명시하거나 `.env`의
`AI_DO_PROD_KEYWORD_REINDEX_ALL_ACTIVE=1`을 사용할 수 있다. 이 설정과
`AI_DO_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS`는 상호 배타적이며, 전체 workspace 선택은 암묵적
기본값이 아니다. Gate는 등록된 모든 search entity를 workspace별로 rebuild하고 total/entity별 count를
출력한 뒤 smoke를 실행한다. 물리 index 없음은 실패지만 정상적인 0-document workspace는
성공이다. Smoke는 활성 source별 projection 문서 수와 인덱스 문서 수를 일치시키고,
한 건 이상인 경우 실제 검색 hit까지 확인한다. 비활성 source의 retained document만 있거나
활성 source projection 자체가 0건인 workspace는 성공이다. 이번 계약은 운영 `.env`에
값을 상시 저장하도록 요구하지 않는다.

Release gate adapter는 `pre_activate` 또는 `post_activate` phase에 속한다.
`keyword_dataset_scope`는 live index를 다시 쓰므로 `pre_activate`에서만 실행한다. 새 API가 실제로
기동되어야 검증할 수 있는 미래 gate는 `post_activate`에 등록하며, activation 직후 일반 smoke가
성공한 뒤 실행하고 마지막에 production smoke를 다시 수행한다.
Files full consistency checker는 release gate adapter로 등록하지 않는다.

OpenSearch keyword mapping generation을 전환할 때는 기존 outbox row의 `created_at/id`를 delta
high-water mark로 사용하지 않는다. pending job은 같은 row에서 operation을 갱신할 수 있어 이 값이
새 write를 완전하게 포착하지 못하기 때문이다. `prod-systemd.sh quiesce-search-writers`로 API와
search-index worker를 모두 멈춘 상태에서 전체 active workspace를 새 generation에 backfill한다.
백필과 활성화는 반드시 별도 명령이어야 하며 평가가 끝날 때까지 writer를 재시작하지 않는다.
다음 명령과 artifact v2 계약은 일반 workspace keyword/OpenSearch v2 generation 전용이며 Files
v3에는 사용하지 않는다.

```bash
cd apps/api
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m ai_do_api.backfill_keyword_search \
  --all-active \
  --index-generation release_<release-id>

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m ai_do_api.evaluate_retrieval_quality \
  --corpus /path/to/retrieval-corpus-v1.json \
  --index-generation release_<release-id> \
  --output /path/to/retrieval-quality-release_<release-id>.json

# Workspace keyword v2 generation을 활성화하되 writer는 계속 정지한 상태로 둔다.
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m ai_do_api.backfill_keyword_search \
  --activate-existing-generation release_<release-id> \
  --quality-report /path/to/retrieval-quality-release_<release-id>.json \
  --quality-corpus /path/to/retrieval-corpus-v1.json \
  --confirm-writes-quiesced
```

Workspace keyword v2의 `--quality-report`는 `artifact_version=2`, corpus ID/SHA-256, 동일한 index generation,
평가 시점 OpenSearch 물리 UUID, mapping/settings SHA-256, 전체 문서 SHA-256,
그리고 hybrid/BM25/dense 각각 최소 60 query의 평가 결과를 담는다. ACL/citation 실패,
p95 5초 초과, Recall 회귀, nDCG·MRR uplift 미달 또는 세 baseline의 query count 불일치가
있으면 activation은 실행되지 않는다. SHA-256은 `--quality-corpus` 파일의 raw bytes에서 다시
계산하며 artifact 값과 다르면 실패한다. Backfill 뒤에는 v2 mapping `_meta.schema_version`,
전체 문서 count, 물리 UUID, 구성/content SHA-256도 확인한 뒤에만 alias를 전환한다. 평가용 Qdrant
collection은 generation별로 격리되고 기본적으로 평가 종료 시 삭제된다.

한 릴리스 동안 보존한 이전 workspace keyword v2 generation으로 rollback할 때도 writer를
quiesce한 뒤 같은 확인 계약을 사용한다. rollback은 물리 index를 삭제하거나 다시 쓰지 않고
alias만 원자적으로 되돌린다. Files v3 rollback은 이 경로를 사용하지 않고 Files generation
cutover runbook을 따른다. 현재 Files runner는 후속 generation upgrade/rollback을 fail-closed한다.

```bash
cd apps/api
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m ai_do_api.backfill_keyword_search \
  --activate-existing-generation release_<previous-release-id> \
  --quality-report /path/to/retrieval-quality-release_<previous-release-id>.json \
  --quality-corpus /path/to/retrieval-corpus-v1.json \
  --confirm-writes-quiesced
```

초기 canonical legacy v1 index로 복구해야 할 때만 임의 target을 받지 않는 전용 경로를 쓴다.
이 경로도 현재 active projection source count와 v1 문서 수가 정확히 일치해야 한다.

```bash
cd apps/api
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 python -m ai_do_api.backfill_keyword_search \
  --rollback-legacy-v1 \
  --confirm-writes-quiesced
```

운영 migration 전에는 최소 `pg_dump` 또는 DB snapshot을 생성한다. 위험 migration은
maintenance window, staging dry-run, restore rehearsal까지 포함한다. Alembic downgrade는
삭제된 데이터를 복구하지 못할 수 있으므로 보조 수단으로만 본다.

`prod:deploy`는 Alembic revision graph 검증, DB backup, web build, app writer quiesce,
Alembic migration, DB current revision 검증, pre-activation release gate, prod systemd restart,
일반 smoke, post-activation release gate, 최종 smoke를 한 흐름으로 묶는다.
중복 revision ID, Alembic cycle, 복수 head, migration 후 DB current/head 불일치가 있으면
API 재시작 전에 중단한다. 중간 단계가 실패하면 즉시 중단하며 자동 rollback은 수행하지
않는다. Nginx 설정 설치/reload는 이 명령의 범위가 아니다. 실패 시 출력된 backup 경로와
실패 단계를 기준으로 수동 복구를 판단한다.

Web build는 서비스 중인 `dist/apps/web`을 직접 비우지 않는다. 같은 filesystem의
`dist/apps/.web-staging-*`에서 build와 manifest 검증을 모두 완료한 뒤 search-writing app unit을
정지하고 migration과 DB 검증까지 통과하면 현재 `web`을 `.web-previous`로 이동한 후 staging 디렉터리를 `web`으로
승격한다. `.web-previous`는 정적 서빙 경로가 아닌 rollback 판단용 artifact이며, 이전 release의
asset을 현재 release의 `/assets`에 섞지 않는다. build 또는 migration이 실패하면 현재 `web`은
변경되지 않으며 migration quiesce 이후 실패는 구 API가 새 schema에 쓰는 것을 막기 위해 app unit을
정지한 채 fail-closed한다. 같은 checkout의 배포는 non-blocking file lock으로 직렬화한다. frontend 승격
전 pre-activation gate가 실패하면 staged frontend를 활성화하지 않고 API, collab, worker, beat를
quiesce한 채 fail-closed한다. `ai-do-prod-infra.service`와 OpenSearch는 gate 동안 유지한다. 승격 완료
후 unit restart가 실패하거나 배포 프로세스가 interrupt된 경우에만 cleanup trap이 새 frontend와
맞는 search-writing app unit 전체를 다시 기동한다. `prod-systemd.sh quiesce-search-writers`와
`resume-search-writers`는 이 배포 상태 전이를 위한 명시적 내부 명령이다. Pre-activation gate 실패
후에는 같은 실패 checkout을 수동 resume하지 않고 원인을 수정하거나 revert한 표준 release를 다시
실행한다.

Knowledge runtime 퇴역 Release N과 registry tombstone 제거 N+1에는 별도 설정이나 skip flag로
우회할 수 없는 임시 pre-activation gate를 둔다. Writer를 quiesce하고 migration/current 검증을
마친 뒤 `audit_knowledge_retirement.py --require-safe-cutover`를 한 번 실행해 legacy 4-table이
온전히 보존됐는지 확인한다. 허용하는 잔존 행은 canonical PMS·Meeting attachment와 원천·Workspace·
connector·workspace-scope active/default retrieval partition(있을 때)·storage·owner·파일 메타데이터가
정확히 일치하고 `succeeded/excluded`, chunk 0인 rollback용 mirror, 그리고 원문 행이 없고
projection/fence/checksum/error가 모두 비어 있는 `delete/succeeded`
RAG 영수증뿐이다. Knowledge artifact·ingest job·projection head/event·search job, 그 밖의 source·
connector, 미참조 connector, 불완전 mirror, unsafe RAG history와 모든 PostgreSQL schema의 외부
inbound FK는 0이어야 한다. 하나라도 남으면
frontend를 승격하지 않고 app unit을 quiesce한 채 종료한다. 이 검사는 cron이나 상시 monitor가
아니며 N+2에서 물리 table과 audit script를 제거할 때 배포 hook도 함께 제거한다.

임시 gate가 차단되면 DB row를 수동 삭제하거나 gate를 우회하지 않는다. Gate 자체는 read-only이므로
실패만으로 DB를 restore하지 않는다. Release N을 되돌릴 때만 gate hook까지 함께 되돌린 표준
rollback release를 `dev`→`main`으로 승격하고, 직전 writer가 필요하면 canonical attachment에서
mirror를 재구성한다. Forward 재시도는 승인된 data migration·cleanup으로 unsafe 분류를 0으로 만든
새 release에서 수행한다. 두 경로 모두 출력된 로컬 backup과 inventory를 보존한다.

Activation과 첫 smoke 이후 post-activation gate가 실패하면 새 runtime은 기동 상태로 유지한다.
배포 프로세스는 실패 reason을 콘솔에 남기고 non-zero로 종료하며 자동 관리자 알림이나 rollback을
수행하지 않는다. 운영자는 명령을 백그라운드로 분리하지 않고 Files 활성 환경의 `status=ok`, 최종 smoke,
`[prod-deploy] deployment flow complete`를 모두 확인할 때까지 같은 콘솔을 모니터링한다. 이 완료
표시 전에 콘솔이 종료되거나 연결이 끊겼으면 배포 성공으로 간주하지 않고 상태·smoke·journal을
재확인한다.

Production web build는 동일한 build ID를 JavaScript bundle과 `.ai-do-build-id`에 기록한다.
브라우저의 same-origin API fetch/XHR/WebSocket 요청은 이 ID를 전달하고, API는 현재 ID와 다른
요청을 route/handler 실행 전에 차단한다. HTTP mismatch는 `409`, `Cache-Control: no-store`,
`X-AI-DO-Reload-Required: 1`로 응답하고 WebSocket은 close code `4409`를 사용한다. 브라우저는
현재 URL에 일회성 `__reload` 값을 붙여 최신 HTML로 이동하며 정상 bootstrap 후 해당 값만
제거한다. build ID가 없는 non-browser API client는 기존 계약을 유지한다.

이 guard를 처음 도입하는 release 전에 이미 열려 있던 구 bundle에는 build header와 자동 reload
처리가 없다. 그 탭의 same-origin fetch/XHR은 잘못된 API 호출을 허용하지 않고 `409`로 fail-closed
하며, 사용자는 **브라우저 캐시 삭제 없이 일반 새로고침 한 번**으로 새 bundle을 받아야 한다.
missing build ID를 일시 허용하면 최초 전환은 매끄럽지만 구 bundle이 새 API를 호출할 수 있으므로
이 서비스는 안전을 위해 grace period를 두지 않는다. guard 도입 이후 release부터는 mismatch가
자동 cache-busting reload로 복구된다.

Nginx 설정이 변경된 릴리스는 별도 운영 절차로 설정을 설치하고 `nginx -t` 성공을 확인한
뒤 reload한다. 이를 일반 애플리케이션 배포에 포함됐다고 가정하지 않는다.

## 런타임 OS 패키지 전제

애플리케이션 의존성은 repo/venv/pnpm lockfile로 관리하지만, 일부 문서 변환 기능은 운영
호스트의 OS 패키지를 직접 사용한다. 배포 전 prod 호스트에서 아래 명령이 성공해야 한다.

```bash
# PPT finalize: HTML 미리보기/spec 을 다운로드용 .pptx 로 변환할 때 필요.
# 없으면 "PPT로 전환"이 실패하고 pptx_key 가 생성되지 않는다.
command -v google-chrome-stable || command -v google-chrome || \
  command -v microsoft-edge-stable || command -v microsoft-edge || \
  command -v chromium || command -v chromium-browser

# 세미나 & 출장 보고서: 첨부 Excel 도형/화살표 시트를 일정표 이미지로 렌더할 때 필요.
# 없으면 일정표 똑딱이만 생략되고 나머지 PPT 생성은 계속된다.
command -v libreoffice || command -v soffice

# 스캔 PDF/이미지 OCR fallback. 없으면 OCR 텍스트 보강만 생략된다.
command -v tesseract
```

PPT finalize 는 `ai-do-prod-worker-ppt.service`가 수행하므로 chromium/chrome 계열 브라우저는
prod PPT worker 호스트에 설치되어야 한다. 워커는 systemd sandbox와 충돌하기 쉬운 Snap Chromium
래퍼보다 시스템 Chrome/Edge를 우선하며, 기동 전 `ppt_browser_smoke`로 실제 HTML→PPT 변환까지
확인한다. smoke가 실패하면 PPT 워커도 시작하지 않으므로 unit 로그의 브라우저 stderr를 먼저
확인한다. 표준 PATH 밖의 브라우저를 쓸 때는 `AI_DO_PPT_BROWSER_PATH`가 해당 systemd 서비스의
프로세스 환경에 전달되도록 unit override 또는 렌더링된 `Environment=`에 명시한다.

첨부 Excel 일정표 렌더는 `POST /ppt-generator/generate` 요청 처리 중 API 호스트에서 수행하므로
LibreOffice Calc/soffice 는 prod API 호스트에 필요하다. 경로가 표준 PATH 밖이면
`AI_DO_PPT_SOFFICE`로 명시한다.

## Worker 큐 이름 변경 (drain / requeue / empty)

Celery 브로커는 Redis이고 큐 이름 prefix를 쓰지 않으므로, 각 큐는 broker DB(0)에
**큐 이름 그대로의 Redis LIST 키**로 존재한다(예: `ppt_generate`, `ppt_generate_dedicated`).
워커는 자신이 `-Q`로 구독한 큐 키에서만 pop한다. 따라서 큐 **이름을 바꾸면**(예:
`ppt_generate` → `ppt_generate_dedicated`), 이름 변경 이전에 옛 키(`ppt_generate`)로
enqueue된 잔여 메시지는 새 워커가 소비하지 않아 **고아 상태**가 된다. 큐 이름을 바꾸는
release는 아래 drain/requeue/empty 절차를 함께 수행한다.

현재 큐 이름·그룹의 정본은 `apps/api/src/ai_do_api/core/worker_queue_contract.py`이며,
배포 대상 큐 목록은 다음으로 확인한다.

```bash
apps/worker/.venv/bin/python -m ai_do_worker.queue_contract --celery-queues
```

PPT 생성은 브라우저·전용 환경이 필요해 `ppt` 그룹(`ppt_generate_dedicated`)을
`ai-do-prod-worker-ppt.service`만 전용 소비한다(원격/공용 long 워커의 가로채기 방지).
특허 선행기술 조사는 `patent` 그룹(`patent_prior_art_server_v1`)을
`ai-do-prod-worker-patent.service`만 concurrency 1로 소비한다. 인자 없는
`--celery-queues`는 로컬/일반 worker 목록이므로 이 서버 전용 큐를 출력하지 않는다.

절차(옛 이름 `OLD`, 새 이름 `NEW`. 아래 예시는 PPT):

```bash
# 0) 브로커 접속 — prod .env 의 Redis broker DSN(db 0). worker 는 AI_DO_WORKER_BROKER_URL 을 읽는다.
BROKER="$(grep -E '^AI_DO_WORKER_BROKER_URL=' /projects/ai-do/prod/.env | tail -1 | cut -d= -f2-)"
OLD=ppt_generate; NEW=ppt_generate_dedicated

# 1) 옛 큐에 잔여 메시지가 있는지 확인
redis-cli -u "$BROKER" LLEN "$OLD"        # 0 이면 할 일 없음 → 종료

# 2-a) requeue(권장): 메시지가 여전히 유효하면 새 큐로 옮긴다.
#      Redis 브로커는 "어느 LIST 키에서 pop하느냐"로만 소비가 정해지므로 raw 메시지
#      이동으로 재배치가 성립한다(메시지 본문의 라우팅 정보는 소비에 영향 없음).
while [ "$(redis-cli -u "$BROKER" LLEN "$OLD")" -gt 0 ]; do
  redis-cli -u "$BROKER" RPOPLPUSH "$OLD" "$NEW" >/dev/null
done

# 2-b) empty(옛 코드로 처리되면 안 되는 stale job만): 폐기
#      redis-cli -u "$BROKER" DEL "$OLD"
#      → 폐기하면 해당 PPT job 은 DB 에서 queued/running 상태로 멈출 수 있다.
#        stale 감지(heartbeat)로 정리되거나 사용자가 재생성해야 함을 릴리스 노트에 명시.

# 3) 옛 큐가 비었는지 확인
redis-cli -u "$BROKER" LLEN "$OLD"        # 0 이어야 함

# 4) 새 전용 워커가 새 큐를 소비하는지 확인(배포 스크립트의 assert_worker_queues_consumed 와 동일)
apps/worker/.venv/bin/python -m celery -A ai_do_worker.celery_app:celery_app \
  inspect active_queues        # ppt_generate_dedicated 가 보여야 함
```

주의 — **옛 `-Q`를 물고 있는 워커의 재구독**: 옛 설정(원격/공용 long 등)에 `ppt_generate`가
`-Q`로 박혀 있으면 브로커 재접속 때마다 옛 큐를 다시 구독해 가로챈다. `inspect active_queues`
결과에 `ppt_generate`를 소비하는 워커가 남아 있으면 그 워커에 대해
`celery -A ai_do_worker.celery_app:celery_app control cancel_consumer ppt_generate`로 즉시
중단하되, **재시작하면 되살아나므로** 그 워커의 기동 설정(`-Q`)을 현행 `queue_contract` 기준
(`--celery-queues`)으로 교정해야 근본 해결된다.

특허 큐 전환은 `patent_prior_art` → `patent_prior_art_server_v1`이다. 구버전 worker가
공유 broker에서 구 큐를 계속 광고하면 새 큐의 동작 여부와 무관하게 stale worker로 간주한다.
`prod:smoke`는 다음을 모두 만족해야 통과한다.

- API, collab, 관리형 worker, Beat의 시작 시 고정 `runtime_revision`이 배포 checkout의
  현재 Git revision과 같다.
- `patent_prior_art_server_v1`의 소비자는
  `ai-do-prod-worker-patent@...` 하나뿐이고 pool concurrency는 1이다.
- 어떤 Celery 노드도 구 큐 `patent_prior_art`를 소비하지 않는다.

특허 작업의 현재 시도와 재시도 시점은 DB가 정본이다. 구 Redis LIST의 메시지를 새 큐로
무조건 옮기면 오래된 delivery가 되살아날 수 있으므로 특허 큐에는 위의 일반
`RPOPLPUSH` 절차를 사용하지 않는다. 표준 `prod:deploy`는 API, collab, 모든 worker와
Beat를 포함한 production writer unit 전체를 멈추고 rollback backup을 확보한 뒤
lease/fencing migration과 다음 cutover를 순서대로 자동 수행한다.

1. Redis의 일회성 cutover marker가 없거나 구 LIST 잔량이 있으면 queued/running 작업의
   기존 `celery_task_id`와 `execution_id`를 DB에서 먼저 무효화한다.
2. 구 LIST `patent_prior_art`를 삭제하고 `LLEN=0`을 확인한다.
3. DB 정본으로 각 작업에 새 task fence를 발급해 `patent_prior_art_server_v1`에 발행한다.
4. 모든 active 작업이 발행되고 구 LIST가 계속 0일 때만 marker를 기록한다.

이 단계가 일부라도 실패하면 배포는 non-zero로 끝나고 모든 production writer unit은
quiesced 상태를 유지한다. 재실행 시 marker와 구 LIST 잔량을 함께 검사하므로 완료된
cutover는 건너뛰고, 중단되었거나 구 메시지가 다시 나타난 cutover만 다시 수행한다.
출력은 메시지·작업 수만 포함하며 broker URL이나 작업 입력을 기록하지 않는다.

## DB Migration 원칙

일반 release에서 허용하기 쉬운 변경:

- 테이블 추가
- nullable 컬럼 추가
- default 있는 컬럼 추가
- 인덱스 추가
- 새 코드가 쓰기 전의 보조 테이블 추가

주의가 필요한 변경:

- `NOT NULL` 강제
- unique/foreign key 제약 추가
- 대량 UPDATE
- 대형 인덱스 생성

일반 release에서 피해야 할 변경:

- `drop table`
- `drop column`
- `rename table`
- `rename column`
- 기존 enum/status 값 제거
- 기존 데이터 의미 변경

rename/drop은 expand-contract 방식으로 나눈다.

```text
1. 새 컬럼/테이블 추가
2. 앱이 old/new 둘 다 읽고 새 경로도 쓰게 변경
3. backfill 실행
4. 앱이 새 경로만 읽도록 변경
5. 한두 release 뒤 old 경로 삭제
```

## 롤백 원칙

운영 checkout은 항상 `main` branch와 clean worktree를 유지한다. detached HEAD로 과거
commit을 checkout한 뒤 `prod:restart`를 실행하는 절차는 systemd guard가 거부하므로 사용하지
않는다.

일반 rollback은 원인 변경을 `dev`에서 되돌리고 검증한 뒤 `dev` -> `main` MR로 승격하고,
병합된 `origin/main`을 표준 `prod:deploy`로 배포한다. DB schema가 이미 변경된 경우에는 이전
코드와의 호환성, backup 복구 범위, 데이터 손실 가능성을 별도로 검증한다. 이 조건을 충족하지
못한 긴급 rollback은 일반화된 명령을 제공하지 않으며, 승인된 break-glass 계획 없이는 실행하지
않는다.

특허 전용 worker를 도입한 release 이전으로 되돌릴 때는 현행 checkout을 바꾸기 전에
`bash scripts/prod-systemd.sh rollback-patent-worker`를 실행한다. 이 명령은 API, collab,
모든 worker와 Beat를 먼저 중단하고 실제 inactive 상태를 확인한 뒤 다음 순서로 역전환한다.

1. queued/running 작업의 현재 task/execution fence를 DB에서 무효화한다.
2. 신·구 Redis LIST를 모두 비우고 forward cutover marker를 제거한다.
3. fresh task ID로 모든 active 작업을 구 큐 `patent_prior_art`에 발행하고 DB의
   `dispatch_published_at`을 확인 상태로 기록한다.
4. 신 큐가 0이고 구 큐 잔량이 발행 작업 수와 일치해야만 전용 unit을 disable하고 렌더링
   파일을 제거한다.

writer 중단이나 역전환이 실패하면 unit 삭제로 진행하지 않고 모든 writer를 중단한 상태로
남긴다. 성공 후에만 이전 revision checkout/deploy를 계속한다. 준비 없이 코드가 먼저
되돌아가더라도 새 unit의 `PartOf=ai-do-prod-api.service`가 API stop/restart에 함께 worker를
중단하고, checkout에 unit template이 없으면 `ExecCondition`이 재기동을 거부한다. 이
안전장치는 DB migration 호환성 검토를 대신하지 않는다.
