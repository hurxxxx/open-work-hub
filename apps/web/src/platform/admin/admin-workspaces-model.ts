import type { WorkspaceItem } from './admin-api';

export type WorkspaceFilter = 'active' | 'archived' | 'all';

export function selectWorkspaceIdAfterLoad({
  currentWorkspaceId,
  preserveWorkspaceId,
  workspaces,
}: {
  currentWorkspaceId?: string | null;
  preserveWorkspaceId?: string | null;
  workspaces: readonly WorkspaceItem[];
}): string | null {
  if (
    preserveWorkspaceId &&
    workspaces.some((item) => item.id === preserveWorkspaceId)
  ) {
    return preserveWorkspaceId;
  }
  if (
    currentWorkspaceId &&
    workspaces.some((item) => item.id === currentWorkspaceId)
  ) {
    return currentWorkspaceId;
  }
  const fallback =
    workspaces.find((item) => item.active) ?? workspaces[0] ?? null;
  return fallback?.id ?? null;
}

export function filterAdminWorkspaces({
  filter,
  locale,
  searchQuery,
  workspaces,
}: {
  filter: WorkspaceFilter;
  locale: string;
  searchQuery: string;
  workspaces: readonly WorkspaceItem[];
}): WorkspaceItem[] {
  const trimmed = searchQuery.trim().toLowerCase();
  const matchingWorkspaces: WorkspaceItem[] = [];
  for (const workspace of workspaces) {
    const matchesFilter =
      filter === 'active'
        ? workspace.active
        : filter === 'archived'
          ? !workspace.active
          : true;
    if (!matchesFilter) {
      continue;
    }
    const matchesSearch =
      !trimmed ||
      workspace.name.toLowerCase().includes(trimmed) ||
      workspace.key.toLowerCase().includes(trimmed) ||
      workspace.description.toLowerCase().includes(trimmed);
    if (matchesSearch) {
      matchingWorkspaces.push(workspace);
    }
  }
  matchingWorkspaces.sort((left, right) => {
    if (left.active !== right.active) {
      return left.active ? -1 : 1;
    }
    return left.name.localeCompare(right.name, locale);
  });
  return matchingWorkspaces;
}

export function replaceAdminWorkspace(
  workspaces: readonly WorkspaceItem[],
  next: WorkspaceItem,
): WorkspaceItem[] {
  return workspaces.map((item) => (item.id === next.id ? next : item));
}
