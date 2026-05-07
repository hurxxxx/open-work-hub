import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bot,
  CalendarDays,
  FileText,
  ListTodo,
  PencilRuler,
  Search,
  Shield,
  Video,
  type LucideIcon,
} from 'lucide-react';

import { Button, InlineNotice } from '@ai-do/ui';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { i18n } from '@/src/platform/i18n';
import { formatDateTime } from '@/src/platform/time/time-utils';

import { listAdminUsers } from './admin-api';

export const PEOPLE_PAGE_SIZE = 20;
export const PEOPLE_EXPORT_PAGE_SIZE = 100;

export const APP_LABELS: Record<string, string> = {
  ai: 'AI',
  docs: 'Docs',
  whiteboard: 'Whiteboard',
  pms: 'PMS',
  planner: 'Planner',
  meeting: 'Meeting',
  admin: 'Admin',
};

export const WORKSPACE_ENABLED_APP_LABELS = {
  ai: APP_LABELS.ai,
  docs: APP_LABELS.docs,
  whiteboard: APP_LABELS.whiteboard,
  pms: APP_LABELS.pms,
  planner: APP_LABELS.planner,
  meeting: APP_LABELS.meeting,
} satisfies Record<string, string>;

export const APP_ORDER: string[] = ['ai', 'docs', 'whiteboard', 'pms', 'planner', 'meeting'];

type Translate = (key: string, options?: Record<string, unknown>) => string;

const defaultTranslate: Translate = (key, options) => String(i18n.t(key, options));

export const APP_DESCRIPTION_KEYS: Record<string, string> = {
  ai: 'apps:admin.shared.appDescriptions.ai',
  docs: 'apps:admin.shared.appDescriptions.docs',
  whiteboard: 'apps:admin.shared.appDescriptions.whiteboard',
  pms: 'apps:admin.shared.appDescriptions.pms',
  planner: 'apps:admin.shared.appDescriptions.planner',
  meeting: 'apps:admin.shared.appDescriptions.meeting',
};

export const APP_ICONS: Record<string, LucideIcon> = {
  ai: Bot,
  docs: FileText,
  whiteboard: PencilRuler,
  pms: ListTodo,
  planner: CalendarDays,
  meeting: Video,
};

export const WORKSPACE_ROLE_OPTIONS: { value: string; labelKey: string; descriptionKey: string }[] = [
  {
    value: 'admin',
    labelKey: 'apps:admin.shared.roles.admin.label',
    descriptionKey: 'apps:admin.shared.roles.admin.description',
  },
  {
    value: 'member',
    labelKey: 'apps:admin.shared.roles.member.label',
    descriptionKey: 'apps:admin.shared.roles.member.description',
  },
];

export const WORKSPACE_ROLE_LABEL_KEYS: Record<string, string> = WORKSPACE_ROLE_OPTIONS.reduce(
  (acc, option) => {
    acc[option.value] = option.labelKey;
    return acc;
  },
  {} as Record<string, string>,
);

export const WORKSPACE_ROLE_RANK: Record<string, number> = {
  admin: 0,
  member: 1,
};

export const FORM_FIELD_CLASS =
  'app-text-body w-full rounded-lg border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none transition-colors focus:border-app-accent';

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function getAppDescription(code: string, t: Translate = defaultTranslate): string {
  const key = APP_DESCRIPTION_KEYS[code];
  return key ? t(key) : code;
}

export function getWorkspaceRoleOptions(t: Translate = defaultTranslate): { value: string; label: string; description: string }[] {
  return WORKSPACE_ROLE_OPTIONS.map((option) => ({
    value: option.value,
    label: t(option.labelKey),
    description: t(option.descriptionKey),
  }));
}

export function getWorkspaceRoleLabel(role: string, t: Translate = defaultTranslate): string {
  const key = WORKSPACE_ROLE_LABEL_KEYS[role];
  return key ? t(key) : role;
}

export function formatDateLabel(value?: string | null, locale = i18n.resolvedLanguage || i18n.language): string {
  return formatDateTime(value, {
    fallback: '-',
    locale,
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
  });
}

export function isAdminUser(user: Pick<AuthUser, 'system_roles'>): boolean {
  return user.system_roles.length > 0;
}

export function formatAppCodes(codes: string[]): string {
  const labels = Array.from(new Set(codes.map((code) => APP_LABELS[code] ?? code)));
  return labels.join(', ') || '-';
}

export function collectUserAppCodes(
  user: Pick<AuthUser, 'system_roles'>,
): string[] {
  const codes = new Set<string>();
  if (user.system_roles.length > 0) {
    codes.add('admin');
  }
  return Array.from(codes);
}

export function formatUserApps(
  user: Pick<AuthUser, 'system_roles'>,
): string {
  return formatAppCodes(collectUserAppCodes(user));
}

export function formatUserWorkspaces(user: Pick<AuthUser, 'workspaces'>): string {
  return user.workspaces.map((workspace) => workspace.name).join(', ') || '-';
}

export function formatUserGroups(user: Pick<AuthUser, 'group_slugs'>): string {
  return user.group_slugs.join(', ') || '-';
}

export function formatStatusLabel(status: string, t: Translate = defaultTranslate): string {
  if (status === 'active') return t('apps:admin.shared.status.active');
  if (status === 'invited') return t('apps:admin.shared.status.invited');
  if (status === 'suspended') return t('apps:admin.shared.status.suspended');
  return status || '-';
}

const WORKSPACE_ROLE_RANK_DISPLAY: Record<string, number> = {
  admin: 0,
  member: 1,
};

export function UserWorkspaceChips({ user }: { user: Pick<AuthUser, 'workspaces'> }) {
  const { t, i18n: i18next } = useTranslation('apps');
  const locale = i18next.resolvedLanguage ?? i18next.language;
  if (user.workspaces.length === 0) {
    return <span className="text-app-ink/40">-</span>;
  }
  const sorted = [...user.workspaces].sort((a, b) => {
    const rankDiff =
      (WORKSPACE_ROLE_RANK_DISPLAY[a.role] ?? 99) - (WORKSPACE_ROLE_RANK_DISPLAY[b.role] ?? 99);
    if (rankDiff !== 0) return rankDiff;
    return a.name.localeCompare(b.name, locale);
  });
  const visible = sorted.slice(0, 3);
  const hiddenCount = sorted.length - visible.length;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {visible.map((workspace) => {
        const isElevated = workspace.role === 'admin';
        return (
          <span
            key={workspace.id}
            className={`app-text-caption inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${
              isElevated
                ? 'border-app-accent/30 bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-surface-sidebar text-app-ink/70'
            }`}
            title={`${workspace.name} · ${getWorkspaceRoleLabel(workspace.role, t)}`}
          >
            <span>{workspace.name}</span>
            {isElevated ? <span className="opacity-70">🛡</span> : null}
          </span>
        );
      })}
      {hiddenCount > 0 ? (
        <span
          className="app-text-caption text-app-ink/50"
          title={sorted
            .slice(3)
            .map((workspace) => `${workspace.name} (${workspace.role})`)
            .join(', ')}
        >
          +{hiddenCount}
        </span>
      ) : null}
    </div>
  );
}

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
          {description ? <p className="app-text-body mt-1 text-gray-500">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
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
        ? 'border-green-500/20 bg-green-500/10 text-green-600 dark:text-green-400'
        : tone === 'amber'
          ? 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-300'
          : 'border-app-border bg-app-surface-sidebar text-gray-500';

  return (
    <span className={`app-text-label inline-flex items-center rounded-full border px-2.5 py-1 ${toneClassName}`.trim()}>
      {children}
    </span>
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
            ? 'border-amber-500 bg-amber-500/10 text-amber-600 dark:text-amber-300'
            : 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/70 hover:bg-app-surface-sidebar'
      }`}
    >
      {label}
    </button>
  );
}

export function MemberRoleBadge({ role }: { role: string }) {
  const { t } = useTranslation('apps');
  if (role === 'admin') {
    return (
      <span className="app-text-caption inline-flex items-center gap-1 text-app-ink/70">
        <Shield className="text-app-ink/50" size={12} />
        {getWorkspaceRoleLabel(role, t)}
      </span>
    );
  }
  return (
    <span className="app-text-caption text-app-ink/70">
      {getWorkspaceRoleLabel(role, t)}
    </span>
  );
}

// Subject selection contract — shared across inline picker, modal, and future
// org-chart picker. Stores user/group ids that have been ticked but not yet
// committed.
export type SubjectKind = 'user' | 'group';

export interface SelectedSubject {
  id: string;
  kind: SubjectKind;
  label: string;
  secondary?: string;
}

export interface SubjectSelectionState {
  users: Map<string, SelectedSubject>;
  groups: Map<string, SelectedSubject>;
}

export function emptySubjectSelection(): SubjectSelectionState {
  return { users: new Map(), groups: new Map() };
}

export function selectionSize(selection: SubjectSelectionState): number {
  return selection.users.size + selection.groups.size;
}

export function toggleSubject(
  selection: SubjectSelectionState,
  subject: SelectedSubject,
): SubjectSelectionState {
  const target = subject.kind === 'user' ? selection.users : selection.groups;
  const next = new Map(target);
  if (next.has(subject.id)) {
    next.delete(subject.id);
  } else {
    next.set(subject.id, subject);
  }
  return subject.kind === 'user'
    ? { ...selection, users: next }
    : { ...selection, groups: next };
}

export function removeSubject(
  selection: SubjectSelectionState,
  kind: SubjectKind,
  id: string,
): SubjectSelectionState {
  const target = kind === 'user' ? selection.users : selection.groups;
  if (!target.has(id)) return selection;
  const next = new Map(target);
  next.delete(id);
  return kind === 'user'
    ? { ...selection, users: next }
    : { ...selection, groups: next };
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
  const locale = i18next.resolvedLanguage ?? i18next.language;
  const resolvedMembershipLabel = membershipLabel ?? t('admin.shared.directory.alreadyMember');
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(search.trim()), 200);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const response = await listAdminUsers(token, {
          page,
          page_size: PEOPLE_PAGE_SIZE,
          q: debouncedSearch || undefined,
        });
        if (!cancelled) {
          setUsers(response.items);
          setTotal(response.total);
        }
      } catch {
        if (!cancelled) {
          setUsers([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, page, debouncedSearch]);

  const totalPages = Math.max(1, Math.ceil(total / PEOPLE_PAGE_SIZE));

  return (
    <div className={`flex h-full flex-col ${className ?? ''}`}>
      <div className="flex items-center gap-2 border-b border-app-border px-3 py-2">
        <div className="flex flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
          <Search size={12} className="text-app-ink/50" />
          <input
            className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
            placeholder={t('admin.shared.directory.searchPlaceholder')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            autoFocus
          />
        </div>
        <span className="app-text-caption text-app-ink/50">{t('admin.shared.directory.total', { total })}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="app-text-body-sm w-full">
          <thead className="sticky top-0 bg-app-bg">
            <tr className="border-b border-app-border">
              <th className="w-8 px-2 py-1.5 text-left"></th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.user')}</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.org')}</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.group')}</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.workspace')}</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.status')}</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.recent')}</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && !loading ? (
              <tr>
                <td colSpan={7} className="px-2 py-8 text-center text-app-ink/60">
                  {t('common:empty.noResults')}
                </td>
              </tr>
            ) : (
              users.map((user) => {
                const isExcluded = excludeIds.has(user.id);
                const isChecked = selection.users.has(user.id);
                return (
                  <tr
                    key={user.id}
                    className={`border-b border-app-border/50 ${
                      isExcluded ? 'opacity-50' : 'hover:bg-app-surface-hover/40'
                    }`}
                  >
                    <td className="px-2 py-1">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={isExcluded}
                        onChange={() =>
                          onToggleSelect({
                            id: user.id,
                            kind: 'user',
                            label: user.display_name || user.full_name,
                            secondary: user.email,
                          })
                        }
                      />
                    </td>
                    <td className="px-2 py-1">
                      <div className="min-w-0">
                        <span className="font-medium text-app-ink">
                          {user.display_name || user.full_name}
                        </span>
                        <span className="ml-2 text-app-ink/50">{user.email}</span>
                      </div>
                    </td>
                    <td className="max-w-[140px] truncate px-2 py-1 text-app-ink/60">
                      {user.primary_org_unit?.name ?? '-'}
                    </td>
                    <td className="max-w-[140px] truncate px-2 py-1 text-app-ink/60">
                      {formatUserGroups(user)}
                    </td>
                    <td className="px-2 py-1">
                      <UserWorkspaceChips user={user} />
                    </td>
                    <td className="px-2 py-1">
                      {isExcluded ? (
                        <Badge tone="green">{resolvedMembershipLabel}</Badge>
                      ) : user.status === 'invited' ? (
                        <Badge tone="amber">{t('admin.shared.status.invitedShort')}</Badge>
                      ) : user.status === 'suspended' ? (
                        <Badge tone="amber">{t('admin.shared.status.suspendedShort')}</Badge>
                      ) : (
                        <span className="text-app-ink/60">{t('admin.shared.status.activeShort')}</span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-app-ink/60">
                      {formatDateLabel(user.last_login_at, locale)}
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
          {total === 0
            ? '0'
            : `${(page - 1) * PEOPLE_PAGE_SIZE + 1}-${Math.min(page * PEOPLE_PAGE_SIZE, total)} / ${total}`}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t('admin.shared.pagination.previous')}
          </Button>
          <span className="app-text-caption px-2 text-app-ink/60">
            {page} / {totalPages}
          </span>
          <Button
            variant="ghost"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('admin.shared.pagination.next')}
          </Button>
        </div>
      </div>
    </div>
  );
}
