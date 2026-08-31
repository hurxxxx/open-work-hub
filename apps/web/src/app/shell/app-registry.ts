import type { ComponentType, ReactNode } from 'react';
import {
  createCoreAppModuleRegistry,
  createCoreAppModuleRegistryApi,
  type CoreAppModuleRegistration,
  type CoreAppModuleRegistry,
} from '@open-work-hub/core-web/app-registry';
import { APP_CONTRACTS } from '@open-work-hub/contracts/app-contracts';

import {
  DEFAULT_APP_MODULES,
  DEFAULT_FEATURE_MODULES,
  DEFAULT_SHELL_MODULES,
} from './app-module-manifests';
import { compileFeatureModuleRegistry } from './feature-module-registry';
import type { BackgroundWorkSource } from '@/src/platform/background-work/background-work-session';
import type {
  AppBarItem,
  AppModuleId,
  AppModuleManifest,
  AppShellNavResolver,
  LauncherGlobalPaths,
  NavItem,
  StaticRouteDefinition,
} from './navigation-types';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from './route-types';
import type { AppSidebarConfig } from './sidebar-types';

export type ShellProviderComponent = ComponentType<{ children: ReactNode }>;

export type AppModuleRegistration = CoreAppModuleRegistration<
  AppModuleId,
  NavItem,
  AppModuleManifest,
  StaticRouteDefinition,
  WorkspaceRouteDefinition,
  ToolViewRouteDefinition,
  BackgroundWorkSource,
  AppSidebarConfig,
  AppShellNavResolver,
  ShellProviderComponent
>;

export type AppModuleRegistry = CoreAppModuleRegistry<
  AppModuleId,
  NavItem,
  AppModuleManifest,
  AppBarItem,
  StaticRouteDefinition,
  WorkspaceRouteDefinition,
  ToolViewRouteDefinition,
  BackgroundWorkSource,
  AppSidebarConfig,
  AppShellNavResolver,
  ShellProviderComponent
>;

type AppModuleRegistryInput = AppModuleManifest | AppModuleRegistration;

export function createAppModuleRegistry(
  manifests: readonly AppModuleManifest[],
): AppModuleRegistry;
export function createAppModuleRegistry(
  registrations: readonly AppModuleRegistration[],
): AppModuleRegistry;
export function createAppModuleRegistry(
  inputs: readonly AppModuleRegistryInput[],
): AppModuleRegistry {
  return createCoreAppModuleRegistry<
    AppModuleId,
    NavItem,
    AppModuleManifest,
    AppBarItem,
    StaticRouteDefinition,
    WorkspaceRouteDefinition,
    ToolViewRouteDefinition,
    BackgroundWorkSource,
    AppSidebarConfig,
    AppShellNavResolver,
    ShellProviderComponent
  >(inputs);
}

export function createAppModuleRegistryApi(
  inputs: readonly AppModuleRegistryInput[],
) {
  return createCoreAppModuleRegistryApi<
    AppModuleId,
    NavItem,
    AppModuleManifest,
    AppBarItem,
    StaticRouteDefinition,
    WorkspaceRouteDefinition,
    ToolViewRouteDefinition,
    BackgroundWorkSource,
    AppSidebarConfig,
    AppShellNavResolver,
    ShellProviderComponent
  >(inputs);
}

const APP_MODULE_REGISTRY_API = createAppModuleRegistryApi(DEFAULT_APP_MODULES);
const SHELL_MODULE_REGISTRY_API = createAppModuleRegistryApi(
  DEFAULT_SHELL_MODULES,
);
const FEATURE_MODULE_REGISTRY = compileFeatureModuleRegistry(
  DEFAULT_FEATURE_MODULES,
  {
    reservedBackgroundWorkSourceIds:
      APP_MODULE_REGISTRY_API.APP_BACKGROUND_WORK_SOURCES.map(
        (source) => source.id,
      ),
    reservedModuleIds: APP_MODULE_REGISTRY_API.APP_MODULE_MANIFESTS.map(
      (manifest) => manifest.appBarItem.id,
    ).concat(
      SHELL_MODULE_REGISTRY_API.APP_MODULE_MANIFESTS.map(
        (manifest) => manifest.appBarItem.id,
      ),
    ),
  },
);

export const APP_MODULE_MANIFESTS: readonly AppModuleManifest[] =
  APP_MODULE_REGISTRY_API.APP_MODULE_MANIFESTS;
export const SHELL_MODULE_MANIFESTS: readonly AppModuleManifest[] =
  SHELL_MODULE_REGISTRY_API.APP_MODULE_MANIFESTS;
export const APP_BAR_ITEMS: readonly AppBarItem[] = [
  ...APP_MODULE_REGISTRY_API.APP_BAR_ITEMS,
  ...SHELL_MODULE_REGISTRY_API.APP_BAR_ITEMS,
];
export const APP_BACKGROUND_WORK_SOURCES: readonly BackgroundWorkSource[] = [
  ...APP_MODULE_REGISTRY_API.APP_BACKGROUND_WORK_SOURCES,
  ...FEATURE_MODULE_REGISTRY.backgroundWorkSources,
];
export const APP_SHELL_PROVIDERS: readonly ShellProviderComponent[] =
  APP_MODULE_REGISTRY_API.APP_SHELL_PROVIDERS;
export const NAV_ITEMS: readonly NavItem[] = [
  ...APP_MODULE_REGISTRY_API.NAV_ITEMS,
  ...SHELL_MODULE_REGISTRY_API.NAV_ITEMS,
];
export const APP_WORKSPACE_ROUTES: readonly WorkspaceRouteDefinition[] =
  APP_MODULE_REGISTRY_API.APP_WORKSPACE_ROUTES;
export const APP_GLOBAL_ROUTES: readonly StaticRouteDefinition[] =
  APP_MODULE_REGISTRY_API.APP_GLOBAL_ROUTES;
export const APP_TOOL_VIEW_ROUTES: readonly ToolViewRouteDefinition[] =
  APP_MODULE_REGISTRY_API.APP_TOOL_VIEW_ROUTES;
export const WORKSPACE_AI_TOOL_APP_IDS: readonly string[] =
  FEATURE_MODULE_REGISTRY.aiToolAppIds;

function deriveFeatureGuideToolIds(): ReadonlySet<string> {
  const registeredToolIds = new Set<string>(NAV_ITEMS.map((item) => item.id));
  const declaredToolIds = [
    ...APP_MODULE_MANIFESTS.flatMap(
      (manifest) => manifest.surfaces?.featureGuides?.toolIds ?? [],
    ),
    ...FEATURE_MODULE_REGISTRY.featureGuideToolIds,
  ];
  const featureGuideToolIds = new Set<string>();

  for (const toolId of declaredToolIds) {
    if (featureGuideToolIds.has(toolId)) {
      throw new Error(`Duplicate feature guide tool id: ${toolId}`);
    }
    if (!registeredToolIds.has(toolId)) {
      throw new Error(`Feature guide tool id is not registered: ${toolId}`);
    }
    featureGuideToolIds.add(toolId);
  }

  return featureGuideToolIds;
}

export const APP_FEATURE_GUIDE_TOOL_IDS = deriveFeatureGuideToolIds();

export const APP_LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map(
  APP_CONTRACTS.filter((app) => app.availability_scope === 'platform').map(
    (app) => [app.app_id, app.route_base] as const,
  ),
);
export const APP_BAR_FIXED_APP_IDS: readonly AppModuleId[] =
  APP_CONTRACTS.filter((app) => app.launcher.placement === 'fixed').map(
    (app) => app.app_id,
  );
export const APP_BAR_PINNED_BY_DEFAULT_APP_IDS: readonly AppModuleId[] =
  APP_CONTRACTS.filter((app) => app.launcher.pinned_by_default).map(
    (app) => app.app_id,
  );

export const getAppModuleManifest = (appId: AppModuleId) =>
  APP_MODULE_REGISTRY_API.getAppModuleManifest(appId) ??
  SHELL_MODULE_REGISTRY_API.getAppModuleManifest(appId);
export const getNavItem = (navItemId: string) =>
  APP_MODULE_REGISTRY_API.getNavItem(navItemId) ??
  SHELL_MODULE_REGISTRY_API.getNavItem(navItemId);
export const getAppModuleSidebarConfig = (appId: AppModuleId) =>
  APP_MODULE_REGISTRY_API.getAppModuleSidebarConfig(appId) ??
  SHELL_MODULE_REGISTRY_API.getAppModuleSidebarConfig(appId);
export const getAppShellNavResolver = (appId: AppModuleId) =>
  APP_MODULE_REGISTRY_API.getAppShellNavResolver(appId) ??
  SHELL_MODULE_REGISTRY_API.getAppShellNavResolver(appId);
export const assertAppModuleStaticRouteContract = (
  appId: AppModuleId,
  routes: Parameters<
    typeof APP_MODULE_REGISTRY_API.assertAppModuleStaticRouteContract
  >[1],
) => {
  const registry = APP_MODULE_REGISTRY_API.getAppModuleManifest(appId)
    ? APP_MODULE_REGISTRY_API
    : SHELL_MODULE_REGISTRY_API;
  return registry.assertAppModuleStaticRouteContract(appId, routes);
};
export const getToolViewRoute = APP_MODULE_REGISTRY_API.getToolViewRoute;
export const getAppModuleWorkspaceRoutes = (appId: AppModuleId) =>
  APP_MODULE_REGISTRY_API.getAppModuleWorkspaceRoutes(appId).length > 0
    ? APP_MODULE_REGISTRY_API.getAppModuleWorkspaceRoutes(appId)
    : SHELL_MODULE_REGISTRY_API.getAppModuleWorkspaceRoutes(appId);
export const getAppModuleGlobalRoutes = (appId: AppModuleId) =>
  APP_MODULE_REGISTRY_API.getAppModuleGlobalRoutes(appId).length > 0
    ? APP_MODULE_REGISTRY_API.getAppModuleGlobalRoutes(appId)
    : SHELL_MODULE_REGISTRY_API.getAppModuleGlobalRoutes(appId);
