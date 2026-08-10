import {
  type WheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';

import {
  type PatentCostRun,
  type PatentFieldDef,
  type PatentRecord,
  createPatentDisclosure,
  createPatentRecord,
  deletePatentRecord,
  downloadPatentCostExcel,
  exportPatentRecords,
  fetchPatentFields,
  fetchPatentRecords,
  generatePatentApprovalHtml,
  importPatentRecords,
  ingestPatentCostFiles,
  updatePatentRecord,
} from '../api/patent-automation-api';

type TabId = 'records' | 'cost' | 'tracking';

// Curated editable fields shown in the record detail panel (field_defs keys).
// labelKey resolves against the `apps` i18n namespace at render time.
const EDITABLE_FIELDS: Array<{ key: string; labelKey: string }> = [
  {
    key: 'invention_title',
    labelKey: 'patentAutomation.fields.inventionTitle',
  },
  { key: 'inventors', labelKey: 'patentAutomation.fields.inventors' },
  { key: 'submit_team', labelKey: 'patentAutomation.fields.submitTeam' },
  { key: 'application_no', labelKey: 'patentAutomation.fields.applicationNo' },
  {
    key: 'application_date',
    labelKey: 'patentAutomation.fields.applicationDate',
  },
  {
    key: 'registration_no',
    labelKey: 'patentAutomation.fields.registrationNo',
  },
  {
    key: 'registration_date',
    labelKey: 'patentAutomation.fields.registrationDate',
  },
  { key: 'patent_status', labelKey: 'patentAutomation.fields.patentStatus' },
  { key: 'patent_office', labelKey: 'patentAutomation.fields.patentOffice' },
  {
    key: 'exam_request_date',
    labelKey: 'patentAutomation.fields.examRequestDate',
  },
  { key: 'annuity_year', labelKey: 'patentAutomation.fields.annuityYear' },
  {
    key: 'annuity_payment_date',
    labelKey: 'patentAutomation.fields.annuityPaymentDate',
  },
  { key: 'expiry_due_date', labelKey: 'patentAutomation.fields.expiryDueDate' },
  { key: 'abstract', labelKey: 'patentAutomation.fields.abstract' },
];

const TABS: Array<{ id: TabId; labelKey: string }> = [
  { id: 'records', labelKey: 'patentAutomation.tabs.records' },
  { id: 'cost', labelKey: 'patentAutomation.tabs.cost' },
  { id: 'tracking', labelKey: 'patentAutomation.tabs.tracking' },
];

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function formatMoney(value: number | null | undefined): string {
  if (value == null) return '-';
  return value.toLocaleString('ko-KR');
}

const LONG_TEXT_KEYS = new Set([
  'invention_title',
  'abstract',
  'representative_claim',
  'invention_review_log',
  'draft_spec_log',
  'exam_request_log',
  'exam_progress_log',
  'foreign_app_log',
  'reference_materials',
  'kipo_prior_art_docs',
  'deliberation_result',
]);

function columnWidth(f: PatentFieldDef): {
  minWidth: number;
  maxWidth: number;
} {
  if (f.type === 'date') return { minWidth: 96, maxWidth: 110 };
  if (f.type === 'int' || f.type === 'money')
    return { minWidth: 92, maxWidth: 130 };
  if (f.type === 'enum') return { minWidth: 64, maxWidth: 96 };
  if (LONG_TEXT_KEYS.has(f.key)) return { minWidth: 240, maxWidth: 420 };
  return { minWidth: 120, maxWidth: 220 };
}

function formatFieldValue(f: PatentFieldDef, value: string): string {
  if (!value) return '';
  // 년도(_year)·년월(_ym)·실적(_metric) 코드값은 int이지만 수량이 아니므로
  // 천단위 콤마를 붙이지 않고 원문 그대로 표시한다 (예: 2029, 202211).
  if (/(_year|_ym|_metric)$/.test(f.key)) return value;
  if (f.type === 'money' || f.type === 'int') {
    const n = Number(value.replace(/,/g, ''));
    if (Number.isFinite(n)) return Math.round(n).toLocaleString('ko-KR');
  }
  return value;
}

export function PatentAutomationView() {
  const { t } = useTranslation(['apps']);
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [tab, setTab] = useState<TabId>('records');
  const [scope, setScope] = useState<'domestic' | 'overseas'>('domestic');
  const [records, setRecords] = useState<PatentRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<PatentRecord | null>(null);
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [fields, setFields] = useState<PatentFieldDef[]>([]);
  const [editingCell, setEditingCell] = useState<{
    recordId: string;
    key: string;
  } | null>(null);
  const [cellDraft, setCellDraft] = useState('');
  const [gridEditMode, setGridEditMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // 그리드 페이지네이션 — 현황관리는 컬럼이 96개라 전체 행을 한번에 렌더하면 DOM이 수만 셀로
  // 커져 느려진다. 페이지당 PAGE_SIZE행만 렌더한다(가로 스크롤·전체 컬럼은 유지).
  const [page, setPage] = useState(0);
  const gridScrollRef = useRef<HTMLDivElement | null>(null);
  const PAGE_SIZE = 50;
  const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const pagedRecords = useMemo(
    () => records.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [records, page],
  );

  // Shift + wheel → horizontal scroll (Google-Sheets-like) over the full grid.
  const handleGridWheel = useCallback((e: WheelEvent<HTMLDivElement>) => {
    const el = gridScrollRef.current;
    if (!el) return;
    if (e.shiftKey && e.deltaY !== 0) {
      el.scrollLeft += e.deltaY;
    }
  }, []);

  // Cost tab state.
  const [costRegion, setCostRegion] = useState('산업');
  const [costPeriod, setCostPeriod] = useState('');
  const [costFiles, setCostFiles] = useState<File[]>([]);
  const [costRun, setCostRun] = useState<PatentCostRun | null>(null);
  // 품의 본문 생성용: 2번 누적표를 추출할 6번(건수·금액 정리) 파일.
  const [countAmountFile, setCountAmountFile] = useState<File | null>(null);

  const loadRecords = useCallback(
    async (q?: string) => {
      if (!token || !workspaceSlug) return;
      setLoading(true);
      setError(null);
      try {
        const result = await fetchPatentRecords({
          token,
          workspaceSlug,
          query: q,
          source: scope,
          limit: 500,
        });
        setRecords(result.items);
        setTotal(result.total);
        setPage(0);
      } catch (e) {
        setError(errorText(e, t('patentAutomation.errors.loadRecords')));
      } finally {
        setLoading(false);
      }
    },
    [token, workspaceSlug, scope, t],
  );

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    void fetchPatentFields({ token, workspaceSlug, scope })
      .then((res) => setFields(res.fields))
      .catch(() => setFields([]));
  }, [token, workspaceSlug, scope]);

  const handleImport = useCallback(
    async (file: File) => {
      if (!token || !workspaceSlug) return;
      setBusy('import');
      setError(null);
      try {
        const result = await importPatentRecords({
          token,
          workspaceSlug,
          file,
        });
        await loadRecords();
        const warn = result.warnings.length
          ? t('patentAutomation.alerts.importWarn', {
              count: result.warnings.length,
            })
          : '';
        window.alert(
          t('patentAutomation.alerts.importDone', {
            created: result.created,
            updated: result.updated,
            skipped: result.skipped,
            removed: result.removed,
            events: result.progress_events,
            warn,
          }),
        );
      } catch (e) {
        setError(errorText(e, t('patentAutomation.errors.import')));
      } finally {
        setBusy(null);
      }
    },
    [token, workspaceSlug, loadRecords, t],
  );

  const handleAddDisclosure = useCallback(
    async (file: File) => {
      if (!token || !workspaceSlug) return;
      setBusy('disclosure');
      setError(null);
      try {
        const created = await createPatentDisclosure({
          token,
          workspaceSlug,
          file,
        });
        if (scope !== 'domestic') setScope('domestic');
        await loadRecords();
        setSelected(created);
        setEditing(false);
        window.alert(
          t('patentAutomation.alerts.disclosureAdded', {
            title: created.invention_title ?? created.id,
          }),
        );
      } catch (e) {
        setError(errorText(e, t('patentAutomation.errors.disclosure')));
      } finally {
        setBusy(null);
      }
    },
    [token, workspaceSlug, loadRecords, scope, t],
  );

  const handleExport = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setBusy('export');
    try {
      const blob = await exportPatentRecords({ token, workspaceSlug });
      downloadBlobAsFile(blob, t('patentAutomation.files.records'));
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.export')));
    } finally {
      setBusy(null);
    }
  }, [token, workspaceSlug, t]);

  const handleIngest = useCallback(async () => {
    if (!token || !workspaceSlug || costFiles.length === 0) return;
    setBusy('ingest');
    setError(null);
    try {
      const run = await ingestPatentCostFiles({
        token,
        workspaceSlug,
        files: costFiles,
        region: costRegion,
        fiscalPeriod: costPeriod || undefined,
      });
      setCostRun(run);
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.ingest')));
    } finally {
      setBusy(null);
    }
  }, [token, workspaceSlug, costFiles, costRegion, costPeriod, t]);

  const handleCostDownload = useCallback(
    async (kind: 'industrial' | 'overseas' | 'count-amount') => {
      if (!token || !workspaceSlug || !costRun) return;
      try {
        const blob = await downloadPatentCostExcel({
          token,
          workspaceSlug,
          runId: costRun.id,
          kind,
        });
        const name =
          kind === 'industrial'
            ? t('patentAutomation.files.industrial')
            : kind === 'overseas'
              ? t('patentAutomation.files.overseas')
              : t('patentAutomation.files.countAmount');
        downloadBlobAsFile(blob, name);
      } catch (e) {
        setError(errorText(e, t('patentAutomation.errors.download')));
      }
    },
    [token, workspaceSlug, costRun, t],
  );

  // 사용 가능한 다운로드 종류(산업/해외/건수금액) — '한번에 받기' 버튼 라벨/동작에 사용.
  const costDownloadKinds = useMemo<
    Array<'industrial' | 'overseas' | 'count-amount'>
  >(() => {
    if (!costRun) return [];
    const kinds: Array<'industrial' | 'overseas' | 'count-amount'> = [];
    if (costRun.has_industrial) kinds.push('industrial');
    if (costRun.has_overseas) kinds.push('overseas');
    kinds.push('count-amount');
    return kinds;
  }, [costRun]);

  const handleCostDownloadAll = useCallback(async () => {
    for (const kind of costDownloadKinds) {
      await handleCostDownload(kind);
    }
  }, [costDownloadKinds, handleCostDownload]);

  const handleGenerateApproval = useCallback(async () => {
    if (!token || !workspaceSlug || !costRun) return;
    setBusy('approval');
    try {
      const result = await generatePatentApprovalHtml({
        token,
        workspaceSlug,
        runId: costRun.id,
        countAmountFile: countAmountFile ?? undefined,
      });
      // 본문은 클립보드로 복사(그룹웨어 붙여넣기) + .txt로도 저장.
      try {
        await navigator.clipboard.writeText(result.html);
      } catch {
        /* 클립보드 권한 없으면 무시 — .txt 저장으로 대체 */
      }
      downloadBlobAsFile(
        new Blob([result.html], { type: 'text/html;charset=utf-8' }),
        result.filename,
      );
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.download')));
    } finally {
      setBusy(null);
    }
  }, [token, workspaceSlug, costRun, countAmountFile, t]);

  const startEdit = useCallback((record: PatentRecord) => {
    const seed: Record<string, string> = {};
    for (const f of EDITABLE_FIELDS) {
      seed[f.key] = record.field_values[f.key] ?? '';
    }
    setEditValues(seed);
    setEditing(true);
  }, []);

  const saveEdit = useCallback(async () => {
    if (!token || !workspaceSlug || !selected) return;
    setBusy('save');
    setError(null);
    try {
      const updated = await updatePatentRecord({
        token,
        workspaceSlug,
        recordId: selected.id,
        fieldValues: editValues,
      });
      setSelected(updated);
      setEditing(false);
      setRecords((current) =>
        current.map((r) => (r.id === updated.id ? updated : r)),
      );
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.save')));
    } finally {
      setBusy(null);
    }
  }, [token, workspaceSlug, selected, editValues, t]);

  const handleAddRow = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setBusy('add');
    setError(null);
    try {
      const created = await createPatentRecord({
        token,
        workspaceSlug,
        fieldValues: {},
      });
      setRecords((curr) => [created, ...curr]);
      setTotal((t) => t + 1);
      setSelected(created);
      startEdit(created);
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.addRow')));
    } finally {
      setBusy(null);
    }
  }, [token, workspaceSlug, startEdit, t]);

  const handleDeleteRecord = useCallback(
    async (record: PatentRecord) => {
      if (!token || !workspaceSlug) return;
      const label =
        record.invention_title ||
        record.application_no ||
        t('patentAutomation.confirm.thisRow');
      if (!window.confirm(t('patentAutomation.confirm.deleteRow', { label })))
        return;
      setBusy('delete');
      setError(null);
      try {
        await deletePatentRecord({ token, workspaceSlug, recordId: record.id });
        setRecords((curr) => curr.filter((r) => r.id !== record.id));
        setTotal((t) => Math.max(0, t - 1));
        if (selected?.id === record.id) {
          setSelected(null);
          setEditing(false);
        }
      } catch (e) {
        setError(errorText(e, t('patentAutomation.errors.deleteRow')));
      } finally {
        setBusy(null);
      }
    },
    [token, workspaceSlug, selected, t],
  );

  const handleBulkDelete = useCallback(async () => {
    if (!token || !workspaceSlug || selectedIds.size === 0) return;
    if (
      !window.confirm(
        t('patentAutomation.confirm.deleteSelected', {
          count: selectedIds.size,
        }),
      )
    )
      return;
    setBusy('delete');
    setError(null);
    const ids = Array.from(selectedIds);
    try {
      for (const id of ids) {
        await deletePatentRecord({ token, workspaceSlug, recordId: id });
      }
      setRecords((curr) => curr.filter((r) => !selectedIds.has(r.id)));
      setTotal((t) => Math.max(0, t - ids.length));
      if (selected && selectedIds.has(selected.id)) {
        setSelected(null);
        setEditing(false);
      }
      setSelectedIds(new Set());
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.bulkDelete')));
    } finally {
      setBusy(null);
    }
  }, [token, workspaceSlug, selectedIds, selected, t]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const beginCellEdit = useCallback(
    (recordId: string, key: string, value: string) => {
      setEditingCell({ recordId, key });
      setCellDraft(value);
    },
    [],
  );

  const saveCell = useCallback(async () => {
    if (!token || !workspaceSlug || !editingCell) return;
    const { recordId, key } = editingCell;
    const rec = records.find((r) => r.id === recordId);
    const current = rec?.field_values[key] ?? '';
    setEditingCell(null);
    if (cellDraft === current) return;
    try {
      const updated = await updatePatentRecord({
        token,
        workspaceSlug,
        recordId,
        fieldValues: { [key]: cellDraft },
      });
      setRecords((curr) => curr.map((r) => (r.id === recordId ? updated : r)));
      if (selected?.id === recordId) setSelected(updated);
    } catch (e) {
      setError(errorText(e, t('patentAutomation.errors.cellSave')));
    }
  }, [token, workspaceSlug, editingCell, cellDraft, records, selected, t]);

  const phaseCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of records) {
      const phase =
        r.lifecycle_phase ?? t('patentAutomation.tracking.unclassified');
      counts.set(phase, (counts.get(phase) ?? 0) + 1);
    }
    return Array.from(counts.entries());
  }, [records, t]);

  return (
    <div className="flex h-full flex-col gap-4 bg-app-surface p-6 text-app-ink">
      <header>
        <h1 className="text-title-md font-semibold text-app-ink">
          {t('patentAutomation.header.title')}
        </h1>
        <p className="text-body-sm text-app-ink/70">
          {t('patentAutomation.header.subtitle')}
        </p>
      </header>

      <nav className="flex gap-1 border-b border-app-border">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`px-4 py-2 text-body-sm font-medium ${
              tab === item.id
                ? 'border-b-2 border-app-accent text-app-accent'
                : 'text-app-ink/60 hover:text-app-ink'
            }`}
          >
            {t(item.labelKey)}
          </button>
        ))}
      </nav>

      {error && (
        <div className="rounded border border-app-danger/40 bg-app-danger/10 px-3 py-2 text-body-sm text-app-danger-text">
          {error}
        </div>
      )}

      {tab === 'records' && (
        <section className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex overflow-hidden rounded border border-app-border">
              {(['domestic', 'overseas'] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    if (s === scope) return;
                    setScope(s);
                    setSelected(null);
                    setSelectedIds(new Set());
                    setEditingCell(null);
                    setGridEditMode(false);
                  }}
                  className={`px-3 py-1.5 text-body-sm ${
                    scope === s
                      ? 'bg-app-accent font-medium text-app-accent-fg'
                      : 'bg-app-surface text-app-ink hover:bg-app-surface-hover'
                  }`}
                >
                  {s === 'domestic'
                    ? t('patentAutomation.scope.domestic')
                    : t('patentAutomation.scope.overseas')}
                </button>
              ))}
            </div>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void loadRecords(query);
              }}
              placeholder={t('patentAutomation.actions.searchPlaceholder')}
              className="w-64 rounded border border-app-border bg-app-surface px-3 py-1.5 text-body-sm text-app-ink placeholder:text-app-ink/40"
            />
            <button
              type="button"
              onClick={() => void loadRecords(query)}
              className="rounded bg-app-surface-muted px-3 py-1.5 text-body-sm text-app-ink hover:bg-app-surface-hover"
            >
              {t('patentAutomation.actions.search')}
            </button>
            <label className="cursor-pointer rounded bg-app-accent px-3 py-1.5 text-body-sm font-medium text-app-accent-fg hover:bg-app-accent-hover">
              {busy === 'import'
                ? t('patentAutomation.actions.importing')
                : t('patentAutomation.actions.import')}
              <input
                type="file"
                accept=".xlsx"
                className="hidden"
                disabled={busy === 'import'}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleImport(file);
                  e.target.value = '';
                }}
              />
            </label>
            {scope === 'domestic' && (
              <label
                className="cursor-pointer rounded border border-app-accent px-3 py-1.5 text-body-sm font-medium text-app-accent hover:bg-app-accent/10"
                title={t('patentAutomation.actions.disclosureHint')}
              >
                {busy === 'disclosure'
                  ? t('patentAutomation.actions.disclosureProcessing')
                  : t('patentAutomation.actions.addDisclosure')}
                <input
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  disabled={busy === 'disclosure'}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void handleAddDisclosure(file);
                    e.target.value = '';
                  }}
                />
              </label>
            )}
            <button
              type="button"
              onClick={() => void handleExport()}
              disabled={busy === 'export'}
              className="rounded border border-app-border px-3 py-1.5 text-body-sm text-app-ink hover:bg-app-surface-hover"
            >
              {busy === 'export'
                ? t('patentAutomation.actions.exporting')
                : t('patentAutomation.actions.export')}
            </button>
            {gridEditMode ? (
              <button
                type="button"
                onClick={() => {
                  if (editingCell) void saveCell();
                  setGridEditMode(false);
                }}
                className="rounded border border-app-accent bg-app-accent/15 px-3 py-1.5 text-body-sm font-medium text-app-accent hover:bg-app-accent/25"
              >
                {t('patentAutomation.actions.save')}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setGridEditMode(true)}
                className="rounded border border-app-border px-3 py-1.5 text-body-sm text-app-ink hover:bg-app-surface-hover"
              >
                {t('patentAutomation.actions.edit')}
              </button>
            )}
            <button
              type="button"
              onClick={() => void handleAddRow()}
              disabled={busy === 'add'}
              className="rounded border border-app-border px-3 py-1.5 text-body-sm text-app-ink hover:bg-app-surface-hover"
            >
              {busy === 'add'
                ? t('patentAutomation.actions.addingRow')
                : t('patentAutomation.actions.addRow')}
            </button>
            {selectedIds.size > 0 && (
              <button
                type="button"
                onClick={() => void handleBulkDelete()}
                disabled={busy === 'delete'}
                className="rounded border border-app-danger/40 px-3 py-1.5 text-body-sm text-app-danger-text hover:bg-app-danger/10 disabled:opacity-50"
              >
                {busy === 'delete'
                  ? t('patentAutomation.actions.deleting')
                  : t('patentAutomation.actions.bulkDelete', {
                      count: selectedIds.size,
                    })}
              </button>
            )}
            <span className="ml-auto text-body-sm text-app-ink/60">
              {t('patentAutomation.actions.count', { count: total })}
            </span>
            {records.length > PAGE_SIZE && (
              <div className="flex items-center gap-2 text-body-sm text-app-ink/70">
                <button
                  type="button"
                  disabled={page <= 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="rounded border border-app-border px-2 py-1 hover:bg-app-surface-hover disabled:opacity-40"
                >
                  ‹
                </button>
                <span className="tabular-nums">
                  {page * PAGE_SIZE + 1}–
                  {Math.min((page + 1) * PAGE_SIZE, records.length)} /{' '}
                  {records.length}
                </span>
                <button
                  type="button"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                  className="rounded border border-app-border px-2 py-1 hover:bg-app-surface-hover disabled:opacity-40"
                >
                  ›
                </button>
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-1 gap-3">
            <div
              ref={gridScrollRef}
              onWheel={handleGridWheel}
              className="min-h-0 flex-1 overflow-auto rounded border border-app-border"
            >
              <table className="w-max border-separate border-spacing-0 text-body-sm">
                <thead className="sticky top-0 z-20 bg-app-surface-raised text-left text-micro text-app-ink/70 shadow-sm">
                  <tr>
                    <th className="sticky left-0 z-30 w-10 border-b border-r border-app-border bg-app-surface-raised px-2 py-2 text-center">
                      <input
                        type="checkbox"
                        aria-label={t('patentAutomation.grid.selectAll')}
                        checked={
                          records.length > 0 &&
                          records.every((r) => selectedIds.has(r.id))
                        }
                        onChange={(e) =>
                          setSelectedIds(
                            e.target.checked
                              ? new Set(records.map((r) => r.id))
                              : new Set(),
                          )
                        }
                      />
                    </th>
                    <th className="sticky left-10 z-30 border-b border-r border-app-border bg-app-surface-raised px-3 py-2 whitespace-nowrap">
                      {t('patentAutomation.grid.applicationNo')}
                    </th>
                    {fields.map((f) => (
                      <th
                        key={f.key}
                        style={columnWidth(f)}
                        className="border-b border-app-border bg-app-surface-raised px-3 py-2 align-bottom whitespace-normal break-words leading-tight"
                        title={`${f.group_ko} · ${f.label_ko}`}
                      >
                        {f.label_ko}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td
                        colSpan={fields.length + 2}
                        className="px-3 py-6 text-center text-app-ink/50"
                      >
                        {t('patentAutomation.grid.loading')}
                      </td>
                    </tr>
                  ) : records.length === 0 ? (
                    <tr>
                      <td
                        colSpan={fields.length + 2}
                        className="px-3 py-6 text-center text-app-ink/50"
                      >
                        {t('patentAutomation.grid.empty')}
                      </td>
                    </tr>
                  ) : (
                    pagedRecords.map((r) => {
                      const isSel = selected?.id === r.id;
                      return (
                        <tr
                          key={r.id}
                          className={
                            isSel
                              ? 'bg-app-accent/10'
                              : 'hover:bg-app-surface-hover'
                          }
                        >
                          <td
                            className={`sticky left-0 z-10 w-10 border-b border-r border-app-border/60 px-2 py-2 text-center ${
                              isSel
                                ? 'bg-[color-mix(in_srgb,var(--color-app-accent)_10%,var(--color-app-surface))]'
                                : 'bg-app-surface'
                            }`}
                          >
                            <input
                              type="checkbox"
                              aria-label={t('patentAutomation.grid.selectRow')}
                              checked={selectedIds.has(r.id)}
                              onChange={() => toggleSelect(r.id)}
                            />
                          </td>
                          <td
                            onClick={() => {
                              setSelected(r);
                              setEditing(false);
                            }}
                            title={t('patentAutomation.grid.viewDetail')}
                            className={`sticky left-10 z-10 cursor-pointer border-b border-r border-app-border/60 px-3 py-2 font-mono text-micro whitespace-nowrap text-app-ink hover:underline ${
                              isSel
                                ? 'bg-[color-mix(in_srgb,var(--color-app-accent)_10%,var(--color-app-surface))]'
                                : 'bg-app-surface'
                            }`}
                          >
                            {r.application_no ?? '-'}
                          </td>
                          {fields.map((f) => {
                            const value = r.field_values[f.key] ?? '';
                            const isEditingCell =
                              editingCell?.recordId === r.id &&
                              editingCell.key === f.key;
                            const isFlag =
                              value === '●' || value === 'O' || value === 'o';
                            const isNum =
                              f.type === 'money' || f.type === 'int';
                            return (
                              <td
                                key={f.key}
                                style={
                                  isEditingCell ? undefined : columnWidth(f)
                                }
                                onClick={() => {
                                  if (gridEditMode && !isEditingCell)
                                    beginCellEdit(r.id, f.key, value);
                                }}
                                title={isFlag ? '' : value}
                                className={`${gridEditMode ? 'cursor-text' : 'cursor-default'} border-b border-app-border/60 px-3 py-2 text-app-ink/90 ${
                                  isEditingCell
                                    ? ''
                                    : isFlag
                                      ? 'text-center'
                                      : `overflow-hidden text-ellipsis whitespace-nowrap ${isNum ? 'text-right' : ''}`
                                }`}
                              >
                                {isEditingCell ? (
                                  <input
                                    autoFocus
                                    value={cellDraft}
                                    onChange={(e) =>
                                      setCellDraft(e.target.value)
                                    }
                                    onBlur={() => void saveCell()}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') {
                                        e.preventDefault();
                                        void saveCell();
                                      } else if (e.key === 'Escape') {
                                        setEditingCell(null);
                                      }
                                    }}
                                    className="w-full min-w-[140px] rounded border border-app-accent bg-app-surface px-1 py-0.5 text-app-ink outline-none"
                                  />
                                ) : isFlag ? (
                                  <span
                                    className="text-app-success-text"
                                    title={t(
                                      'patentAutomation.grid.flagTarget',
                                    )}
                                  >
                                    ✓
                                  </span>
                                ) : (
                                  formatFieldValue(f, value)
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {selected && (
              <aside className="w-96 shrink-0 overflow-auto rounded border border-app-border bg-app-surface-raised p-4">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <h2 className="text-body font-semibold text-app-ink">
                    {selected.invention_title ??
                      t('patentAutomation.detail.untitled')}
                  </h2>
                  <div className="flex shrink-0 items-center gap-2">
                    {editing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => void saveEdit()}
                          disabled={busy === 'save'}
                          className="rounded bg-app-accent px-2 py-1 text-micro font-medium text-app-accent-fg hover:bg-app-accent-hover disabled:opacity-50"
                        >
                          {busy === 'save'
                            ? t('patentAutomation.detail.saving')
                            : t('patentAutomation.detail.save')}
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditing(false)}
                          className="rounded border border-app-border px-2 py-1 text-micro text-app-ink hover:bg-app-surface-hover"
                        >
                          {t('patentAutomation.detail.cancel')}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(selected)}
                          className="rounded border border-app-border px-2 py-1 text-micro text-app-ink hover:bg-app-surface-hover"
                        >
                          {t('patentAutomation.detail.edit')}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDeleteRecord(selected)}
                          disabled={busy === 'delete'}
                          className="rounded border border-app-danger/40 px-2 py-1 text-micro text-app-danger-text hover:bg-app-danger/10 disabled:opacity-50"
                        >
                          {t('patentAutomation.detail.delete')}
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(null);
                        setEditing(false);
                      }}
                      className="text-app-ink/50 hover:text-app-ink"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                {editing ? (
                  <div className="space-y-2">
                    {EDITABLE_FIELDS.map((f) => (
                      <label key={f.key} className="block">
                        <span className="text-micro text-app-ink/50">
                          {t(f.labelKey)}
                        </span>
                        <input
                          value={editValues[f.key] ?? ''}
                          onChange={(e) =>
                            setEditValues((prev) => ({
                              ...prev,
                              [f.key]: e.target.value,
                            }))
                          }
                          className="mt-0.5 w-full rounded border border-app-border bg-app-surface px-2 py-1 text-micro text-app-ink"
                        />
                      </label>
                    ))}
                  </div>
                ) : (
                  <dl className="space-y-1 text-micro text-app-ink/80">
                    <div className="flex gap-2">
                      <dt className="w-20 text-app-ink/50">
                        {t('patentAutomation.detail.applicationNo')}
                      </dt>
                      <dd className="font-mono">
                        {selected.application_no ?? '-'}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-20 text-app-ink/50">
                        {t('patentAutomation.detail.registrationNo')}
                      </dt>
                      <dd className="font-mono">
                        {selected.registration_no ?? '-'}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-20 text-app-ink/50">
                        {t('patentAutomation.detail.inventors')}
                      </dt>
                      <dd>{selected.inventors ?? '-'}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-20 text-app-ink/50">
                        {t('patentAutomation.detail.disclosureApplicationDate')}
                      </dt>
                      <dd>
                        {selected.disclosure_date ?? '-'} /{' '}
                        {selected.application_date ?? '-'}
                      </dd>
                    </div>
                  </dl>
                )}
                <h3 className="mb-2 mt-4 text-micro font-semibold text-app-ink/80">
                  {t('patentAutomation.detail.timeline')}
                </h3>
                <ol className="space-y-1 border-l border-app-border pl-3 text-micro">
                  {selected.progress_events.length === 0 ? (
                    <li className="text-app-ink/50">
                      {t('patentAutomation.detail.noRecords')}
                    </li>
                  ) : (
                    selected.progress_events.map((ev) => (
                      <li key={ev.id} className="relative">
                        <span className="text-app-ink/50">
                          {ev.event_date ?? ''}
                        </span>{' '}
                        <span className="text-app-ink/90">{ev.stage}</span>
                        <span className="ml-1 text-app-ink/40">
                          [{ev.kind}]
                        </span>
                      </li>
                    ))
                  )}
                </ol>
              </aside>
            )}
          </div>
        </section>
      )}

      {tab === 'cost' && (
        <section className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3 rounded border border-app-border bg-app-surface-raised p-3">
            <label className="text-body-sm text-app-ink">
              <span className="mr-2 text-app-ink/60">
                {t('patentAutomation.cost.region')}
              </span>
              <select
                value={costRegion}
                onChange={(e) => setCostRegion(e.target.value)}
                className="app-field-input-sm w-auto"
              >
                <option value="산업">
                  {t('patentAutomation.cost.regionDomestic')}
                </option>
                <option value="해외">
                  {t('patentAutomation.cost.regionOverseas')}
                </option>
              </select>
            </label>
            <label className="text-body-sm text-app-ink">
              <span className="mr-2 text-app-ink/60">
                {t('patentAutomation.cost.period')}
              </span>
              <input
                value={costPeriod}
                onChange={(e) => setCostPeriod(e.target.value)}
                placeholder="2026-01"
                className="w-28 rounded border border-app-border bg-app-surface px-2 py-1.5 text-body-sm text-app-ink placeholder:text-app-ink/40"
              />
            </label>
            <label className="cursor-pointer rounded border border-app-border px-3 py-1.5 text-body-sm text-app-ink hover:bg-app-surface-hover">
              {t('patentAutomation.cost.addFiles')}
              <input
                type="file"
                accept=".pdf,.xlsx,.PDF"
                multiple
                className="hidden"
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  // 여러 폴더에서 나눠 선택할 수 있도록 기존 목록에 누적(이름+크기로 중복 제거).
                  setCostFiles((prev) => {
                    const seen = new Set(
                      prev.map((f) => `${f.name}:${f.size}`),
                    );
                    return [
                      ...prev,
                      ...picked.filter((f) => !seen.has(`${f.name}:${f.size}`)),
                    ];
                  });
                  e.target.value = '';
                }}
              />
            </label>
            {costFiles.length > 0 && (
              <button
                type="button"
                onClick={() => setCostFiles([])}
                className="rounded border border-app-border px-2 py-1.5 text-body-sm text-app-ink/70 hover:bg-app-surface-hover"
              >
                {t('patentAutomation.cost.clear')}
              </button>
            )}
            <button
              type="button"
              onClick={() => void handleIngest()}
              disabled={busy === 'ingest' || costFiles.length === 0}
              className="rounded bg-app-accent px-3 py-1.5 text-body-sm font-medium text-app-accent-fg hover:bg-app-accent-hover disabled:opacity-50"
            >
              {busy === 'ingest'
                ? t('patentAutomation.cost.processing')
                : t('patentAutomation.cost.process', {
                    count: costFiles.length,
                  })}
            </button>
          </div>

          {costFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {costFiles.map((f, i) => (
                <span
                  key={`${f.name}:${f.size}`}
                  className="inline-flex items-center gap-1 rounded bg-app-surface-muted px-2 py-0.5 text-micro text-app-ink/80"
                  title={f.name}
                >
                  <span className="max-w-[220px] truncate">{f.name}</span>
                  <button
                    type="button"
                    aria-label={t('patentAutomation.cost.removeFile')}
                    onClick={() =>
                      setCostFiles((prev) => prev.filter((_, idx) => idx !== i))
                    }
                    className="text-app-ink/50 hover:text-app-danger-text"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          {costRun && (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div className="flex flex-wrap items-center gap-3 text-body-sm text-app-ink">
                <span>
                  {t('patentAutomation.cost.industrialTotal')}{' '}
                  <b>{formatMoney(costRun.industrial_total)}</b>{' '}
                  {t('patentAutomation.cost.won')}
                </span>
                <span>
                  {t('patentAutomation.cost.overseasTotal')}{' '}
                  <b>{formatMoney(costRun.overseas_total)}</b>{' '}
                  {t('patentAutomation.cost.won')}
                </span>
                {costRun.has_industrial && (
                  <button
                    type="button"
                    onClick={() => void handleCostDownload('industrial')}
                    className="rounded border border-app-border px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
                  >
                    {t('patentAutomation.cost.downloadIndustrial')}
                  </button>
                )}
                {costRun.has_overseas && (
                  <button
                    type="button"
                    onClick={() => void handleCostDownload('overseas')}
                    className="rounded border border-app-border px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
                  >
                    {t('patentAutomation.cost.downloadOverseas')}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void handleCostDownload('count-amount')}
                  className="rounded border border-app-border px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
                >
                  {t('patentAutomation.cost.downloadCountAmount')}
                </button>
                {costDownloadKinds.length > 1 && (
                  <button
                    type="button"
                    onClick={() => void handleCostDownloadAll()}
                    className="ml-auto rounded bg-app-accent px-3 py-1.5 font-medium text-app-accent-fg hover:bg-app-accent-hover"
                  >
                    {t('patentAutomation.cost.downloadAll', {
                      count: costDownloadKinds.length,
                    })}
                  </button>
                )}
              </div>

              {/* 품의 본문 생성: 6번(건수·금액 정리) 파일을 첨부하면 2번 누적표까지 채워 HTML 생성 */}
              <div className="flex flex-wrap items-center gap-3 rounded border border-app-border bg-app-surface px-3 py-2 text-body-sm text-app-ink">
                <span className="font-medium">
                  {t('patentAutomation.cost.approvalTitle')}
                </span>
                <label className="cursor-pointer rounded border border-app-border px-3 py-1.5 hover:bg-app-surface-hover">
                  {countAmountFile
                    ? countAmountFile.name
                    : t('patentAutomation.cost.approvalPickFile')}
                  <input
                    type="file"
                    accept=".xlsx"
                    className="hidden"
                    onChange={(e) =>
                      setCountAmountFile(e.target.files?.[0] ?? null)
                    }
                  />
                </label>
                {countAmountFile && (
                  <button
                    type="button"
                    onClick={() => setCountAmountFile(null)}
                    className="text-micro text-app-ink-subtle hover:text-app-ink"
                  >
                    {t('patentAutomation.cost.removeFile')}
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy === 'approval'}
                  onClick={() => void handleGenerateApproval()}
                  className="ml-auto rounded bg-app-accent px-3 py-1.5 font-medium text-app-accent-fg hover:bg-app-accent-hover disabled:opacity-50"
                >
                  {busy === 'approval'
                    ? t('patentAutomation.cost.approvalGenerating')
                    : t('patentAutomation.cost.approvalGenerate')}
                </button>
              </div>

              {costRun.warnings.length > 0 && (
                <div className="rounded border border-app-warning-border bg-app-warning/10 px-3 py-2 text-micro text-app-warning-text">
                  <div className="mb-1 font-semibold">
                    {t('patentAutomation.cost.reviewNeeded', {
                      count: costRun.warnings.length,
                    })}
                  </div>
                  <ul className="list-disc pl-4">
                    {costRun.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="min-h-0 flex-1 overflow-auto rounded border border-app-border">
                <table className="w-full text-body-sm">
                  <thead className="sticky top-0 z-20 bg-app-surface-raised text-left text-micro text-app-ink/70 shadow-sm [&_th]:bg-app-surface-raised">
                    <tr>
                      <th className="px-3 py-2">
                        {t('patentAutomation.cost.colSection')}
                      </th>
                      <th className="px-3 py-2">
                        {t('patentAutomation.cost.colApplicationNo')}
                      </th>
                      <th className="px-3 py-2">
                        {t('patentAutomation.cost.colTitle')}
                      </th>
                      <th className="px-3 py-2 text-right">
                        {t('patentAutomation.cost.colSupply')}
                      </th>
                      <th className="px-3 py-2 text-right">
                        {t('patentAutomation.cost.colVat')}
                      </th>
                      <th className="px-3 py-2 text-right">
                        {t('patentAutomation.cost.colTotal')}
                      </th>
                      <th className="px-3 py-2">
                        {t('patentAutomation.cost.colVerify')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {costRun.lines.map((line) => (
                      <tr
                        key={line.id}
                        className="border-t border-app-border/60"
                      >
                        <td className="px-3 py-2 text-app-ink/80">
                          {line.section}
                        </td>
                        <td className="px-3 py-2 font-mono text-micro text-app-ink">
                          {line.application_no ?? '-'}
                        </td>
                        <td className="px-3 py-2 text-app-ink">
                          {line.title ?? '-'}
                        </td>
                        <td className="px-3 py-2 text-right text-app-ink">
                          {formatMoney(line.supply_amount)}
                        </td>
                        <td className="px-3 py-2 text-right text-app-ink">
                          {formatMoney(line.vat)}
                        </td>
                        <td className="px-3 py-2 text-right text-app-ink">
                          {formatMoney(line.line_total)}
                        </td>
                        <td className="px-3 py-2">
                          {line.reconciled ? (
                            <span className="text-app-success-text">✓</span>
                          ) : (
                            <span className="text-app-danger-text">
                              {t('patentAutomation.cost.mismatch')}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {tab === 'tracking' && (
        <section className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            {phaseCounts.map(([phase, count]) => (
              <div
                key={phase}
                className="rounded border border-app-border bg-app-surface-raised px-3 py-2 text-body-sm"
              >
                <div className="text-app-ink/60">{phase}</div>
                <div className="text-title-md font-semibold text-app-ink">
                  {count}
                </div>
              </div>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded border border-app-border">
            <table className="w-full text-body-sm">
              <thead className="sticky top-0 z-20 bg-app-surface-raised text-left text-micro text-app-ink/70 shadow-sm [&_th]:bg-app-surface-raised">
                <tr>
                  <th className="px-3 py-2">
                    {t('patentAutomation.tracking.colApplicationNo')}
                  </th>
                  <th className="px-3 py-2">
                    {t('patentAutomation.tracking.colTitle')}
                  </th>
                  <th className="px-3 py-2">
                    {t('patentAutomation.tracking.colPhase')}
                  </th>
                  <th className="px-3 py-2">
                    {t('patentAutomation.tracking.colExpiry')}
                  </th>
                  <th className="px-3 py-2">
                    {t('patentAutomation.tracking.colAnnuityDate')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id} className="border-t border-app-border/60">
                    <td className="px-3 py-2 font-mono text-micro text-app-ink">
                      {r.application_no ?? '-'}
                    </td>
                    <td className="px-3 py-2 text-app-ink">
                      {r.invention_title ?? '-'}
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded bg-app-surface-muted px-2 py-0.5 text-micro text-app-ink/80">
                        {r.lifecycle_phase ?? '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-app-ink/80">
                      {r.field_values['expiry_due_date'] ?? '-'}
                    </td>
                    <td className="px-3 py-2 text-app-ink/80">
                      {r.field_values['annuity_payment_date'] ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
