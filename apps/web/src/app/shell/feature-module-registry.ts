import type { ReactNode } from 'react';

import type { BackgroundWorkSource } from '@/src/platform/background-work/background-work-session';
import type {
  FeatureModuleManifest,
  NavItem,
  ShellRouteSubSidebar,
} from './navigation-types';

export type FeatureBackgroundWorkSource = Omit<BackgroundWorkSource, 'appId'>;

export interface FeatureModuleContext<TModuleId extends string = string> {
  appId: TModuleId;
}

export type FeatureBackgroundWorkSourceFactory<
  TModuleId extends string = string,
> = (context: FeatureModuleContext<TModuleId>) => FeatureBackgroundWorkSource;

export type FeatureShellNavRegistration = Omit<NavItem, 'appId' | 'linkAppId'>;

export interface FeatureShellWorkspaceRouteRegistration {
  element: ReactNode;
  pathSuffix: `/${string}`;
  subSidebar?: ShellRouteSubSidebar;
}

export interface FeatureShellToolRegistration {
  element: ReactNode;
  /** Opt this tool's registered ids into the app-owned feature guide surface. */
  featureGuide?: boolean;
  subSidebar?: ShellRouteSubSidebar;
  toolIds?: readonly string[];
}

export interface FeatureShellRegistration {
  navItem: FeatureShellNavRegistration;
  tool: FeatureShellToolRegistration;
  workspaceRoutes?: readonly FeatureShellWorkspaceRouteRegistration[];
}

export interface CompiledFeatureShellRegistration {
  appId: string;
  navItem: FeatureShellNavRegistration;
  toolRoute: {
    element: ReactNode;
    id: string;
    path: string;
    subSidebar?: ShellRouteSubSidebar;
    toolIds: readonly string[];
  };
  workspaceRoutes: readonly {
    element: ReactNode;
    path: string;
    subSidebar?: ShellRouteSubSidebar;
  }[];
}

export interface FeatureModuleRegistration<
  TManifest extends FeatureModuleManifest = FeatureModuleManifest,
> {
  manifest: TManifest;
  /** The registry supplies the manifest identity and owns final appId injection. */
  backgroundWorkSourceFactories?: readonly FeatureBackgroundWorkSourceFactory[];
  /** App-local shell metadata; identity and canonical paths are registry-owned. */
  shell?: FeatureShellRegistration;
}

export type FeatureModuleRegistryInput =
  | FeatureModuleManifest
  | FeatureModuleRegistration;

export interface FeatureModuleRegistry {
  aiToolAppIds: readonly string[];
  backgroundWorkSources: readonly BackgroundWorkSource[];
  featureGuideToolIds: readonly string[];
  manifests: readonly FeatureModuleManifest[];
  shellRegistrations: readonly CompiledFeatureShellRegistration[];
}

export function defineFeatureModule<const TModuleId extends string>(
  manifest: FeatureModuleManifest<TModuleId>,
): FeatureModuleManifest<TModuleId> {
  return manifest;
}

export function defineFeatureModuleRegistration<
  const TManifest extends FeatureModuleManifest,
>(
  registration: FeatureModuleRegistration<TManifest>,
): FeatureModuleRegistration<TManifest> {
  return registration;
}

function normalizeFeatureModuleRegistration(
  input: FeatureModuleRegistryInput,
): FeatureModuleRegistration {
  return 'manifest' in input ? input : { manifest: input };
}

export function compileFeatureModuleRegistry(
  inputs: readonly FeatureModuleRegistryInput[],
  {
    reservedBackgroundWorkSourceIds = [],
    reservedModuleIds = [],
  }: {
    reservedBackgroundWorkSourceIds?: Iterable<string>;
    reservedModuleIds?: Iterable<string>;
  } = {},
): FeatureModuleRegistry {
  const manifests: FeatureModuleManifest[] = [];
  const backgroundWorkSources: BackgroundWorkSource[] = [];
  const aiToolAppIds: string[] = [];
  const featureGuideToolIds: string[] = [];
  const shellRegistrations: CompiledFeatureShellRegistration[] = [];
  const moduleIds = new Set<string>(reservedModuleIds);
  const sourceIds = new Set<string>(reservedBackgroundWorkSourceIds);
  const shellNavItemIds = new Set<string>();
  const shellRouteIds = new Set<string>();
  const shellRoutePaths = new Set<string>();
  const shellToolIds = new Set<string>();

  for (const input of inputs) {
    const registration = normalizeFeatureModuleRegistration(input);
    const { manifest } = registration;
    if (moduleIds.has(manifest.moduleId)) {
      throw new Error(`Duplicate feature module id: ${manifest.moduleId}`);
    }
    moduleIds.add(manifest.moduleId);
    manifests.push(manifest);

    if (manifest.surfaces?.aiToolEntry) {
      aiToolAppIds.push(manifest.moduleId);
    }

    if (registration.shell) {
      const { navItem, tool, workspaceRoutes = [] } = registration.shell;
      if ((navItem as NavItem).appId || (navItem as NavItem).linkAppId) {
        throw new Error(
          `Feature shell nav item ${navItem.id} must not declare appId or linkAppId; ` +
            `the registry injects ${manifest.moduleId}`,
        );
      }
      if (shellNavItemIds.has(navItem.id)) {
        throw new Error(`Duplicate feature shell nav item id: ${navItem.id}`);
      }
      shellNavItemIds.add(navItem.id);

      const routeId = `${manifest.moduleId}.main`;
      const routePath = `/w/:workspaceSlug/${manifest.moduleId}`;
      const toolIds = tool.toolIds ?? [navItem.id];
      if (shellRouteIds.has(routeId)) {
        throw new Error(`Duplicate feature shell route id: ${routeId}`);
      }
      if (shellRoutePaths.has(routePath)) {
        throw new Error(`Duplicate feature shell route path: ${routePath}`);
      }
      shellRouteIds.add(routeId);
      shellRoutePaths.add(routePath);
      for (const toolId of toolIds) {
        if (shellToolIds.has(toolId)) {
          throw new Error(`Duplicate feature shell tool id: ${toolId}`);
        }
        shellToolIds.add(toolId);
      }
      if (tool.featureGuide) {
        featureGuideToolIds.push(...toolIds);
      }

      const compiledWorkspaceRoutes = workspaceRoutes.map((route) => {
        const path = `${routePath}${route.pathSuffix}`;
        if (shellRoutePaths.has(path)) {
          throw new Error(`Duplicate feature shell route path: ${path}`);
        }
        shellRoutePaths.add(path);
        return {
          element: route.element,
          path,
          subSidebar: route.subSidebar,
        };
      });
      shellRegistrations.push({
        appId: manifest.moduleId,
        navItem,
        toolRoute: {
          element: tool.element,
          id: routeId,
          path: routePath,
          subSidebar: tool.subSidebar,
          toolIds,
        },
        workspaceRoutes: compiledWorkspaceRoutes,
      });
    }

    for (const createSource of registration.backgroundWorkSourceFactories ??
      []) {
      const source = createSource({ appId: manifest.moduleId });
      const explicitAppId = (source as BackgroundWorkSource).appId;
      if (explicitAppId) {
        throw new Error(
          `Feature background work source ${source.id} must not declare appId; ` +
            `the registry injects ${manifest.moduleId}`,
        );
      }
      if (sourceIds.has(source.id)) {
        throw new Error(`Duplicate background work source id: ${source.id}`);
      }
      sourceIds.add(source.id);
      backgroundWorkSources.push({
        ...source,
        appId: manifest.moduleId,
      });
    }
  }

  return {
    aiToolAppIds,
    backgroundWorkSources,
    featureGuideToolIds,
    manifests,
    shellRegistrations,
  };
}
