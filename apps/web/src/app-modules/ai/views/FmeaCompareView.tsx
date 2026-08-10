import { useCallback, useReducer, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ClipboardCopy,
  Download,
  FileSpreadsheet,
  Loader2,
  RefreshCw,
  Upload,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  type FmeaAiMode,
  type FmeaAnalyzeResult,
  type FmeaCompareResult,
  type FmeaItem,
  FmeaCompareApiError,
  aiAnalyzeFmea,
  analyzeFmea,
  compareFmea,
} from '../api/fmea-compare-api';

const ACCEPTED = '.xls,.xlsx';
type MainTab = 'compare' | 'analyze';
type SubTab = 'all' | 'high' | 'noaction';
const ANALYZE_MIN_PANEL_WIDTH = 280;
const ANALYZE_MAX_PANEL_WIDTH = 900;
const RESIZE_STEP = 40;

type AnalyzePanelState = {
  result: FmeaAnalyzeResult | null;
  loading: boolean;
  error: string | null;
  subTab: SubTab;
  aiMode: FmeaAiMode;
  aiResult: string;
  aiLoading: boolean;
  leftWidth: number | null;
};

type AnalyzePanelAction =
  | { type: 'uploadStart' }
  | { type: 'uploadSuccess'; result: FmeaAnalyzeResult }
  | { type: 'uploadError'; error: string }
  | { type: 'setSubTab'; subTab: SubTab }
  | { type: 'aiStart'; mode: FmeaAiMode }
  | { type: 'aiSuccess'; mode: FmeaAiMode; result: string }
  | { type: 'aiError'; error: string }
  | { type: 'setAiModeResult'; mode: FmeaAiMode; result: string }
  | { type: 'setLeftWidth'; leftWidth: number };

const INITIAL_ANALYZE_PANEL_STATE: AnalyzePanelState = {
  result: null,
  loading: false,
  error: null,
  subTab: 'all',
  aiMode: 'summary',
  aiResult: '',
  aiLoading: false,
  leftWidth: null,
};

function analyzePanelReducer(
  state: AnalyzePanelState,
  action: AnalyzePanelAction,
): AnalyzePanelState {
  switch (action.type) {
    case 'uploadStart':
      return {
        ...state,
        loading: true,
        error: null,
        result: null,
        aiResult: '',
      };
    case 'uploadSuccess':
      return { ...state, loading: false, result: action.result, subTab: 'all' };
    case 'uploadError':
      return { ...state, loading: false, error: action.error };
    case 'setSubTab':
      return { ...state, subTab: action.subTab };
    case 'aiStart':
      return { ...state, aiMode: action.mode, aiLoading: true, aiResult: '' };
    case 'aiSuccess':
      return {
        ...state,
        aiMode: action.mode,
        aiLoading: false,
        aiResult: action.result,
      };
    case 'aiError':
      return { ...state, aiLoading: false, error: action.error };
    case 'setAiModeResult':
      return { ...state, aiMode: action.mode, aiResult: action.result };
    case 'setLeftWidth':
      return { ...state, leftWidth: action.leftWidth };
  }
}

type ComparePanelState = {
  fileA: File | null;
  fileB: File | null;
  result: FmeaCompareResult | null;
  loading: boolean;
  error: string | null;
};

type ComparePanelAction =
  | { type: 'setFileA'; file: File | null }
  | { type: 'setFileB'; file: File | null }
  | { type: 'requestStart' }
  | { type: 'requestSuccess'; result: FmeaCompareResult }
  | { type: 'requestError'; error: string };

const INITIAL_COMPARE_PANEL_STATE: ComparePanelState = {
  fileA: null,
  fileB: null,
  result: null,
  loading: false,
  error: null,
};

function comparePanelReducer(
  state: ComparePanelState,
  action: ComparePanelAction,
): ComparePanelState {
  switch (action.type) {
    case 'setFileA':
      return { ...state, fileA: action.file };
    case 'setFileB':
      return { ...state, fileB: action.file };
    case 'requestStart':
      return { ...state, loading: true, error: null, result: null };
    case 'requestSuccess':
      return { ...state, loading: false, result: action.result };
    case 'requestError':
      return { ...state, loading: false, error: action.error };
  }
}

const FMEA_RISK_COLORS = {
  high: 'var(--ui-color-danger)',
  warning: 'var(--ui-color-warning)',
  muted: 'var(--ui-color-ink-subtle)',
} as const;

function rpnColor(rpn: number): string {
  if (rpn >= 100) return FMEA_RISK_COLORS.high;
  if (rpn >= 50) return FMEA_RISK_COLORS.warning;
  return FMEA_RISK_COLORS.muted;
}

function itemRpn(it: FmeaItem): number {
  return parseInt(it.rpn || '0', 10) || 0;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof FmeaCompareApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function FmeaCompareView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const workspaceName =
    workspaceBootstrap.data?.workspace.name ?? workspaceSlug ?? '';

  const [tab, setTab] = useState<MainTab>('compare');
  // Remount key per tab: bumping it resets that tab's panel to its initial state.
  const [compareKey, setCompareKey] = useState(0);
  const [analyzeKey, setAnalyzeKey] = useState(0);
  const resetActiveTab = () => {
    if (tab === 'compare') setCompareKey((k) => k + 1);
    else setAnalyzeKey((k) => k + 1);
  };

  return (
    <main className="flex min-h-screen flex-col bg-app-bg text-app-ink">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-app-border bg-app-surface px-6">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <h1 className="truncate app-text-title-md font-semibold tracking-normal">
            {t('ai.fmeaCompare.title')}
          </h1>
          {workspaceName ? (
            <span className="truncate app-text-body font-medium text-app-ink/60">
              {workspaceName}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <TabButton
            active={tab === 'compare'}
            onClick={() => setTab('compare')}
          >
            {t('ai.fmeaCompare.tabs.compare')}
          </TabButton>
          <TabButton
            active={tab === 'analyze'}
            onClick={() => setTab('analyze')}
          >
            {t('ai.fmeaCompare.tabs.analyze')}
          </TabButton>
          <button
            type="button"
            onClick={resetActiveTab}
            title={t('ai.fmeaCompare.reset')}
            className="ml-1 inline-flex h-9 items-center gap-1.5 rounded-md border border-app-border px-3 app-text-body font-medium text-app-ink/70 hover:bg-app-surface-hover"
          >
            <RefreshCw className="size-4" />
            {t('ai.fmeaCompare.reset')}
          </button>
        </div>
      </header>

      {/* Both panels stay mounted so switching tabs preserves their state
          (uploaded files, comparison result, AI analysis cache). */}
      <div className="min-h-0 flex-1">
        <div className={cn('h-full', tab === 'compare' ? '' : 'hidden')}>
          <ComparePanel
            key={compareKey}
            token={token}
            workspaceSlug={workspaceSlug}
          />
        </div>
        <div className={cn('h-full', tab === 'analyze' ? '' : 'hidden')}>
          <AnalyzePanel
            key={analyzeKey}
            token={token}
            workspaceSlug={workspaceSlug}
          />
        </div>
      </div>
    </main>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'h-9 rounded-md px-3 app-text-body font-medium transition',
        active
          ? 'bg-app-accent text-app-accent-fg'
          : 'text-app-ink/70 hover:bg-app-surface-hover',
      )}
    >
      {children}
    </button>
  );
}

function SubTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md px-3 py-1.5 app-text-caption font-medium transition',
        active
          ? 'bg-app-accent text-app-accent-fg'
          : 'text-app-ink/60 hover:bg-app-surface-hover',
      )}
    >
      {children}
    </button>
  );
}

// ─────────────────────────── 분석 탭 ───────────────────────────

function AnalyzePanel({
  token,
  workspaceSlug,
}: {
  token: string | null;
  workspaceSlug: string | null;
}) {
  const { t } = useTranslation('apps');
  const [state, dispatch] = useReducer(
    analyzePanelReducer,
    INITIAL_ANALYZE_PANEL_STATE,
  );
  const {
    result,
    loading,
    error,
    subTab,
    aiMode,
    aiResult,
    aiLoading,
    leftWidth,
  } = state;
  const aiCache = useRef<Partial<Record<FmeaAiMode, string>>>({});
  const splitRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const resizeBy = useCallback(
    (delta: number) => {
      const next = Math.max(
        ANALYZE_MIN_PANEL_WIDTH,
        Math.min(ANALYZE_MAX_PANEL_WIDTH, (state.leftWidth ?? 520) + delta),
      );
      dispatch({ type: 'setLeftWidth', leftWidth: next });
    },
    [state.leftWidth],
  );

  const runAi = useCallback(
    async (mode: FmeaAiMode, items: FmeaItem[]) => {
      const cached = aiCache.current[mode];
      if (cached !== undefined) {
        dispatch({ type: 'setAiModeResult', mode, result: cached });
        return;
      }
      if (!token) return;
      dispatch({ type: 'aiStart', mode });
      try {
        const data = await aiAnalyzeFmea({ token, workspaceSlug, items, mode });
        aiCache.current[mode] = data.result;
        dispatch({ type: 'aiSuccess', mode, result: data.result });
      } catch (err) {
        dispatch({
          type: 'aiError',
          error: errorMessage(err, t('ai.fmeaCompare.errors.aiFailed')),
        });
      }
    },
    [t, token, workspaceSlug],
  );

  const handleUpload = useCallback(
    async (file: File | undefined | null) => {
      if (!file || !token) return;
      dispatch({ type: 'uploadStart' });
      aiCache.current = {};
      try {
        const data = await analyzeFmea({ token, workspaceSlug, file });
        dispatch({ type: 'uploadSuccess', result: data });
        void runAi('summary', data.items.slice(0, 30));
      } catch (err) {
        dispatch({
          type: 'uploadError',
          error: errorMessage(err, t('ai.fmeaCompare.errors.analyzeFailed')),
        });
      }
    },
    [runAi, t, token, workspaceSlug],
  );

  const startResize = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    const container = splitRef.current;
    if (!container) return;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = (e: MouseEvent) => {
      const left = container.getBoundingClientRect().left;
      dispatch({
        type: 'setLeftWidth',
        leftWidth: Math.max(
          ANALYZE_MIN_PANEL_WIDTH,
          Math.min(ANALYZE_MAX_PANEL_WIDTH, e.clientX - left),
        ),
      });
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  const items =
    result == null
      ? []
      : subTab === 'high'
        ? result.high_risk
        : subTab === 'noaction'
          ? result.no_action
          : result.items;

  if (loading) {
    return (
      <div className="flex h-full min-h-[360px] items-center justify-center">
        <div className="flex flex-col items-center gap-3 app-text-body text-app-ink/60">
          <Loader2 className="size-6 animate-spin" />
          {t('ai.fmeaCompare.analyze.loading')}
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex h-full min-h-[360px] items-center justify-center p-6">
        <label
          htmlFor="fmea-analyze-file"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void handleUpload(e.dataTransfer.files?.[0]);
          }}
          className="flex w-full max-w-lg cursor-pointer flex-col items-center rounded-xl border border-dashed border-app-border bg-app-surface p-10 text-center transition hover:border-app-ink/40"
        >
          <FileSpreadsheet className="size-10 text-app-ink/50" />
          <h2 className="mt-4 app-text-title-md font-semibold">
            {t('ai.fmeaCompare.analyze.uploadTitle')}
          </h2>
          <p className="mt-2 app-text-body text-app-ink/60">
            {t('ai.fmeaCompare.analyze.uploadHint')}
          </p>
          <span className="mt-5 inline-flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 app-text-body font-semibold text-app-accent-fg">
            <Upload className="size-4" />
            {t('ai.fmeaCompare.analyze.choose')}
          </span>
          {error ? (
            <p className="mt-4 app-text-body text-app-danger-text dark:text-app-danger-text">
              {error}
            </p>
          ) : null}
          <input
            id="fmea-analyze-file"
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED}
            className="sr-only"
            onChange={(e) => void handleUpload(e.target.files?.[0])}
          />
        </label>
      </div>
    );
  }

  return (
    <div ref={splitRef} className="flex h-[calc(100vh-4rem)] min-h-0">
      {/* Left: data */}
      <div
        className="min-w-[280px] shrink-0 overflow-y-auto p-5"
        style={{ width: leftWidth ? `${leftWidth}px` : '50%' }}
      >
        <div className="mb-4">
          <p className="truncate app-text-body font-medium text-app-ink/60">
            {result.filename}
          </p>
        </div>

        {error ? (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-app-danger-border bg-app-danger-bg p-3 app-text-body text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard>
            <p className="app-text-caption text-app-ink/60">
              {t('ai.fmeaCompare.analyze.stats.summary')}
            </p>
            <p className="mt-2 app-text-caption leading-6 text-app-ink/80">
              {t('ai.fmeaCompare.analyze.stats.total')}:{' '}
              <b>{result.stats.total}</b>
              <br />
              {t('ai.fmeaCompare.analyze.stats.avgRpn')}:{' '}
              <b>{result.stats.avg_rpn}</b>
              <br />
              {t('ai.fmeaCompare.analyze.stats.maxRpn')}:{' '}
              <b>{result.stats.max_rpn}</b>
            </p>
          </StatCard>
          <StatCard>
            <p className="app-text-caption text-app-ink/60">
              {t('ai.fmeaCompare.analyze.highRiskTitle')}
            </p>
            <p
              className="mt-2 text-2xl font-bold"
              style={{ color: FMEA_RISK_COLORS.high }}
            >
              {result.stats.high_risk_count}
            </p>
          </StatCard>
          <StatCard>
            <p className="app-text-caption text-app-ink/60">
              {t('ai.fmeaCompare.analyze.noActionTitle')}
            </p>
            <p
              className="mt-2 text-2xl font-bold"
              style={{ color: FMEA_RISK_COLORS.warning }}
            >
              {result.stats.no_action_count}
            </p>
          </StatCard>
        </div>

        <div className="mb-3 flex gap-1">
          <SubTabButton
            active={subTab === 'all'}
            onClick={() => dispatch({ type: 'setSubTab', subTab: 'all' })}
          >
            {t('ai.fmeaCompare.subtabs.all')}
          </SubTabButton>
          <SubTabButton
            active={subTab === 'high'}
            onClick={() => dispatch({ type: 'setSubTab', subTab: 'high' })}
          >
            {t('ai.fmeaCompare.subtabs.high')}
          </SubTabButton>
          <SubTabButton
            active={subTab === 'noaction'}
            onClick={() => dispatch({ type: 'setSubTab', subTab: 'noaction' })}
          >
            {t('ai.fmeaCompare.subtabs.noaction')}
          </SubTabButton>
        </div>

        {items.length === 0 ? (
          <div className="rounded-md border border-dashed border-app-border p-8 text-center app-text-body text-app-ink/60">
            {t(`ai.fmeaCompare.empty.${subTab}`)}
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((it, i) => (
              <FmeaItemCard key={fmeaItemKey(subTab, it)} index={i} item={it} />
            ))}
          </div>
        )}
      </div>

      {/* Drag handle */}
      <button
        type="button"
        aria-label={t('ai.fmeaCompare.resizePanels')}
        onMouseDown={startResize}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') {
            event.preventDefault();
            resizeBy(-RESIZE_STEP);
          } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            resizeBy(RESIZE_STEP);
          }
        }}
        className="m-0 w-1.5 shrink-0 cursor-col-resize border-0 bg-app-surface-hover transition hover:bg-app-surface-hover focus:outline-none"
      />

      {/* Right: AI analysis */}
      <div className="flex min-w-[280px] flex-1 flex-col border-l border-app-border">
        <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
          <h2 className="app-text-body font-semibold">
            {t('ai.fmeaCompare.ai.title')}
          </h2>
        </div>
        <div className="flex gap-1 border-b border-app-border px-3 py-2">
          <SubTabButton
            active={aiMode === 'summary'}
            onClick={() => void runAi('summary', items.slice(0, 30))}
          >
            {t('ai.fmeaCompare.ai.summary')}
          </SubTabButton>
          <SubTabButton
            active={aiMode === 'improvement'}
            onClick={() => void runAi('improvement', items.slice(0, 30))}
          >
            {t('ai.fmeaCompare.ai.improve')}
          </SubTabButton>
          <SubTabButton
            active={aiMode === 'missing'}
            onClick={() => void runAi('missing', items.slice(0, 30))}
          >
            {t('ai.fmeaCompare.ai.missing')}
          </SubTabButton>
        </div>
        <div className="relative min-h-0 flex-1">
          {aiLoading ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-surface/80">
              <div className="flex flex-col items-center gap-2 app-text-body text-app-ink/60">
                <Loader2 className="size-5 animate-spin" />
                {t('ai.fmeaCompare.ai.loading')}
              </div>
            </div>
          ) : null}
          <div className="h-full overflow-y-auto whitespace-pre-wrap p-4 app-text-body leading-7 text-app-ink/80">
            {aiResult || t('ai.fmeaCompare.ai.placeholder')}
          </div>
        </div>
        <div className="flex gap-2 border-t border-app-border px-3 py-2">
          <button
            type="button"
            disabled={!aiResult}
            onClick={() => void navigator.clipboard.writeText(aiResult)}
            className="inline-flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 app-text-caption text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-50"
          >
            <ClipboardCopy className="size-3" />
            {t('ai.fmeaCompare.ai.copy')}
          </button>
          <button
            type="button"
            disabled={!aiResult}
            onClick={() => downloadText(aiResult)}
            className="inline-flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 app-text-caption text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-50"
          >
            <Download className="size-3" />
            {t('ai.fmeaCompare.ai.download')}
          </button>
        </div>
      </div>
    </div>
  );
}

function StatCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-app-border bg-app-surface p-3.5">
      {children}
    </div>
  );
}

function fmeaItemKey(subTab: SubTab, item: FmeaItem): string {
  return [
    subTab,
    item.item,
    item.failure_mode,
    item.failure_effect,
    item.failure_cause,
    item.rpn,
    item.recommended_action,
    item.action_date,
  ].join('|');
}

function FmeaItemCard({ index, item }: { index: number; item: FmeaItem }) {
  const { t } = useTranslation('apps');
  const rpn = itemRpn(item);
  return (
    <div className="rounded-lg border border-app-border bg-app-surface p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="app-text-caption font-semibold text-app-ink/50">
          {index + 1}
        </span>
        <span className="app-text-body font-semibold text-app-ink/80">
          {item.item || 'N/A'}
        </span>
        <span
          className="ml-auto app-text-body font-bold"
          style={{ color: rpnColor(rpn) }}
        >
          RPN {rpn}
        </span>
      </div>
      <div className="space-y-0.5 app-text-caption leading-6 text-app-ink/70">
        {item.failure_mode ? (
          <Field
            label={t('ai.fmeaCompare.fields.failureMode')}
            value={item.failure_mode}
          />
        ) : null}
        {item.failure_effect ? (
          <Field
            label={t('ai.fmeaCompare.fields.effect')}
            value={item.failure_effect}
          />
        ) : null}
        {item.failure_cause ? (
          <Field
            label={t('ai.fmeaCompare.fields.cause')}
            value={item.failure_cause}
          />
        ) : null}
        <div>
          <b>S:</b> {item.severity || '-'} <b>O:</b> {item.occurrence || '-'}{' '}
          <b>D:</b> {item.detection || '-'}
        </div>
        {item.prevention ? (
          <Field
            label={t('ai.fmeaCompare.fields.prevention')}
            value={item.prevention}
          />
        ) : null}
        {item.detection_method ? (
          <Field
            label={t('ai.fmeaCompare.fields.detection')}
            value={item.detection_method}
          />
        ) : null}
        {item.recommended_action ? (
          <div className="text-app-ink/80">
            <b>{t('ai.fmeaCompare.fields.recommended')}:</b>{' '}
            {item.recommended_action}
          </div>
        ) : null}
        {item.action_result ? (
          <Field
            label={t('ai.fmeaCompare.fields.result')}
            value={item.action_result}
          />
        ) : null}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <b>{label}:</b> {value}
    </div>
  );
}

// ─────────────────────────── 비교 탭 ───────────────────────────

function ComparePanel({
  token,
  workspaceSlug,
}: {
  token: string | null;
  workspaceSlug: string | null;
}) {
  const { t } = useTranslation('apps');
  const [state, dispatch] = useReducer(
    comparePanelReducer,
    INITIAL_COMPARE_PANEL_STATE,
  );
  const { fileA, fileB, result, loading, error } = state;

  const run = useCallback(async () => {
    if (!fileA || !fileB) {
      dispatch({
        type: 'requestError',
        error: t('ai.fmeaCompare.errors.needTwoFiles'),
      });
      return;
    }
    if (!token) return;
    dispatch({ type: 'requestStart' });
    try {
      const data = await compareFmea({ token, workspaceSlug, fileA, fileB });
      dispatch({ type: 'requestSuccess', result: data });
    } catch (err) {
      dispatch({
        type: 'requestError',
        error: errorMessage(err, t('ai.fmeaCompare.errors.compareFailed')),
      });
    }
  }, [fileA, fileB, t, token, workspaceSlug]);

  return (
    <div className="mx-auto max-w-4xl p-5 md:p-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <CompareFilePicker
          id="fmea-cmp-a"
          label={t('ai.fmeaCompare.compare.fileA')}
          file={fileA}
          onChange={(file) => dispatch({ type: 'setFileA', file })}
        />
        <CompareFilePicker
          id="fmea-cmp-b"
          label={t('ai.fmeaCompare.compare.fileB')}
          file={fileB}
          onChange={(file) => dispatch({ type: 'setFileB', file })}
        />
      </div>

      <button
        type="button"
        onClick={() => void run()}
        disabled={loading || !fileA || !fileB}
        className="mt-4 inline-flex h-11 items-center justify-center gap-2 rounded-md bg-app-accent px-6 app-text-body font-semibold text-app-accent-fg hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:bg-app-surface-hover disabled:text-app-ink/40"
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <RefreshCw className="size-4" />
        )}
        {t('ai.fmeaCompare.compare.run')}
      </button>

      {error ? (
        <div className="mt-4 flex items-start gap-2 rounded-md border border-app-danger-border bg-app-danger-bg p-3 app-text-body text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {loading ? (
        <div className="mt-6 flex flex-col items-center gap-3 rounded-md border border-app-border bg-app-surface p-10 app-text-body text-app-ink/60">
          <Loader2 className="size-6 animate-spin" />
          {t('ai.fmeaCompare.compare.loading')}
        </div>
      ) : null}

      {result ? (
        <div className="mt-6 rounded-md border border-app-border bg-app-surface p-5">
          <div className="mb-3 border-b border-app-border pb-3 app-text-body text-app-ink/60">
            <div>
              [A] {result.file_a.filename} ({result.file_a.count})
            </div>
            <div>
              [B] {result.file_b.filename} ({result.file_b.count})
            </div>
          </div>
          <div className="whitespace-pre-wrap app-text-body leading-7 text-app-ink/80">
            {result.comparison}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CompareFilePicker({
  id,
  label,
  file,
  onChange,
}: {
  id: string;
  label: string;
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div>
      <p className="mb-2 app-text-body font-semibold text-app-ink/80">
        {label}
      </p>
      <label
        htmlFor={id}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onChange(e.dataTransfer.files?.[0] ?? null);
        }}
        className="flex min-h-20 cursor-pointer items-center justify-center rounded-md border border-dashed border-app-border bg-app-bg p-4 text-center app-text-body transition hover:border-app-ink/40"
      >
        {file ? (
          <span className="truncate font-medium text-app-ink">{file.name}</span>
        ) : (
          <span className="text-app-ink/60">
            {t('ai.fmeaCompare.compare.choose')}
          </span>
        )}
        <input
          id={id}
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
        />
      </label>
    </div>
  );
}

function downloadText(text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'FMEA_analysis.txt';
  a.click();
  URL.revokeObjectURL(url);
}
