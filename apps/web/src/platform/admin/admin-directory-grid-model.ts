import type { AuthUser } from '@/src/platform/auth/auth-api';

import {
  formatDateLabel,
  type SelectedSubject,
  type SubjectSelectionState,
  WORKSPACE_ROLE_RANK,
} from './admin-shared-model';

export interface UserWorkspaceChip {
  id: string;
  name: string;
  role: string;
  elevated: boolean;
}

export interface UserWorkspaceChipModel {
  visible: UserWorkspaceChip[];
  hiddenCount: number;
  hiddenTitle: string;
}

export interface PeopleDirectoryGridState {
  users: AuthUser[];
  total: number;
  page: number;
  search: string;
  debouncedSearch: string;
  loading: boolean;
}

export type PeopleDirectoryGridAction =
  | { type: 'setSearch'; search: string }
  | { type: 'commitSearch'; search: string }
  | { type: 'setPage'; page: number }
  | { type: 'loadStarted' }
  | { type: 'loadLoaded'; users: AuthUser[]; total: number }
  | { type: 'loadFailed' };

export interface PeopleDirectoryPagination {
  page: number;
  total: number;
  pageSize: number;
  totalPages: number;
  rangeText: string;
  previousDisabled: boolean;
  nextDisabled: boolean;
}

export type PeopleDirectoryUserStatusKind =
  | 'active'
  | 'excluded'
  | 'invited'
  | 'suspended';

export interface PeopleDirectoryUserRow {
  user: AuthUser;
  id: string;
  name: string;
  email: string;
  orgName: string;
  checkboxLabel: string;
  checked: boolean;
  disabled: boolean;
  subject: SelectedSubject;
  statusKind: PeopleDirectoryUserStatusKind;
  workspaceChips: UserWorkspaceChipModel;
  lastLoginLabel: string;
}

export const INITIAL_PEOPLE_DIRECTORY_GRID_STATE: PeopleDirectoryGridState = {
  users: [],
  total: 0,
  page: 1,
  search: '',
  debouncedSearch: '',
  loading: false,
};

export function buildUserWorkspaceChipModel(
  workspaces: Pick<AuthUser, 'workspaces'>['workspaces'],
  locale: string,
): UserWorkspaceChipModel {
  const sorted = Array.from(workspaces).sort((a, b) => {
    const rankDiff =
      (WORKSPACE_ROLE_RANK[a.role] ?? 99) - (WORKSPACE_ROLE_RANK[b.role] ?? 99);
    if (rankDiff !== 0) return rankDiff;
    return a.name.localeCompare(b.name, locale);
  });
  const visible = sorted.slice(0, 3).map((workspace) => ({
    id: workspace.id,
    name: workspace.name,
    role: workspace.role,
    elevated: workspace.role === 'admin',
  }));
  const hidden = sorted.slice(3);
  return {
    visible,
    hiddenCount: hidden.length,
    hiddenTitle: hidden
      .map((workspace) => `${workspace.name} (${workspace.role})`)
      .join(', '),
  };
}

export function peopleDirectoryGridReducer(
  state: PeopleDirectoryGridState,
  action: PeopleDirectoryGridAction,
): PeopleDirectoryGridState {
  switch (action.type) {
    case 'setSearch':
      return { ...state, search: action.search };
    case 'commitSearch':
      return {
        ...state,
        debouncedSearch: action.search,
        page: 1,
      };
    case 'setPage':
      return { ...state, page: action.page };
    case 'loadStarted':
      return { ...state, loading: true };
    case 'loadLoaded':
      return {
        ...state,
        users: action.users,
        total: action.total,
        loading: false,
      };
    case 'loadFailed':
      return {
        ...state,
        users: [],
        total: 0,
        loading: false,
      };
    default:
      return state;
  }
}

export function buildPeopleDirectoryPagination({
  page,
  total,
  pageSize,
  loading,
}: {
  page: number;
  total: number;
  pageSize: number;
  loading: boolean;
}): PeopleDirectoryPagination {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return {
    page,
    total,
    pageSize,
    totalPages,
    rangeText:
      total === 0
        ? '0'
        : `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} / ${total}`,
    previousDisabled: page <= 1 || loading,
    nextDisabled: page >= totalPages || loading,
  };
}

export function buildPeopleDirectoryUserRow({
  user,
  selection,
  excludeIds,
  locale,
  timeZone,
}: {
  user: AuthUser;
  selection: SubjectSelectionState;
  excludeIds: ReadonlySet<string>;
  locale: string;
  timeZone?: string | null;
}): PeopleDirectoryUserRow {
  const name = user.display_name || user.full_name;
  const disabled = excludeIds.has(user.id);
  return {
    user,
    id: user.id,
    name,
    email: user.email,
    orgName: user.primary_org_unit?.name ?? '-',
    checkboxLabel: name,
    checked: selection.users.has(user.id),
    disabled,
    subject: {
      id: user.id,
      kind: 'user',
      label: name,
      secondary: user.email,
    },
    statusKind: disabled
      ? 'excluded'
      : user.status === 'invited'
        ? 'invited'
        : user.status === 'suspended'
          ? 'suspended'
          : 'active',
    workspaceChips: buildUserWorkspaceChipModel(user.workspaces, locale),
    lastLoginLabel: formatDateLabel(user.last_login_at, locale, timeZone),
  };
}
