export type CoreRoutePathDefinition = { path: string };

export interface CoreNavItem<TAppId extends string = string> {
  appId: TAppId;
  id: string;
}

export interface CoreAppBarItem<TAppId extends string = string> {
  id: TAppId;
}

export type CoreAppModuleContract = Record<never, never>;

export interface CoreAppModuleManifest<
  TAppId extends string = string,
  TNavItem extends CoreNavItem<TAppId> = CoreNavItem<TAppId>,
> {
  appBarItem: CoreAppBarItem<TAppId>;
  contract: CoreAppModuleContract;
  globalRoutePaths?: readonly string[];
  navItems: readonly TNavItem[];
  staticGlobalRoutePaths?: readonly string[];
  staticWorkspaceRoutePaths?: readonly string[];
  workspaceRoutePaths: readonly string[];
}

export interface CoreStaticRouteDefinition<TAppId extends string = string> {
  appId?: TAppId;
  path: string;
}

export interface CoreWorkspaceRouteDefinition<TAppId extends string = string> {
  appId: TAppId;
  path: string;
}

export interface CoreToolViewRouteMatchContext<TNavItem> {
  item: TNavItem | null;
  toolId: string;
}

export interface CoreToolViewRouteDefinition<
  TAppId extends string = string,
  TNavItem = CoreNavItem<TAppId>,
> {
  appId: TAppId;
  id: string;
  match: (context: CoreToolViewRouteMatchContext<TNavItem>) => boolean;
  toolIds?: readonly string[];
}

export interface CoreBackgroundWorkSource {
  appId: string;
  id: string;
  requiredNavItemId?: string;
}

type CoreBackgroundWorkSourceRegistration<
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
> = Omit<TBackgroundWorkSource, 'appId'>;

export type CoreRegisteredBackgroundWorkSource<
  TAppId extends string,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
> = CoreBackgroundWorkSourceRegistration<TBackgroundWorkSource> & {
  appId: TAppId;
};

export interface CoreAppModuleRegistration<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
> {
  backgroundWorkSources?: readonly CoreBackgroundWorkSourceRegistration<TBackgroundWorkSource>[];
  globalRoutes?: readonly TStaticRoute[];
  manifest: TManifest;
  sidebarConfig?: TSidebarConfig;
  shellNavResolver?: TShellNavResolver;
  shellProviders?: readonly TShellProvider[];
  toolViewRoutes?: readonly TToolViewRoute[];
  workspaceRoutes?: readonly TWorkspaceRoute[];
}

export interface CoreAppModuleRegistry<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TAppBarItem,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
> {
  appBarItems: readonly TAppBarItem[];
  appGlobalRoutes: readonly TStaticRoute[];
  backgroundWorkSources: readonly CoreRegisteredBackgroundWorkSource<
    TAppId,
    TBackgroundWorkSource
  >[];
  globalRoutesByAppId: ReadonlyMap<TAppId, readonly TStaticRoute[]>;
  manifestByAppId: ReadonlyMap<TAppId, TManifest>;
  manifests: readonly TManifest[];
  navItemById: ReadonlyMap<string, TNavItem>;
  navItems: readonly TNavItem[];
  shellNavResolverByAppId: ReadonlyMap<TAppId, TShellNavResolver>;
  shellProviders: readonly TShellProvider[];
  sidebarConfigByAppId: ReadonlyMap<TAppId, TSidebarConfig>;
  toolViewRouteById: ReadonlyMap<string, TToolViewRoute>;
  toolViewRoutes: readonly TToolViewRoute[];
  workspaceRoutes: readonly TWorkspaceRoute[];
  workspaceRoutesByAppId: ReadonlyMap<TAppId, readonly TWorkspaceRoute[]>;
}

export interface CoreAppModuleRegistryApi<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TAppBarItem,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
> {
  APP_BACKGROUND_WORK_SOURCES: readonly CoreRegisteredBackgroundWorkSource<
    TAppId,
    TBackgroundWorkSource
  >[];
  APP_BAR_ITEMS: readonly TAppBarItem[];
  APP_GLOBAL_ROUTES: readonly TStaticRoute[];
  APP_MODULE_MANIFESTS: readonly TManifest[];
  APP_MODULE_REGISTRY: CoreAppModuleRegistry<
    TAppId,
    TNavItem,
    TManifest,
    TAppBarItem,
    TStaticRoute,
    TWorkspaceRoute,
    TToolViewRoute,
    TBackgroundWorkSource,
    TSidebarConfig,
    TShellNavResolver,
    TShellProvider
  >;
  APP_SHELL_PROVIDERS: readonly TShellProvider[];
  APP_TOOL_VIEW_ROUTES: readonly TToolViewRoute[];
  APP_WORKSPACE_ROUTES: readonly TWorkspaceRoute[];
  NAV_ITEMS: readonly TNavItem[];
  assertAppModuleStaticRouteContract: (
    appId: TAppId,
    routes: {
      globalRoutes?: readonly CoreRoutePathDefinition[];
      workspaceRoutes?: readonly CoreRoutePathDefinition[];
    },
  ) => void;
  getAppModuleGlobalRoutes: (appId: TAppId) => readonly TStaticRoute[];
  getAppModuleManifest: (appId: TAppId) => TManifest | null;
  getAppModuleSidebarConfig: (appId: string) => TSidebarConfig | null;
  getAppModuleWorkspaceRoutes: (appId: TAppId) => readonly TWorkspaceRoute[];
  getAppShellNavResolver: (appId: TAppId) => TShellNavResolver | null;
  getNavItem: (itemId: string) => TNavItem | null;
  getToolViewRoute: ({
    item,
    toolId,
  }: {
    item: TNavItem | null;
    toolId: string;
  }) => TToolViewRoute | null;
}

type CoreAppModuleRegistryInput<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
> =
  | TManifest
  | CoreAppModuleRegistration<
      TAppId,
      TNavItem,
      TManifest,
      TStaticRoute,
      TWorkspaceRoute,
      TToolViewRoute,
      TBackgroundWorkSource,
      TSidebarConfig,
      TShellNavResolver,
      TShellProvider
    >;

const EMPTY_ROUTES: readonly CoreRoutePathDefinition[] = [];

function normalizeRegistration<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
>(
  input: CoreAppModuleRegistryInput<
    TAppId,
    TNavItem,
    TManifest,
    TStaticRoute,
    TWorkspaceRoute,
    TToolViewRoute,
    TBackgroundWorkSource,
    TSidebarConfig,
    TShellNavResolver,
    TShellProvider
  >,
): CoreAppModuleRegistration<
  TAppId,
  TNavItem,
  TManifest,
  TStaticRoute,
  TWorkspaceRoute,
  TToolViewRoute,
  TBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider
> {
  if ('manifest' in input) {
    return input;
  }
  return { manifest: input };
}

function assertUniqueRoutePath(
  routeKind: string,
  routePath: string,
  seenRoutePaths: Set<string>,
) {
  if (seenRoutePaths.has(routePath)) {
    throw new Error(`Duplicate ${routeKind} route path: ${routePath}`);
  }
  seenRoutePaths.add(routePath);
}

function assertDeclaredRoutePath(
  routeKind: string,
  appId: string,
  routePath: string,
  declaredRoutePaths: ReadonlySet<string>,
) {
  if (!declaredRoutePaths.has(routePath)) {
    throw new Error(
      `${routeKind} route path ${routePath} is not declared in manifest ${appId}`,
    );
  }
}

function assertRegisteredRoutePaths(
  routeKind: string,
  appId: string,
  declaredRoutePaths: ReadonlySet<string>,
  registeredRoutePaths: ReadonlySet<string>,
) {
  for (const routePath of declaredRoutePaths) {
    if (!registeredRoutePaths.has(routePath)) {
      throw new Error(
        `${routeKind} route path ${routePath} is declared in manifest ${appId} but not registered`,
      );
    }
  }
}

function assertToolViewRouteToolIdContract(
  route: { id: string; toolIds?: readonly string[] },
  toolIdsByOwnerRouteId: Map<string, string>,
) {
  for (const toolId of route.toolIds ?? []) {
    const ownerRouteId = toolIdsByOwnerRouteId.get(toolId);
    if (ownerRouteId) {
      throw new Error(
        `Tool id ${toolId} is declared by both ${ownerRouteId} and ${route.id}`,
      );
    }
    toolIdsByOwnerRouteId.set(toolId, route.id);
  }
}

function assertDeclaredToolIdsMatchSingleRoute<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
>({
  navItemById,
  toolIdsByOwnerRouteId,
  toolViewRoutes,
}: {
  navItemById: ReadonlyMap<string, TNavItem>;
  toolIdsByOwnerRouteId: ReadonlyMap<string, string>;
  toolViewRoutes: readonly TToolViewRoute[];
}) {
  for (const [toolId, ownerRouteId] of toolIdsByOwnerRouteId) {
    const item = navItemById.get(toolId) ?? null;
    const matchingRouteIds = toolViewRoutes
      .filter((route) => route.match({ item, toolId }))
      .map((route) => route.id);
    if (matchingRouteIds.length !== 1 || matchingRouteIds[0] !== ownerRouteId) {
      throw new Error(
        `Tool id ${toolId} must match only tool view route ${ownerRouteId}, matched: ${matchingRouteIds.join(', ') || 'none'}`,
      );
    }
  }
}

function selectSingleToolViewRoute<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
>({
  item,
  toolId,
  toolViewRoutes,
}: {
  item: TNavItem | null;
  toolId: string;
  toolViewRoutes: readonly TToolViewRoute[];
}): TToolViewRoute | null {
  const matchingRoutes = toolViewRoutes.filter((route) =>
    route.match({ item, toolId }),
  );
  if (matchingRoutes.length > 1) {
    throw new Error(
      `Ambiguous tool view route for ${toolId}: ${matchingRoutes.map((route) => route.id).join(', ')}`,
    );
  }
  return matchingRoutes[0] ?? null;
}

function assertBackgroundWorkSourceContract(
  appId: string,
  source: CoreBackgroundWorkSourceRegistration<CoreBackgroundWorkSource>,
  declaredNavItemIds: ReadonlySet<string>,
) {
  if ('appId' in source) {
    if (source.appId !== appId) {
      throw new Error(
        `Background work source ${source.id} belongs to ${String(source.appId)} but is registered with manifest ${appId}`,
      );
    }
    throw new Error(
      `Background work source ${source.id} must not declare appId; the registry injects ${appId}`,
    );
  }
  if (
    source.requiredNavItemId &&
    !declaredNavItemIds.has(source.requiredNavItemId)
  ) {
    throw new Error(
      `Background work source ${source.id} requires nav item ${source.requiredNavItemId} that is not declared in manifest ${appId}`,
    );
  }
}

function assertStaticRoutePaths(
  routeKind: string,
  appId: string,
  declaredRoutePaths: readonly string[],
  registeredRoutes: readonly CoreRoutePathDefinition[],
): void {
  const declared = new Set(declaredRoutePaths);
  const registered = new Set(registeredRoutes.map((route) => route.path));
  for (const route of registeredRoutes) {
    assertDeclaredRoutePath(routeKind, appId, route.path, declared);
  }
  assertRegisteredRoutePaths(routeKind, appId, declared, registered);
}

export function createCoreAppModuleRegistry<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TAppBarItem,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
>(
  inputs: readonly CoreAppModuleRegistryInput<
    TAppId,
    TNavItem,
    TManifest,
    TStaticRoute,
    TWorkspaceRoute,
    TToolViewRoute,
    TBackgroundWorkSource,
    TSidebarConfig,
    TShellNavResolver,
    TShellProvider
  >[],
): CoreAppModuleRegistry<
  TAppId,
  TNavItem,
  TManifest,
  TAppBarItem,
  TStaticRoute,
  TWorkspaceRoute,
  TToolViewRoute,
  TBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider
> {
  const registrations = inputs.map(normalizeRegistration);
  const manifestByAppId = new Map<TAppId, TManifest>();
  const navItemById = new Map<string, TNavItem>();
  const workspaceRoutePaths = new Set<string>();
  const globalRoutePaths = new Set<string>();
  const workspaceRoutes: TWorkspaceRoute[] = [];
  const workspaceRoutesByAppId = new Map<TAppId, TWorkspaceRoute[]>();
  const appGlobalRoutes: TStaticRoute[] = [];
  const globalRoutesByAppId = new Map<TAppId, TStaticRoute[]>();
  const toolViewRoutes: TToolViewRoute[] = [];
  const toolViewRouteById = new Map<string, TToolViewRoute>();
  const toolIdsByOwnerRouteId = new Map<string, string>();
  const backgroundWorkSources: CoreRegisteredBackgroundWorkSource<
    TAppId,
    TBackgroundWorkSource
  >[] = [];
  const backgroundWorkSourceIds = new Set<string>();
  const sidebarConfigByAppId = new Map<TAppId, TSidebarConfig>();
  const shellNavResolverByAppId = new Map<TAppId, TShellNavResolver>();
  const shellProviders: TShellProvider[] = [];

  for (const registration of registrations) {
    const { manifest } = registration;
    const appId = manifest.appBarItem.id;
    if (manifestByAppId.has(appId)) {
      throw new Error(`Duplicate app module id: ${appId}`);
    }
    manifestByAppId.set(appId, manifest);

    for (const navItem of manifest.navItems) {
      if (navItemById.has(navItem.id)) {
        throw new Error(`Duplicate nav item id: ${navItem.id}`);
      }
      navItemById.set(navItem.id, navItem);
    }

    const appWorkspaceRoutes = [...(registration.workspaceRoutes ?? [])];
    const declaredWorkspaceRoutePaths = new Set(manifest.workspaceRoutePaths);
    const registeredWorkspaceRoutePaths = new Set<string>();
    for (const route of appWorkspaceRoutes) {
      if (route.appId !== appId) {
        throw new Error(
          `Workspace route ${route.path} belongs to ${route.appId} but is registered with manifest ${appId}`,
        );
      }
      assertUniqueRoutePath('workspace', route.path, workspaceRoutePaths);
      assertDeclaredRoutePath(
        'Workspace',
        appId,
        route.path,
        declaredWorkspaceRoutePaths,
      );
      workspaceRoutes.push(route);
      registeredWorkspaceRoutePaths.add(route.path);
    }
    assertRegisteredRoutePaths(
      'Workspace',
      appId,
      declaredWorkspaceRoutePaths,
      registeredWorkspaceRoutePaths,
    );
    if (appWorkspaceRoutes.length > 0) {
      workspaceRoutesByAppId.set(appId, appWorkspaceRoutes);
    }

    const appRoutes = [...(registration.globalRoutes ?? [])];
    const registeredAppRoutes: TStaticRoute[] = [];
    const declaredGlobalRoutePaths = new Set(manifest.globalRoutePaths ?? []);
    const registeredGlobalRoutePaths = new Set<string>();
    for (const route of appRoutes) {
      assertUniqueRoutePath('global', route.path, globalRoutePaths);
      assertDeclaredRoutePath(
        'Global',
        appId,
        route.path,
        declaredGlobalRoutePaths,
      );
      const registeredRoute = { ...route, appId };
      appGlobalRoutes.push(registeredRoute);
      registeredAppRoutes.push(registeredRoute);
      registeredGlobalRoutePaths.add(route.path);
    }
    assertRegisteredRoutePaths(
      'Global',
      appId,
      declaredGlobalRoutePaths,
      registeredGlobalRoutePaths,
    );
    if (appRoutes.length > 0) {
      globalRoutesByAppId.set(appId, registeredAppRoutes);
    }

    const appToolViewRoutes = [...(registration.toolViewRoutes ?? [])];
    for (const route of appToolViewRoutes) {
      if (route.appId !== appId) {
        throw new Error(
          `Tool view route ${route.id} belongs to ${route.appId} but is registered with manifest ${appId}`,
        );
      }
      if (toolViewRouteById.has(route.id)) {
        throw new Error(`Duplicate tool view route id: ${route.id}`);
      }
      assertToolViewRouteToolIdContract(route, toolIdsByOwnerRouteId);
      toolViewRouteById.set(route.id, route);
      toolViewRoutes.push(route);
    }

    const appBackgroundWorkSources = [
      ...(registration.backgroundWorkSources ?? []),
    ];
    const declaredNavItemIds = new Set(
      manifest.navItems.map((item) => item.id),
    );
    for (const source of appBackgroundWorkSources) {
      assertBackgroundWorkSourceContract(appId, source, declaredNavItemIds);
      if (backgroundWorkSourceIds.has(source.id)) {
        throw new Error(`Duplicate background work source id: ${source.id}`);
      }
      backgroundWorkSourceIds.add(source.id);
      backgroundWorkSources.push({ ...source, appId });
    }

    if (registration.sidebarConfig) {
      sidebarConfigByAppId.set(appId, registration.sidebarConfig);
    }
    if (registration.shellNavResolver) {
      shellNavResolverByAppId.set(appId, registration.shellNavResolver);
    }
    shellProviders.push(...(registration.shellProviders ?? []));
  }

  assertDeclaredToolIdsMatchSingleRoute({
    navItemById,
    toolIdsByOwnerRouteId,
    toolViewRoutes,
  });

  const manifests = registrations.map((registration) => registration.manifest);
  const appBarItems = manifests.map(
    (manifest) => manifest.appBarItem,
  ) as TAppBarItem[];
  const navItems = manifests.flatMap((manifest) => manifest.navItems);

  return {
    appBarItems,
    appGlobalRoutes,
    backgroundWorkSources,
    globalRoutesByAppId,
    shellNavResolverByAppId,
    manifestByAppId,
    manifests,
    navItemById,
    navItems,
    sidebarConfigByAppId,
    shellProviders,
    toolViewRouteById,
    toolViewRoutes,
    workspaceRoutes,
    workspaceRoutesByAppId,
  };
}

export function createCoreAppModuleRegistryApi<
  TAppId extends string,
  TNavItem extends CoreNavItem<TAppId>,
  TManifest extends CoreAppModuleManifest<TAppId, TNavItem>,
  TAppBarItem,
  TStaticRoute extends CoreStaticRouteDefinition<TAppId>,
  TWorkspaceRoute extends CoreWorkspaceRouteDefinition<TAppId>,
  TToolViewRoute extends CoreToolViewRouteDefinition<TAppId, TNavItem>,
  TBackgroundWorkSource extends CoreBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider,
>(
  inputs: readonly CoreAppModuleRegistryInput<
    TAppId,
    TNavItem,
    TManifest,
    TStaticRoute,
    TWorkspaceRoute,
    TToolViewRoute,
    TBackgroundWorkSource,
    TSidebarConfig,
    TShellNavResolver,
    TShellProvider
  >[],
): CoreAppModuleRegistryApi<
  TAppId,
  TNavItem,
  TManifest,
  TAppBarItem,
  TStaticRoute,
  TWorkspaceRoute,
  TToolViewRoute,
  TBackgroundWorkSource,
  TSidebarConfig,
  TShellNavResolver,
  TShellProvider
> {
  const registry = createCoreAppModuleRegistry<
    TAppId,
    TNavItem,
    TManifest,
    TAppBarItem,
    TStaticRoute,
    TWorkspaceRoute,
    TToolViewRoute,
    TBackgroundWorkSource,
    TSidebarConfig,
    TShellNavResolver,
    TShellProvider
  >(inputs);

  return {
    APP_BACKGROUND_WORK_SOURCES: registry.backgroundWorkSources,
    APP_BAR_ITEMS: registry.appBarItems,
    APP_GLOBAL_ROUTES: registry.appGlobalRoutes,
    APP_MODULE_MANIFESTS: registry.manifests,
    APP_MODULE_REGISTRY: registry,
    APP_SHELL_PROVIDERS: registry.shellProviders,
    APP_TOOL_VIEW_ROUTES: registry.toolViewRoutes,
    APP_WORKSPACE_ROUTES: registry.workspaceRoutes,
    NAV_ITEMS: registry.navItems,
    assertAppModuleStaticRouteContract: (
      appId,
      { globalRoutes = EMPTY_ROUTES, workspaceRoutes = EMPTY_ROUTES },
    ) => {
      const manifest = registry.manifestByAppId.get(appId);
      if (!manifest) {
        throw new Error(
          `Static route app manifest is not registered: ${appId}`,
        );
      }

      assertStaticRoutePaths(
        'Static workspace',
        appId,
        manifest.staticWorkspaceRoutePaths ?? [],
        workspaceRoutes,
      );
      assertStaticRoutePaths(
        'Static global',
        appId,
        manifest.staticGlobalRoutePaths ?? [],
        globalRoutes,
      );
    },
    getAppModuleGlobalRoutes: (appId) =>
      registry.globalRoutesByAppId.get(appId) ?? [],
    getAppModuleManifest: (appId) =>
      registry.manifestByAppId.get(appId) ?? null,
    getAppModuleSidebarConfig: (appId) =>
      registry.sidebarConfigByAppId.get(appId as TAppId) ?? null,
    getAppModuleWorkspaceRoutes: (appId) =>
      registry.workspaceRoutesByAppId.get(appId) ?? [],
    getAppShellNavResolver: (appId) =>
      registry.shellNavResolverByAppId.get(appId) ?? null,
    getNavItem: (itemId) => registry.navItemById.get(itemId) ?? null,
    getToolViewRoute: ({ item, toolId }) =>
      selectSingleToolViewRoute({
        item,
        toolId,
        toolViewRoutes: registry.toolViewRoutes,
      }),
  };
}
