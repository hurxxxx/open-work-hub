import {
  AlertTriangle,
  CheckCircle2,
  Database,
  GitBranch,
  Loader2,
  Search,
  XCircle,
} from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import type {
  RetrievalAnswerMode,
  RetrievalHit,
  RetrievalSource,
  RetrievalStrategy,
} from '@/src/platform/retrieval/retrieval-api';
import {
  isSelectableRetrievalSource,
  RETRIEVAL_ANSWER_MODES,
  RETRIEVAL_STRATEGIES,
  RETRIEVAL_TOP_K_OPTIONS,
  retrievalHitKey,
  type RetrievalTopK,
} from './retrieval-search-view-model';
import { useRetrievalSearchController } from './useRetrievalSearchController';

export function RetrievalSearchView() {
  const { t } = useTranslation('apps');
  const { token, logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const companyName = t('common:labels.company');
  const {
    actions,
    state: {
      answerMode,
      error,
      loadingSources,
      queryInput,
      response,
      searching,
      selectedSources,
      sourceError,
      sources,
      strategy,
      topK,
    },
  } = useRetrievalSearchController({
    logout,
    messages: {
      authMissing: t('ai.retrievalSearch.authMissing'),
      loadFailed: t('ai.retrievalSearch.loadFailed'),
      queryRequired: t('ai.retrievalSearch.queryRequired'),
      sessionExpired: t('ai.retrievalSearch.sessionExpired'),
      sourcesLoadFailed: t('ai.retrievalSearch.sourcesLoadFailed'),
    },
    searchParams,
    setSearchParams,
    token,
  });

  const hits = response?.hits ?? [];
  const profile = response?.profile ?? null;
  const backendProfileText = useMemo(() => {
    if (!profile?.backend_profiles) {
      return '';
    }
    return JSON.stringify(profile.backend_profiles, null, 2);
  }, [profile?.backend_profiles]);

  if (!token) {
    return (
      <div className="p-8 app-text-body text-app-ink/60">
        {t('ai.retrievalSearch.authMissing')}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-app-bg">
      <header className="border-b border-app-border bg-app-surface px-6 py-4">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="app-text-title-lg text-app-ink">
              {t('ai.retrievalSearch.title')}
            </h1>
            <p className="app-text-caption text-app-ink/55">
              {companyName
                ? t('ai.retrievalSearch.subtitle', {
                    company: companyName,
                  })
                : t('ai.retrievalSearch.subtitleFallback')}
            </p>
          </div>

          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              actions.submitSearch();
            }}
          >
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
              <div className="flex min-h-10 flex-1 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 focus-within:border-app-accent">
                <Search size={17} className="shrink-0 text-app-ink/35" />
                <input
                  aria-label={t('ai.retrievalSearch.queryLabel')}
                  className="app-text-body min-w-0 flex-1 bg-transparent text-app-ink outline-none"
                  onChange={(event) =>
                    actions.setQueryInput(event.target.value)
                  }
                  placeholder={t('ai.retrievalSearch.placeholder')}
                  value={queryInput}
                />
              </div>
              <div className="flex items-center gap-2">
                <select
                  aria-label={t('ai.retrievalSearch.topK')}
                  className="app-field-input-sm w-auto"
                  onChange={(event) =>
                    actions.setTopK(Number(event.target.value) as RetrievalTopK)
                  }
                  value={topK}
                >
                  {RETRIEVAL_TOP_K_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {t('ai.retrievalSearch.topKValue', { count: option })}
                    </option>
                  ))}
                </select>
                <button
                  className="inline-flex min-h-10 items-center gap-2 rounded-md bg-app-accent px-4 app-text-control-sm font-semibold text-app-accent-fg disabled:opacity-60"
                  disabled={searching || !queryInput.trim()}
                  type="submit"
                >
                  {searching ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Search size={15} />
                  )}
                  {t('ai.retrievalSearch.search')}
                </button>
              </div>
            </div>

            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
              <div className="flex flex-wrap gap-2">
                {RETRIEVAL_STRATEGIES.map((option) => (
                  <SegmentButton
                    key={option}
                    active={strategy === option}
                    label={strategyLabel(t, option)}
                    onClick={() => actions.setStrategy(option)}
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-2 xl:justify-end">
                {RETRIEVAL_ANSWER_MODES.map((option) => (
                  <SegmentButton
                    key={option}
                    active={answerMode === option}
                    label={answerModeLabel(t, option)}
                    onClick={() => actions.setAnswerMode(option)}
                  />
                ))}
              </div>
            </div>
          </form>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 gap-5 overflow-y-auto px-6 py-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="flex min-w-0 flex-col gap-4">
          <SourceSelector
            actions={actions}
            loading={loadingSources}
            selectedSources={selectedSources}
            sourceError={sourceError}
            sources={sources}
            t={t}
          />

          {error ? (
            <div
              className="rounded-md border border-app-danger-border bg-app-danger-bg px-4 py-3 app-text-body-sm text-app-danger-text"
              role="alert"
            >
              {error}
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-3">
            <p
              className="app-text-caption text-app-ink/55"
              role="status"
              aria-live="polite"
            >
              {response
                ? t('ai.retrievalSearch.resultStatus', {
                    count: hits.length,
                    latency: response.latency_ms,
                  })
                : t('ai.retrievalSearch.ready')}
            </p>
            {response?.trace_id ? (
              <span className="truncate app-text-caption text-app-ink/45">
                {t('ai.retrievalSearch.traceId', {
                  traceId: response.trace_id,
                })}
              </span>
            ) : null}
          </div>

          {searching && !response ? (
            <div className="grid gap-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={index}
                  className="h-24 animate-pulse rounded-md border border-app-border bg-app-surface"
                />
              ))}
            </div>
          ) : null}

          {response && hits.length === 0 && !searching ? (
            <div className="flex min-h-48 items-center justify-center rounded-md border border-app-border bg-app-surface app-text-body text-app-ink/55">
              {t('ai.retrievalSearch.empty')}
            </div>
          ) : null}

          {hits.length > 0 ? (
            <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface">
              {hits.map((hit) => (
                <RetrievalHitRow key={retrievalHitKey(hit)} hit={hit} t={t} />
              ))}
            </div>
          ) : null}
        </section>

        <aside className="min-w-0">
          <div className="sticky top-5 flex flex-col gap-4">
            <DiagnosticsPanel
              backendProfileText={backendProfileText}
              response={response}
              t={t}
            />
          </div>
        </aside>
      </main>
    </div>
  );
}

type TranslationFn = ReturnType<typeof useTranslation>['t'];

function SourceSelector({
  actions,
  loading,
  selectedSources,
  sourceError,
  sources,
  t,
}: {
  actions: ReturnType<typeof useRetrievalSearchController>['actions'];
  loading: boolean;
  selectedSources: string[];
  sourceError: string | null;
  sources: RetrievalSource[];
  t: TranslationFn;
}) {
  return (
    <section className="rounded-md border border-app-border bg-app-surface p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="app-text-title-sm text-app-ink">
          {t('ai.retrievalSearch.sources')}
        </h2>
        <button
          className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-app-border px-3 app-text-control-sm text-app-ink/65 hover:bg-app-surface-hover"
          onClick={actions.reloadSources}
          type="button"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : null}
          {t('ai.retrievalSearch.reloadSources')}
        </button>
      </div>

      {sourceError ? (
        <div className="mb-3 rounded-md border border-app-warning-border bg-app-warning-bg px-3 py-2 app-text-caption text-app-warning-text">
          {sourceError}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          className={cn(
            'inline-flex min-h-9 items-center gap-2 rounded-md border px-3 app-text-control-sm',
            selectedSources.length === 0
              ? 'border-app-accent bg-app-accent/10 text-app-accent'
              : 'border-app-border bg-app-bg text-app-ink/60 hover:bg-app-surface-hover',
          )}
          onClick={actions.clearSources}
          type="button"
        >
          <GitBranch size={14} />
          {t('ai.retrievalSearch.defaultSources')}
        </button>
        {sources.map((source) => {
          const selectable = isSelectableRetrievalSource(source);
          const selected = selectedSources.includes(source.source);
          return (
            <button
              key={source.source}
              className={cn(
                'inline-flex min-h-9 items-center gap-2 rounded-md border px-3 app-text-control-sm transition-colors',
                selected
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border bg-app-bg text-app-ink/70 hover:bg-app-surface-hover',
                !selectable && 'cursor-not-allowed opacity-55',
              )}
              disabled={!selectable}
              onClick={() => actions.toggleSource(source.source)}
              type="button"
            >
              <Database size={14} />
              <span>{sourceLabel(t, source)}</span>
              <SourceStatusIcon source={source} />
            </button>
          );
        })}
      </div>
    </section>
  );
}

function RetrievalHitRow({ hit, t }: { hit: RetrievalHit; t: TranslationFn }) {
  const metadata = hit.metadata ?? {};
  const methods = hit.methods ?? [];
  return (
    <article className="flex flex-col gap-2 px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <SourceBadge source={hit.source} />
            {hit.source_kind ? <MutedBadge label={hit.source_kind} /> : null}
            <MutedBadge label={hit.resource_type} />
          </div>
          <h3 className="app-text-title-sm text-app-ink">
            {hit.title || t('ai.retrievalSearch.untitled')}
          </h3>
        </div>
        <span className="rounded-md bg-app-bg px-2 py-1 app-text-caption text-app-ink/55">
          {t('ai.retrievalSearch.score', {
            score: Number(hit.score ?? 0).toFixed(3),
          })}
        </span>
      </div>
      {hit.summary ? (
        <p className="app-text-body-sm text-app-ink/70">{hit.summary}</p>
      ) : null}
      {hit.excerpt ? (
        <p className="app-text-body-sm text-app-ink/60">{hit.excerpt}</p>
      ) : null}
      {hit.citation ? (
        <p className="app-text-caption text-app-ink/45">{hit.citation}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {methods.map((method) => (
          <MutedBadge key={method} label={method} />
        ))}
        {Object.entries(metadata)
          .slice(0, 4)
          .map(([key, value]) => (
            <MutedBadge
              key={key}
              label={`${key}: ${formatMetadataValue(value)}`}
            />
          ))}
      </div>
    </article>
  );
}

function DiagnosticsPanel({
  backendProfileText,
  response,
  t,
}: {
  backendProfileText: string;
  response: ReturnType<
    typeof useRetrievalSearchController
  >['state']['response'];
  t: TranslationFn;
}) {
  const profile = response?.profile ?? null;
  return (
    <section className="rounded-md border border-app-border bg-app-surface p-4">
      <h2 className="app-text-title-sm text-app-ink">
        {t('ai.retrievalSearch.diagnostics')}
      </h2>
      {profile ? (
        <div className="mt-3 flex flex-col gap-3">
          <DiagnosticRow
            label={t('ai.retrievalSearch.strategy')}
            value={strategyLabel(t, profile.strategy)}
          />
          <DiagnosticRow
            label={t('ai.retrievalSearch.resolvedSources')}
            value={formatList(profile.resolved_sources)}
          />
          <DiagnosticRow
            label={t('ai.retrievalSearch.requestedSources')}
            value={formatList(profile.requested_sources)}
          />
          <DiagnosticRow
            label={t('ai.retrievalSearch.methods')}
            value={formatList(profile.methods ?? response?.methods)}
          />
          <DiagnosticRow
            label={t('ai.retrievalSearch.degraded')}
            value={formatList(profile.degraded_reasons)}
            warning={Boolean(profile.degraded_reasons?.length)}
          />
          {backendProfileText ? (
            <div>
              <p className="mb-1 app-text-caption font-semibold text-app-ink/55">
                {t('ai.retrievalSearch.backendProfiles')}
              </p>
              <pre className="max-h-72 overflow-auto rounded-md bg-app-bg p-3 text-[0.72rem] leading-relaxed text-app-ink/70">
                {backendProfileText}
              </pre>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 app-text-body-sm text-app-ink/55">
          {t('ai.retrievalSearch.diagnosticsReady')}
        </p>
      )}
    </section>
  );
}

function DiagnosticRow({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: string;
  warning?: boolean;
}) {
  return (
    <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-3 app-text-body-sm">
      <dt className="text-app-ink/50">{label}</dt>
      <dd
        className={cn(
          'min-w-0 break-words text-app-ink/75',
          warning && 'text-app-warning-text',
        )}
      >
        {warning ? <AlertTriangle size={14} className="mr-1 inline" /> : null}
        {value}
      </dd>
    </div>
  );
}

function SegmentButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        'min-h-9 rounded-md border px-3 app-text-control-sm transition-colors',
        active
          ? 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/65 hover:bg-app-surface-hover',
      )}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function SourceStatusIcon({ source }: { source: RetrievalSource }) {
  if (!source.active || !source.available) {
    return <XCircle size={14} className="text-app-ink/35" />;
  }
  return <CheckCircle2 size={14} className="text-app-success-text" />;
}

function SourceBadge({ source }: { source: string }) {
  return (
    <span className="inline-flex items-center rounded-md bg-app-accent/10 px-2 py-0.5 app-text-caption font-semibold text-app-accent">
      {source}
    </span>
  );
}

function MutedBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-app-border px-2 py-0.5 app-text-caption text-app-ink/55">
      {label}
    </span>
  );
}

function sourceLabel(t: TranslationFn, source: RetrievalSource): string {
  return t(`ai.retrievalSearch.sourceLabels.${source.source}`, {
    defaultValue: source.label,
  });
}

function strategyLabel(t: TranslationFn, strategy: RetrievalStrategy): string {
  return t(`ai.retrievalSearch.strategyLabels.${strategy}`);
}

function answerModeLabel(
  t: TranslationFn,
  answerMode: RetrievalAnswerMode,
): string {
  return t(`ai.retrievalSearch.answerModeLabels.${answerMode}`);
}

function formatList(values: readonly string[] | undefined): string {
  return values && values.length > 0 ? values.join(', ') : '-';
}

function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '-';
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return JSON.stringify(value);
}
