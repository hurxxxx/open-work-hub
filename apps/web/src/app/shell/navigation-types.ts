import type { LucideIcon } from 'lucide-react';

export type AppModuleId =
  | 'home'
  | 'ai'
  | 'pms'
  | 'docs'
  | 'whiteboard'
  | 'planner'
  | 'meeting'
  | 'recording'
  | 'learning'
  | 'settings';

export type WorkspaceShellAppId = Exclude<AppModuleId, 'settings'>;

export interface NavItem {
  id: string;
  title: string;
  icon: LucideIcon;
  description?: string;
  category: string;
  /** SubSidebar filtering target: which AppBar app owns this nav item. */
  appId: AppModuleId;
  /**
   * Workspace app target used when a sidebar item deep-links into another app.
   * Example: meeting-minutes appears under AI but opens the meeting app.
   */
  linkAppId?: Exclude<AppModuleId, 'home' | 'settings'>;
  /** Suffix appended after the workspace app path, such as `?tab=recordings`. */
  pathSuffix?: string;
  /** Non-workspace-aware absolute path, mostly admin/settings pages. */
  absolutePath?: string;
  /** Legacy or planned tools render as ready-but-disabled sidebar entries. */
  comingSoon?: boolean;
}

export interface AppBarItem {
  id: AppModuleId;
  title: string;
  icon: LucideIcon;
}

export interface AppModuleManifest {
  appBarItem: AppBarItem;
  defaultActiveNavItemId: string;
  navItems: NavItem[];
  workspaceRoutePaths: string[];
  globalRoutePaths?: string[];
}
