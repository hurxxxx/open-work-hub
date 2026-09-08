import { SubSidebar } from '@/src/components/layout/SubSidebar';
import type { AdminSectionAccessResolver } from '@/src/platform/admin/admin-permissions';
import type {
  BootstrapApp,
  BootstrapNavItem,
} from '@/src/platform/apps/apps-api';
import type { ReactNode } from 'react';
import {
  EMPTY_LAUNCHER_GLOBAL_PATHS,
  type AppBarItem,
  type LauncherGlobalPaths,
  type NavItem,
} from './navigation-types';
import type { AppSidebarConfig } from './sidebar-types';

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
  enabledShellAppIds,
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
  apps,
  appNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  appBarItems?: readonly AppBarItem[];

  enabledShellAppIds?: readonly string[];
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
  apps: BootstrapApp[];
  appNavItems: BootstrapNavItem[];
}) {
  if (!isRegisteredAppModuleId({ getAppModuleManifest, value: activeAppId })) {
    return null;
  }

  return (
    <SubSidebar
      activeAppId={activeAppId}
      activeNavItemId={activeNavItemId}
      appBarItems={appBarItems}
      enabledShellAppIds={enabledShellAppIds}
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
      apps={apps}
      appNavItems={appNavItems}
    />
  );
}
