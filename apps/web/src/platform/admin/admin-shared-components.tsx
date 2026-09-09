import { Search } from 'lucide-react';
import { useEffect, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, InlineNotice } from '@open-work-hub/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';

import { listAdminUsers } from './admin-api';
import {
  buildPeopleDirectoryPagination,
  buildPeopleDirectoryUserRow,
  INITIAL_PEOPLE_DIRECTORY_GRID_STATE,
  peopleDirectoryGridReducer,
} from './admin-directory-grid-model';
import {
  PEOPLE_PAGE_SIZE,
  type SelectedSubject,
  type SubjectSelectionState,
} from './admin-shared-model';

export function SurfaceCard({
  title,
  description,
  children,
  actions,
  className = '',
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`space-y-4 ${className}`.trim()}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="app-text-title-md text-app-ink">{title}</h2>
          {description ? (
            <p className="app-text-body mt-1 text-app-ink/55">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex items-center gap-2">{actions}</div>
        ) : null}
      </div>
      <div>{children}</div>
    </section>
  );
}

export function Badge({
  children,
  tone = 'default',
}: {
  children: React.ReactNode;
  tone?: 'default' | 'purple' | 'green' | 'amber';
}) {
  const toneClassName =
    tone === 'purple'
      ? 'border-app-accent/20 bg-app-accent/10 text-app-accent'
      : tone === 'green'
        ? 'border-app-success-border bg-app-success/10 text-app-success-text'
        : tone === 'amber'
          ? 'border-app-warning/20 bg-app-warning/10 text-app-warning-text dark:text-app-warning-text'
          : 'border-app-border bg-app-surface-sidebar text-app-ink/55';

  return (
    <span
      className={`app-text-label inline-flex items-center rounded-full border px-2.5 py-1 ${toneClassName}`.trim()}
    >
      {children}
    </span>
  );
}

export function HeadCell({
  children,
  className = '',
  dense = false,
}: {
  children: React.ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <th
      className={`app-text-overline border-b border-app-border text-left text-app-ink/55 ${
        dense ? 'px-2 py-1.5' : 'px-4 py-3'
      } ${className}`.trim()}
    >
      {children}
    </th>
  );
}

export function BodyCell({
  children,
  className = '',
  dense = false,
}: {
  children: React.ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <td
      className={`border-b border-app-border text-app-ink ${
        dense
          ? 'app-text-body-sm px-2 py-1.5 align-middle'
          : 'app-text-body px-4 py-3 align-top'
      } ${className}`.trim()}
    >
      {children}
    </td>
  );
}

export function EmptyRow({
  colSpan,
  title,
  description,
}: {
  colSpan: number;
  title: string;
  description: string;
}) {
  return (
    <tr>
      <td className="px-3 py-10 text-center" colSpan={colSpan}>
        <div className="space-y-1">
          <div className="app-text-body font-medium text-app-ink">{title}</div>
          <div className="app-text-body text-app-ink/55">{description}</div>
        </div>
      </td>
    </tr>
  );
}

export function EmptyPanel({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-4 py-10 text-center">
      <div className="space-y-1">
        <div className="app-text-body font-medium text-app-ink">{title}</div>
        <div className="app-text-body text-app-ink/55">{description}</div>
      </div>
    </div>
  );
}

export function SectionMessage({
  message,
  error,
}: {
  message: string | null;
  error: string | null;
}) {
  if (!message && !error) {
    return null;
  }

  return (
    <div className="space-y-3">
      {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
    </div>
  );
}

export function FilterChip({
  label,
  active,
  onClick,
  tone,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  tone?: 'warning';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`app-text-control rounded-full border px-3 py-1 transition-colors ${
        active
          ? tone === 'warning'
            ? 'border-amber-500 bg-app-warning/10 text-app-warning-text dark:text-app-warning-text'
            : 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/70 hover:bg-app-surface-sidebar'
      }`}
    >
      {label}
    </button>
  );
}

export function PeopleDirectoryGrid({
  token,
  selection,
  onToggleSelect,
  excludeIds,
  membershipLabel,
  className,
}: {
  token: string;
  selection: SubjectSelectionState;
  onToggleSelect: (subject: SelectedSubject) => void;
  excludeIds: Set<string>;
  membershipLabel?: string;
  className?: string;
}) {
  const { t, i18n: i18next } = useTranslation('apps');
  const { user } = useAuth();
  const locale = i18next.resolvedLanguage ?? i18next.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const resolvedMembershipLabel =
    membershipLabel ?? t('admin.shared.directory.alreadyMember');
  const [{ users, total, page, search, debouncedSearch, loading }, dispatch] =
    useReducer(peopleDirectoryGridReducer, INITIAL_PEOPLE_DIRECTORY_GRID_STATE);

  useEffect(() => {
    const handle = window.setTimeout(
      () => dispatch({ type: 'commitSearch', search: search.trim() }),
      200,
    );
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: 'loadStarted' });
    listAdminUsers(token, {
      page,
      page_size: PEOPLE_PAGE_SIZE,
      q: debouncedSearch || undefined,
    })
      .then((response) => {
        if (cancelled) return;
        dispatch({
          type: 'loadLoaded',
          users: response.items,
          total: response.total,
        });
      })
      .catch(() => {
        if (cancelled) return;
        dispatch({ type: 'loadFailed' });
      });
    return () => {
      cancelled = true;
    };
  }, [token, page, debouncedSearch]);

  const rows = users.map((user) =>
    buildPeopleDirectoryUserRow({
      user,
      selection,
      excludeIds,
      locale,
      timeZone,
    }),
  );
  const pagination = buildPeopleDirectoryPagination({
    page,
    total,
    pageSize: PEOPLE_PAGE_SIZE,
    loading,
  });

  return (
    <div className={`flex h-full flex-col ${className ?? ''}`}>
      <div className="flex items-center gap-2 border-b border-app-border px-3 py-2">
        <div className="flex flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
          <Search size={12} className="text-app-ink/50" />
          <input
            className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
            placeholder={t('admin.shared.directory.searchPlaceholder')}
            value={search}
            onChange={(event) =>
              dispatch({ type: 'setSearch', search: event.target.value })
            }
            aria-label={t('admin.shared.directory.searchPlaceholder')}
          />
        </div>
        <span className="app-text-caption text-app-ink/50">
          {t('admin.shared.directory.total', { total })}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="app-text-body-sm w-full">
          <thead className="sticky top-0 bg-app-bg">
            <tr className="border-b border-app-border">
              <th
                aria-label={t('common:actions.select')}
                className="w-8 px-2 py-1.5 text-left"
              />
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                {t('admin.shared.directory.user')}
              </th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                {t('admin.shared.directory.groups')}
              </th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                {t('admin.shared.directory.status')}
              </th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                {t('admin.shared.directory.recent')}
              </th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && !loading ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-2 py-8 text-center text-app-ink/60"
                >
                  {t('common:empty.noResults')}
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                return (
                  <tr
                    key={row.id}
                    className={`border-b border-app-border/50 ${
                      row.disabled
                        ? 'opacity-50'
                        : 'hover:bg-app-surface-hover/40'
                    }`}
                  >
                    <td className="px-2 py-1">
                      <input
                        type="checkbox"
                        aria-label={row.checkboxLabel}
                        checked={row.checked}
                        disabled={row.disabled}
                        onChange={() => onToggleSelect(row.subject)}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <div className="min-w-0">
                        <span className="font-medium text-app-ink">
                          {row.name}
                        </span>
                        <span className="ml-2 text-app-ink/50">
                          {row.email}
                        </span>
                      </div>
                    </td>
                    <td className="px-2 py-1">
                      <span>{row.user.group_ids.length}</span>
                    </td>
                    <td className="px-2 py-1">
                      {row.statusKind === 'excluded' ? (
                        <Badge tone="green">{resolvedMembershipLabel}</Badge>
                      ) : row.statusKind === 'invited' ? (
                        <Badge tone="amber">
                          {t('admin.shared.status.invitedShort')}
                        </Badge>
                      ) : row.statusKind === 'suspended' ? (
                        <Badge tone="amber">
                          {t('admin.shared.status.suspendedShort')}
                        </Badge>
                      ) : (
                        <span className="text-app-ink/60">
                          {t('admin.shared.status.activeShort')}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-app-ink/60">
                      {row.lastLoginLabel}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-app-border px-3 py-1.5">
        <span className="app-text-caption text-app-ink/60">
          {pagination.rangeText}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            disabled={pagination.previousDisabled}
            onClick={() =>
              dispatch({
                type: 'setPage',
                page: Math.max(1, page - 1),
              })
            }
          >
            {t('admin.shared.pagination.previous')}
          </Button>
          <span className="app-text-caption px-2 text-app-ink/60">
            {pagination.page} / {pagination.totalPages}
          </span>
          <Button
            variant="ghost"
            disabled={pagination.nextDisabled}
            onClick={() => dispatch({ type: 'setPage', page: page + 1 })}
          >
            {t('admin.shared.pagination.next')}
          </Button>
        </div>
      </div>
    </div>
  );
}
