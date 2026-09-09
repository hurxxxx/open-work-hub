import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

/**
 * App identities are supplied by registered app/feature manifests. Keeping
 * the shared shell type open prevents every new leaf app from also requiring
 * an edit to a central id union.
 */
export type AppModuleId = string;

export type ShellAppId = AppModuleId;

export interface NavItem {
  id: string;
  title: string;
  icon: LucideIcon;
  description?: string;
  category: string;
  /** SubSidebar filtering target: which AppBar app owns this nav item. */
  appId: AppModuleId;
  /** App target used when a sidebar item deep-links into another app. */
  linkAppId?: AppModuleId;
  /** Suffix appended after the app path, such as `?tab=recordings`. */
  pathSuffix?: string;
  /** Absolute path, mostly admin/settings pages. */
  absolutePath?: string;
  /** Legacy or planned tools render as ready-but-disabled sidebar entries. */
  comingSoon?: boolean;
}

export interface AppBarItem {
  id: AppModuleId;
  title: string;
  icon: LucideIcon;
}

export type ShellRouteChrome =
  | 'standard'
  | 'fullSurface'
  | 'containedSurface'
  | 'shared';
export type ShellRouteSubSidebar = 'auto' | 'hidden';

export interface StaticRouteDefinition {
  appId?: AppModuleId;
  chrome?: ShellRouteChrome;
  element: ReactNode;
  path: string;
  subSidebar?: ShellRouteSubSidebar;
}

export interface AppModuleContract {
  owner: string;
  permissions: string[];
  apiDomain: string | null;

  /** This app contributes content to, and enables, company search. */
  aiCapabilities: string[];
  writeAuditActions: string[];
  appLocalTests: string[];
}

export type LauncherGlobalPaths = ReadonlyMap<AppModuleId, `/${string}`>;

export const EMPTY_LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map();

export interface FeatureGuideModuleSurface {
  /** Tool ids with an app-owned static guide asset. */
  toolIds: readonly string[];
}

export interface AppModuleSurfaces {
  featureGuides?: FeatureGuideModuleSurface;
}

export interface AppModuleManifest {
  appBarItem: AppBarItem;
  contract: AppModuleContract;
  defaultActiveNavItemId: string;
  navItems: NavItem[];
  surfaces?: AppModuleSurfaces;
  /**
   * App routes owned by this app module and mounted through the app route registry.
   */
  appRoutePaths: string[];
  /**
   * App routes declared by this manifest but mounted by a shell/static route adapter.
   * Use this only for platform-owned settings routes.
   */
  staticAppRoutePaths?: string[];
  /**
   * Global routes owned by this app module and mounted through the app route registry.
   */
  globalRoutePaths?: string[];
  /**
   * Global routes declared by this manifest but mounted by a shell/static route adapter.
   */
  staticGlobalRoutePaths?: string[];
}

export interface AppShellNavResolverContext {
  appId: AppModuleId;
  manifest: AppModuleManifest;
  navItems: readonly NavItem[];
  path: string;
  pathname: string;
}

export type AppShellNavResolver = (
  context: AppShellNavResolverContext,
) => string | null | undefined;

export interface FeatureModuleSurfaces extends AppModuleSurfaces {
  /** Expose this app in registry-driven AI tool pickers. */
  aiToolEntry?: boolean;
}

export interface FeatureModuleManifest<TModuleId extends string = string> {
  moduleKind: 'feature';
  moduleId: TModuleId;
  contract: AppModuleContract;
  surfaces?: FeatureModuleSurfaces;
}
