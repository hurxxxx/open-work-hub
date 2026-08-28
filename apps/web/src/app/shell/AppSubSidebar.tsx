import { SubSidebar } from '@/src/components/layout/SubSidebar';
import {
  EMPTY_LAUNCHER_GLOBAL_PATHS,
  type AppBarItem,
  type LauncherGlobalPaths,
  type NavItem,
} from './navigation-types';
import type { AppSidebarConfig } from './sidebar-types';
import type {
  WorkspaceBootstrapApp,
  WorkspaceBootstrapNavItem,
} from '@/src/platform/workspaces/workspaces-api';
import type { AdminSectionAccessResolver } from '@/src/platform/admin/admin-permissions';
import type { ReactNode } from 'react';

const getNoopAppModuleManifest = () => null;

function isRegisteredAppModuleId({
  getAppModuleManifest,
  value,
}: {
  getAppModuleManifest: (appId: string) => unknown | null;
  value: string;
}): boolean {
  return getAppModuleManifest(value) !== null;
}

export function AppSubSidebar({
  activeAppId,
  activeNavItemId,
  appBarItems,
  currentWorkspaceSlug,
  enabledWorkspaceAppIds,
  getAppModuleManifest = getNoopAppModuleManifest,
  getAppSidebarConfig,
  headerSlot,
  hasAdminSectionAccess,
  launcherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
  navItems,
  onNavigate,
  onPinnedChange,
  overlay,
  pinned,
  variant,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  appBarItems?: readonly AppBarItem[];
  currentWorkspaceSlug: string | null;
  enabledWorkspaceAppIds?: readonly string[];
  getAppModuleManifest?: (appId: string) => unknown | null;
  getAppSidebarConfig?: (appId: string) => AppSidebarConfig | null;
  headerSlot?: ReactNode;
  hasAdminSectionAccess?: AdminSectionAccessResolver;
  launcherGlobalPaths?: LauncherGlobalPaths;
  navItems?: readonly NavItem[];
  onNavigate?: () => void;
  onPinnedChange?: (pinned: boolean) => void;
  overlay?: boolean;
  pinned?: boolean;
  variant?: 'desktop' | 'mobile';
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) {
  if (!isRegisteredAppModuleId({ getAppModuleManifest, value: activeAppId })) {
    return null;
  }

  return (
    <SubSidebar
      activeAppId={activeAppId}
      activeNavItemId={activeNavItemId}
      appBarItems={appBarItems}
      currentWorkspaceSlug={currentWorkspaceSlug}
      enabledWorkspaceAppIds={enabledWorkspaceAppIds}
      getAppSidebarConfig={getAppSidebarConfig}
      headerSlot={headerSlot}
      hasAdminSectionAccess={hasAdminSectionAccess}
      launcherGlobalPaths={launcherGlobalPaths}
      navItems={navItems}
      onNavigate={onNavigate}
      onPinnedChange={onPinnedChange}
      overlay={overlay}
      pinned={pinned}
      variant={variant}
      workspaceApps={workspaceApps}
      workspaceNavItems={workspaceNavItems}
    />
  );
}
