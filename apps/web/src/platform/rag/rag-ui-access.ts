import type { WorkspaceBootstrapNavItem } from '@/src/platform/workspaces/workspaces-api';

export {
  getEnabledWorkspaceAppIds,
  isWorkspaceAppEnabled,
} from '@/src/platform/workspaces/workspace-app-access';

export function isWorkspaceNavItemEnabled(
  nav: readonly Pick<WorkspaceBootstrapNavItem, 'id'>[] | null | undefined,
  itemId: string,
): boolean {
  return (nav ?? []).some((item) => item.id === itemId);
}
