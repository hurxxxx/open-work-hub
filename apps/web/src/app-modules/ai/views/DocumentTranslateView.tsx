import { useCallback, useReducer, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ClipboardCopy,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  Upload,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  type DocMode,
  type SummaryLevel,
  type TargetLang,
  DocumentTranslateApiError,
  processDocumentFile,
  processDocumentText,
} from '../api/document-translate-api';

const ACCEPTED = '.pdf,.docx,.xlsx,.pptx,.txt';
const MODES: DocMode[] = ['translate', 'summarize', 'extract'];
const LANGS: TargetLang[] = ['ko', 'en', 'zh', 'ja', 'es', 'de'];
const MIN_PANEL_WIDTH = 320;
const RESIZE_STEP = 40;

type DocumentTranslateState = {
  mode: DocMode;
  targetLang: TargetLang;
  summaryLevel: SummaryLevel;
  text: string;
  file: File | null;
  result: string;
  loading: boolean;
  error: string | null;
  copied: boolean;
};

type DocumentTranslateAction =
  | { type: 'setMode'; mode: DocMode }
  | { type: 'setTargetLang'; targetLang: TargetLang }
  | { type: 'setSummaryLevel'; summaryLevel: SummaryLevel }
  | { type: 'setText'; text: string }
  | { type: 'setFile'; file: File | null }
  | { type: 'requestStart' }
  | { type: 'requestSuccess'; result: string }
  | { type: 'requestError'; error: string }
  | { type: 'setCopied'; copied: boolean }
  | { type: 'reset' };

const INITIAL_DOCUMENT_TRANSLATE_STATE: DocumentTranslateState = {
  mode: 'translate',
  targetLang: 'ko',
  summaryLevel: 'detailed',
  text: '',
  file: null,
  result: '',
  loading: false,
  error: null,
  copied: false,
};

function documentTranslateReducer(
  state: DocumentTranslateState,
  action: DocumentTranslateAction,
): DocumentTranslateState {
  switch (action.type) {
    case 'setMode':
      return { ...state, mode: action.mode };
    case 'setTargetLang':
      return { ...state, targetLang: action.targetLang };
    case 'setSummaryLevel':
      return { ...state, summaryLevel: action.summaryLevel };
    case 'setText':
      return { ...state, text: action.text };
    case 'setFile':
      return { ...state, file: action.file };
    case 'requestStart':
      return { ...state, loading: true, error: null, result: '', copied: false };
    case 'requestSuccess':
      return { ...state, loading: false, result: action.result };
    case 'requestError':
      return { ...state, loading: false, error: action.error };
    case 'setCopied':
      return { ...state, copied: action.copied };
    case 'reset':
      return INITIAL_DOCUMENT_TRANSLATE_STATE;
  }
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof DocumentTranslateApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function DocumentTranslateView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ?? resolveShellWorkspaceSlug(user, null);
  const workspaceName = workspaceBootstrap.data?.workspace.name ?? workspaceSlug ?? '';

  const [state, dispatch] = useReducer(
    documentTranslateReducer,
    INITIAL_DOCUMENT_TRANSLATE_STATE,
  );
  const {
    mode,
    targetLang,
    summaryLevel,
    text,
    file,
    result,
    loading,
    error,
    copied,
  } = state;
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Draggable split between input (left) and result (right).
  const [leftWidth, setLeftWidth] = useState<number | null>(null);
  const splitRef = useRef<HTMLDivElement | null>(null);

  const resizeBy = useCallback((delta: number) => {
    const container = splitRef.current;
    if (!container) return;
    const total = container.getBoundingClientRect().width;
    setLeftWidth((current) => {
      const base = current ?? total / 2;
      return Math.max(MIN_PANEL_WIDTH, Math.min(total - MIN_PANEL_WIDTH, base + delta));
    });
  }, []);

  const startResize = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    const container = splitRef.current;
    if (!container) return;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = (e: MouseEvent) => {
      const left = container.getBoundingClientRect().left;
      const total = container.getBoundingClientRect().width;
      setLeftWidth(Math.max(MIN_PANEL_WIDTH, Math.min(total - MIN_PANEL_WIDTH, e.clientX - left)));
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

  const reset = useCallback(() => {
    dispatch({ type: 'reset' });
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const run = useCallback(async () => {
    if (!token) return;
    if (!file && !text.trim()) {
      dispatch({ type: 'requestError', error: t('ai.documentTranslate.errors.noInput') });
      return;
    }
    dispatch({ type: 'requestStart' });
    try {
      const data = file
        ? await processDocumentFile({ token, workspaceSlug, file, mode, targetLang, summaryLevel })
        : await processDocumentText({ token, workspaceSlug, text, mode, targetLang, summaryLevel });
      dispatch({ type: 'requestSuccess', result: data.result });
    } catch (err) {
      dispatch({
        type: 'requestError',
        error: errorMessage(err, t('ai.documentTranslate.errors.processFailed')),
      });
    }
  }, [file, mode, summaryLevel, t, targetLang, text, token, workspaceSlug]);

  const copyResult = useCallback(async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result);
      dispatch({ type: 'setCopied', copied: true });
      window.setTimeout(() => dispatch({ type: 'setCopied', copied: false }), 1500);
    } catch {
      /* clipboard unavailable — ignore */
    }
  }, [result]);

  const downloadResult = useCallback(() => {
    if (!result) return;
    const blob = new Blob([result], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${mode}-result.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [mode, result]);

  return (
    <main className="flex min-h-screen flex-col bg-app-bg text-app-ink">
      <DocumentTranslateHeader
        mode={mode}
        workspaceName={workspaceName}
        onModeChange={(nextMode) => dispatch({ type: 'setMode', mode: nextMode })}
        onReset={reset}
      />
      <div ref={splitRef} className="flex min-h-0 flex-1">
        <section
          className="flex min-w-[320px] shrink-0 flex-col gap-3 overflow-y-auto p-5"
          style={{ width: leftWidth ? `${leftWidth}px` : '50%' }}
        >
          <DocumentTranslateOptions
            mode={mode}
            summaryLevel={summaryLevel}
            targetLang={targetLang}
            onSummaryLevelChange={(nextLevel) =>
              dispatch({ type: 'setSummaryLevel', summaryLevel: nextLevel })
            }
            onTargetLangChange={(nextLang) =>
              dispatch({ type: 'setTargetLang', targetLang: nextLang })
            }
          />
          <DocumentTranslateSourceInput
            file={file}
            fileInputRef={fileInputRef}
            text={text}
            onFileChange={(nextFile) => dispatch({ type: 'setFile', file: nextFile })}
            onTextChange={(nextText) => dispatch({ type: 'setText', text: nextText })}
          />
          <button
            type="button"
            onClick={() => void run()}
            disabled={loading || (!file && !text.trim())}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-app-accent px-4 app-text-body font-semibold text-app-accent-fg transition hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:bg-app-surface-hover disabled:text-app-ink/40"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />}
            {t(`ai.documentTranslate.modes.${mode}`)}
          </button>

          {error ? (
            <div className="flex items-start gap-2 rounded-md border border-ui-danger/30 bg-ui-danger/10 p-3 app-text-body text-ui-danger">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}
        </section>
        <ResizeHandle
          label={t('ai.documentTranslate.resizePanels')}
          onMouseDown={startResize}
          onResizeBy={resizeBy}
        />
        <DocumentTranslateResultPane
          copied={copied}
          loading={loading}
          result={result}
          onCopy={copyResult}
          onDownload={downloadResult}
        />
      </div>
    </main>
  );
}

function DocumentTranslateHeader({
  mode,
  workspaceName,
  onModeChange,
  onReset,
}: {
  mode: DocMode;
  workspaceName: string;
  onModeChange: (mode: DocMode) => void;
  onReset: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-app-border bg-app-surface px-6">
      <div className="flex min-w-0 items-baseline gap-2.5">
        <h1 className="truncate app-text-title-md font-semibold tracking-normal">
          {t('ai.documentTranslate.title')}
        </h1>
        {workspaceName ? (
          <span className="truncate app-text-body font-medium text-app-ink/60">{workspaceName}</span>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {MODES.map((m) => (
          <TabButton key={m} active={mode === m} onClick={() => onModeChange(m)}>
            {t(`ai.documentTranslate.modes.${m}`)}
          </TabButton>
        ))}
        <button
          type="button"
          onClick={onReset}
          title={t('ai.documentTranslate.reset')}
          className="ml-1 inline-flex h-9 items-center gap-1.5 rounded-md border border-app-border px-3 app-text-body font-medium text-app-ink/70 hover:bg-app-surface-hover"
        >
          <RefreshCw className="size-4" />
          {t('ai.documentTranslate.reset')}
        </button>
      </div>
    </header>
  );
}

function DocumentTranslateOptions({
  mode,
  summaryLevel,
  targetLang,
  onSummaryLevelChange,
  onTargetLangChange,
}: {
  mode: DocMode;
  summaryLevel: SummaryLevel;
  targetLang: TargetLang;
  onSummaryLevelChange: (level: SummaryLevel) => void;
  onTargetLangChange: (lang: TargetLang) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <>
      <p className="rounded-md bg-app-surface-sidebar px-3 py-2 app-text-caption leading-5 text-app-ink/70">
        {t(`ai.documentTranslate.descriptions.${mode}`)}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 app-text-body">
          <span className="text-app-ink/60">{t('ai.documentTranslate.targetLang')}</span>
          <select
            value={targetLang}
            onChange={(event) => onTargetLangChange(event.target.value as TargetLang)}
            className="app-field-input-sm w-auto"
          >
            {LANGS.map((lang) => (
              <option key={lang} value={lang}>
                {t(`ai.documentTranslate.langs.${lang}`)}
              </option>
            ))}
          </select>
        </label>
        {mode === 'summarize' ? (
          <div className="flex items-center gap-1">
            <SubTabButton
              active={summaryLevel === 'brief'}
              onClick={() => onSummaryLevelChange('brief')}
            >
              {t('ai.documentTranslate.summaryLevels.brief')}
            </SubTabButton>
            <SubTabButton
              active={summaryLevel === 'detailed'}
              onClick={() => onSummaryLevelChange('detailed')}
            >
              {t('ai.documentTranslate.summaryLevels.detailed')}
            </SubTabButton>
          </div>
        ) : null}
      </div>
    </>
  );
}

function DocumentTranslateSourceInput({
  file,
  fileInputRef,
  text,
  onFileChange,
  onTextChange,
}: {
  file: File | null;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  text: string;
  onFileChange: (file: File | null) => void;
  onTextChange: (text: string) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <>
      <label
        htmlFor="doc-translate-file"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          const dropped = event.dataTransfer.files?.[0];
          if (dropped) onFileChange(dropped);
        }}
        className="flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-app-border bg-app-surface px-4 py-3 app-text-body transition hover:border-app-ink/40"
      >
        <Upload className="size-4 text-app-ink/40" />
        <span className="min-w-0 flex-1 truncate text-app-ink/70">
          {file ? file.name : t('ai.documentTranslate.uploadHint')}
        </span>
        {file ? (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              onFileChange(null);
              if (fileInputRef.current) fileInputRef.current.value = '';
            }}
            className="app-text-caption font-medium text-app-ink/55 hover:text-app-ink"
          >
            {t('ai.documentTranslate.clearFile')}
          </button>
        ) : null}
        <input
          id="doc-translate-file"
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
        />
      </label>
      <div className="flex items-center gap-2 app-text-caption text-app-ink/40">
        <span className="h-px flex-1 bg-app-border" />
        {t('ai.documentTranslate.or')}
        <span className="h-px flex-1 bg-app-border" />
      </div>
      <textarea
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        disabled={file != null}
        aria-label={t('ai.documentTranslate.inputLabel')}
        placeholder={t('ai.documentTranslate.textPlaceholder')}
        className="min-h-[260px] flex-1 resize-none rounded-lg border border-app-border bg-app-surface p-3 app-text-body outline-none focus:border-app-ink/40 disabled:opacity-50"
      />
    </>
  );
}

function ResizeHandle({
  label,
  onMouseDown,
  onResizeBy,
}: {
  label: string;
  onMouseDown: (event: React.MouseEvent) => void;
  onResizeBy: (delta: number) => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onMouseDown={onMouseDown}
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          onResizeBy(-RESIZE_STEP);
        } else if (event.key === 'ArrowRight') {
          event.preventDefault();
          onResizeBy(RESIZE_STEP);
        }
      }}
      className="m-0 w-1.5 shrink-0 cursor-col-resize border-0 bg-app-border transition hover:bg-app-ink/20 focus:bg-app-ink/20 focus:outline-none"
    />
  );
}

function DocumentTranslateResultPane({
  copied,
  loading,
  result,
  onCopy,
  onDownload,
}: {
  copied: boolean;
  loading: boolean;
  result: string;
  onCopy: () => Promise<void>;
  onDownload: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <section className="flex min-w-[320px] flex-1 flex-col overflow-hidden p-5">
      <div className="mb-3 flex items-center justify-between">
        <span className="app-text-body font-medium text-app-ink/60">
          {t('ai.documentTranslate.resultTitle')}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void onCopy()}
            disabled={!result}
            title={t('ai.documentTranslate.copy')}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border px-2.5 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-40"
          >
            <ClipboardCopy className="size-3.5" />
            {copied ? t('ai.documentTranslate.copied') : t('ai.documentTranslate.copy')}
          </button>
          <button
            type="button"
            onClick={onDownload}
            disabled={!result}
            title={t('ai.documentTranslate.download')}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border px-2.5 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-40"
          >
            <Download className="size-3.5" />
            {t('ai.documentTranslate.download')}
          </button>
        </div>
      </div>
      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-3 app-text-body text-app-ink/60">
            <Loader2 className="size-6 animate-spin" />
            {t('ai.documentTranslate.processing')}
          </div>
        </div>
      ) : (
        <textarea
          readOnly
          value={result}
          aria-label={t('ai.documentTranslate.resultTitle')}
          placeholder={t('ai.documentTranslate.resultPlaceholder')}
          className="flex-1 resize-none rounded-lg border border-app-border bg-app-surface p-3 app-text-body outline-none"
        />
      )}
    </section>
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
