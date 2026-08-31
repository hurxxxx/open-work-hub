import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, ChevronDown, Loader2, Search } from 'lucide-react';
import { useFeedback } from '@open-work-hub/ui';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from './workspace-bootstrap-context';
import {
  setAppWorkspacePreference,
  type EligibleWorkspace,
} from './workspaces-api';
import { useEligibleWorkspaceSearch } from './useEligibleWorkspaceSearch';

export function WorkspaceContextSelector({
  appId,
  onNavigate,
  onPreferenceChanged,
  variant = 'sidebar',
  workspaceSlug,
}: {
  appId: string;
  onNavigate?: () => void;
  onPreferenceChanged?: () => void;
  variant?: 'compact' | 'sidebar';
  workspaceSlug: string;
}) {
  const { token } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const navigate = useNavigate();
  const feedback = useFeedback();
  const { t } = useTranslation('shell');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const generatedId = useId();
  const listboxId = `${generatedId}-workspace-listbox`;
  const bootstrapWorkspace = workspaceBootstrap.data?.workspace;
  const current: EligibleWorkspace | null =
    bootstrapWorkspace?.slug === workspaceSlug
      ? {
          id: bootstrapWorkspace.id,
          name: bootstrapWorkspace.name,
          slug: bootstrapWorkspace.slug,
        }
      : null;
  const currentLoading = workspaceBootstrap.loading && current === null;
  const workspaceSearch = useEligibleWorkspaceSearch({
    appId,
    resetKey: workspaceSlug,
    token,
  });
  const isSingleWorkspace =
    current !== null && workspaceSearch.unfilteredTotal === 1;

  const closeSelector = useCallback(
    (restoreFocus: boolean) => {
      setOpen(false);
      setActiveIndex(-1);
      workspaceSearch.setQuery('');
      if (restoreFocus) {
        window.requestAnimationFrame(() => triggerRef.current?.focus());
      }
    },
    [workspaceSearch.setQuery],
  );

  const openSelector = () => {
    if (currentLoading || saving || isSingleWorkspace) return;
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const firstSelectableIndex = workspaceSearch.items.findIndex(
      (workspace) => workspace.id !== current?.id,
    );
    setActiveIndex(firstSelectableIndex >= 0 ? firstSelectableIndex : 0);
  }, [current?.id, open, workspaceSearch.items]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() =>
      searchRef.current?.focus(),
    );
    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        closeSelector(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, [closeSelector, open]);

  const selectWorkspace = async (nextWorkspaceId: string) => {
    const next = workspaceSearch.items.find(
      (workspace) => workspace.id === nextWorkspaceId,
    );
    if (!token || !next || saving) return;
    if (next.slug === workspaceSlug) {
      closeSelector(true);
      return;
    }
    const contract = APP_CONTRACT_BY_ID.get(appId as AppId);
    if (!contract || contract.availability_scope !== 'workspace') {
      feedback.error(t('workspaceContext.switchFailedTitle'));
      return;
    }
    setSaving(true);
    try {
      await setAppWorkspacePreference(token, appId, next.id);
      closeSelector(false);
      onPreferenceChanged?.();
      feedback.info(
        t('workspaceContext.switchedTitle', { workspace: next.name }),
        t('workspaceContext.switchedDescription'),
      );
      onNavigate?.();
      navigate(
        buildAppHref({
          routeId: contract.entry_route_id,
          workspaceSlug: next.slug,
        }),
      );
    } catch (caught) {
      feedback.error(
        t('workspaceContext.switchFailedTitle'),
        caught instanceof Error ? caught.message : String(caught),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleComboboxKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const itemCount = workspaceSearch.items.length;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeSelector(true);
      return;
    }
    if (itemCount < 1) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      setActiveIndex((currentIndex) => {
        const base =
          currentIndex < 0 ? (delta > 0 ? -1 : itemCount) : currentIndex;
        return Math.min(itemCount - 1, Math.max(0, base + delta));
      });
      return;
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      setActiveIndex(event.key === 'Home' ? 0 : itemCount - 1);
      return;
    }
    if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      const activeWorkspace = workspaceSearch.items[activeIndex];
      if (activeWorkspace) void selectWorkspace(activeWorkspace.id);
    }
  };

  if (variant === 'compact' && isSingleWorkspace) {
    return null;
  }

  const selectorPanel = open ? (
    <div
      className={cn(
        'rounded-lg border border-app-border bg-app-bg p-2 shadow-xl',
        variant === 'compact'
          ? 'absolute left-0 top-full z-50 mt-2 w-[min(20rem,calc(100vw-2rem))]'
          : 'mt-2',
      )}
    >
      <label className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface px-2.5 py-2 focus-within:border-app-accent">
        <Search aria-hidden size={15} className="shrink-0 text-app-ink/45" />
        <input
          ref={searchRef}
          aria-activedescendant={
            activeIndex >= 0
              ? `${generatedId}-workspace-option-${activeIndex}`
              : undefined
          }
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-expanded="true"
          aria-label={t('workspaceContext.searchLabel')}
          className="app-text-caption min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
          onChange={(event) =>
            workspaceSearch.setQuery(event.currentTarget.value)
          }
          onKeyDown={handleComboboxKeyDown}
          placeholder={t('workspaceContext.searchPlaceholder')}
          role="combobox"
          type="search"
          value={workspaceSearch.query}
        />
      </label>
      <div
        aria-label={t('workspaceContext.label')}
        className="mt-2 max-h-52 space-y-1 overflow-y-auto"
        id={listboxId}
        role="listbox"
      >
        {workspaceSearch.items.map((workspace, index) => {
          const selected = workspace.id === current?.id;
          const active = index === activeIndex;
          return (
            <button
              aria-selected={selected}
              className={cn(
                'app-text-body-sm flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-app-ink outline-none transition hover:bg-app-surface-hover',
                active && 'bg-app-surface-hover',
              )}
              disabled={saving}
              id={`${generatedId}-workspace-option-${index}`}
              key={workspace.id}
              onClick={() => void selectWorkspace(workspace.id)}
              onMouseEnter={() => setActiveIndex(index)}
              role="option"
              tabIndex={-1}
              type="button"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">
                  {workspace.name}
                </span>
                <span className="app-text-micro block truncate text-app-ink/45">
                  {workspace.slug}
                </span>
              </span>
              {selected ? (
                <Check
                  aria-hidden
                  className="shrink-0 text-app-accent"
                  size={15}
                />
              ) : null}
            </button>
          );
        })}
        {workspaceSearch.loading && workspaceSearch.items.length === 0 ? (
          <p className="app-text-caption px-2.5 py-3 text-app-ink/50">
            {t('workspaceContext.loading')}
          </p>
        ) : null}
        {!workspaceSearch.loading && workspaceSearch.items.length === 0 ? (
          <p className="app-text-caption px-2.5 py-3 text-app-ink/50">
            {t('workspaceContext.noResults')}
          </p>
        ) : null}
      </div>
      {workspaceSearch.hasMore ? (
        <button
          className="app-text-caption mt-2 w-full rounded-md border border-app-border px-2.5 py-2 font-medium text-app-ink"
          disabled={workspaceSearch.loading}
          onClick={() => void workspaceSearch.loadMore()}
          type="button"
        >
          {workspaceSearch.loading
            ? t('workspaceContext.loading')
            : t('workspaceContext.loadMore')}
        </button>
      ) : null}
    </div>
  ) : null;

  return (
    <div
      ref={containerRef}
      className={cn(
        variant === 'sidebar'
          ? 'border-b border-app-border px-3 py-3'
          : 'relative inline-block',
      )}
    >
      {variant === 'sidebar' ? (
        <div className="app-text-overline text-app-ink/55">
          {t('workspaceContext.label')}
        </div>
      ) : null}
      {isSingleWorkspace && variant === 'sidebar' ? (
        <div
          aria-label={t('workspaceContext.label')}
          className="app-text-body-sm mt-1.5 rounded-lg border border-app-border bg-app-bg px-3 py-2 text-app-ink"
        >
          {current.name}
        </div>
      ) : (
        <div className={cn('relative', variant === 'sidebar' && 'mt-1.5')}>
          <button
            ref={triggerRef}
            aria-label={t('workspaceContext.label')}
            aria-expanded={open}
            aria-haspopup="listbox"
            className={cn(
              'outline-none focus:border-app-accent disabled:cursor-default',
              variant === 'sidebar'
                ? 'app-text-body-sm flex w-full items-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2 text-left text-app-ink'
                : 'app-text-caption inline-flex h-8 items-center gap-1 rounded-lg border border-app-border bg-app-surface px-2.5 font-medium text-app-ink transition hover:bg-app-surface-hover',
            )}
            disabled={currentLoading || saving}
            onClick={() => {
              if (open) {
                closeSelector(true);
              } else {
                openSelector();
              }
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                openSelector();
              }
            }}
            type="button"
          >
            {variant === 'sidebar' ? (
              <span className="min-w-0 flex-1 truncate">
                {current?.name ?? t('workspaceContext.currentUnavailable')}
              </span>
            ) : (
              <span>{t('workspaceContext.change')}</span>
            )}
            {!currentLoading && !saving ? (
              <ChevronDown
                aria-hidden
                size={16}
                className="shrink-0 text-app-ink/45"
              />
            ) : null}
          </button>
          {currentLoading || saving ? (
            <Loader2
              aria-hidden
              className={cn(
                'absolute animate-spin text-app-ink/45',
                variant === 'sidebar' ? 'right-2.5 top-2.5' : 'right-2 top-2',
              )}
              size={16}
            />
          ) : null}
          {selectorPanel}
        </div>
      )}
      {workspaceSearch.error ? (
        <div className="app-text-caption mt-1.5 flex items-center justify-between gap-2 text-app-danger-text">
          <p>{t('workspaceContext.loadFailed')}</p>
          <button
            className="shrink-0 rounded-md border border-app-danger/30 px-2 py-1 font-medium"
            disabled={workspaceSearch.loading}
            onClick={workspaceSearch.retry}
            type="button"
          >
            {t('workspaceContext.retry')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
