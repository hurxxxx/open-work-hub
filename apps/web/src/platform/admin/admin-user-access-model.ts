import type { AuthUser } from '@/src/platform/auth/auth-api';

import type { WorkspaceItem } from './admin-api';

export const DEFAULT_WORKSPACE_MEMBER_ROLE = 'member';

export function activeWorkspaces(
  workspaces: readonly WorkspaceItem[],
): WorkspaceItem[] {
  return workspaces.filter((workspace) => workspace.active);
}

export function workspaceMembershipIdsForUser(
  user: Pick<AuthUser, 'workspaces'>,
): string[] {
  return user.workspaces.map((workspace) => workspace.id);
}
