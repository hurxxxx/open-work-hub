# Files Retrieval Source Activation

이 문서는 Files 앱 업로드 파일을 OpenSearch BM25와 Qdrant dense retrieval에 연결하기
위한 구현·검증·활성화 순서의 정본이다. 경계와 품질 기준은
[ADR 0004](../../../adr/0004-retrieval-rag-boundary-policy.md)와
[ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md),
[Retrieval 서비스 레이어](../retrieval/README.md)를 따른다.

## 현재 상태

Files retrieval adapter는 플랫폼 registry에 합성되어 ownership, projection, lifecycle hook,
ACL 계약을 검증한다. named gate와 generation control plane은 다음처럼 동작한다.

- 모든 runtime: operator gate와 validation-passed ACTIVE Files OpenSearch v3/Qdrant v1 pair가
  모두 준비된 경우에만 partition-aware write/query를 연다. 어느 한쪽이라도 없으면 503으로
  fail-closed하고 legacy 또는 무필터 query로 fallback하지 않는다.
- development: 2026-07-23 최초 generation adoption/materialize/quality/validation/alias cutover와
  checker를 통과해 gate가 열려 있다. 기존 default Qdrant collection에는 canonical point를 섞지 않는다.
- production: 2026-07-23 `prod-empty-20260723` empty physical pair의 validation/alias cutover와
  release checker를 통과해 gate가 열려 있다. 활성 Files row는 0이며 실제 운영 API에서
  keyword/semantic/hybrid 모두 HTTP 200과 빈 결과를 확인했다. 이는 검색 가용성 부트스트랩이며
  실데이터 품질 승인이 아니므로 `quality_status=deferred_until_nonempty` 상태다. Generation 누락,
  pair 불일치 또는 backend 장애는 계속 503으로 fail-closed한다.
- Files 목록은 vector와 keyword index job이 모두 성공한 경우에만 `ready`를 반환한다.
  처리 중에는 `pending`/`processing`, 지원하지 않는 형식은 `unsupported`, terminal failure는
  `failed`로 반환하며 raw worker 오류는 노출하지 않는다.

환경별 동작은 `apps/api/src/ai_do_api/domains/files/retrieval_contract.py`의 named gate가
소유한다. 별도 임시 환경변수로 우회하지 않는다. Gate가 닫혀도 Files source transaction은
canonical projection event/head를 항상 기록한다.
중단되는 것은 Search/RAG job 발행과 backend mutation뿐이다. 이미 대기 중이던 Files job은
`pending` 상태와 기존 attempt 수를 보존한 채 지연되며 operator disable만으로 dead-letter되지
않는다. 따라서 비활성 기간의 업로드·이동·삭제를 재활성화 전에 watermark로 복구할 수 있다.
Gate가 닫힌 최초 production source에 extraction artifact가 아직 없으면 operator-only
`bootstrap-extraction`이 object storage와 parser/OCR만 사용해 artifact를 resumable batch로
저장하고 checksum source fence를 갱신한다. 이 명령에는 vector/keyword backend mutation
인터페이스가 없으며, writer/worker 정지 확인과 production 전용 확인 문자열이 필요하다.

비활성 expand release는 개발 DB migration과 API/worker/browser Files CRUD를 통과했다.
Development runtime은 최초 generation materialize, v3 품질 평가와 실제 파일 canary의
검색/다운로드/workspace-company-A→B ACL 전환·정리를 통과했다. 이는 development capability
증거일 뿐 production의 전체 처리량·비용·품질·rollback 승인 증거가 아니다. Production
승격 절차는 [Files generation cutover runbook](files-generation-cutover-runbook.md)이 소유한다.

Files live writer/read path는 ACTIVE control-plane selector가 가리키는 OpenSearch v3/Qdrant v1 pair만
사용한다. Corpus의 workspace/company 범위나 관리 workspace를 바꿔도 stable resource/chunk identity와
immutable partition binding을 유지하며 source metadata/ACL만 바꾼다. 따라서 steady-state 전환은
OpenSearch 재색인, Qdrant 재임베딩, OCR/parser 재실행 또는 MinIO object copy를 호출하지 않는다.
이 개발 증거는 Files에 한정되며 Docs/QNA 등은 각 source owner의 별도 activation 증거를 요구한다.

## 파이프라인 계약

```text
Files corpus/partition + upload DB transaction
  -> source row binding + canonical projection event/version
  -> RAG realtime outbox
  -> server-observed MIME/signature validation
  -> structured parser (slide/page/sheet/paragraph/heading/list/table-row locator)
  -> native-first sufficiency gate
     -> OCR fallback with explicit document_ocr provenance
  -> Korean-aware locator chunks
  -> extraction artifact
     -> embedding -> Qdrant dense vectors
     -> OpenSearch Nori/BM25 document
  -> Retrieval RRF(k=60) -> one global rerank -> one grounding pass
```

세부 계약:

- storage object는 1 MiB stream으로 읽고 120 MiB retrieval 한도를 적용한다. Files 자체 업로드
  한도와 retrieval 처리 한도는 별개다.
- 지원 대상은 PDF, PPT/PPTX, DOC/DOCX, XLS/XLSX/XLSM, HTML/HTM, PNG/JPEG/TIFF/WebP,
  UTF-8/CP949 text 계열이다. 클라이언트 MIME만 신뢰하지 않고 magic/container signature를
  관찰한다. OpenXML은 entry 수, 개별·전체 해제 크기, 암호화 여부, 압축률을 해제 전에
  검사해 ZIP bomb를 차단한다.
- structured parser 결과의 slide/page/sheet/table/HTML title·heading·paragraph·list·table-row
  locator를 chunk metadata에 보존한다.
- HTML은 브라우저로 렌더링하거나 링크·프레임·리소스를 요청하지 않는 bounded streaming parser로
  처리한다. `script`, `style`, `noscript`, `iframe`, `object`, `embed`, `template` 등 실행·비가시
  요소와 명시적 hidden 요소를 제거하고 charset, 처리 문자·표 행 수, 처리 시간과 truncation
  여부·사유를 extraction metadata에 기록한다. 가시 본문이 128자 미만인 helper page는
  `html_visible_text_below_minimum`으로 제외한다.
- DOCX의 연속 paragraph는 각 짧은 paragraph를 별도 vector로 만들지 않고 약 900자 단위로 합친다.
  chunk에는 `locator_start_label`과 `locator_end_label`을 기록해 `¶1–¶5`처럼 원문 범위를
  보존한다. 한 파일의 vector chunk는 결정적 원문 순서의 앞 512개로 제한하고 projection metadata의
  `chunking`에 hard limit, 제한 전/후 개수와 truncation 여부를 명시한다. BM25 extraction body는 이
  vector cap 때문에 잘리지 않는다.
- OCR은 structured 결과를 대체하지 않는다. DOCX/PPTX/XLSX/PDF의 structured 본문이 128자
  이상이면 OCR provider를 호출하지 않는다. 독립 이미지이거나 structured 본문이 없거나 128자
  미만일 때만 OCR fallback을 시도한다. 기존 structured 본문이 있으면 중복이 아닌 텍스트만
  `document_ocr` / `OCR supplement`로 추가한다. OCR 시도 여부, fallback 이유, 정책 버전,
  provider/status/문자 수를 artifact metadata에 기록하며, 짧더라도 structured 본문이 있으면
  OCR 장애 때문에 그 본문까지 버리지 않는다.
- 추출 artifact는 checksum, normalized text, evidence blocks, parser/OCR provenance, status,
  error code를 `file_manager_files`에 저장한다. 큰 text/JSON은 일반 Files 조회에서 deferred
  load하고, soft delete transaction에서 즉시 비운다. 추출 저장은 `deleted_at IS NULL` 조건부
  update이며 delete worker도 방어적으로 다시 purge해 동시 삭제 후 본문 복원을 막는다.
  재시도는 ready artifact를 재사용한다.
- Upload event 이후 처음 계산된 extraction checksum이 head와 다르면 worker는 backend write 전에 새
  content event/version을 기록하고 최신 fenced RAG job을 만든다. 이전 job은 head fence에서
  supersede되며, 같은 cached extraction을 재사용한 최신 job만 OpenSearch/Qdrant를 변경한다.
- RAG와 keyword job은 canonical `(file_manager_file, file_id)` projection event/version을 공유한다.
  Qdrant partition-aware writer와 OpenSearch v3 staging writer는 scope-neutral canonical ID를 지원한다.
  이 ID 계약은 새 physical generation에서만 활성화하며 legacy live generation에는 혼합하지 않는다.
- 신규 object key는 file ID 기반의 scope-neutral key다. 기존 workspace 포함 key는 opaque
  compatibility key로 계속 읽고, workspace 이동을 이유로 copy하지 않는다.
- 일반 전체텍스트 검색은 정밀도를 위한 BM25 `AND`를 유지하고, 자연어 retrieval의 BM25
  후보 생성은 recall을 위해 `OR`와 `minimum_should_match=30%`를 사용한다. 긴 자연어 질의를
  `AND`로 보내 BM25 후보가 0건이 되면 hybrid가 vector-only로 조용히 퇴화하며, 제한 없는
  `OR`는 공통 토큰 후보를 과다 생성하므로 세 정책을 혼용하지 않는다.
- 자연어 retrieval의 OpenSearch `size`는 해당 실행의 `candidate_k`로 제한한다. 일반
  전체텍스트 검색용 10,000건 방어적 후보 기본값을 retrieval에 재사용하면 흔한 토큰 하나가
  ACL 후검사와 DB 접근을 대량으로 유발하므로 두 경로의 후보 상한을 분리한다.
- 추출 artifact가 ready가 되면 keyword projection을 vector embedding보다 먼저 독립 outbox로
  발행한다. embedding provider 장애는 vector job만 실패시키며 ready 추출 artifact와 BM25
  색인을 parser 실패로 되돌리지 않는다. Files의 최종 RAG 상태는 vector와 keyword job이 모두
  성공해야 계속 `ready`다.
- 현재 `file_manager_files`에는 bulk source의 상대 경로가 없고 object key도 file ID와 안전한
  filename만 보존하므로 parser/worker는 작은 PNG가 정상 도면인지 HTML companion asset인지 안전하게
  구분할 수 없다. 따라서 크기나 filename만으로 PNG를 사후 제외하지 않는다. Directory/bulk ingestion은
  source-relative manifest가 살아 있는 업로드 전에 companion HTML asset directory와 Office 임시 잠금
  파일을 제외하고, 사용자가 명시적으로 선택한 독립 이미지에는 기존 PNG OCR 지원을 유지해야 한다.

## ACL 계약

- `retrieval_partition_id`는 coarse candidate envelope이며 file/folder/corpus 권한을 부여하지 않는다.
- 모든 후보는 soft-delete, source workspace/corpus, owner, visibility, folder ancestry의 최종
  PostgreSQL ACL을 통과해야 한다. 이 검사는 facet/highlight/rerank/grounding/citation보다 먼저다.
- workspace admin은 해당 workspace의 모든 활성 파일을 읽을 수 있다.
- 일반 구성원은 자신이 소유한 파일 또는 `visibility=workspace` 파일만 읽을 수 있다.
- folder 안의 파일은 현재 Files API와 같은 ancestor 접근 검사를 추가로 통과해야 한다.
- OpenSearch ACL branch는 `owner_user_id`와 `visibility`를 사용한다.
- Qdrant 결과는 같은 `SourceAclPolicy.can_read_rag_resource`로 post-filter한다.
- Partition-aware keyword query는 전환 후 허용된 company corpus를 legacy workspace ACL hint가 미리
  제거하지 않도록 해당 hint를 사용하지 않는다. Partition predicate 뒤 source-owned batch ACL과 refill이
  candidate 정본이며, 향후 hint를 다시 도입하려면 전환 전후 completeness를 증명해야 한다.
- ACL 탈락으로 top-k가 부족하면 bounded refill하며, OpenSearch는 PIT + `search_after`를 사용한다.
- Search/RAG 응답의 workspace, scope, visibility, origin/deep-link는 backend payload를 그대로 신뢰하지
  않고 file/corpus row에서 다시 hydrate한다. 현재 검색 UI는 execution workspace 안에서 fresh download를
  지원한다. 다른 workspace에서 company file의 원래 Files 상세 화면을 직접 여는 scope-neutral resolver는
  아직 없으므로 production의 광범위한 company browse/deep-link 승인은 별도 gate다.
- Download/preview signed capability는 발급 user와 execution workspace, corpus ACL metadata version을
  서명하고 byte stream 직전에 active user와 현재 Files source ACL을 다시 검사한다. Corpus 전환은 기존
  capability를 즉시 무효화하고 content 응답은 `no-store`로 제공한다.
- ACL 평가 corpus는 owner/member/admin, private/workspace, nested folder, deleted file을 모두
  포함하고 위반 0건이어야 한다.

10,000개처럼 함께 이동·공개할 batch는 업로드 전에 source-owned `files_corpus` security cohort와
non-default partition을 만든다. Mixed private/workspace 파일이 들어 있는 workspace default
partition은 whole-partition company publication 대상으로 사용하지 않는다. 실제 전환은 corpus/source
ACL row와 partition directory를 같은 transaction에서 변경한다. 과도기 file별 workspace 정본을
유지하는 경우 PostgreSQL cursor/bulk update는 허용하지만 OpenSearch/Qdrant/OCR/embedding/MinIO
rewrite는 하지 않는다.

관리 API는 `GET/POST /api/v1/workspaces/{workspace}/files/corpora`와
`POST .../files/corpora/{corpus_id}/transition`이다. Folder JSON과 upload multipart는 선택적
`corpus_id`를 받는다. Corpus 내부 child는 하나의 ACL cohort이므로 `private`/`workspace`를 섞지
않고 corpus ACL이 child visibility를 대체한다. 다른 ACL이 필요하면 업로드 전에 corpus를 나눈다.
Company corpus로의 전환과 이후 file/folder ingest는 platform admin만 수행할 수 있다.

## 기존 corpus inventory와 bounded development canary

기존 파일 묶음을 적재하기 전에는 다음 두 소유 도구를 사용한다.

- `apps/api/scripts/files_rag_readonly_harness.py`: 원본을 변경하지 않는 결정적 inventory/canary manifest
- `apps/api/scripts/files_rag_live_e2e.py`: development data plane에만 bounded canary를
  업로드·전환·검색·삭제하는 검증

읽기 전용 harness는 원본을 `O_RDONLY | O_NOFOLLOW`로 열고 scan 중 inode·크기·수정 시각이
바뀌거나 signature/archive 안전 검증에 실패한 파일을 제외한다. 원본 디렉터리 또는 symlink로
연결된 하위 경로에 manifest를 쓰지 않으며 stdout과 mode `0600` manifest에는 집계, 고정 enum,
크기와 SHA-256 ID만 남긴다. HTML도 같은 parser로 가시 본문 128자를 확인해 짧은 실행용 helper를
제외하고, generated `support/lib`·`support/slwebview_files` 하위 이미지는 HTML companion asset으로
제외한다. 파일명, 상대 경로, 본문, 검색 질의와 결과 ID 원문은 기록하지 않는다.

```bash
uv run --project apps/api python \
  apps/api/scripts/files_rag_readonly_harness.py \
  --source '/home/dwdcc/Documents/전장 RAG' \
  --dry-run \
  --workers 4 \
  --canaries-per-stratum 2 \
  --manifest-out /tmp/ai-do-files-rag-canaries.json
```

Live E2E는 loopback development API와 dev 전용 DB·bucket·index/collection prefix가 아니면
fail-closed한다. 서로 다른 actor와 두 Workspace observer token을 환경 변수로만 받고, 최대 6개·
50 MiB canary의 upload, keyword/semantic/hybrid, pagination/snippet/download,
workspace A→company→A→B ACL 전환과 cleanup을 검증한다.

```bash
AI_DO_FILES_E2E_ACTOR_TOKEN='...' \
AI_DO_FILES_E2E_A_TOKEN='...' \
AI_DO_FILES_E2E_B_TOKEN='...' \
uv run --project apps/api python apps/api/scripts/files_rag_live_e2e.py \
  --source '/home/dwdcc/Documents/전장 RAG' \
  --report-out /tmp/ai-do-files-rag-live-e2e.json \
  --workspace-a ai-tft \
  --workspace-b administrator \
  --actor-token-env AI_DO_FILES_E2E_ACTOR_TOKEN \
  --workspace-a-observer-token-env AI_DO_FILES_E2E_A_TOKEN \
  --workspace-b-observer-token-env AI_DO_FILES_E2E_B_TOKEN \
  --max-canaries 6 \
  --max-total-mib 50 \
  --execute-live-e2e \
  --acknowledge-development live-e2e-development
```

성공·실패 모두 commit된 canary child를 다시 찾아 MinIO, OpenSearch, Qdrant와 delete job까지
정리한다. 이 inventory와 bounded canary는 전체 corpus parser/OCR/embedding 처리량, 이동 중 query
concurrency, production 품질 또는 rollback 증거가 아니다.

```bash
uv run --project apps/api pytest -q \
  apps/api/tests/test_files_rag_readonly_harness.py \
  apps/api/tests/test_files_rag_live_e2e.py
```

## Operator-managed production bulk ingest와 purge

전체 디렉터리 적재는 일반 Files multipart API를 반복 호출하지 않고
`manage_files_bulk_ingest.py`의 전용 run/corpus를 사용한다. 이 corpus는 `operator_managed=true`라
일반 UI/API 업로드가 섞이지 않으며 source-relative hierarchy, manifest/content SHA-256, 안정적인
예약 file ID와 entry 상태를 보존한다. 경로를 포함하는 manifest는 stdout이나 저장소에 남기지 않고
반드시 mode `0600` 보안 경로에 둔다.

Inventory는 위 read-only harness의 동일 eligibility를 사용한다. 확장자와 120 MiB 한도를 추가로
좁힐 수 있지만 signature/archive/HTML helper/companion asset 제외를 우회할 수 없다.

```bash
cd apps/api
uv run --python 3.12 scripts/manage_files_bulk_ingest.py inventory \
  --source-root '/home/dwdcc/Documents/전장 RAG' \
  --manifest /secure/path/technical-research-files-manifest.json \
  --max-file-bytes 125829120 \
  --workers 8 \
  --include-extension docx --include-extension xlsx \
  --include-extension pptx --include-extension pdf \
  --include-extension xls --include-extension txt \
  --include-extension xlsm --include-extension ppt \
  --include-extension html
```

Manifest 집계와 SHA-256을 승인한 뒤 운영 workspace와 actor를 명시해 run을 한 번 만든다.
`--run-key`는 같은 생성 요청을 재시도할 때 그대로 쓰고, 완전히 purge한 뒤 새 적재를 만들 때만
새 값으로 바꾼다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  scripts/manage_files_bulk_ingest.py create-run \
  --manifest /secure/path/technical-research-files-manifest.json \
  --workspace-key '기술연구소' \
  --actor-login-id '<workspace-admin-login>' \
  --run-key technical-research-safe-20260729-v1 \
  --corpus-name '전장 RAG 안전 적재 2026-07-29' \
  --root-folder-name '전장 RAG' \
  --confirm-production 'workspace:기술연구소'
```

출력된 `run_id`로 25개, 추가 75개, 100개 단위 네 번까지 누적 500개를 먼저 적재한다. 각 단계에서
Files extraction 상태, Search/RAG queue drain, keyword/semantic/hybrid, ACL과 download를 확인한다.
이후 한 번에 최대 100개씩 진행하고 누적 500개마다 같은 checkpoint를 반복한다. 한 entry라도
예상하지 못한 오류가 나면 run은 `failed`로 멈추고 같은 manifest/run ID의 `ingest`를 다시 실행해야
한다. 성공 entry는 다시 업로드하지 않고 실패 entry의 동일 예약 ID만 재시도한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  scripts/manage_files_bulk_ingest.py ingest \
  --manifest /secure/path/technical-research-files-manifest.json \
  --run-id '<run-id>' \
  --actor-login-id '<workspace-admin-login>' \
  --limit 25 \
  --confirm-production 'run:<run-id>'

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  scripts/manage_files_bulk_ingest.py status --run-id '<run-id>'
```

적재를 중간에 폐기할 때는 먼저 `pause`하고, 이미 `completed` 또는 `failed`인 run은 바로 purge를
시작한다. Purge는 100개 cursor transaction으로 source row를 soft-delete하고 extraction artifact를
지운 뒤 versioned Search/RAG delete와 MinIO cleanup job을 같은 transaction에 기록한다. Durable
cleanup worker가 5분 lease, bounded retry/backoff와 dead-letter로 object를 삭제하므로 batch commit
직후 operator process가 중단되어도 누락되지 않는다. `state=purged`가 될 때까지 같은 명령을 반복하고
worker queue를 drain한 뒤 `verify-clean`을 실행한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  scripts/manage_files_bulk_ingest.py purge \
  --run-id '<run-id>' \
  --actor-login-id '<workspace-admin-login>' \
  --limit 100 \
  --confirm-production 'run:<run-id>'

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  scripts/manage_files_bulk_ingest.py verify-clean --run-id '<run-id>'
```

`verify-clean`은 active source와 extraction artifact, MinIO object와 cleanup job, projection head,
nonterminal Search/RAG job뿐 아니라 ACTIVE physical OpenSearch document와 Qdrant point를 대상
resource ID로 직접 세어 모두 0이어야 성공한다. Audit/tombstone/event/corpus/run/entry row는 삭제하지
않아 재현과 사후 분석에 보존한다.

## Production 활성화와 롤백

정확한 reconcile, prepare, materialize, v3 quality, validate와 cutover 명령은
[Files generation cutover runbook](files-generation-cutover-runbook.md)만 따른다. 일반
`evaluate_retrieval_quality`, `backfill_keyword_search --activate-existing-generation` 또는 legacy
collection fallback은 Files v3 승인·전환 경로가 아니다.

- Source mutation producer와 ACL writer를 정지하고 고정 Files watermark까지 replay한다.
- Ready extraction artifact를 재사용하며 object, parser와 OCR을 다시 실행하지 않는다.
- 비어 있지 않은 source는 OpenSearch v3/Qdrant v1 exact physical pair를 최소 60-query corpus와
  source-owned ACL로 검증한다.
- active Files row가 정확히 0인 최초 production은 별도 확인 문자열로만 empty pair의 구조,
  zero-count inventory와 embedding/reranker identity를 검증한다. validation에는
  `quality_status=deferred_until_nonempty`를 기록하며 품질 통과로 표현하지 않는다.
- Source head와 두 backend inventory, alias와 PostgreSQL generation pair가 모두 일치한 뒤 gate를
  마지막으로 연다. Queue depth 0만으로 승인하지 않는다.
- Unsupported 파일은 `unsupported`, 반복 불가능한 parser 실패는 `failed`로 표시하고 provider
  transient 오류는 기존 worker lease/retry/dead-letter 계약으로 처리한다.
- Gate를 닫으면 신규 query와 backend mutation은 멈추지만 canonical event/head와 pending job은
  보존한다.
- 현재 runner는 최초 activation만 지원한다. 성공 전 오류는 보상하지만 성공 후 서비스 rollback은
  gate-off와 code/config rollback이며 dedicated physical pair를 삭제하거나 legacy alias로 돌리지
  않는다.
- 후속 physical generation upgrade/rollback은 replay-aware 명령이 구현되지 않아
  `generation_upgrade_rollback_unsupported`로 fail-closed한다.

Production 승인은 runbook의 migration/unit/integration 검증 외에도 worker health/queue, Nori,
실제 upload-to-hybrid, ACL/citation와 gate-off rollback smoke를 요구한다.
Empty bootstrap 직후에는 세 검색 모드의 200/빈 결과를 확인하고, 첫 문서가 들어오면 동일 ACTIVE
pair에 keyword/vector가 생성되는 upload-to-hybrid canary를 즉시 수행한다. Representative
corpus가 생기면 generation runbook의 `attest-active`로 최소 60-query v3 evidence를 append-only
기록한다. 기존 empty validation을 덮어쓰거나 workspace 증거를 company scope 승인으로 재사용하지
않는다.
