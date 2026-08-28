import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Loader2, Search } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  setAppWorkspacePreference,
  type EligibleWorkspace,
} from '@/src/platform/workspaces/workspaces-api';
import { useEligibleWorkspaceSearch } from './useEligibleWorkspaceSearch';

export function WorkspaceContextSelector({
  appId,
  onNavigate,
  onPreferenceChanged,
  workspaceSlug,
}: {
  appId: string;
  onNavigate?: () => void;
  onPreferenceChanged?: () => void;
  workspaceSlug: string;
}) {
  const { token } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const navigate = useNavigate();
  const { t } = useTranslation('shell');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
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

  const closeSelector = () => {
    setOpen(false);
    workspaceSearch.setQuery('');
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  };

  const selectWorkspace = async (nextWorkspaceId: string) => {
    const next = workspaceSearch.items.find(
      (workspace) => workspace.id === nextWorkspaceId,
    );
    if (!token || !next || next.slug === workspaceSlug || saving) return;
    setSaving(true);
    setSelectionError(null);
    try {
      await setAppWorkspacePreference(token, appId, next.id);
      setOpen(false);
      onPreferenceChanged?.();
      onNavigate?.();
      navigate(buildWorkspaceAppPath(next.slug, appId));
    } catch (caught) {
      setSelectionError(
        caught instanceof Error ? caught.message : String(caught),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="border-b border-app-border px-3 py-3"
      onKeyDown={(event) => {
        if (open && event.key === 'Escape') {
          event.preventDefault();
          event.stopPropagation();
          closeSelector();
        }
      }}
    >
      <label className="app-text-overline block text-app-ink/55">
        {t('workspaceContext.label')}
      </label>
      <div className="relative mt-1.5">
        <button
          ref={triggerRef}
          aria-label={t('workspaceContext.label')}
          aria-expanded={open}
          aria-haspopup="listbox"
          className="app-text-body-sm flex w-full items-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2 text-left text-app-ink outline-none focus:border-app-accent disabled:cursor-default"
          disabled={
            currentLoading ||
            saving ||
            (current !== null && workspaceSearch.unfilteredTotal === 1)
          }
          onClick={() => {
            if (open) {
              closeSelector();
            } else {
              setOpen(true);
            }
          }}
          type="button"
        >
          <span className="min-w-0 flex-1 truncate">
            {current?.name ?? t('workspaceContext.currentUnavailable')}
          </span>
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
            className="absolute right-2.5 top-2.5 animate-spin text-app-ink/45"
            size={16}
          />
        ) : null}
      </div>
      {open ? (
        <div className="mt-2 rounded-lg border border-app-border bg-app-bg p-2">
          <label className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface px-2.5 py-2 focus-within:border-app-accent">
            <Search
              aria-hidden
              size={15}
              className="shrink-0 text-app-ink/45"
            />
            <input
              aria-label={t('workspaceContext.searchLabel')}
              className="app-text-caption min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
              onChange={(event) =>
                workspaceSearch.setQuery(event.currentTarget.value)
              }
              placeholder={t('workspaceContext.searchPlaceholder')}
              type="search"
              value={workspaceSearch.query}
            />
          </label>
          <div
            className="mt-2 max-h-52 space-y-1 overflow-y-auto"
            role="listbox"
          >
            {workspaceSearch.items.map((workspace) => (
              <button
                aria-selected={workspace.id === current?.id}
                className="app-text-body-sm w-full rounded-md px-2.5 py-2 text-left text-app-ink transition hover:bg-app-surface-hover disabled:opacity-50"
                disabled={saving || workspace.id === current?.id}
                key={workspace.id}
                onClick={() => void selectWorkspace(workspace.id)}
                role="option"
                type="button"
              >
                <span className="block truncate font-medium">
                  {workspace.name}
                </span>
                <span className="app-text-micro block truncate text-app-ink/45">
                  {workspace.slug}
                </span>
              </button>
            ))}
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
      ) : null}
      {selectionError ? (
        <p className="app-text-caption mt-1.5 text-app-danger">
          {selectionError}
        </p>
      ) : null}
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
