import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useMemo } from 'react';
import { Loader2, Search, X } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { type KeywordSearchEntityType } from '@/src/platform/search/search-api';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  getWorkspaceBySlug,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  SearchEntityFilterButton,
  SearchResultPreview,
  SearchResultRow,
  SortButton,
} from './RagSearchViewParts';
import {
  buildSearchEntityLabelMap,
  buildWorkspaceSearchSubtitle,
  resolveSearchEntityLabel,
  type SearchEntityOption,
} from './RagSearchViewPresentation';
import { useRagSearchController } from './useRagSearchController';

export function RagSearchView() {
  return useRagSearchViewElement();
}

function useRagSearchViewElement() {
  const { t } = useTranslation('apps');
  const { token, user, logout } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlWorkspaceSlug = searchParams.get('workspace')?.trim() || null;
  const workspaceSlug =
    getWorkspaceBySlug(user, urlWorkspaceSlug)?.slug ??
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const workspaceId =
    workspaceBootstrap.data?.workspace.id ??
    getWorkspaceBySlug(user, workspaceSlug)?.id ??
    null;
  const workspaceName =
    workspaceBootstrap.data?.workspace.name ??
    getWorkspaceBySlug(user, workspaceSlug)?.name ??
    workspaceSlug ??
    '';
  const timeZone = normalizeTimeZone(user?.time_zone);
  const keywordSearchEntityTypes = useMemo(
    () => workspaceBootstrap.data?.keyword_search?.entity_types ?? [],
    [workspaceBootstrap.data?.keyword_search?.entity_types],
  );
  const availableEntityTypes = useMemo(
    () => keywordSearchEntityTypes.map((entityType) => entityType.value),
    [keywordSearchEntityTypes],
  );
  const {
    actions,
    state: {
      error,
      queryInput,
      response,
      searching,
      selectedEntityTypes,
      selectedHit,
      selectedHitKey,
      sortField,
    },
  } = useRagSearchController({
    availableEntityTypes,
    logout,
    messages: {
      authMissing: t('ai.search.authMissing'),
      loadFailed: t('ai.search.loadFailed'),
      sessionExpired: t('ai.search.sessionExpired'),
      workspaceMissing: t('ai.search.workspaceMissing'),
    },
    searchParams,
    setSearchParams,
    token,
    workspaceId,
    workspaceSlug,
  });
  const entityOptions = useMemo(() => {
    const options: SearchEntityOption[] = [
      { id: null, label: t('ai.search.entityAll') },
    ];
    const seen = new Set<KeywordSearchEntityType>();
    for (const descriptor of keywordSearchEntityTypes) {
      if (seen.has(descriptor.value)) {
        continue;
      }
      seen.add(descriptor.value);
      options.push({
        id: descriptor.value,
        label: resolveSearchEntityLabel(descriptor, t),
      });
    }
    return options;
  }, [keywordSearchEntityTypes, t]);
  const entityTypeLabels = useMemo(
    () => buildSearchEntityLabelMap(entityOptions),
    [entityOptions],
  );
  const subtitle = buildWorkspaceSearchSubtitle({
    entityTypeLabels,
    fallback: t('ai.search.subtitleFallback'),
    workspaceName,
  });

  if (!token) {
    return (
      <div className="p-8 text-app-ink/60">{t('ai.search.authMissing')}</div>
    );
  }
  if (!workspaceSlug) {
    return (
      <div className="p-8 text-app-ink/60">
        {t('ai.search.workspaceMissing')}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="sticky top-0 z-10 border-b border-app-border bg-app-surface/95 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="app-text-title-lg text-app-ink">
                {t('ai.search.title')}
              </h1>
              <p className="app-text-caption mt-1 truncate text-app-ink/55">
                {subtitle}
              </p>
            </div>
            <div className="hidden items-center gap-1 rounded-md border border-app-border bg-app-bg p-1 sm:flex">
              <SortButton
                active={sortField === 'relevance'}
                label={t('ai.search.sortRelevance')}
                onClick={() => actions.changeSort('relevance')}
              />
              <SortButton
                active={sortField === 'updated_at'}
                label={t('ai.search.sortLatest')}
                onClick={() => actions.changeSort('updated_at')}
              />
            </div>
          </div>

          <form
            className="flex items-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2 focus-within:border-app-accent"
            onSubmit={(event) => {
              event.preventDefault();
              actions.submitSearch();
            }}
          >
            <Search size={17} className="text-app-ink/35" />
            <input
              aria-label={t('ai.search.title')}
              className="app-text-body min-h-9 flex-1 bg-transparent text-app-ink outline-none"
              onChange={(event) => actions.setQueryInput(event.target.value)}
              placeholder={t('ai.search.placeholder')}
              value={queryInput}
            />
            {queryInput ? (
              <button
                aria-label={t('ai.search.clearQuery')}
                className="rounded-md p-1 text-app-ink/45 hover:bg-app-surface-hover"
                onClick={() => actions.setQueryInput('')}
                type="button"
              >
                <X size={15} />
              </button>
            ) : null}
            <button
              className="inline-flex min-h-8 items-center gap-2 rounded-md bg-app-accent px-3 text-[0.84rem] font-semibold text-app-accent-fg disabled:opacity-60"
              disabled={searching}
              type="submit"
            >
              {searching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : null}
              {t('ai.search.search')}
            </button>
          </form>

          <div className="flex flex-wrap items-center gap-2">
            {entityOptions.map((option) => {
              const active =
                option.id === null
                  ? selectedEntityTypes.length === 0
                  : selectedEntityTypes.includes(option.id);
              const count =
                option.id === null
                  ? response?.total
                  : response?.facets.entity_types.find(
                      (facet) => facet.value === option.id,
                    )?.count;
              return (
                <SearchEntityFilterButton
                  key={option.id === null ? 'all' : `entity:${option.id}`}
                  active={active}
                  count={count}
                  entityType={option.id}
                  label={option.label}
                  onClick={() => actions.toggleEntityType(option.id)}
                />
              );
            })}
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col overflow-y-auto px-6 py-5">
        {error ? (
          <div className="mb-4 rounded-md border border-app-danger-border bg-app-danger-bg px-4 py-3 text-[0.9rem] text-app-danger-text">
            {error}
          </div>
        ) : null}

        <div className="mb-3 flex items-center justify-between">
          <p
            className="app-text-caption text-app-ink/55"
            role="status"
            aria-live="polite"
          >
            {response
              ? t('ai.search.resultStatus', {
                  total: response.total,
                  shownPart:
                    response.total > 0
                      ? t('ai.search.resultStatusShown', {
                          shown: response.hits.length,
                        })
                      : '',
                })
              : t('ai.search.ready')}
          </p>
          <div className="flex items-center gap-1 rounded-md border border-app-border bg-app-bg p-1 sm:hidden">
            <SortButton
              active={sortField === 'relevance'}
              label={t('ai.search.sortRelevance')}
              onClick={() => actions.changeSort('relevance')}
            />
            <SortButton
              active={sortField === 'updated_at'}
              label={t('ai.search.sortLatest')}
              onClick={() => actions.changeSort('updated_at')}
            />
          </div>
        </div>

        {searching && !response ? (
          <div className="grid gap-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="h-20 animate-pulse rounded-md border border-app-border bg-app-surface"
              />
            ))}
          </div>
        ) : null}

        {response && response.hits.length === 0 && !searching ? (
          <div className="flex h-56 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/55">
            {t('ai.search.empty')}
          </div>
        ) : null}

        {response && response.hits.length > 0 ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface">
              {response.hits.map((hit) => {
                const isSelected =
                  `${hit.entity_type}:${hit.entity_id}` === selectedHitKey;
                return (
                  <div key={`${hit.entity_type}:${hit.entity_id}`}>
                    <SearchResultRow
                      entityTypeLabels={entityTypeLabels}
                      hit={hit}
                      isSelected={isSelected}
                      onSelect={actions.selectHit}
                      timeZone={timeZone}
                    />
                    {isSelected ? (
                      <div className="border-t border-app-border bg-app-bg/60 p-4 lg:hidden">
                        <SearchResultPreview
                          entityTypeLabels={entityTypeLabels}
                          hit={hit}
                          timeZone={timeZone}
                          variant="inline"
                        />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
            <aside
              aria-label={t('ai.search.previewPane')}
              className="hidden lg:block"
            >
              <div className="sticky top-5">
                {selectedHit ? (
                  <SearchResultPreview
                    entityTypeLabels={entityTypeLabels}
                    hit={selectedHit}
                    timeZone={timeZone}
                    variant="side"
                  />
                ) : (
                  <div className="rounded-md border border-app-border bg-app-surface px-4 py-6 text-[0.86rem] text-app-ink/55">
                    {t('ai.search.noSelectedResult')}
                  </div>
                )}
              </div>
            </aside>
          </div>
        ) : null}

        {response?.has_more ? (
          <button
            className="mx-auto mt-5 min-h-9 rounded-md border border-app-border bg-app-surface px-4 text-[0.86rem] font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-60"
            disabled={searching}
            onClick={actions.loadMore}
            type="button"
          >
            {t('ai.search.more')}
          </button>
        ) : null}
      </main>
    </div>
  );
}
