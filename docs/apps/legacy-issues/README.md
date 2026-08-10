# Legacy Issues AI Search

Legacy Issue AI Search is an app-owned evidence search surface. It is
user-facing and retrieval-integrated, but it is not Generic RAG.

## Boundary

| area                   | policy                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| Backend                | App-owned LlamaIndex metadata/evidence retrieval on PostgreSQL FTS/pgvector and final source ACL. |
| Scope                  | Workspace-scoped legacy issue datasets and attachments.                                           |
| Retrieval integration  | Exposed through `legacy_issues` as an active retrieval source.                                    |
| Generic RAG            | Not used for legacy issue records or attachment evidence.                                         |
| Conversation artifacts | Owned by the legacy issues app and rendered through AI analysis and report-management views.      |

## Rules

- Keep legacy issue evidence payloads and conversation artifacts documented here,
  not in Generic RAG docs.
- The assistant reuses the shared chatbot UI and conversation transport, but its
  server-owned conversation experience belongs to `legacy-issues` and executes
  the `legacy_issues.conversation_answer` workload. Disabling the standalone
  `chatbot` app must not disable this scoped assistant; disabling `legacy-issues`
  must block new and stored assistant conversations.
- Retrieval may normalize legacy issue hits for cross-source search, but it must
  not hide the app-specific search and ACL rules.
- Records, revisions, attachments, attachment-index jobs, and derived AI chunks
  inherit the same immutable `retrieval_partition_id`. Native PostgreSQL
  FTS/trigram/pgvector queries apply the partition predicate as a coarse candidate
  envelope and retain workspace/revision rules as the final ACL. Legacy Issues is
  not duplicated into Generic RAG or Qdrant for partition consistency.
- During the nullable expand release, every native candidate and follow-up hydrate
  uses `workspace/dataset/revision AND (partition IS NULL OR partition IN server scope)`.
  An empty server scope may return only genuine legacy NULL rows, never an unfiltered
  result. Remove the NULL branch only after all revision/record/attachment/chunk/job
  bindings are non-NULL, parent-child mismatches and orphans are zero, all producers
  dual-write, and the validated composite FK/NOT NULL contract is deployed.
- Changes to legacy issue search quality should update app tests and retrieval
  source catalog expectations together.

## AI analysis graph and artifact contract

[ADR 0010](../../../adr/0010-durable-ai-graph-artifact-and-grounded-analysis.md)
defines the shared durable execution and artifact model.

- A scoped assistant submission persists its user turn, assistant placeholder,
  `ai_graph_runs` projection, pending artifact, and dispatch record before it is
  acknowledged. The dedicated `ai_graph` worker owns execution after that point.
  Browser navigation, refresh, disconnect, and worker restart do not cancel the
  run. Reload reads the conversation and graph-run projection; live events only
  accelerate the same DB-backed state.
- Before applying the analysis data-plane migration, a database administrator
  provisions the cluster-wide `open_alm_analysis_reader` role and grants it to the
  application role. The idempotent bootstrap is
  `psql "$ADMIN_DSN" --set=app_role=<application-role> --file scripts/provision-ai-analysis-reader.sql`.
  The migration fails closed if this least-privilege role contract is absent.
- LangGraph is the only graph/checkpoint state machine. The projection stores
  only ACL, progress, current stage, outcome, conversation, and artifact links.
  Every LLM node uses its own registered `legacy_issues.*` workload through the
  AI Gateway.
- Structured analysis is recipe-first. Versioned YAML recipes cover general
  count, distribution, rank, cross-tab, time, comparison, change, share/rate,
  Pareto, duration, completeness, detail, issue/cause/countermeasure, and
  checklist questions. A guarded free SQL route is available only after the
  planner explicitly establishes that no compatible recipe exists; an empty
  result or execution error does not authorize fallback.
- The bounded SQL agent's final text is not an answer source. If it reaches its
  step limit or a model-action error, deterministic supplementation verifies
  that every requested source class (statistics, semantic evidence, and
  checklists) has successful captured results. Only then may the parent graph
  continue and record `execution_warnings` with degraded analysis health.
  Missing required sources, failed queries or retrieval, unresolved scope, and
  missing revision snapshots remain hard failures.
- Recipe results preserve both SQL bindings and the validated logical arguments
  (dimensions, filters, ordering, and limits). Report nodes receive the recipe
  title, counting unit, result shape, explicit metric numerator/denominator
  definitions, denominator-bearing columns, and whether a limited result covers
  the full population. SQL result-row counts and presentation limits are never
  treated as business counts, and semantic hits remain qualitative examples
  rather than aggregate totals.
- Generic two- and three-dimension recipes keep every compared dimension in the
  same atomic result row. Missing dimension values are emitted as `미입력` and
  remain distinct from a literal `-`. Detail recipes support allowlisted exact
  filters, including explicit null filters, so representative
  supplier/part/stage/process/cause rows cannot be selected by a broad text
  match.
- SQL can read only `legacy_issue_analysis.*_v1` security-barrier views. The
  server binds workspace, partition, module, effective revision, and checklist
  IDs in the same read-only transaction. Missing scope returns zero rows.
  SQLGlot enforces one parameterized SELECT, allowed views/columns/functions,
  bounded joins, a five-second statement timeout, at most 1,000 rows, and at
  most 250 KiB. Invalid typed source values become null and are excluded from
  typed conditions rather than repaired during analysis.
- LlamaIndex retrieves SQL metadata and legacy issue evidence from PostgreSQL
  pgvector. The assistant and common Retrieval `legacy_issues` source use the
  same app-owned retriever. Every candidate still passes the ADR 0009 partition
  envelope and source-owned workspace/module/effective-revision ACL before LLM
  input or citation.
- An explicitly requested report runs four waves: question-appropriate outline
  plus applicable quantitative/evidence/checklist specialists in parallel;
  draft; grounding review; finalization. A server validator checks numeric
  literals, evidence IDs, and internal-processing commentary against captured
  sources. It allows one correction call, then uses a generic source-derived
  Markdown fallback that omits unsupported claims. A requested metric whose
  required source column does not exist is carried as a hard capability
  limitation; report generation and fallback state that limitation instead of
  substituting a similar field or dumping unrelated query tables.
- Cross-tab recipes return row and overall denominators, composite hotspot
  recipes return their own shares, and checklist recipes distinguish linked
  from unlinked items/issues. Low-coverage ties are ordered by issue count so a
  recipe limit cannot turn an alphabetical slice into a risk ranking. Report
  validation keeps a dimension label and its metrics on one captured result
  row, rejects all-population claims from limited rows, and accepts rank
  ordinals only in an explicit contiguous rank column.
- `ai_artifacts` owns completed report/analysis content; `ai_artifact_queries`
  owns parameterized SQL, typed parameters, status, result schema/rows,
  duration, count, and truncation; `ai_artifact_sources` owns semantic and
  checklist evidence. Completed content and lineage are immutable. Owner-audited
  `private`/`workspace` visibility changes and FK nulling caused by conversation
  deletion are access/link metadata changes and do not alter the content hash.
  Report numbers use `AIR-YYYYMMDD-##########`, analyses use
  `AIA-YYYYMMDD-##########`, and regeneration creates a new artifact linked by
  `supersedes`.
- Report management queries only completed `report` artifacts. Its default list
  contains reports owned by the current member; a separate shared list contains
  reports that other members explicitly made workspace-visible. A report opens
  independently from its conversation with the final Markdown first. Stored SQL,
  typed parameters, and captured result rows appear in `SQL·조회 결과`, while
  semantic and checklist evidence appear in `의미검색 근거`. These views never
  rerun SQL or present internal JSON as another top-level report.
- Every list, detail, chat report panel, and Markdown download shows the same
  `AIR-*` report number. Historical reports without captured SQL/result lineage
  show a distinct not-captured state and never reconstruct missing evidence.
- Historical conversation artifacts that were explicitly stored as completed
  `document` reports are migrated before old tables are removed. Standalone
  assistant answers without a persisted report type remain legacy compatibility
  data and never appear in report history. Missing historical SQL/result
  lineage is `not_captured`; migration never reconstructs evidence that was not
  stored.

## AI effective revision contract

- AI discovery searches every enabled legacy-issue module in the current
  workspace. For each module it selects the active saved draft when one exists;
  otherwise it selects only the latest published revision.
- Older published revisions, canceled drafts, and unsaved browser edits are not
  AI search candidates. Every exact/term/FTS/trigram/vector/related-field path is
  fenced by the selected revision IDs.
- Draft creation rebuilds the record text projection from the copied records
  without an external model call. It reuses a base-revision embedding only when
  the stable record, chunk key, normalized generated search content, embedding
  model, and dimensions all still match. Normalization only removes the legacy
  `revision:` metadata segment immediately after the dataset title in summary
  chunks. Before searching, the app verifies that every
  selected revision record has its canonical summary chunk;
  missing record projections are rebuilt as SQL text projections under a revision
  lock in a separate short transaction, without calling the embedding provider.
  Retrieval and report LLM transactions therefore stay read-only. The same
  reconciliation queues legacy `not_indexed` attachments on an effective revision
  when attachment indexing is enabled, with one shared bounded batch per search
  request. When a draft copies an attachment whose source indexing is pending or
  processing, the target attachment receives a bounded post-commit indexing job
  batch; remaining `not_indexed` attachments are reconciled by later searches.
- Evidence hydration is history replay, not discovery. Saved references to a
  published revision remain resolvable; a draft reference resolves only while
  that exact draft is active. Hydration applies the same workspace, dataset,
  enabled-module, revision, and server-resolved partition envelope as search.

## Master data revision contract

- `common-master` remains the authoritative physical dataset; module screens are
  filtered by `module_key`.
- Every enabled module, including heat exchanger, owns an independent revision
  sequence.
- The first module read persists its initial published revision before the Web
  requests the revision list. This keeps the returned base revision stable so a
  newly registered module with no prior revision can start its first draft and
  accept initial data immediately.
- The All screen combines the latest published revision from every module and
  supports list/search only.
- Platform administrators and users explicitly assigned to that module may
  create, update, and delete rows and manage their attachments in the latest
  published module revision without incrementing that revision, but only while
  the module has no active draft. Platform administrators manage assignments
  from the platform-admin-only Direct Edit Permissions settings page.
  Assignments are workspace- and module-scoped, require an active workspace
  membership, and do not grant module-field management. The settings page shows
  every enabled module and its assigned users together, with module-local user
  search and grant/revoke controls. Attachment management includes upload,
  delete, description, and primary-file changes. Import continues to use the
  normal draft workflow.
- Existing-record attachment changes are staged in the detail panel and applied
  only by an explicit Save action. The detail panel exposes Save on the
  Attachments tab; pending uploads and metadata changes do not call attachment
  mutation APIs before a save.
- Overview revision-history rows are display metadata. Platform administrators
  may add rows, change their displayed revision number, or hide them from the
  Overview table. A row linked to a published data revision keeps that stable
  link even when its display number changes; hiding it never deletes or
  renumbers the published revision, its records, attachments, or audit events.
- Publishing a new master data revision continues to create its corresponding
  Overview revision-history row automatically.
- Every module exposes a compact Meeting Minutes tab grouped by revision. It
  keeps revision metadata to the revision number, date, and a short summary so
  users can scan and manage all attached files without repeating the full
  Overview table. Each Overview row also provides a Meeting Minutes action that
  opens the same file manager in a revision-scoped dialog. Both entry points use
  the same visible revision-history rows, including imported and manually added
  rows. Every visible published data revision is backed by a stable
  overview-history row; the migration links a matching active unlinked row
  before creating a missing system row and never reactivates a hidden row.
- Meeting-minutes attachments belong to the stable overview-history row rather
  than a mutable display revision number. Workspace members may list, download,
  and upload multiple files on visible rows. The uploader and platform
  administrators may update an attachment description, while only platform
  administrators may delete an attachment. Hiding an Overview row also hides
  its meeting files from normal access but retains their metadata, objects, and
  audit history.
- Meeting-minutes files accept arbitrary formats up to 1 GiB per non-empty
  file and are always served as downloads. Uploads use counted streaming and
  rollback compensation. A stable per-file client request ID makes response-loss
  retries return the original attachment instead of storing or auditing a
  duplicate. Deletion commits a cleanup outbox entry before object removal and
  periodic retry. These files do not reset revision review or approval, copy
  into a draft, participate in AI indexing, or appear in Excel exports.
- A draft is shared workspace data, while `locked_by_id` represents only the
  current editing session. The immutable creator is audit metadata and does not
  retain edit ownership after save. Starting editing claims an unlocked active
  draft; saving the draft releases it so another workspace member can claim and
  continue the same draft. An unlocked draft's record and attachment content is
  read-only until it is claimed, while its reviewer and approver may still be
  assigned unless another editor currently owns the lock. Assignee candidates
  are restricted to active members of the draft's workspace.
  Draft claims, content mutations, and release operations lock the revision row
  for the transaction so a delayed request from a previous editor cannot commit
  after a new editor has acquired the draft. Ordinary row saves persist changes
  and release editing in one batch transaction; attachment workflows finalize
  the release after their file operations and can retry that final step.
- Ordinary draft cancellation requires an explicit destructive confirmation
  even when the browser has no unsaved changes. It warns that all saved
  unpublished records and attachment changes will disappear from the normal UI
  and directs users who only want to release the edit lock to Finish editing.
  Cancellation retains persisted revision data for audit and incident recovery,
  but the product has no normal restore workflow.
- A platform administrator or a user with direct-edit access to the draft's
  module may force-cancel an active draft locked by another user. The API
  exposes this capability only for the matching module, and the Web action
  requires an explicit destructive confirmation that names the current editor
  and warns that unpublished and browser-only work cannot be recovered. The
  client sends an explicit force flag that the API requires. The cancellation is
  serialized by the revision row lock and records both a `force_cancel`
  revision event and a global audit log containing the authorization source,
  module, previous editor, and immutable creator. It changes the revision status
  and releases the active-draft slot without physically deleting revision
  records, attachments, shared storage objects, or derived artifacts; canceled
  content has no normal user restore workflow.
- Any draft record or attachment content change clears prior review and approval
  completion. The assigned reviewer and approver remain, but the changed content
  must be reviewed and approved again before publication.
- Draft cells that differ from the draft's base revision stay highlighted after
  save, refresh, and editor handoff. The highlight is derived from the persisted
  base-to-draft comparison, cached per mutable revision version as a best-effort
  display aid, and hydrated independently so comparison latency does not delay
  record loading or save completion. It disappears when the draft is published
  or canceled rather than being scoped to one browser's unsaved edit state.

## Vehicle module checklist contract

- Navigation is vehicle list → vehicle-development stage → module list →
  module checklist detail. Each vehicle shows its stages in registration order,
  and each stage shows checklists grouped by the independently revised source
  module.
- Every vehicle is created atomically with one required initial stage. Later
  stages are append-only history: their display names are unique per vehicle,
  their order comes from registration sequence rather than name parsing, and
  they are not deleted or reordered.
- A stage owns a stable identifier independent of its display name. Renaming a
  stage updates that one stage record, while checklist references, predecessor
  lineage, ordering, badges, tabs, and titles continue to resolve through the
  stable identifier and show the current name.
- Existing vehicles are backfilled with one `기존` stage so their checklist
  history remains accessible without inferring a development stage from issue
  record fields such as `occurrence_stage`.
- A checklist has no independent revision number. Its identity is the unique
  combination of vehicle, vehicle-development stage, module, and source module
  master revision (`Rev`).
- Registering a later stage creates only the stage record. It never copies
  checklists as a side effect, because modules in the preceding stage may still
  be in progress when the later vehicle stage begins.
- When a module has no checklist in the current stage, the module detail lists
  every completed checklist for the same module from earlier vehicle stages.
  The import dialog identifies each candidate by stage, source master revision,
  completion time, completer, and row count. The user selects one candidate or
  creates a fresh checklist from a published module master revision. Importing
  creates a new draft and copies definition and grid snapshots, source-record
  lineage, ordering, and field values. It does not copy completion state, change
  history, or attachment objects; evidence attachments remain stage-local.
- When a checklist is first generated, each row copies the populated `CHECK`
  values from that source master revision as editable defaults. Later master
  changes do not overwrite the generated checklist.
- Draft checklists allow edits only to `CHECK` values. They may be completed and
  completed checklists may be reopened into the editable draft state.
- Each checklist record may own multiple evidence attachments under the merged
  `CHECK` column. Workspace members may upload or delete those attachments only
  while the checklist is a draft; draft and completed checklists both allow
  attachment listing and download.
- Attachment object deletion is committed through a database cleanup outbox and
  retried periodically by the default worker. An hourly reconciliation removes
  old objects under the vehicle-module-checklist prefix when no attachment row
  exists, covering failed upload compensation without racing active uploads.
- Every workspace member may hard-delete a generated checklist. Deletion has no
  restore flow. It deletes that checklist's own attachment objects and metadata,
  but must never delete its vehicle or any master dataset, revision, record, or
  master attachment.
- During the transition, legacy aggregate checklists are read/history/delete
  only. Their create, edit, complete, and reopen operations remain locked.
- The module-checklist migration must fail unless the legacy generated
  checklist tables contain zero rows. The migration must not clean up or delete
  master data, vehicles, revisions, records, or attachments.
- The shared master and vehicle-module checklist grid preserves explicit line
  breaks in text cells and, by default, automatically expands each affected row
  for both explicit and column-width wrapping, up to twelve display lines.
  Users may disable automatic row-height fitting from the grid toolbar to keep
  every row at the compact default height; this preference is browser-local per
  grid. Variable-height scroll positions use the accumulated row offsets rather
  than a fixed-height approximation.
- `occurrence_date` (발생일) and `received_date` (접수일) are optional by default
  and accept an empty value as null/absent. Populated values are canonical
  `YYYY-MM-DD` strings in the existing JSON/Text record contract. The master
  grid and Excel round-trip use date-aware cells, including copy/paste between
  date cells. Workspace field settings may still make either field required.
  The occurrence-date migration normalizes draft and published master revisions
  while leaving canceled revision history unchanged. Matching AI summary text
  and keyword terms are normalized in place, while the representation-only
  change preserves existing semantic embeddings.
- Grid column order, explicit widths, hidden-column keys, sorts, filters,
  frozen columns, scroll position, and automatic row-height preferences stay
  browser-local and are never sent with sheet saves. Administrator-managed
  column settings remain the default order when no local order exists.
- Master datasets and vehicle-module checklists support asynchronous Excel
  exports with a data-only or attachment-inclusive choice. Data-only exports do
  not query or embed attachments. Attachment-inclusive exports add separate
  attachment-name and attachment-object columns, list multiple names with line
  breaks, and embed every file as an OLE Package object in the same order. The
  OLE cell displays generic icons while original file names remain available in
  both the adjacent name cell and the OLE payload for desktop Excel activation.
- Generated workbooks mirror the grid's two-level grouped headers. They freeze
  both header rows, use readable protected/editable styling, size columns by
  field semantics and sampled content, and expand wrapped data rows within a
  bounded height so long descriptions remain readable without overwhelming the
  sheet.
- Master and vehicle-module checklist exports snapshot the requesting user's
  current grid column order and visibility. Hidden data columns are omitted and
  visible data columns keep their on-screen order. The locked record identifier
  remains first for round-trip identity, while attachment-name and OLE columns
  continue to follow the explicit data-only or attachment-inclusive choice.
- The web exposes one Excel download action. Clicking it opens a modal with a
  data-only choice and an attachment-inclusive choice. The latter explains in
  the modal that OLE processing takes longer, and a visible wait message remains
  while the job is queued or running.
- Export jobs are scoped to the requesting workspace member, survive page
  refresh, run on the dedicated legacy-issue Excel queue, and retain generated
  workbooks for 24 hours before storage cleanup.
- Workspace administrators may permanently delete a vehicle only when it owns
  no legacy or module checklist. The deletion writes a history snapshot and
  must not delete master datasets, revisions, records, or master attachments.
- Inactive vehicles preserve stage badges and existing checklist history, but
  cannot accept a new stage or generate a new checklist until reactivated.
- AI analysis without an explicit stage scope selects checklists from the
  latest registered stage for each vehicle so later edits to an older stage do
  not silently replace the current-stage evidence.
- A definition-only common-code refresh must preserve unsaved master-data
  edits and must not reload the master-data records.
