import { type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  Search,
} from 'lucide-react';
import { InlineNotice } from '@open-work-hub/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import type { FileSearchHit, FileSearchStrategy } from '../api/files-api';
import {
  fileSearchSnippetSegments,
  FILE_SEARCH_STRATEGIES,
} from './file-search-view-model';
import { formatFileSize } from './file-manager-view-model';
import {
  useFileSearchController,
  type FileSearchController,
} from './useFileSearchController';

export function FileSearchView() {
  const { t } = useTranslation(['apps', 'common']);
  const { token, logout } = useAuth();
  const { workspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const controller = useFileSearchController({
    logout,
    messages: {
      authMissing: t('files.search.errors.authMissing'),
      downloadFailed: t('files.errors.downloadFailed'),
      loadFailed: t('files.search.errors.loadFailed'),
      queryRequired: t('files.search.errors.queryRequired'),
      sessionExpired: t('files.search.errors.sessionExpired'),
      workspaceMissing: t('files.search.errors.workspaceMissing'),
    },
    searchParams,
    setSearchParams,
    token,
    workspaceSlug,
  });
  return <FileSearchViewContent controller={controller} />;
}

export function FileSearchViewContent({
  controller,
}: {
  controller: FileSearchController;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const { actions, state } = controller;
  const {
    busyDownloadId,
    error,
    queryInput,
    response,
    searching,
    strategy,
  } = state;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    actions.submitSearch();
  };
  const statusText = searching
    ? t('files.search.searching')
    : response
      ? t('files.search.resultStatus', {
          count: response.hits.length,
          latency: response.latency_ms,
          page: response.page,
        })
      : t('files.search.ready');

  return (
    <div className="flex h-full min-h-0 flex-col bg-app-bg">
      <header className="border-b border-app-border bg-app-bg px-5 py-4">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
          <div>
            <div className="flex items-center gap-2 text-app-ink/60">
              <Search aria-hidden="true" size={16} />
              <span className="app-text-overline">
                {t('files.search.eyebrow')}
              </span>
            </div>
            <h1 className="app-text-title mt-1 text-app-ink">
              {t('files.search.title')}
            </h1>
            <p className="mt-1 app-text-body-sm text-app-ink/60">
              {t('files.search.description')}
            </p>
          </div>

          <form className="flex flex-col gap-3" onSubmit={submit}>
            <div className="flex flex-col gap-2 sm:flex-row">
              <label className="sr-only" htmlFor="files-search-query">
                {t('files.search.queryLabel')}
              </label>
              <div className="relative min-w-0 flex-1">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/40"
                  size={17}
                />
                <input
                  id="files-search-query"
                  className="h-10 w-full rounded-md border border-app-border bg-app-surface pl-10 pr-3 app-text-body text-app-ink outline-none transition-shadow placeholder:text-app-ink/35 focus:ring-2 focus:ring-app-accent/30"
                  maxLength={2000}
                  onChange={(event) =>
                    actions.setQueryInput(event.target.value)
                  }
                  placeholder={t('files.search.queryPlaceholder')}
                  type="search"
                  value={queryInput}
                />
              </div>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-app-accent px-4 app-text-control text-app-accent-fg transition-opacity disabled:opacity-60"
                disabled={searching}
                type="submit"
              >
                {searching ? (
                  <Loader2
                    aria-hidden="true"
                    className="animate-spin"
                    size={16}
                  />
                ) : (
                  <Search aria-hidden="true" size={16} />
                )}
                {t('files.search.actions.search')}
              </button>
            </div>

            <fieldset className="flex flex-wrap items-center gap-2">
              <legend className="sr-only">{t('files.search.strategy')}</legend>
              {FILE_SEARCH_STRATEGIES.map((option) => (
                <StrategyButton
                  active={strategy === option}
                  key={option}
                  label={strategyLabel(t, option)}
                  onClick={() => actions.setStrategy(option)}
                />
              ))}
            </fieldset>
          </form>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
          {error ? (
            <InlineNotice className="app-text-body-sm" role="alert" tone="danger">
              {error}
            </InlineNotice>
          ) : null}

          <p
            aria-live="polite"
            className="app-text-caption text-app-ink/55"
            role="status"
          >
            {statusText}
          </p>

          {searching && !response ? <SearchLoadingRows /> : null}

          {response && response.hits.length === 0 && !searching ? (
            <div className="flex min-h-48 items-center justify-center rounded-md border border-app-border bg-app-surface px-4 text-center app-text-body text-app-ink/55">
              {t('files.search.empty')}
            </div>
          ) : null}

          {response?.hits.length ? (
            <section
              aria-label={t('files.search.results')}
              className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface"
            >
              {response.hits.map((hit) => (
                <FileSearchResultRow
                  busy={busyDownloadId === hit.file_id}
                  hit={hit}
                  key={hit.file_id}
                  onDownload={() => actions.download(hit.file_id)}
                  t={t}
                />
              ))}
            </section>
          ) : null}

          {response ? (
            <nav
              aria-label={t('files.search.pagination.label')}
              className="flex items-center justify-between gap-3"
            >
              <button
                className="inline-flex h-9 items-center gap-1.5 rounded-md border border-app-border px-3 app-text-control-sm text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-45"
                disabled={searching || response.page <= 1}
                onClick={actions.previousPage}
                type="button"
              >
                <ChevronLeft aria-hidden="true" size={15} />
                {t('files.search.pagination.previous')}
              </button>
              <span className="app-text-caption tabular-nums text-app-ink/55">
                {t('files.search.pagination.page', { page: response.page })}
              </span>
              <button
                className="inline-flex h-9 items-center gap-1.5 rounded-md border border-app-border px-3 app-text-control-sm text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-45"
                disabled={searching || !response.has_more}
                onClick={actions.nextPage}
                type="button"
              >
                {t('files.search.pagination.next')}
                <ChevronRight aria-hidden="true" size={15} />
              </button>
            </nav>
          ) : null}
        </div>
      </main>
    </div>
  );
}

type TranslationFn = ReturnType<typeof useTranslation>['t'];

function formatFileSearchScore(score: number): string {
  if (!Number.isFinite(score)) {
    return '-';
  }
  const absoluteScore = Math.abs(score);
  if (absoluteScore === 0 || absoluteScore >= 0.001) {
    return score.toFixed(3);
  }
  return score.toPrecision(3);
}

function StrategyButton({
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
      aria-pressed={active}
      className={cn(
        'inline-flex h-8 items-center rounded-md border px-3 app-text-control-sm transition-colors',
        active
          ? 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
      )}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function FileSearchResultRow({
  busy,
  hit,
  onDownload,
  t,
}: {
  busy: boolean;
  hit: FileSearchHit;
  onDownload: () => void;
  t: TranslationFn;
}) {
  const segments = fileSearchSnippetSegments(hit.snippet);
  return (
    <article
      aria-label={hit.filename}
      className="flex flex-col gap-3 px-4 py-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 rounded-md bg-app-bg p-2 text-app-ink/50">
            <FileText aria-hidden="true" size={18} />
          </span>
          <div className="min-w-0">
            <h2 className="truncate app-text-title-sm text-app-ink">
              {hit.filename}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 app-text-caption text-app-ink/50">
              <span>{t('files.search.rank', { rank: hit.rank })}</span>
              <span>{hit.content_type}</span>
              <span>{formatFileSize(hit.size_bytes)}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-app-bg px-2 py-1 app-text-caption tabular-nums text-app-ink/60">
            {t('files.search.score', { score: formatFileSearchScore(hit.score) })}
          </span>
          <button
            aria-label={t('files.actions.download')}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border px-2.5 app-text-control-sm text-app-ink transition-colors hover:bg-app-surface-hover disabled:opacity-60"
            disabled={busy}
            onClick={onDownload}
            type="button"
          >
            {busy ? (
              <Loader2
                aria-hidden="true"
                className="animate-spin"
                size={14}
              />
            ) : (
              <Download aria-hidden="true" size={14} />
            )}
            {t('files.actions.download')}
          </button>
        </div>
      </div>

      {segments.length ? (
        <p className="app-text-body-sm leading-relaxed text-app-ink/70">
          {segments.map((segment, index) =>
            segment.highlighted ? (
              <mark
                className="rounded-sm bg-app-warning-bg px-0.5 text-app-ink"
                key={`${index}:${segment.text}`}
              >
                {segment.text}
              </mark>
            ) : (
              <span key={`${index}:${segment.text}`}>{segment.text}</span>
            ),
          )}
        </p>
      ) : null}

      {hit.methods.length ? (
        <div className="flex flex-wrap gap-1.5">
          {hit.methods.map((method) => (
            <span
              className="rounded-full border border-app-border bg-app-bg px-2 py-0.5 app-text-caption text-app-ink/55"
              key={method}
            >
              {methodLabel(t, method)}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function SearchLoadingRows() {
  return (
    <div aria-hidden="true" className="grid gap-2">
      {Array.from({ length: 5 }, (_, index) => (
        <div
          className="h-28 animate-pulse rounded-md border border-app-border bg-app-surface"
          key={index}
        />
      ))}
    </div>
  );
}

function strategyLabel(t: TranslationFn, strategy: FileSearchStrategy): string {
  return t(`files.search.strategies.${strategy}`);
}

function methodLabel(t: TranslationFn, method: string): string {
  const key =
    {
      bm25: 'bm25',
      company_rag: 'companyRag',
      cross_encoder: 'crossEncoder',
      dense_vector: 'denseVector',
      hybrid_merge: 'hybridMerge',
      rrf: 'rrf',
      semantic: 'semantic',
      vector: 'vector',
    }[method] ?? null;
  return key ? t(`files.search.methods.${key}`) : method;
}
