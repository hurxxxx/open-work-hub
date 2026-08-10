import type { WorkspaceBindingItem, WorkspaceItem } from './admin-api';

export const DEFAULT_WORKSPACE_MEMBER_ROLE = 'member';

export type WorkspaceBindingReplacementPayload = {
  users: Array<{ subject_id: string; role: string }>;
};

export function activeWorkspaces(
  workspaces: readonly WorkspaceItem[],
): WorkspaceItem[] {
  return workspaces.filter((workspace) => workspace.active);
}

export function formatWorkspaceSelectionSummary(
  workspaces: readonly WorkspaceItem[],
  workspaceIds: readonly string[],
): string {
  const selectedIds = new Set(workspaceIds);
  const names: string[] = [];
  for (const workspace of workspaces) {
    if (selectedIds.has(workspace.id)) {
      names.push(workspace.name);
    }
  }
  return names.join(', ') || '-';
}

export function selectedWorkspaceMemberships(
  workspaces: readonly WorkspaceItem[],
  workspaceIds: readonly string[],
): WorkspaceItem[] {
  const selectedIds = new Set(workspaceIds);
  return workspaces.filter((workspace) => selectedIds.has(workspace.id));
}

export function workspaceMembershipAddCandidates(
  workspaces: readonly WorkspaceItem[],
  selectedWorkspaceIds: readonly string[],
  query: string,
): WorkspaceItem[] {
  const selectedIds = new Set(selectedWorkspaceIds);
  const normalizedQuery = query.trim().toLowerCase();
  return workspaces.filter((workspace) => {
    if (selectedIds.has(workspace.id)) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    return [workspace.name, workspace.key, workspace.description ?? ''].some(
      (value) => value.toLowerCase().includes(normalizedQuery),
    );
  });
}

export function addWorkspaceMembershipIds(
  currentWorkspaceIds: readonly string[],
  addedWorkspaceIds: readonly string[],
): string[] {
  return Array.from(new Set([...currentWorkspaceIds, ...addedWorkspaceIds]));
}

export function removeWorkspaceMembershipId(
  currentWorkspaceIds: readonly string[],
  workspaceId: string,
): string[] {
  return currentWorkspaceIds.filter((currentId) => currentId !== workspaceId);
}

export function directWorkspaceIdsForUser(
  bindingResults: readonly {
    workspace: WorkspaceItem;
    bindings: readonly WorkspaceBindingItem[];
  }[],
  userId: string,
): string[] {
  const directWorkspaceIds: string[] = [];
  for (const { workspace, bindings } of bindingResults) {
    const hasDirectBinding = bindings.some(
      (binding) =>
        binding.subject_type === 'user' && binding.subject_id === userId,
    );
    if (hasDirectBinding) {
      directWorkspaceIds.push(workspace.id);
    }
  }
  return directWorkspaceIds;
}

export function workspaceBindingReplacementPayloadForUser(
  bindings: readonly WorkspaceBindingItem[],
  userId: string,
  shouldIncludeUser: boolean,
): WorkspaceBindingReplacementPayload {
  let existingUserRole: string | null = null;
  const nextUsers: WorkspaceBindingReplacementPayload['users'] = [];
  for (const binding of bindings) {
    if (binding.subject_type !== 'user') {
      continue;
    }
    if (binding.subject_id === userId) {
      existingUserRole = binding.role;
      continue;
    }
    nextUsers.push({
      subject_id: binding.subject_id,
      role: binding.role,
    });
  }

  if (shouldIncludeUser) {
    nextUsers.push({
      subject_id: userId,
      role: existingUserRole ?? DEFAULT_WORKSPACE_MEMBER_ROLE,
    });
  }

  return { users: nextUsers };
}
