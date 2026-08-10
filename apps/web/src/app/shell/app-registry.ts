import type { ComponentType, ReactNode } from 'react';
import {
  createCoreAppModuleRegistry,
  createCoreAppModuleRegistryApi,
  type CoreAppModuleRegistration,
  type CoreAppModuleRegistry,
} from '@open-work-hub/core-web/app-registry';

import {
  DEFAULT_APP_MODULES,
  DEFAULT_FEATURE_MODULES,
  DEFAULT_PLATFORM_MODULE_MANIFESTS,
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
const FEATURE_MODULE_REGISTRY = compileFeatureModuleRegistry(
  DEFAULT_FEATURE_MODULES,
  {
    reservedBackgroundWorkSourceIds:
      APP_MODULE_REGISTRY_API.APP_BACKGROUND_WORK_SOURCES.map(
        (source) => source.id,
      ),
    reservedModuleIds: APP_MODULE_REGISTRY_API.APP_MODULE_MANIFESTS.map(
      (manifest) => manifest.appBarItem.id,
    ),
  },
);

export const APP_MODULE_MANIFESTS: readonly AppModuleManifest[] =
  APP_MODULE_REGISTRY_API.APP_MODULE_MANIFESTS;
export const APP_BAR_ITEMS: readonly AppBarItem[] =
  APP_MODULE_REGISTRY_API.APP_BAR_ITEMS;
export const APP_BACKGROUND_WORK_SOURCES: readonly BackgroundWorkSource[] = [
  ...APP_MODULE_REGISTRY_API.APP_BACKGROUND_WORK_SOURCES,
  ...FEATURE_MODULE_REGISTRY.backgroundWorkSources,
];
export const APP_SHELL_PROVIDERS: readonly ShellProviderComponent[] =
  APP_MODULE_REGISTRY_API.APP_SHELL_PROVIDERS;
export const NAV_ITEMS: readonly NavItem[] = APP_MODULE_REGISTRY_API.NAV_ITEMS;
export const APP_WORKSPACE_ROUTES: readonly WorkspaceRouteDefinition[] =
  APP_MODULE_REGISTRY_API.APP_WORKSPACE_ROUTES;
export const APP_GLOBAL_ROUTES: readonly StaticRouteDefinition[] =
  APP_MODULE_REGISTRY_API.APP_GLOBAL_ROUTES;
export const APP_TOOL_VIEW_ROUTES: readonly ToolViewRouteDefinition[] =
  APP_MODULE_REGISTRY_API.APP_TOOL_VIEW_ROUTES;
export const WORKSPACE_AI_TOOL_APP_IDS: readonly string[] =
  FEATURE_MODULE_REGISTRY.aiToolAppIds;

function deriveFeatureGuideToolIds(): ReadonlySet<string> {
  const registeredToolIds = new Set<string>([
    ...NAV_ITEMS.map((item) => item.id),
    ...APP_TOOL_VIEW_ROUTES.flatMap((route) => route.toolIds ?? []),
  ]);
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

const platformManifestAppId = (
  manifest: (typeof DEFAULT_PLATFORM_MODULE_MANIFESTS)[number],
): AppModuleId =>
  ('appBarItem' in manifest
    ? manifest.appBarItem.id
    : manifest.moduleId) as AppModuleId;
export const APP_LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map(
  DEFAULT_PLATFORM_MODULE_MANIFESTS.flatMap((manifest) => {
    const globalPath = manifest.surfaces?.launcher?.globalPath;
    return globalPath
      ? ([[platformManifestAppId(manifest), globalPath]] as const)
      : [];
  }),
);
const fixedLauncherManifests = DEFAULT_PLATFORM_MODULE_MANIFESTS.filter(
  (manifest) => manifest.surfaces?.launcher?.fixed,
);
const defaultPinnedLauncherManifests = [...DEFAULT_PLATFORM_MODULE_MANIFESTS]
  .filter(
    (manifest) => manifest.surfaces?.launcher?.defaultPinOrder !== undefined,
  )
  .sort(
    (left, right) =>
      (left.surfaces?.launcher?.defaultPinOrder ?? 0) -
      (right.surfaces?.launcher?.defaultPinOrder ?? 0),
  );
const conflictingLauncherManifest = defaultPinnedLauncherManifests.find(
  (manifest) => manifest.surfaces?.launcher?.fixed,
);
if (conflictingLauncherManifest) {
  throw new Error(
    `Fixed launcher app cannot be pinned by default: ${platformManifestAppId(conflictingLauncherManifest)}`,
  );
}
export const APP_BAR_FIXED_APP_IDS: readonly AppModuleId[] =
  fixedLauncherManifests.map(platformManifestAppId);
export const APP_BAR_PINNED_BY_DEFAULT_APP_IDS: readonly AppModuleId[] =
  defaultPinnedLauncherManifests.map(platformManifestAppId);

export const getAppModuleManifest =
  APP_MODULE_REGISTRY_API.getAppModuleManifest;
export const getNavItem = APP_MODULE_REGISTRY_API.getNavItem;
export const getAppModuleSidebarConfig =
  APP_MODULE_REGISTRY_API.getAppModuleSidebarConfig;
export const getAppShellNavResolver =
  APP_MODULE_REGISTRY_API.getAppShellNavResolver;
export const assertAppModuleStaticRouteContract =
  APP_MODULE_REGISTRY_API.assertAppModuleStaticRouteContract;
export const getToolViewRoute = APP_MODULE_REGISTRY_API.getToolViewRoute;
export const getAppModuleWorkspaceRoutes =
  APP_MODULE_REGISTRY_API.getAppModuleWorkspaceRoutes;
export const getAppModuleGlobalRoutes =
  APP_MODULE_REGISTRY_API.getAppModuleGlobalRoutes;
