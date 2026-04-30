import { SubSidebar } from '@/src/components/layout/SubSidebar';
import { getAppModuleManifest } from './app-registry';
import type { AppModuleId } from './navigation-types';
import type {
  WorkspaceBootstrapApp,
  WorkspaceBootstrapNavItem,
} from '@/src/domains/workspaces/workspaces-api';

function isAppModuleId(value: string): value is AppModuleId {
  return getAppModuleManifest(value as AppModuleId) !== null;
}

export function AppSubSidebar({
  activeAppId,
  activeNavItemId,
  currentWorkspaceSlug,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) {
  if (!isAppModuleId(activeAppId)) {
    return null;
  }

  return (
    <SubSidebar
      activeAppId={activeAppId}
      activeNavItemId={activeNavItemId}
      currentWorkspaceSlug={currentWorkspaceSlug}
      workspaceApps={workspaceApps}
      workspaceNavItems={workspaceNavItems}
    />
  );
}
