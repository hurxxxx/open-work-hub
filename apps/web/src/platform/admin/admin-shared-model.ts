import type { AuthUser } from '@/src/platform/auth/auth-api';
import { i18n } from '@/src/platform/i18n';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

export const PEOPLE_PAGE_SIZE = 20;
export const ADMIN_PEOPLE_DEFAULT_PAGE_SIZE = 12;
export const ADMIN_PEOPLE_PAGE_SIZE_OPTIONS = [12, 20, 50, 100] as const;
export const PEOPLE_EXPORT_PAGE_SIZE = 100;

const APP_LABELS: Record<string, string> = {
  ai: 'AI',
  docs: 'Docs',
  whiteboard: 'Whiteboard',
  pms: 'PMS',
  planner: 'Planner',
  meeting: 'Meeting',
  admin: 'Admin',
};

class AdminAppLabelCatalog {
  constructor(private readonly labels: Record<string, string> = APP_LABELS) {}

  format(codes: string[]): string {
    const labels = Array.from(
      new Set(codes.map((code) => this.labels[code] ?? code)),
    );
    return labels.join(', ') || '-';
  }

  userCodes(user: Pick<AuthUser, 'system_roles'>): string[] {
    const codes = new Set<string>();
    if (user.system_roles.length > 0) {
      codes.add('admin');
    }
    return Array.from(codes);
  }
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

const defaultTranslate: Translate = (key, options) =>
  String(i18n.t(key, options));

const WORKSPACE_ROLE_OPTIONS: {
  value: string;
  labelKey: string;
  descriptionKey: string;
}[] = [
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

const WORKSPACE_ROLE_LABEL_KEYS: Record<string, string> =
  WORKSPACE_ROLE_OPTIONS.reduce(
    (acc, option) => {
      acc[option.value] = option.labelKey;
      return acc;
    },
    {} as Record<string, string>,
  );

class WorkspaceRoleCatalog {
  constructor(
    private readonly options = WORKSPACE_ROLE_OPTIONS,
    private readonly labelKeys = WORKSPACE_ROLE_LABEL_KEYS,
  ) {}

  optionsFor(
    t: Translate,
  ): { value: string; label: string; description: string }[] {
    return this.options.map((option) => ({
      value: option.value,
      label: t(option.labelKey),
      description: t(option.descriptionKey),
    }));
  }

  label(role: string, t: Translate): string {
    const key = this.labelKeys[role];
    return key ? t(key) : role;
  }
}

class SubjectSelection {
  constructor(private readonly selection: SubjectSelectionState) {}

  static empty(): SubjectSelectionState {
    return { users: new Map() };
  }

  size(): number {
    return this.selection.users.size;
  }

  toggle(subject: SelectedSubject): SubjectSelectionState {
    const next = new Map(this.selection.users);
    if (next.has(subject.id)) {
      next.delete(subject.id);
    } else {
      next.set(subject.id, subject);
    }
    return { users: next };
  }

  remove(kind: SubjectKind, id: string): SubjectSelectionState {
    if (kind !== 'user' || !this.selection.users.has(id)) return this.selection;
    const next = new Map(this.selection.users);
    next.delete(id);
    return { users: next };
  }
}

const appLabelCatalog = new AdminAppLabelCatalog();
const workspaceRoleCatalog = new WorkspaceRoleCatalog();

export const WORKSPACE_ROLE_RANK: Record<string, number> = {
  admin: 0,
  member: 1,
};

export const FORM_FIELD_CLASS =
  'app-text-body w-full rounded-lg border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none transition-colors focus:border-app-accent';

export type SubjectKind = 'user';

export interface SelectedSubject {
  id: string;
  kind: SubjectKind;
  label: string;
  secondary?: string;
}

export interface SubjectSelectionState {
  users: Map<string, SelectedSubject>;
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function getWorkspaceRoleOptions(
  t: Translate = defaultTranslate,
): { value: string; label: string; description: string }[] {
  return workspaceRoleCatalog.optionsFor(t);
}

export function getWorkspaceRoleLabel(
  role: string,
  t: Translate = defaultTranslate,
): string {
  return workspaceRoleCatalog.label(role, t);
}

export function formatDateLabel(
  value?: string | null,
  locale = i18n.resolvedLanguage || i18n.language,
  timeZone?: string | null,
): string {
  return formatDateTime(value, {
    fallback: '-',
    locale,
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    timeZone: normalizeTimeZone(timeZone),
  });
}

export function isAdminUser(user: Pick<AuthUser, 'system_roles'>): boolean {
  return user.system_roles.length > 0;
}

export function formatUserApps(user: Pick<AuthUser, 'system_roles'>): string {
  return appLabelCatalog.format(appLabelCatalog.userCodes(user));
}

export function formatUserWorkspaces(
  user: Pick<AuthUser, 'workspaces'>,
): string {
  return user.workspaces.map((workspace) => workspace.name).join(', ') || '-';
}

export function formatStatusLabel(
  status: string,
  t: Translate = defaultTranslate,
): string {
  if (status === 'active') return t('apps:admin.shared.status.active');
  if (status === 'invited') return t('apps:admin.shared.status.invited');
  if (status === 'suspended') return t('apps:admin.shared.status.suspended');
  return status || '-';
}

export function emptySubjectSelection(): SubjectSelectionState {
  return SubjectSelection.empty();
}

export function selectionSize(selection: SubjectSelectionState): number {
  return new SubjectSelection(selection).size();
}

export function toggleSubject(
  selection: SubjectSelectionState,
  subject: SelectedSubject,
): SubjectSelectionState {
  return new SubjectSelection(selection).toggle(subject);
}

export function removeSubject(
  selection: SubjectSelectionState,
  kind: SubjectKind,
  id: string,
): SubjectSelectionState {
  return new SubjectSelection(selection).remove(kind, id);
}
