import { SubSidebar } from '@/src/components/layout/SubSidebar';
import { getAppModuleManifest } from './app-registry';
import type { AppModuleId } from './navigation-types';
import type {
  WorkspaceBootstrapApp,
  WorkspaceBootstrapNavItem,
} from '@/src/platform/workspaces/workspaces-api';

function isAppModuleId(value: string): value is AppModuleId {
  return getAppModuleManifest(value as AppModuleId) !== null;
}

export function AppSubSidebar({
  activeAppId,
  activeNavItemId,
  currentWorkspaceSlug,
  onNavigate,
  variant,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  onNavigate?: () => void;
  variant?: 'desktop' | 'mobile';
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
      onNavigate={onNavigate}
      variant={variant}
      workspaceApps={workspaceApps}
      workspaceNavItems={workspaceNavItems}
    />
  );
}
