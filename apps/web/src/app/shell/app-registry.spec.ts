import { describe, expect, it } from 'vitest';
import {
  APP_CONTRACTS,
  APP_ROUTE_BY_ID,
  type AppRouteId,
} from '@open-work-hub/contracts/app-contracts';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { communityGlobalRoutes } from '@/src/app-modules/community';
import { settingsManifest } from '@/src/app-modules/settings';
import { DEFAULT_APP_CONTRACT_MANIFESTS } from './app-contract-manifests';
import {
  APP_BACKGROUND_WORK_SOURCES,
  APP_BAR_FIXED_APP_IDS,
  APP_BAR_PINNED_BY_DEFAULT_APP_IDS,
  APP_FEATURE_GUIDE_TOOL_IDS,
  APP_GLOBAL_ROUTES,
  APP_LAUNCHER_GLOBAL_PATHS,
  APP_MODULE_MANIFESTS,
  APP_TOOL_VIEW_ROUTES,
  APP_ROUTES,
  AI_TOOL_APP_IDS,
  assertAppModuleStaticRouteContract,
  createAppModuleRegistry,
  getAppModuleGlobalRoutes,
  getAppModuleAppRoutes,
  getToolViewRoute,
  type AppModuleRegistration,
} from './app-registry';
import { DEFAULT_APP_MODULE_MANIFESTS } from './app-module-manifests';
import {
  staticAdminLandingRoute,
  staticAdminRedirectRoutes,
  staticAdminSectionRoutes,
  staticAppGlobalRoutes,
  appRouteDefinitions,
} from './app-route-definitions';
import type { AppModuleManifest } from './navigation-types';

function manifestWithoutRoutes(manifest: AppModuleManifest): AppModuleManifest {
  return {
    ...manifest,
    globalRoutePaths: [],
    staticGlobalRoutePaths: [],
    staticAppRoutePaths: [],
    appRoutePaths: [],
  };
}

function isAppRoutePathForApp(routePath: string, appId: string): boolean {
  const prefix = `/apps/${appId}`;
  return routePath === prefix || routePath.startsWith(`${prefix}/`);
}

describe('app module registry', () => {
  it('registers leaf executable identities and no display categories', () => {
    const appIds = APP_MODULE_MANIFESTS.map(
      (manifest) => manifest.appBarItem.id,
    );
    expect(appIds).toEqual(APP_CONTRACTS.map((app) => app.app_id));
    expect(appIds).not.toContain('settings');
    expect(appIds).not.toEqual(
      expect.arrayContaining(['ai', 'collaboration', 'business']),
    );
    expect(APP_MODULE_MANIFESTS).toEqual(DEFAULT_APP_MODULE_MANIFESTS);
    expect(
      DEFAULT_APP_CONTRACT_MANIFESTS.map((manifest) => manifest.appBarItem.id),
    ).toEqual(appIds);
  });

  it('rejects duplicate app and navigation identities', () => {
    const home = manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]);
    expect(() => createAppModuleRegistry([home, home])).toThrow(
      /Duplicate app module id: home/,
    );

    const docs = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'docs',
    );
    expect(docs).toBeDefined();
    if (!docs) return;
    const duplicateNav = manifestWithoutRoutes({
      ...docs,
      navItems: [...docs.navItems, { ...docs.navItems[0] }],
    });
    expect(() => createAppModuleRegistry([duplicateNav])).toThrow(
      /Duplicate nav item id/,
    );
  });

  it('keeps platform administration outside executable app routes', () => {
    expect(settingsManifest.appRoutePaths).toEqual([]);
    expect(settingsManifest.staticAppRoutePaths ?? []).toEqual([]);
    expect(settingsManifest.staticGlobalRoutePaths).toEqual([
      staticAdminLandingRoute.path,
      ...staticAdminRedirectRoutes.map((route) => route.path),
      ...staticAdminSectionRoutes.map((route) => route.path),
    ]);
    expect(getAppModuleAppRoutes('settings')).toEqual([]);
  });

  it('derives canonical app routes from each leaf app', () => {
    expect(appRouteDefinitions).toEqual(APP_ROUTES);
    expect(getAppModuleAppRoutes('docs').map((route) => route.path)).toContain(
      '/apps/docs/documents/:docId',
    );
    expect(getAppModuleAppRoutes('bento').map((route) => route.path)).toContain(
      '/apps/bento/presentations/:documentId',
    );
    expect(getAppModuleAppRoutes('pms').map((route) => route.path)).toContain(
      '/apps/pms/lists/:taskListId',
    );

    for (const route of appRouteDefinitions) {
      const routeAppId = route.appId;
      expect(route.appId).toBe(routeAppId);
      expect(isAppRoutePathForApp(route.path, routeAppId)).toBe(true);
    }
  });

  it('derives canonical global and shared routes from leaf apps', () => {
    expect(staticAppGlobalRoutes).toEqual(APP_GLOBAL_ROUTES);
    expect(getAppModuleGlobalRoutes('community')).toEqual(
      communityGlobalRoutes.map((route) => ({ ...route, appId: 'community' })),
    );
    expect(getAppModuleGlobalRoutes('docs').map((route) => route.path)).toEqual(
      expect.arrayContaining([
        '/apps/docs/shared/:shareToken',
        '/apps/docs/shared/:shareToken/html/:pageId',
      ]),
    );
    expect(getAppModuleGlobalRoutes('pms')).toEqual([]);
  });

  it('keeps every registered route chrome aligned with the generated contract', () => {
    const routeIdByPattern = new Map(
      Array.from(APP_ROUTE_BY_ID.keys()).map((routeId) => [
        getAppRoutePattern(routeId),
        routeId,
      ]),
    );
    for (const route of [...APP_ROUTES, ...APP_GLOBAL_ROUTES]) {
      const routeId = routeIdByPattern.get(route.path) as
        | AppRouteId
        | undefined;
      expect(routeId, route.path).toBeDefined();
      if (!routeId) continue;
      expect(route.chrome ?? 'standard', route.path).toBe(
        getAppRouteChrome(routeId),
      );
    }
    expect(
      [...APP_ROUTES, ...APP_GLOBAL_ROUTES].map((route) => route.path).sort(),
    ).toEqual(
      [...APP_ROUTE_BY_ID.keys()]
        .map((routeId) => getAppRoutePattern(routeId))
        .sort(),
    );
  });

  it('has no generic tool route ownership or aggregate AI tool app ids', () => {
    expect(APP_TOOL_VIEW_ROUTES).toEqual([]);
    expect(getToolViewRoute({ item: null, toolId: 'search' })).toBeNull();
    expect([...AI_TOOL_APP_IDS]).toEqual([]);
  });

  it('keeps leaf ownership for background work and launcher policy', () => {
    expect(APP_BACKGROUND_WORK_SOURCES).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          appId: 'bento',
          id: 'bento-ai',
          requiredNavItemId: 'bento-all',
        }),
      ]),
    );
    expect([...APP_FEATURE_GUIDE_TOOL_IDS]).toEqual([]);
    expect([...APP_LAUNCHER_GLOBAL_PATHS]).toEqual(
      APP_CONTRACTS.map((app) => [app.app_id, app.route_base]),
    );
    expect(APP_BAR_FIXED_APP_IDS).toEqual(['home']);
    expect(APP_BAR_PINNED_BY_DEFAULT_APP_IDS).toEqual([
      'pms',
      'docs',
      'whiteboard',
    ]);
  });

  it('rejects static and app routes that violate manifest ownership', () => {
    expect(() =>
      assertAppModuleStaticRouteContract('settings', {
        appRoutes: [{ path: '/admin/unknown', element: null }],
        globalRoutes: [{ path: '/admin/missing', element: null }],
      }),
    ).toThrow(/not declared in manifest settings/);

    const home = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'home',
    );
    expect(home).toBeDefined();
    if (!home) return;

    const wrongOwner: AppModuleRegistration = {
      manifest: home,
      appRoutes: [
        {
          appId: 'chatbot',
          element: null,
          path: '/apps/home',
        },
      ],
    };
    expect(() => createAppModuleRegistry([wrongOwner])).toThrow(
      /belongs to chatbot but is registered with manifest home/,
    );

    const missingPath: AppModuleRegistration = {
      manifest: home,
      appRoutes: [
        {
          appId: 'home',
          element: null,
          path: '/apps/home/missing',
        },
      ],
    };
    expect(() => createAppModuleRegistry([missingPath])).toThrow(
      /not declared in manifest home/,
    );
  });
});
