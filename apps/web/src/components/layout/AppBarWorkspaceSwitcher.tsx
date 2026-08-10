import type { RefObject } from 'react';
import { Plus, Search, Settings as SettingsIcon } from 'lucide-react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { AppBarWorkspaceRow } from './AppBarWorkspaceRow';
import { getInitials, type AppBarTranslator } from './app-bar-model';

export function AppBarWorkspaceSwitcher({
  canCreateWorkspace,
  canManageCurrentWorkspace,
  currentWorkspace,
  defaultWorkspaceOptions,
  defaultWorkspaceSaving,
  normalizedDefaultWorkspaceId,
  onCreateWorkspace,
  onDefaultWorkspaceChange,
  onManageCurrentWorkspace,
  onQueryChange,
  onSelectWorkspace,
  onToggle,
  otherWorkspaces,
  pinnedWorkspace,
  preferenceError,
  query,
  rootRef,
  t,
  workspaceSwitcherOpen,
}: {
  canCreateWorkspace: boolean;
  canManageCurrentWorkspace: boolean;
  currentWorkspace: AuthUser['workspaces'][number] | null;
  defaultWorkspaceOptions: AuthUser['workspaces'];
  defaultWorkspaceSaving: boolean;
  normalizedDefaultWorkspaceId: string | null;
  onCreateWorkspace: () => void;
  onDefaultWorkspaceChange: (workspaceId: string | null) => void;
  onManageCurrentWorkspace: () => void;
  onQueryChange: (query: string) => void;
  onSelectWorkspace: (workspaceSlug: string) => void;
  onToggle: () => void;
  otherWorkspaces: AuthUser['workspaces'];
  pinnedWorkspace: AuthUser['workspaces'][number] | null;
  preferenceError: string | null;
  query: string;
  rootRef: RefObject<HTMLDivElement | null>;
  t: AppBarTranslator;
  workspaceSwitcherOpen: boolean;
}) {
  return (
    <div ref={rootRef} className="relative mb-2">
      <button
        aria-expanded={workspaceSwitcherOpen}
        aria-haspopup="dialog"
        aria-label={t('shell:workspaceSwitcher.switch')}
        className="group flex size-11 flex-col items-center justify-center rounded-xl border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-surface-hover"
        onClick={onToggle}
        title={
          currentWorkspace
            ? t('shell:workspaceSwitcher.currentTitle', {
                name: currentWorkspace.name,
              })
            : t('shell:workspaceSwitcher.switch')
        }
        type="button"
      >
        <span className="app-text-body-sm font-semibold leading-none">
          {getInitials(currentWorkspace?.name ?? 'Workspace', 'WS')}
        </span>
        <span className="app-text-micro mt-1 text-app-ink/55">
          {workspaceSwitcherOpen ? '▲' : '▼'}
        </span>
      </button>

      {workspaceSwitcherOpen ? (
        <dialog
          aria-label={t('common:labels.workspaces')}
          className="fixed left-[4.75rem] top-3 m-0 w-80 rounded-2xl border border-app-border bg-app-surface p-3 text-app-ink shadow-2xl"
          open
        >
          <div className="px-1 pb-2">
            <div className="app-text-overline text-app-ink/55">
              {t('common:labels.workspaces')}
            </div>
          </div>

          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/45"
            />
            <input
              aria-label={t('shell:workspaceSwitcher.searchPlaceholder')}
              className="app-text-body-sm w-full rounded-xl border border-app-border bg-app-bg py-2 pl-9 pr-3 text-app-ink outline-none transition-colors focus:border-app-accent"
              onChange={(event) => onQueryChange(event.currentTarget.value)}
              placeholder={t('shell:workspaceSwitcher.searchPlaceholder')}
              type="text"
              value={query}
            />
          </div>

          <div className="mt-3 max-h-80 overflow-y-auto">
            {pinnedWorkspace ? (
              <AppBarWorkspaceRow
                defaultBadgeLabel={t('shell:workspaceSwitcher.defaultBadge')}
                isCurrent
                isDefault={pinnedWorkspace.id === normalizedDefaultWorkspaceId}
                onClick={() => onSelectWorkspace(pinnedWorkspace.slug)}
                workspace={pinnedWorkspace}
              />
            ) : null}

            {pinnedWorkspace && otherWorkspaces.length > 0 ? (
              <div className="my-2 border-t border-app-border" />
            ) : null}

            {otherWorkspaces.map((workspace) => (
              <AppBarWorkspaceRow
                defaultBadgeLabel={t('shell:workspaceSwitcher.defaultBadge')}
                isDefault={workspace.id === normalizedDefaultWorkspaceId}
                key={workspace.id}
                onClick={() => onSelectWorkspace(workspace.slug)}
                workspace={workspace}
              />
            ))}

            {!pinnedWorkspace && otherWorkspaces.length === 0 ? (
              <div className="rounded-xl border border-dashed border-app-border px-3 py-5 text-center">
                <div className="app-text-body-sm text-app-ink">
                  {t('shell:workspaceSwitcher.noResults')}
                </div>
                <div className="app-text-caption mt-1 text-app-ink/55">
                  {t('shell:workspaceSwitcher.noResultsHint')}
                </div>
              </div>
            ) : null}
          </div>

          {preferenceError ? (
            <div className="app-text-caption mt-2 rounded-xl border border-app-danger/30 bg-app-danger/10 px-3 py-2 text-app-danger">
              {preferenceError}
            </div>
          ) : null}

          {defaultWorkspaceOptions.length > 0 ? (
            <div className="mt-3 border-t border-app-border pt-3">
              <label
                className="app-text-caption block text-app-ink/55"
                htmlFor="appbar-default-workspace"
              >
                {t('shell:workspaceSwitcher.defaultSelectLabel')}
              </label>
              <select
                aria-label={t('shell:workspaceSwitcher.defaultSelectLabel')}
                className="app-field-input mt-1 disabled:cursor-wait"
                disabled={defaultWorkspaceSaving}
                id="appbar-default-workspace"
                onChange={(event) =>
                  onDefaultWorkspaceChange(event.currentTarget.value || null)
                }
                value={normalizedDefaultWorkspaceId ?? ''}
              >
                <option value="">
                  {t('shell:workspaceSwitcher.defaultNone')}
                </option>
                {defaultWorkspaceOptions.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {canCreateWorkspace || canManageCurrentWorkspace ? (
            <div className="mt-3 border-t border-app-border pt-2">
              {canCreateWorkspace ? (
                <button
                  className="app-text-body-sm flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                  onClick={onCreateWorkspace}
                  type="button"
                >
                  <Plus size={14} className="text-app-ink/55" />
                  <span>{t('shell:workspaceSwitcher.create')}</span>
                </button>
              ) : null}

              {canManageCurrentWorkspace && currentWorkspace ? (
                <button
                  className="app-text-body-sm flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                  onClick={onManageCurrentWorkspace}
                  type="button"
                >
                  <SettingsIcon size={14} className="text-app-ink/55" />
                  <span>{t('shell:workspaceSwitcher.manage')}</span>
                </button>
              ) : null}
            </div>
          ) : null}
        </dialog>
      ) : null}
    </div>
  );
}
