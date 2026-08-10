import type { AuthUser, WorkspaceSummary } from '@/src/platform/auth/auth-api';
import {
  hasWorkspaceAdminAccess,
  workspaceRoleAllows,
} from '@/src/platform/auth/auth-api';
import type { WorkspaceItem } from '@/src/platform/admin/admin-api';

export interface WorkspaceSettingsState {
  workspace: WorkspaceItem | null;
  loading: boolean;
  error: string | null;
  message: string | null;
}

export type WorkspaceSettingsAction =
  | { type: 'load-skipped' }
  | { type: 'load-started' }
  | { type: 'load-succeeded'; workspace: WorkspaceItem | null }
  | { type: 'load-failed'; error: string }
  | { type: 'workspace-changed'; workspace: WorkspaceItem }
  | { type: 'flash-success'; message: string }
  | { type: 'clear-message' }
  | { type: 'flash-error'; error: string };

export const INITIAL_WORKSPACE_SETTINGS_STATE: WorkspaceSettingsState = {
  workspace: null,
  loading: true,
  error: null,
  message: null,
};

export function workspaceSettingsReducer(
  state: WorkspaceSettingsState,
  action: WorkspaceSettingsAction,
): WorkspaceSettingsState {
  switch (action.type) {
    case 'load-skipped':
      return { ...state, loading: false };
    case 'load-started':
      return { ...state, loading: true, error: null };
    case 'load-succeeded':
      return { ...state, workspace: action.workspace, loading: false };
    case 'load-failed':
      return { ...state, loading: false, error: action.error };
    case 'workspace-changed':
      return { ...state, workspace: action.workspace };
    case 'flash-success':
      return { ...state, error: null, message: action.message };
    case 'clear-message':
      return { ...state, message: null };
    case 'flash-error':
      return { ...state, message: null, error: action.error };
  }
}

export function selectCurrentWorkspaceSummary(
  workspaces: WorkspaceSummary[] | null | undefined,
  workspaceSlug: string | null | undefined,
): WorkspaceSummary | null {
  return workspaces?.find((item) => item.slug === workspaceSlug) ?? null;
}

export function canManageWorkspaceSettings(
  user: Pick<AuthUser, 'workspaces' | 'system_roles'> | null | undefined,
  workspaceSlug: string | null | undefined,
  summary: Pick<WorkspaceSummary, 'role'> | null | undefined,
): boolean {
  return (
    hasWorkspaceAdminAccess(user, workspaceSlug) ||
    workspaceRoleAllows(summary?.role, 'admin')
  );
}

export function shouldLoadWorkspaceSettings(
  params: WorkspaceSettingsLoadParams,
): params is WorkspaceSettingsLoadParams & {
  token: string;
  workspaceSlug: string;
  canManageWorkspace: true;
} {
  const { token, workspaceSlug, canManageWorkspace } = params;
  return Boolean(token && workspaceSlug && canManageWorkspace);
}

export interface WorkspaceSettingsLoadParams {
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
  canManageWorkspace: boolean;
}

export function buildWorkspaceSettingsTitle({
  workspace,
  summary,
  workspaceSlug,
}: {
  workspace: Pick<WorkspaceItem, 'name'> | null | undefined;
  summary: Pick<WorkspaceSummary, 'name'> | null | undefined;
  workspaceSlug: string | null | undefined;
}): string {
  return workspace?.name ?? summary?.name ?? workspaceSlug ?? '';
}

export function buildWorkspaceDetailCapabilities({
  canBrowseDirectory,
}: {
  canBrowseDirectory: boolean;
}) {
  return {
    canEditProfile: true,
    canManageMembers: true,
    canArchive: false,
    canDelete: false,
    canBrowseDirectory,
  };
}
