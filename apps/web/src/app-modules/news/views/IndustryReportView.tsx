import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bookmark,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Search,
  Sparkles,
  Star,
  Trash2,
  Upload,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  deleteRecommendedReport,
  deleteReportScrap,
  deleteTrendFile,
  fetchAiRecommendedReports,
  fetchAutojournalIssues,
  fetchKdiItems,
  fetchRecommendedReports,
  fetchReportScraps,
  fetchTrendCompanies,
  fetchTrendFileObjectUrl,
  fetchTrendFiles,
  recommendReport,
  resolveKdiPdfUrl,
  scrapReport,
  triggerReportCurate,
  uploadTrendFile,
  type KdiPath,
  type ReportItem,
  type RecommendedReport,
  type ReportSnapshotPayload,
  type ScrapReport,
  type TrendCompany,
  type TrendFile,
} from '../api/industry-report-api';

export type ReportTab = 'trend' | 'autojournal' | 'kdi' | 'recommended' | 'ai' | 'scraps';
export const REPORT_TABS: ReportTab[] = ['trend', 'autojournal', 'kdi', 'recommended', 'ai', 'scraps'];
const KDI_PATHS: KdiPath[] = ['nara', 'material', 'domestic'];

/** 저장 중복 판단용 키 — 트렌드는 file_id, 그 외는 url. */
function payloadRef(p: { kind: string; url?: string; file_id?: string | null }): string {
  return p.kind === 'trend' ? `trend:${p.file_id ?? ''}` : (p.url ?? '').trim();
}

/** 패널 공용 추천/스크랩 상태 훅. */
function useReportCollections(token: string | null) {
  const [recommendedRefs, setRecommendedRefs] = useState<Set<string>>(new Set());
  const [scrapRefs, setScrapRefs] = useState<Set<string>>(new Set());
  const refresh = useCallback(() => {
    fetchRecommendedReports(token)
      .then((data) => setRecommendedRefs(new Set(data.items.map(payloadRef))))
      .catch(() => undefined);
    fetchReportScraps(token)
      .then((data) => setScrapRefs(new Set(data.items.map(payloadRef))))
      .catch(() => undefined);
  }, [token]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  const recommend = useCallback(
    async (payload: ReportSnapshotPayload) => {
      await recommendReport(token, payload);
      setRecommendedRefs((prev) => new Set(prev).add(payloadRef(payload)));
    },
    [token],
  );
  const scrap = useCallback(
    async (payload: ReportSnapshotPayload) => {
      await scrapReport(token, payload);
      setScrapRefs((prev) => new Set(prev).add(payloadRef(payload)));
    },
    [token],
  );
  return {
    isRecommended: (ref: string) => recommendedRefs.has(ref),
    isScrapped: (ref: string) => scrapRefs.has(ref),
    recommend,
    scrap,
  };
}

/** 개인 스크랩 + 관리자 추천 액션. */
function ReportActionButtons({
  canRecommend,
  recommended,
  scrapped,
  onRecommend,
  onScrap,
}: {
  canRecommend: boolean;
  recommended: boolean;
  scrapped: boolean;
  onRecommend: () => void;
  onScrap: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex shrink-0 items-center gap-0.5">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          if (!scrapped) onScrap();
        }}
        disabled={scrapped}
        title={scrapped ? t('industryReport.scraps.scrappedLabel') : t('industryReport.scraps.scrapLabel')}
        className={`rounded-md p-1.5 transition-colors ${
          scrapped ? 'text-app-accent' : 'text-app-ink/30 hover:bg-app-accent/10 hover:text-app-accent'
        }`}
      >
        <Bookmark size={14} fill={scrapped ? 'currentColor' : 'none'} />
      </button>
      {canRecommend ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            if (!recommended) onRecommend();
          }}
          disabled={recommended}
          title={
            recommended
              ? t('industryReport.recommended.recommendedLabel')
              : t('industryReport.recommended.recommendLabel')
          }
          className={`rounded-md p-1.5 transition-colors ${
            recommended ? 'text-app-warning' : 'text-app-ink/30 hover:bg-app-warning/10 hover:text-app-warning'
          }`}
        >
          <Star size={14} fill={recommended ? 'currentColor' : 'none'} />
        </button>
      ) : null}
    </div>
  );
}

function isPdfTrendFile(file: TrendFile): boolean {
  const contentType = file.content_type.split(';', 1)[0]?.trim().toLowerCase();
  return contentType === 'application/pdf' && file.filename.toLowerCase().endsWith('.pdf');
}

/**
 * Renders one industry-report section. Which section is shown is controlled by
 * the parent (driven by the left-sidebar nav via the `?tab` query); there is no
 * in-page tab row — navigation lives in the app sidebar.
 */
export function IndustryReportView({ tab }: { tab: ReportTab }) {
  return (
    <div className="h-full w-full pt-3">
      {tab === 'trend' && <TrendPanel />}
      {tab === 'autojournal' && <AutojournalPanel />}
      {tab === 'kdi' && <KdiPanel />}
      {tab === 'recommended' && <ReportCollectionPanel mode="recommended" />}
      {tab === 'ai' && <ReportCollectionPanel mode="ai" />}
      {tab === 'scraps' && <ReportCollectionPanel mode="scraps" />}
    </div>
  );
}

// ── Two-pane scaffold (resizable list panel) ────────────────
const PANE_MIN_WIDTH = 240;
const PANE_MAX_WIDTH = 720;
const PANE_DEFAULT_WIDTH = 340;
const PANE_WIDTH_STORAGE_KEY = 'aido.industryReport.listWidth';

function readStoredPaneWidth(): number {
  try {
    const stored = Number(window.localStorage.getItem(PANE_WIDTH_STORAGE_KEY));
    if (Number.isFinite(stored) && stored >= PANE_MIN_WIDTH && stored <= PANE_MAX_WIDTH) {
      return stored;
    }
  } catch {
    /* localStorage unavailable (private mode, etc.) — fall back to default */
  }
  return PANE_DEFAULT_WIDTH;
}

function TwoPane({
  collapsed,
  onToggle,
  listHeader,
  listControls,
  list,
  detail,
}: {
  collapsed: boolean;
  onToggle: () => void;
  listHeader: React.ReactNode;
  listControls?: React.ReactNode;
  list: React.ReactNode;
  detail: React.ReactNode;
}) {
  const { t } = useTranslation('apps');
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const [width, setWidth] = useState(readStoredPaneWidth);

  // Remember the chosen width across reloads (shared by all three sections).
  useEffect(() => {
    try {
      window.localStorage.setItem(PANE_WIDTH_STORAGE_KEY, String(width));
    } catch {
      /* ignore persistence failures */
    }
  }, [width]);

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const left = containerRef.current.getBoundingClientRect().left;
      const next = Math.min(PANE_MAX_WIDTH, Math.max(PANE_MIN_WIDTH, event.clientX - left));
      setWidth(next);
    };
    const stop = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', stop);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', stop);
    };
  }, []);

  const startDrag = () => {
    draggingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <div ref={containerRef} className="flex h-full">
      {collapsed ? (
        <button
          type="button"
          onClick={onToggle}
          className="mr-3 flex w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/50 hover:border-app-accent"
          aria-label={t('industryReport.panel.expand')}
        >
          <ChevronRight size={16} />
        </button>
      ) : (
        <>
          <aside
            style={{ width }}
            className="flex shrink-0 flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface"
          >
            <div className="flex items-center justify-between gap-2 border-b border-app-border px-3 py-2">
              <div className="min-w-0 flex-1 app-text-caption font-semibold text-app-ink">{listHeader}</div>
              <button
                type="button"
                onClick={onToggle}
                className="shrink-0 text-app-ink/40 hover:text-app-ink"
                aria-label={t('industryReport.panel.collapse')}
              >
                <ChevronLeft size={16} />
              </button>
            </div>
            {listControls ? <div className="border-b border-app-border p-2">{listControls}</div> : null}
            <div className="min-h-0 flex-1 overflow-y-auto p-2">{list}</div>
          </aside>
          {/* Drag handle — resize the list panel width. */}
          <div
            role="separator"
            aria-orientation="vertical"
            onMouseDown={startDrag}
            onDoubleClick={() => setWidth(PANE_DEFAULT_WIDTH)}
            className="group relative w-3 shrink-0 cursor-col-resize"
          >
            <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-app-border transition-colors group-hover:w-0.5 group-hover:bg-app-accent" />
          </div>
        </>
      )}
      <section className="min-w-0 flex-1 rounded-lg border border-app-border bg-app-surface">{detail}</section>
    </div>
  );
}

function ViewerPlaceholder({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      <FileText size={32} className="text-app-ink/20" />
      <div className="app-text-body-sm text-app-ink/50">{title}</div>
      <div className="app-text-caption text-app-ink/35">{hint}</div>
    </div>
  );
}

function Loading() {
  const { t } = useTranslation('apps');
  return <div className="py-12 text-center app-text-body-sm text-app-ink/50">{t('industryReport.loading')}</div>;
}

// ── Trend (자동차 연구원) ────────────────────────────────────
function TrendPanel() {
  const { t } = useTranslation('apps');
  const { token, hasPermission } = useAuth();
  const isAdmin = hasPermission('admin.access');

  const [collapsed, setCollapsed] = useState(false);
  const [companies, setCompanies] = useState<TrendCompany[]>([]);
  const [company, setCompany] = useState<string | null>(null);
  const [files, setFiles] = useState<TrendFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<TrendFile | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploading, setUploading] = useState(false);
  const { isRecommended, isScrapped, recommend, scrap } = useReportCollections(token);

  useEffect(() => {
    fetchTrendCompanies(token)
      .then((data) => {
        setCompanies(data.companies);
        setCompany((current) => current ?? data.companies[0]?.code ?? null);
      })
      .catch(() => undefined);
  }, [token]);

  const loadFiles = useCallback(
    (code: string) => {
      setLoading(true);
      fetchTrendFiles(token, code)
        .then((data) => setFiles(data.files))
        .catch(() => setFiles([]))
        .finally(() => setLoading(false));
    },
    [token],
  );

  useEffect(() => {
    if (company) loadFiles(company);
  }, [company, loadFiles]);

  // Revoke the object URL when it changes or on unmount.
  useEffect(() => () => {
    if (viewerUrl) URL.revokeObjectURL(viewerUrl);
  }, [viewerUrl]);

  const openFile = async (file: TrendFile) => {
    setSelected(file);
    try {
      const url = await fetchTrendFileObjectUrl(token, file.id);
      setViewerUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch {
      setViewerUrl(null);
    }
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !company) return;
    setUploading(true);
    try {
      await uploadTrendFile(token, company, { file, title: uploadTitle.trim() || undefined });
      setUploadTitle('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadFiles(company);
    } catch {
      /* ignore */
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (file: TrendFile) => {
    if (!company) return;
    try {
      await deleteTrendFile(token, file.id);
      if (selected?.id === file.id) {
        setSelected(null);
        setViewerUrl(null);
      }
      loadFiles(company);
    } catch {
      /* ignore */
    }
  };

  const companyLabel = companies.find((c) => c.code === company)?.label ?? company ?? '';

  return (
    <TwoPane
      collapsed={collapsed}
      onToggle={() => setCollapsed((v) => !v)}
      listHeader={`${companyLabel} · ${files.length}${t('industryReport.countSuffix')}`}
      listControls={
        <div className="flex flex-col gap-2">
          <select
            value={company ?? ''}
            onChange={(event) => {
              setCompany(event.target.value);
              setSelected(null);
            }}
            className="app-field-input-sm"
          >
            {companies.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
                {item.file_count > 0 ? ` (${item.file_count})` : ''}
              </option>
            ))}
          </select>
          {isAdmin && (
            <div className="flex items-center gap-2">
              <input
                value={uploadTitle}
                onChange={(event) => setUploadTitle(event.target.value)}
                placeholder={t('industryReport.trend.titlePlaceholder')}
                className="min-w-0 flex-1 rounded-md border border-app-border bg-app-surface px-2 py-1.5 app-text-caption text-app-ink outline-none focus:border-app-accent"
              />
              <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" hidden onChange={handleUpload} />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="flex shrink-0 items-center gap-1 rounded-md bg-app-accent px-2 py-1.5 app-text-caption text-app-accent-fg disabled:opacity-60"
              >
                <Upload size={13} />
                {uploading ? t('industryReport.trend.uploading') : t('industryReport.trend.upload')}
              </button>
            </div>
          )}
        </div>
      }
      list={
        loading ? (
          <Loading />
        ) : files.length === 0 ? (
          <div className="py-12 text-center app-text-caption text-app-ink/45">{t('industryReport.trend.empty')}</div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {files.map((file) => (
              <li key={file.id} className="group flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void openFile(file)}
                  className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors ${
                    selected?.id === file.id ? 'bg-app-accent/10' : 'hover:bg-app-surface-muted'
                  }`}
                >
                  <FileText size={14} className="shrink-0 text-app-ink/40" />
                  <span className="min-w-0 flex-1 app-text-caption text-app-ink line-clamp-1">{file.title}</span>
                  {file.source !== 'upload' ? (
                    <span className="shrink-0 rounded-full bg-app-surface-muted px-1.5 py-0.5 text-[12px] text-app-ink/45">
                      {t('industryReport.trend.autoBadge')}
                    </span>
                  ) : null}
                </button>
                <ReportActionButtons
                  canRecommend={isAdmin}
                  recommended={isRecommended(`trend:${file.id}`)}
                  scrapped={isScrapped(`trend:${file.id}`)}
                  onRecommend={() =>
                    void recommend({
                      kind: 'trend',
                      title: file.title,
                      company: file.company,
                      published_date: file.published_date,
                      file_id: file.id,
                    })
                  }
                  onScrap={() =>
                    void scrap({
                      kind: 'trend',
                      title: file.title,
                      company: file.company,
                      published_date: file.published_date,
                      file_id: file.id,
                    })
                  }
                />
                {isAdmin && file.source === 'upload' && (
                  <button
                    type="button"
                    onClick={() => void handleDelete(file)}
                    aria-label={t('industryReport.trend.delete')}
                    className="shrink-0 text-app-ink/30 opacity-0 hover:text-app-danger group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )
      }
      detail={
        selected && viewerUrl && isPdfTrendFile(selected) ? (
          <iframe src={viewerUrl} title={selected.title} className="h-full w-full rounded-lg" />
        ) : selected && viewerUrl ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
            <FileText size={32} className="text-app-ink/20" />
            <div className="app-text-body-sm text-app-ink/60">{t('industryReport.trend.downloadOnlyTitle')}</div>
            <div className="max-w-sm app-text-caption text-app-ink/40">{t('industryReport.trend.downloadOnlyHint')}</div>
            <a
              href={viewerUrl}
              download={selected.filename}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-app-border px-3 py-1.5 app-text-control text-app-ink/70 hover:border-app-accent"
            >
              <Download size={14} />
              {t('industryReport.trend.downloadFile')}
            </a>
          </div>
        ) : selected ? (
          <Loading />
        ) : (
          <ViewerPlaceholder
            title={t('industryReport.trend.viewerEmptyTitle')}
            hint={t('industryReport.trend.viewerEmptyHint')}
          />
        )
      }
    />
  );
}

// ── Autojournal (오토저널) ──────────────────────────────────
function AutojournalPanel() {
  const { t } = useTranslation('apps');
  const { token, hasPermission } = useAuth();
  const isAdmin = hasPermission('admin.access');

  const [collapsed, setCollapsed] = useState(false);
  const [issues, setIssues] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const { isRecommended, isScrapped, recommend, scrap } = useReportCollections(token);

  useEffect(() => {
    setLoading(true);
    fetchAutojournalIssues(token)
      .then((data) => setIssues(data.items))
      .catch(() => setIssues([]))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <TwoPane
      collapsed={collapsed}
      onToggle={() => setCollapsed((v) => !v)}
      listHeader={t('industryReport.autojournal.listHeader')}
      list={
        loading ? (
          <Loading />
        ) : issues.length === 0 ? (
          <div className="py-12 text-center app-text-caption text-app-ink/45">{t('industryReport.autojournal.empty')}</div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {issues.map((issue) => (
              <li key={issue.url} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setSelected(issue)}
                  className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left transition-colors ${
                    selected?.url === issue.url ? 'bg-app-accent/10' : 'hover:bg-app-surface-muted'
                  }`}
                >
                  <BookOpen size={14} className="shrink-0 text-app-ink/40" />
                  <span className="app-text-caption text-app-ink line-clamp-1">{issue.title}</span>
                </button>
                <ReportActionButtons
                  canRecommend={isAdmin}
                  recommended={isRecommended(issue.url)}
                  scrapped={isScrapped(issue.url)}
                  onRecommend={() =>
                    void recommend({
                      kind: 'autojournal',
                      title: issue.title,
                      published_date: issue.published_date,
                      url: issue.url,
                    })
                  }
                  onScrap={() =>
                    void scrap({
                      kind: 'autojournal',
                      title: issue.title,
                      published_date: issue.published_date,
                      url: issue.url,
                    })
                  }
                />
              </li>
            ))}
          </ul>
        )
      }
      detail={
        selected ? (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between gap-2 border-b border-app-border px-4 py-2">
              <span className="app-text-body-sm font-semibold text-app-ink line-clamp-1">
                {selected.title}
              </span>
              <a
                href={selected.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex shrink-0 items-center gap-1 rounded-md border border-app-border px-2 py-1 app-text-caption text-app-ink/70 hover:border-app-accent"
              >
                <ExternalLink size={13} />
                {t('industryReport.autojournal.openPlatform')}
              </a>
            </div>
            {/* 오토저널 원문(webbook 플랫폼)을 그대로 임베드 */}
            <iframe
              src={selected.url}
              title={selected.title}
              className="min-h-0 flex-1 w-full"
            />
          </div>
        ) : (
          <ViewerPlaceholder
            title={t('industryReport.autojournal.viewerEmptyTitle')}
            hint={t('industryReport.autojournal.viewerEmptyHint')}
          />
        )
      }
    />
  );
}

// ── KDI (경제연구 자료) ─────────────────────────────────────
function KdiPanel() {
  const { t } = useTranslation('apps');
  const { token, hasPermission } = useAuth();
  const isAdmin = hasPermission('admin.access');

  const [collapsed, setCollapsed] = useState(false);
  const [path, setPath] = useState<KdiPath>('nara');
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const { isRecommended, isScrapped, recommend, scrap } = useReportCollections(token);

  useEffect(() => {
    setLoading(true);
    fetchKdiItems(token, path, query || undefined)
      .then((data) => setItems(data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [token, path, query]);

  const selectItem = async (item: ReportItem) => {
    setSelected(item);
    setPdfUrl(null);
    setResolving(true);
    try {
      const result = await resolveKdiPdfUrl(token, item.url);
      setPdfUrl(result.pdf_url);
    } catch {
      setPdfUrl(null);
    } finally {
      setResolving(false);
    }
  };

  return (
    <TwoPane
      collapsed={collapsed}
      onToggle={() => setCollapsed((v) => !v)}
      listHeader={`${t(`industryReport.kdi.sources.${path}`)} · ${items.length}${t('industryReport.countSuffix')}`}
      listControls={
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-1">
            {KDI_PATHS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setPath(value);
                  setSelected(null);
                }}
                className={`rounded-full border px-2.5 py-1 app-text-caption transition-colors ${
                  path === value
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border text-app-ink/70 hover:border-app-accent'
                }`}
              >
                {t(`industryReport.kdi.sources.${value}`)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') setQuery(keyword.trim());
              }}
              placeholder={t('industryReport.kdi.searchPlaceholder')}
              className="min-w-0 flex-1 rounded-md border border-app-border bg-app-surface px-2 py-1.5 app-text-caption text-app-ink outline-none focus:border-app-accent"
            />
            <button
              type="button"
              onClick={() => setQuery(keyword.trim())}
              className="flex shrink-0 items-center rounded-md bg-app-accent px-2 py-1.5 text-app-accent-fg"
              aria-label={t('industryReport.kdi.search')}
            >
              <Search size={13} />
            </button>
          </div>
        </div>
      }
      list={
        loading ? (
          <Loading />
        ) : items.length === 0 ? (
          <div className="py-12 text-center app-text-caption text-app-ink/45">{t('industryReport.kdi.empty')}</div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {items.map((item) => (
              <li key={item.url} className="flex items-start gap-1">
                <button
                  type="button"
                  onClick={() => void selectItem(item)}
                  className={`flex min-w-0 flex-1 flex-col gap-0.5 rounded-md px-2 py-1.5 text-left transition-colors ${
                    selected?.url === item.url ? 'bg-app-accent/10' : 'hover:bg-app-surface-muted'
                  }`}
                >
                  <span className="app-text-caption text-app-ink line-clamp-2">{item.title}</span>
                  <span className="flex gap-2 text-[12px] text-app-ink/45">
                    {item.org ? <span className="line-clamp-1">{item.org}</span> : null}
                    {item.published_date ? <span className="shrink-0">{item.published_date}</span> : null}
                  </span>
                </button>
                <ReportActionButtons
                  canRecommend={isAdmin}
                  recommended={isRecommended(item.url)}
                  scrapped={isScrapped(item.url)}
                  onRecommend={() =>
                    void recommend({
                      kind: item.source as ReportSnapshotPayload['kind'],
                      title: item.title,
                      org: item.org,
                      published_date: item.published_date,
                      url: item.url,
                    })
                  }
                  onScrap={() =>
                    void scrap({
                      kind: item.source as ReportSnapshotPayload['kind'],
                      title: item.title,
                      org: item.org,
                      published_date: item.published_date,
                      url: item.url,
                    })
                  }
                />
              </li>
            ))}
          </ul>
        )
      }
      detail={
        selected ? (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between gap-2 border-b border-app-border px-4 py-2">
              <div className="min-w-0">
                <div className="app-text-body-sm font-semibold text-app-ink line-clamp-1">{selected.title}</div>
                <div className="app-text-caption text-app-ink/45">
                  {[selected.org, selected.published_date].filter(Boolean).join(' · ')}
                </div>
              </div>
              <a
                href={selected.url}
                target="_blank"
                rel="noreferrer"
                className="flex shrink-0 items-center gap-1 rounded-md border border-app-border px-2 py-1.5 app-text-caption text-app-ink/70 hover:border-app-accent"
              >
                <ExternalLink size={13} />
                {t('industryReport.kdi.openOriginal')}
              </a>
            </div>
            {resolving ? (
              <Loading />
            ) : (
              // PDF가 있으면(나라경제) PDF를, 없으면(정책/연구자료) 해당 문서의
              // KDI 페이지를 그대로 임베드한다.
              <iframe
                src={pdfUrl ?? selected.url}
                title={selected.title}
                className="min-h-0 flex-1 rounded-b-lg"
              />
            )}
          </div>
        ) : (
          <ViewerPlaceholder
            title={t('industryReport.kdi.viewerEmptyTitle')}
            hint={t('industryReport.kdi.viewerEmptyHint')}
          />
        )
      }
    />
  );
}

// ── 추천/스크랩 산업 리포트 ─────────────────────────────────
type ReportCollectionMode = 'recommended' | 'ai' | 'scraps';
type ReportCollectionItem = RecommendedReport | ScrapReport;

function reportKindTabKey(kind: ReportSnapshotPayload['kind']): 'trend' | 'autojournal' | 'kdi' {
  if (kind === 'trend') return 'trend';
  if (kind === 'autojournal') return 'autojournal';
  return 'kdi';
}

function isRecommendedItem(item: ReportCollectionItem): item is RecommendedReport {
  return 'reason' in item;
}

function ReportCollectionPanel({ mode }: { mode: ReportCollectionMode }) {
  const { t } = useTranslation('apps');
  const { token, hasPermission } = useAuth();
  const isAdmin = hasPermission('admin.access');
  const isAi = mode === 'ai';
  const isScraps = mode === 'scraps';
  const ns = isAi
    ? 'industryReport.ai'
    : isScraps
      ? 'industryReport.scraps'
      : 'industryReport.recommended';

  const [collapsed, setCollapsed] = useState(false);
  const [items, setItems] = useState<ReportCollectionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<ReportCollectionItem | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [curating, setCurating] = useState(false);
  const [curateNote, setCurateNote] = useState<string | null>(null);
  const { isScrapped, scrap } = useReportCollections(token);

  const load = useCallback(() => {
    setLoading(true);
    (isAi
      ? fetchAiRecommendedReports(token)
      : isScraps
        ? fetchReportScraps(token)
        : fetchRecommendedReports(token)
    )
      .then((data) => setItems(data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [token, isAi, isScraps]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCurate = async () => {
    setCurating(true);
    setCurateNote(null);
    try {
      const result = await triggerReportCurate(token);
      setCurateNote(
        result.error
          ? t('industryReport.ai.analyzeFailed', { error: result.error })
          : t('industryReport.ai.result', { evaluated: result.evaluated, saved: result.saved }),
      );
      load();
    } catch {
      setCurateNote(t('industryReport.ai.requestFailed'));
    } finally {
      setCurating(false);
    }
  };

  // blob: 미리보기 URL은 교체/언마운트 시 해제.
  useEffect(() => () => {
    if (viewerUrl?.startsWith('blob:')) URL.revokeObjectURL(viewerUrl);
  }, [viewerUrl]);

  const openCollectionItem = async (item: ReportCollectionItem) => {
    setSelected(item);
    setViewerUrl(null);
    setResolving(true);
    try {
      let url: string | null = item.url || null;
      if (item.kind === 'trend' && item.file_id) {
        // 첨부파일(자동차연구원 PDF)을 object URL 로 받아 미리보기.
        url = await fetchTrendFileObjectUrl(token, item.file_id);
      } else if (item.kind !== 'autojournal') {
        // KDI: PDF가 있으면 PDF, 없으면 문서 페이지.
        const res = await resolveKdiPdfUrl(token, item.url);
        url = res.pdf_url ?? item.url;
      }
      setViewerUrl((prev) => {
        if (prev?.startsWith('blob:')) URL.revokeObjectURL(prev);
        return url;
      });
    } catch {
      setViewerUrl(item.url || null);
    } finally {
      setResolving(false);
    }
  };

  const handleDelete = async (item: ReportCollectionItem) => {
    try {
      if (isScraps) {
        await deleteReportScrap(token, item.id);
      } else {
        await deleteRecommendedReport(token, item.id);
      }
      setItems((prev) => prev.filter((x) => x.id !== item.id));
      if (selected?.id === item.id) {
        setSelected(null);
        setViewerUrl(null);
      }
    } catch {
      /* ignore */
    }
  };

  return (
    <TwoPane
      collapsed={collapsed}
      onToggle={() => setCollapsed((v) => !v)}
      listHeader={`${t(`${ns}.listHeader`)} · ${items.length}${t('industryReport.countSuffix')}`}
      listControls={
        isAi && isAdmin ? (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void handleCurate()}
              disabled={curating}
              className="flex items-center gap-1 rounded-md bg-app-accent px-2.5 py-1.5 app-text-caption text-app-accent-fg disabled:opacity-60"
            >
              <Sparkles size={13} className={curating ? 'animate-pulse' : ''} />
              {curating ? t('industryReport.ai.curating') : t('industryReport.ai.curateNow')}
            </button>
            {curateNote ? <span className="app-text-caption text-app-ink/55">{curateNote}</span> : null}
          </div>
        ) : undefined
      }
      list={
        loading ? (
          <Loading />
        ) : items.length === 0 ? (
          <div className="py-12 text-center app-text-caption text-app-ink/45">{t(`${ns}.empty`)}</div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {items.map((item) => (
              <li key={item.id} className="group flex items-start gap-1">
                <button
                  type="button"
                  onClick={() => void openCollectionItem(item)}
                  className={`flex min-w-0 flex-1 flex-col gap-0.5 rounded-md px-2 py-1.5 text-left transition-colors ${
                    selected?.id === item.id ? 'bg-app-accent/10' : 'hover:bg-app-surface-muted'
                  }`}
                >
                  <span className="app-text-caption text-app-ink line-clamp-2">{item.title}</span>
                  <span className="flex flex-wrap gap-1.5 text-[12px] text-app-ink/45">
                    {isAi && isRecommendedItem(item) && item.reason ? (
                      <span className="shrink-0 rounded-full border border-app-accent/40 bg-app-accent/10 px-1.5 py-0.5 text-app-accent">
                        {item.reason}
                      </span>
                    ) : null}
                    <span className="shrink-0 rounded-full bg-app-surface-muted px-1.5 py-0.5 text-app-ink/55">
                      {t(`industryReport.tabs.${reportKindTabKey(item.kind)}`)}
                    </span>
                    {item.published_date ? <span className="shrink-0">{item.published_date}</span> : null}
                  </span>
                </button>
                {!isScraps ? (
                  <button
                    type="button"
                    onClick={() =>
                      !isScrapped(payloadRef(item)) &&
                      void scrap({
                        kind: item.kind,
                        title: item.title,
                        org: item.org,
                        published_date: item.published_date,
                        url: item.url,
                        file_id: item.file_id,
                        company: item.company,
                      })
                    }
                    disabled={isScrapped(payloadRef(item))}
                    aria-label={t('industryReport.scraps.scrapLabel')}
                    className={`shrink-0 p-1.5 ${
                      isScrapped(payloadRef(item))
                        ? 'text-app-accent'
                        : 'text-app-ink/30 hover:text-app-accent'
                    }`}
                  >
                    <Bookmark size={13} fill={isScrapped(payloadRef(item)) ? 'currentColor' : 'none'} />
                  </button>
                ) : null}
                {(isScraps || isAdmin) && (
                  <button
                    type="button"
                    onClick={() => void handleDelete(item)}
                    aria-label={t(`${ns}.delete`)}
                    className="shrink-0 p-1.5 text-app-ink/30 opacity-0 hover:text-app-danger group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )
      }
      detail={
        selected ? (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between gap-2 border-b border-app-border px-4 py-2">
              <div className="min-w-0">
                <div className="app-text-body-sm font-semibold text-app-ink line-clamp-1">{selected.title}</div>
                <div className="app-text-caption text-app-ink/45">
                  {[selected.org, selected.published_date].filter(Boolean).join(' · ')}
                </div>
              </div>
              {selected.kind !== 'trend' && selected.url ? (
                <a
                  href={selected.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex shrink-0 items-center gap-1 rounded-md border border-app-border px-2 py-1.5 app-text-caption text-app-ink/70 hover:border-app-accent"
                >
                  <ExternalLink size={13} />
                  {t('industryReport.kdi.openOriginal')}
                </a>
              ) : null}
            </div>
            {resolving ? (
              <Loading />
            ) : viewerUrl ? (
              <iframe src={viewerUrl} title={selected.title} className="min-h-0 flex-1 rounded-b-lg" />
            ) : (
              <ViewerPlaceholder
                title={t(`${ns}.viewerEmptyTitle`)}
                hint={t(`${ns}.viewerEmptyHint`)}
              />
            )}
          </div>
        ) : (
          <ViewerPlaceholder
            title={t(`${ns}.viewerEmptyTitle`)}
            hint={t(`${ns}.viewerEmptyHint`)}
          />
        )
      }
    />
  );
}
