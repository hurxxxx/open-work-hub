# Files Retrieval Generation Cutover Runbook

이 문서는 Files 전용 OpenSearch v3/Qdrant v1 physical generation을 준비하고 최초로
활성화하는 운영 절차다. 소스·ACL 계약은
[Files Retrieval Source Activation](files-source-activation.md), 일반 generation 원칙은
[ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md)을 따른다.

## 안전 경계

- 모든 명령은 명시적 subcommand이며 production deploy가 generation을 자동 생성하거나
  alias를 변경하지 않는다.
- Files generation은 전용 OpenSearch/Qdrant alias만 변경한다. 기존 전사 legacy alias는
  읽거나 이동하지 않는다.
- checkpoint는 전체 retrieval event 최댓값이 아니라 정확한 최신
  `file_manager_file` event sequence다. Docs 등 다른 source event는 Files 승격을 막거나
  Files checkpoint를 전진시키지 않는다. 반대로 validation 뒤 새 Files event가 하나라도
  생기면 승격을 중단한다.
- initial materializer는 저장된 extraction artifact만 읽는다. object storage, parser, OCR을
  다시 실행하지 않는다. Gate가 닫힌 기존 source의 artifact가 없으면 아래 operator-only
  `bootstrap-extraction`으로 먼저 생성한다. 새 Qdrant physical generation에 vector가 없으면
  embedding은 한 번 생성해야 한다.
- 명령 출력은 집계값과 안정적인 오류 코드만 포함한다. corpus, quality artifact와 원시
  backend dump는 저장소에 commit하지 않는다.
- 현재 runner는 **최초 Files activation만** 허용한다. ACTIVE Files pair가 이미 있으면
  `generation_upgrade_rollback_unsupported`로 후속 generation cutover를 막는다.

## 사전 조건

1. DB migration과 동일 binary가 모든 API/worker instance에 배포되어 있어야 한다.
2. `AI_DO_FILES_RETRIEVAL_ENABLED=false` 상태여야 한다.
3. OpenSearch는 Nori가 포함된 v3 schema를, Qdrant는 partitioned v1 collection과 payload
   index를 지원해야 한다.
4. source mutation producer와 workspace membership/user-status/corpus ACL을 바꾸는 모든 writer를
   중지하고 in-flight API write를 drain한다. Search/RAG worker도 중지한다. 아래 `--confirm-*`
   옵션은 중지 작업을 수행하지 않으며 운영자의 확인을 기록할 뿐이다. 이 정지 경계는 품질 평가
   시작부터 cutover 완료까지 유지해 ACL revision의 ABA 변경을 막는다.
5. 비어 있지 않은 source라면 최소 60개 query의 versioned Files-only judged corpus를 보안 경로에
   준비한다. owner/member/admin, private/workspace/company, folder ancestry, 삭제 및 접근 금지
   resource를 포함한다. 각 relevant ID는 해당 case context에서 읽을 수 있는 active Files row여야
   하고, 각 forbidden ID는 오타나 삭제 row가 아니라 실제 active Files row이면서 keyword/RAG ACL
   모두에서 거부되어야 한다.

active Files row가 정확히 0인 최초 production은 별도 empty bootstrap 절차를 사용할 수 있다.
`resource_count=0`, `unsupported_count=0`, `unavailable_count=0`, 기존 ACTIVE generation 없음,
두 physical backend count=0이 모두 필요하다. 이 경로는 품질 평가를 통과한 것으로 간주하지 않으며
validation에 `quality_status=deferred_until_nonempty`를 기록한다.

production mutation은 generation 명령의 `--confirm-production-generation` 값이 `--generation`과
정확히 같아야 한다. Source extraction은 별도의
`--confirm-production-extraction bootstrap-files-extraction`, legacy adoption은
`--confirm-production-adoption adopt-legacy-files`를 요구한다. 아래 예시는 development 형식이며
production에서는 해당 확인 옵션을 추가한다.

## 1. Gate-closed extraction bootstrap

Gate가 닫혀 있던 동안 등록된 active Files row에 extraction artifact가 없으면, source writer와
Search/RAG worker를 중지한 상태에서 object storage → parser/OCR 결과만 DB에 저장한다. 이 명령은
OpenSearch, Qdrant, embedding을 호출하는 인터페이스를 갖지 않으며, ready checksum 또는 unsupported
tombstone에 맞춰 canonical head/event만 갱신한다.

```bash
cd apps/api
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py bootstrap-extraction \
  --limit 25 \
  --confirm-writes-quiesced \
  --confirm-workers-stopped \
  --confirm-operator-gate-disabled \
  --dry-run
```

dry-run 확인 후 `--dry-run`을 제거한다. 출력의 `next_file_id`를 다음 실행의
`--after-file-id`로 전달하고 `complete=1`까지 반복한다. Production mutation에는
`--confirm-production-extraction bootstrap-files-extraction`을 추가한다.

- `failed_files`가 하나라도 있으면 generation 준비로 진행하지 않는다. storage/parser/OCR 원인을
  해결한 뒤 `--after-file-id`를 생략하고 처음부터 재실행한다. 명령은 실패 상태를 DB에 저장한 뒤
  `extraction_batch_incomplete`와 non-zero exit로 자동화를 중단한다. 이미 ready인 artifact와
  일치하는 source fence는 재사용되므로 backend write나 중복 event가 생기지 않는다.
- `unsupported_files`는 명시적인 deleted source fence로 남고 baseline 대상에서 제외된다.
- 프로세스 중단 전 commit되지 않은 batch는 동일 cursor로 재실행한다. 성공한 이전 batch는 DB
  artifact와 checksum fence를 재사용하므로 재파싱하지 않는다.

## 2. Legacy source 채택

1단계 뒤에도 canonical head/event가 없는 legacy Files row(삭제 row 포함)는 bounded cursor로
채택한다. 이 단계는 backend, object storage, OCR, parser, embedding을 호출하지 않는다.

```bash
cd apps/api
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py reconcile-source \
  --limit 500 \
  --confirm-writes-quiesced \
  --confirm-operator-gate-disabled \
  --dry-run
```

dry-run 확인 후 `--dry-run`을 제거한다. 출력의 `next_file_id`를 다음 실행의
`--after-file-id`로 전달하고 `complete=1`까지 반복한다. production에서는 추가로
`--confirm-production-adoption adopt-legacy-files`가 필요하다. `pending`/`failed` source나
불완전 extraction artifact가 있으면 1단계로 돌아가 원인을 해결하며 unavailable baseline을
건너뛰지 않는다. 마지막 출력의 Files `event_watermark`를 기록한다.

## 3. Physical pair 준비

일반적인 비어 있지 않은 최초 적재는 `cached-artifacts`를 사용한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py prepare \
  --generation release_20260723 \
  --baseline-mode cached-artifacts \
  --dry-run

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py prepare \
  --generation release_20260723 \
  --baseline-mode cached-artifacts
```

- `adopt-prepared`는 두 physical backend가 이미 완전하게 존재하고 source identity/count와
  일치할 때만 사용한다. 하나라도 없으면 생성하지 않고 실패한다.
- `empty`는 source count가 0인 개발 검증 또는 아래의 명시적 production 최초 bootstrap에만
  사용한다.
- 같은 명령의 재실행은 같은 generation row와 physical pair를 재사용한다.

Production empty pair 준비에는 일반 production generation 확인도 함께 사용한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py prepare \
  --generation release_empty_20260723 \
  --baseline-mode empty \
  --confirm-production-generation release_empty_20260723
```

## 4. Cached artifact materialization과 replay

2단계에서 기록한 고정 Files watermark까지 작은 batch로 진행한다. 첫 실행 cursor는 0이고,
`complete=0`이면 출력의 `next_event_sequence`를 다음 `--after-event-sequence`로 전달한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py materialize \
  --generation release_20260723 \
  --after-event-sequence 0 \
  --through-event-sequence 12345 \
  --limit 100 \
  --confirm-writes-quiesced \
  --confirm-workers-stopped
```

두 backend write가 모두 성공한 current fenced event만 대응 Search/RAG paused job을 같은 DB
transaction에서 `succeeded`로 기록한다. 오래된 fenced job은 `cancelled`가 되며 unfenced 또는
불일치 job은 남아서 승격을 막는다. 한 backend만 성공하면 queue row는 성공 처리하지 않고,
재실행이 physical write를 idempotent하게 수렴시킨다.

마지막 `complete=1` batch는 validation inventory를 읽기 전에 Files physical OpenSearch index에
명시적 `_refresh`를 실행한다. OpenSearch write는 평상시 `refresh=false`인 near-real-time 계약이고,
Qdrant upsert/delete는 `wait=true`이므로 이 경계가 없으면 마지막 keyword document가 아직 `_count`나
`_search`에 보이지 않아 `projection_resource_count_mismatch`가 거짓으로 발생할 수 있다. Refresh 또는
inspection이 실패하면 generation을 폐기하거나 cursor를 건너뛰지 말고, writer/worker 정지와 고정
watermark를 다시 확인한 뒤 **같은 cursor와 watermark**로 materialize를 재실행한다. External version과
stable point ID 때문에 이 재실행은 idempotent해야 한다.

중지 중 새 Files event가 생겼거나 watermark가 달라지면 mutation producer 중지를 다시 확인하고
최신 Files watermark까지 `replay` subcommand로 같은 cursor 절차를 반복한다. 다른 source의 event
증가는 replay 대상이 아니다.

## 5. Exact physical v3 품질 평가

legacy v2 evaluator 결과는 승격 증거로 사용할 수 없다. 다음 read-only evaluator는 alias가 아니라
명시한 Files OpenSearch v3/Qdrant v1 physical pair를 BM25, semantic, hybrid 각각 60개 이상 query로
평가하고 mode `0600` artifact를 새 파일로 원자 생성한다. 기존 output을 덮어쓰지 않는다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python -m ai_do_api.evaluate_files_partitioned_quality \
  --corpus /secure/path/retrieval-quality-corpus-v1.json \
  --generation release_20260723 \
  --output /secure/path/files-quality-release_20260723.json
```

artifact v3는 exact corpus SHA-256과 다음 immutable identity를 포함해야 한다.

- OpenSearch physical UUID, mapping/settings SHA-256, 전체 content SHA-256
- Qdrant physical collection ID, schema/config SHA-256, payload/vector content SHA-256
- secret-free embedding model identity와 embedding config SHA-256
- disabled 상태와 candidate-k를 포함한 secret-free reranker identity/config SHA-256
- 평가한 Files source watermark/count/identity/artifact/ACL-envelope SHA-256
- 각 judged principal이 볼 수 있는 전체 active Files keyword/RAG 집합의 secret-free ACL SHA-256

각 case는 실제 active forbidden resource를 적어도 하나 포함해야 하며, 비회원 principal은 평가하지
않는다. 평가 전후 physical inventory, source snapshot 또는 principal ACL 집합이 달라지거나 degraded
retrieval, ACL/citation failure, p95/recall/ranking gate가 실패하면 artifact를 승인하지 않는다. Hybrid
absolute floor는 Recall@10 0.80, MRR@10 0.50, nDCG@10 0.50이며 baseline 대비 recall 무회귀와 nDCG
또는 MRR 5% 상대 개선도 함께 유지한다.

정확히 빈 production 최초 bootstrap은 이 절을 실행하지 않는다. 평가할 content나 relevant ID가
없으므로 60-query 품질 통과를 만들 수 없기 때문이다. 대신 다음 validation에서 두 backend의 구조와
zero-count inventory, secret-free embedding/reranker identity를 고정하고 품질 상태를
`deferred_until_nonempty`로 남긴다.

## 6. Validation

source mutation과 worker가 계속 중지된 상태에서 current Files watermark를 정확히 전달한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py validate \
  --generation release_20260723 \
  --confirm-writes-quiesced \
  --reconciliation-watermark 12345 \
  --quality-corpus /secure/path/retrieval-quality-corpus-v1.json \
  --quality-report /secure/path/files-quality-release_20260723.json \
  --dry-run
```

dry-run 성공 뒤 `--dry-run`을 제거한다. Validation은 source identity, extraction artifact checksum,
unsupported/unavailable count, Files-only cohort, queue drain, 두 backend inventory 및 quality v3의 모든
physical/embedding/reranker identity와 현재 principal ACL SHA-256을 generation row에 기록한다. 이후
새 Files event, source ACL, membership/user 상태 또는 backend/config 변경은 cutover를 막는다.

정확히 빈 production 최초 bootstrap은 quality 파일 대신 별도 고위험 확인 문자열을 사용한다.
확인 문자열이 없거나 다르면 empty validation은 거부된다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py validate \
  --generation release_empty_20260723 \
  --confirm-production-generation release_empty_20260723 \
  --confirm-empty-production-bootstrap bootstrap-empty-files-retrieval \
  --confirm-writes-quiesced \
  --reconciliation-watermark 0 \
  --dry-run

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py validate \
  --generation release_empty_20260723 \
  --confirm-production-generation release_empty_20260723 \
  --confirm-empty-production-bootstrap bootstrap-empty-files-retrieval \
  --confirm-writes-quiesced \
  --reconciliation-watermark 0
```

Dry-run은 mutation 승인을 요구하지 않지만 실제 validation은 두 확인 문자열을 모두 요구한다.
빈 validation은 기존 ACTIVE pair가 있거나 unsupported/pending/failed를 포함한 active Files row가
하나라도 있으면 실패한다.

## 7. 최초 alias cutover

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py cutover \
  --generation release_20260723 \
  --confirm-writes-quiesced \
  --quality-corpus /secure/path/retrieval-quality-corpus-v1.json \
  --rollback-window-hours 168 \
  --dry-run

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py cutover \
  --generation release_20260723 \
  --confirm-writes-quiesced \
  --quality-corpus /secure/path/retrieval-quality-corpus-v1.json \
  --rollback-window-hours 168
```

Runner는 alias precondition을 두 backend 모두 확인한 뒤에만 전환한다. 알 수 없는 alias target이
있으면 외부 alias를 수정하지 않고 `compensation_required`로 닫는다. 한 alias만 이동했거나 DB
completion이 실패하면 실제로 이동한 alias만 이전 target으로 복구하고 pair를 보상한다. Non-empty
pair는 validation에 사용한 동일 corpus를 다시 요구하고 alias 이동 전과 두 alias 이동 후에 현재
principal ACL을 재검증한다. 두 번째 검사에서 membership/ACL 변경이 발견돼도 alias를 복구한다.
Empty bootstrap pair는 `--quality-corpus` 없이 cutover하되
`--confirm-production-generation release_empty_20260723` 확인은 그대로 요구한다.

성공 직후 writer를 재개하기 전에 full read-only evidence gate를 실행한다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/check_files_retrieval_cutover.py
```

이 checker는 ACTIVE/PASSED Files-only cohort, schema/config, 전용 alias 두 개, current source-head/backend
inventory, queue drain을 확인한다. Activation 뒤 정상 write가 진행되면 content count/checksum과 Files
watermark가 바뀌므로 steady-state checker는 과거 activation content checksum을 고정하지 않고 현재
head와 physical inventory의 일치를 검사한다.

마지막으로 표준 production deploy로 `AI_DO_FILES_RETRIEVAL_ENABLED=true` binary를 활성화한다.
위의 writer 재개 전 checker는 최초 generation cutover의 필수 증거이므로 생략하지 않는다. 표준
deploy는 corpus 전체 checker를 다시 실행하지 않는다. checker는 PostgreSQL source, OpenSearch
document, Qdrant payload·vector를 전수 순회하므로 generation cutover, 인덱스 장애 조사, 승인된
명시적 감사에만 사용한다. 일반 배포에서는 최종 smoke와
`[prod-deploy] deployment flow complete`를 확인한다.

Empty bootstrap은 gate 활성화와 API/RAG worker/Search worker 재시작 뒤 keyword, semantic,
hybrid 각각이 HTTP 200, `hits=[]`, `has_more=false`인지 확인한다. Generation 또는 backend 장애를
빈 결과로 바꾸지 않는다. 첫 문서 업로드 뒤에는 extraction → ACTIVE Qdrant/OpenSearch write →
세 검색 모드 → ACL → download canary를 수행한다. Empty bootstrap 자체는 계속 실데이터 품질
승인으로 표시하지 않으며, representative corpus가 준비되면 다음 절의 append-only attestation을
별도로 완료한다.

## 8. Empty bootstrap 이후 실데이터 품질 attestation

이 명령은 처음에 `resource_count=0`,
`quality_status=deferred_until_nonempty`로 활성화된 **현재 ACTIVE pair만** 대상으로 한다.
원래 generation validation을 덮어쓰지 않고
`retrieval_projection_generation_attestations`에 source watermark별 증거를 추가한다.
동일 watermark와 동일 artifact 재실행은 멱등이고, 동일 watermark에 다른 증거를 넣는 시도는
`quality_attestation_conflict`로 중단된다.

업로드를 일시 중지하고 Search/RAG queue를 완전히 drain한 뒤, 현재 실데이터와 exact physical
backend에 대해 5절의 v3 평가를 실행한다. 평가 corpus가 포함하는 scope를 모두 명시하며, 현재
active source의 실제 scope 집합과 정확히 같지 않으면 기록하지 않는다. 예를 들어 워크스페이스
전용 corpus는 다음과 같다.

```bash
AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py attest-active \
  --generation prod-empty-20260723 \
  --confirm-writes-quiesced \
  --quality-corpus /secure/path/retrieval-quality-corpus-v1.json \
  --quality-report /secure/path/files-quality-prod-empty-20260723.json \
  --scope-coverage workspace \
  --dry-run

AI_DO_API_AUTO_MIGRATE=0 uv run --python 3.12 \
  python scripts/manage_files_retrieval_generation.py attest-active \
  --generation prod-empty-20260723 \
  --confirm-writes-quiesced \
  --quality-corpus /secure/path/retrieval-quality-corpus-v1.json \
  --quality-report /secure/path/files-quality-prod-empty-20260723.json \
  --scope-coverage workspace \
  --confirm-production-attestation attest-active-files-quality
```

Runner는 non-empty source, unsupported/unavailable 0, ACTIVE pair/alias, queue drain, current
source/backend reconciliation, embedding/reranker identity, 최소 60 query의 gate 및 현재 principal
ACL digest를 모두 다시 검사한다. 기록 직전 Files event watermark를 다시 확인한다. 이후 정상적인
신규 write는 attestation 당시 content checksum을 steady-state gate로 고정하지 않는다.
워크스페이스 증거를 company 전환 승인으로 재사용하지 말고 전환 scope를 포함한 별도 attestation을
생성한다.

## 실패, 보상, 최초 activation 롤백

| 상태/오류                                                           | 조치                                                                                                                                                                                                                  |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `source_baseline_unavailable`                                       | pending/failed artifact와 head fence를 복구한 뒤 처음부터 snapshot                                                                                                                                                    |
| `*_watermark_mismatch`, `source_changed_*`                          | writer 중지를 확인하고 최신 Files watermark로 replay/validate 반복                                                                                                                                                    |
| `projection_resource_count_mismatch`                                | 완료 batch의 OpenSearch refresh 성공 여부와 source/OpenSearch/Qdrant 고유 resource count를 각각 확인; transient NRT 지연이면 같은 cursor/watermark로 idempotent materialize 재실행, 실제 identity 차이면 cutover 금지 |
| `quality_corpus_required_for_cutover`, `quality_judgment_acl_stale` | 동일 corpus를 다시 제공하고 source·membership·user-status writer 정지 여부를 확인한 뒤 재평가/validate                                                                                                                |
| `alias_precondition_mismatch`                                       | alias를 수동 덮어쓰지 말고 외부 소유자/target 조사; DB는 compensation-required                                                                                                                                        |
| `alias_cutover_failed`, `database_cutover_failed`                   | 자동 복구된 alias와 두 DB row가 `failed`인지 확인 후 새 generation 사용                                                                                                                                               |
| `alias_compensation_required`                                       | Gate를 닫은 채 두 alias와 DB pair를 운영자가 대조; 자동 재시도 금지                                                                                                                                                   |
| `generation_upgrade_rollback_unsupported`                           | 후속 generation 승격 금지; 별도 rollback/replay 기능을 구현·검증한 뒤 진행                                                                                                                                            |

이번 경로는 기존 ACTIVE partitioned Files pair가 없는 **최초 activation**이다. 성공 전 오류는 runner가
자동 보상한다. 성공 후 문제가 발견되면 즉시 Files gate를 다시 끄고 code/config를 rollback한다.
legacy Files retrieval은 이전에 활성화된 적이 없고 legacy alias도 이 절차에서 이동하지 않았으므로,
최초 activation의 안전한 서비스 롤백은 gate-off이며 dedicated physical pair를 급히 삭제하거나 legacy
alias를 변경하지 않는다. 보존된 generation은 사후 분석 대상으로 둔다.

후속 physical generation upgrade에는 이전 ACTIVE pair로 되돌리는 replay-aware 명령이 필요하다. 해당
기능이 아직 없으므로 runner가 upgrade cutover 자체를 fail-closed로 차단한다.

## 코드 검증

```bash
uv run --project apps/api pytest -q \
  apps/api/tests/test_files_generation_runner.py \
  apps/api/tests/test_files_retrieval_cutover.py \
  apps/api/tests/test_retrieval_projection_generations.py \
  apps/api/tests/test_evaluate_files_partitioned_quality.py \
  apps/api/tests/test_file_manager_corpus_scale_migrations.py

cd apps/api
uv run --python 3.12 --group dev lint-imports
```

실제 activation 승인은 위 unit/integration test 외에도 development infrastructure에서 실제 Files upload,
workspace/company ACL 전환, keyword/semantic/hybrid ranking, pagination/snippet/download, worker retry 및
gate-off rollback smoke 증거가 있어야 한다.
