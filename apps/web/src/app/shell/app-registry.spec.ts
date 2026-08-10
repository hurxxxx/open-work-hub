import { describe, expect, it } from 'vitest';
import { Home } from 'lucide-react';

import { aiGlobalRoutes } from '@/src/app-modules/ai';
import { communityGlobalRoutes } from '@/src/app-modules/community';
import {
  APP_BACKGROUND_WORK_SOURCES,
  APP_BAR_FIXED_APP_IDS,
  APP_FEATURE_GUIDE_TOOL_IDS,
  APP_GLOBAL_ROUTES,
  APP_LAUNCHER_GLOBAL_PATHS,
  APP_BAR_PINNED_BY_DEFAULT_APP_IDS,
  APP_MODULE_MANIFESTS,
  APP_SHELL_PROVIDERS,
  APP_TOOL_VIEW_ROUTES,
  APP_WORKSPACE_ROUTES,
  WORKSPACE_AI_TOOL_APP_IDS,
  createAppModuleRegistry,
  getAppModuleGlobalRoutes,
  getAppModuleWorkspaceRoutes,
  getNavItem,
  getToolViewRoute,
  assertAppModuleStaticRouteContract,
  type AppModuleRegistration,
} from './app-registry';
import { DEFAULT_APP_MODULE_MANIFESTS } from './app-module-manifests';
import { getAppSidebarConfig } from './app-sidebar-registry';
import {
  staticAdminLandingRoute,
  staticAdminRedirectRoutes,
  staticAdminSectionRoutes,
  staticAppGlobalRoutes,
  staticDocsGlobalRoutes,
  staticWorkspaceSettingsRoute,
  staticWhiteboardGlobalRoutes,
  workspaceRouteDefinitions,
} from './workspace-route-definitions';
import type { AppModuleManifest } from './navigation-types';

function manifestWithoutRoutes(manifest: AppModuleManifest): AppModuleManifest {
  return {
    ...manifest,
    globalRoutePaths: [],
    workspaceRoutePaths: [],
  };
}

function isWorkspaceRoutePathForApp(routePath: string, appId: string): boolean {
  const prefix = `/w/:workspaceSlug/${appId}`;
  return (
    routePath === prefix ||
    routePath.startsWith(`${prefix}/`) ||
    routePath.startsWith(`${prefix}*`)
  );
}

describe('app module registry', () => {
  it('rejects duplicate app ids', () => {
    const homeManifest = manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]);
    const duplicateHome: AppModuleManifest = {
      ...homeManifest,
      appBarItem: { ...homeManifest.appBarItem, title: 'Duplicate Home' },
      contract: {
        owner: 'platform-shell',
        permissions: [],
        apiDomain: null,
        aiCapabilities: [],
        writeAuditActions: [],
        appLocalTests: ['apps/web/src/app/shell/app-registry.spec.ts'],
      },
      defaultActiveNavItemId: '',
      navItems: [],
    };

    expect(() =>
      createAppModuleRegistry([homeManifest, duplicateHome]),
    ).toThrow(/Duplicate app module id: home/);
  });

  it('rejects duplicate nav item ids', () => {
    const [homeManifest, aiManifest] = APP_MODULE_MANIFESTS.map(
      manifestWithoutRoutes,
    );
    const duplicateAiNav: AppModuleManifest = {
      ...aiManifest,
      appBarItem: { id: 'learning', title: 'Duplicate Learning', icon: Home },
      navItems: [...aiManifest.navItems, { ...aiManifest.navItems[0] }],
    };

    expect(() =>
      createAppModuleRegistry([homeManifest, duplicateAiNav]),
    ).toThrow(/Duplicate nav item id: chatbot/);
  });

  it('keeps app module ids and registered manifests in sync', () => {
    expect(APP_MODULE_MANIFESTS).toEqual(DEFAULT_APP_MODULE_MANIFESTS);
  });

  it('keeps workspace settings as an explicit static route outside workspace apps', () => {
    const settingsManifest = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'settings',
    );

    expect(settingsManifest?.workspaceRoutePaths).toEqual([]);
    expect(settingsManifest?.staticWorkspaceRoutePaths).toEqual([
      staticWorkspaceSettingsRoute.path,
    ]);
    expect(settingsManifest?.globalRoutePaths).toEqual([]);
    expect(settingsManifest?.staticGlobalRoutePaths).toEqual([
      staticAdminLandingRoute.path,
      ...staticAdminRedirectRoutes.map((route) => route.path),
      ...staticAdminSectionRoutes.map((route) => route.path),
    ]);
    expect(settingsManifest?.staticGlobalRoutePaths).toContain('/admin/llm');
    expect(settingsManifest?.staticGlobalRoutePaths).toContain(
      '/admin/model-monitoring',
    );
    expect(settingsManifest?.staticGlobalRoutePaths).toContain(
      '/admin/document-processing',
    );
    expect(getAppModuleWorkspaceRoutes('settings')).toEqual([]);
  });

  it('derives workspace route definitions from the app registry', () => {
    expect(workspaceRouteDefinitions).toEqual(APP_WORKSPACE_ROUTES);
    expect(
      getAppModuleWorkspaceRoutes('collaboration').map((route) => route.path),
    ).toContain('/w/:workspaceSlug/docs');
    expect(
      getAppModuleWorkspaceRoutes('collaboration').map((route) => route.path),
    ).toContain('/w/:workspaceSlug/pms/lists/:taskListId');
    expect(
      getAppModuleWorkspaceRoutes('business').map((route) => route.path),
    ).toContain('/w/:workspaceSlug/document-translate');
    expect(
      getAppModuleWorkspaceRoutes('business').map((route) => route.path),
    ).toContain('/w/:workspaceSlug/retrieval-search');
    expect(
      getAppModuleWorkspaceRoutes('business').map((route) => route.path),
    ).toContain('/w/:workspaceSlug/drafting');
  });

  it('derives app-owned global route definitions from the app registry', () => {
    expect(staticAppGlobalRoutes).toEqual(APP_GLOBAL_ROUTES);
    expect(getAppModuleGlobalRoutes('ai')).toEqual(aiGlobalRoutes);
    expect(getAppModuleGlobalRoutes('community')).toEqual(
      communityGlobalRoutes.map((route) => ({ ...route, appId: 'community' })),
    );
    expect(getAppModuleGlobalRoutes('collaboration')).toEqual(
      staticAppGlobalRoutes.filter((route) => route.appId === 'collaboration'),
    );
    expect(getAppModuleGlobalRoutes('pms')).toEqual([]);
  });

  it('rejects static route definitions missing from the owning app manifest', () => {
    expect(() =>
      assertAppModuleStaticRouteContract('settings', {
        workspaceRoutes: [staticWorkspaceSettingsRoute],
        globalRoutes: [{ path: '/admin/missing', element: null }],
      }),
    ).toThrow(
      /Static global route path \/admin\/missing is not declared in manifest settings/,
    );
  });

  it('derives tool view routes from the app registry', () => {
    const docsItem = getNavItem('docs-all');
    expect(docsItem).not.toBeNull();
    if (!docsItem) {
      throw new Error('tool view route fixture nav items are required');
    }

    expect(APP_TOOL_VIEW_ROUTES.map((route) => route.id)).toEqual([
      'ai.workspace-search',
      'pms.main',
      'docs.main',
      'whiteboard.main',
      'diagrams.main',
      'drafting.main',
      'document-translate.main',
      'spec-compare.main',
      'image-wizard.main',
      'email-assistant.main',
      'retrieval-search.main',
    ]);
    const translateItem = getNavItem('translate');
    const pmsItem = getNavItem('pms-inbox');
    expect(translateItem).not.toBeNull();
    expect(pmsItem).not.toBeNull();
    expect(getToolViewRoute({ item: docsItem, toolId: 'docs-all' })?.id).toBe(
      'docs.main',
    );
    const workspaceSearchRoute = getToolViewRoute({
      item: null,
      toolId: 'search',
    });
    expect(workspaceSearchRoute).toMatchObject({
      appId: 'ai',
      gates: [{ type: 'workspace_search' }],
      id: 'ai.workspace-search',
      type: 'element',
    });
    expect(workspaceSearchRoute).not.toHaveProperty('bootstrapAppId');
    expect(
      getToolViewRoute({ item: translateItem, toolId: 'translate' })?.id,
    ).toBe('document-translate.main');
    expect(
      getToolViewRoute({ item: null, toolId: 'retrieval-search' })?.id,
    ).toBe('retrieval-search.main');
    expect(
      getToolViewRoute({ item: null, toolId: 'drafting' })?.id,
    ).toBe('drafting.main');
    expect(
      pmsItem
        ? getToolViewRoute({ item: pmsItem, toolId: 'pms-inbox' })?.id
        : null,
    ).toBe('pms.main');
    expect(
      getToolViewRoute({ item: null, toolId: 'pms-space-team' }),
    ).toBeNull();
    expect(
      getToolViewRoute({ item: null, toolId: 'pms-list-main' }),
    ).toBeNull();
  });

  it('derives background work sources from the app registry', () => {
    expect(APP_BACKGROUND_WORK_SOURCES.map((source) => source.id)).toEqual([
      'image-wizard',
    ]);
    expect(APP_BACKGROUND_WORK_SOURCES[0]).toMatchObject({
      appId: 'image-wizard',
    });
  });

  it('derives AI tool surfaces from feature module registrations', () => {
    expect([...WORKSPACE_AI_TOOL_APP_IDS].sort()).toEqual([
      'document-translate',
      'drafting',
      'email-assistant',
      'image-wizard',
      'spec-compare',
    ]);
    expect(WORKSPACE_AI_TOOL_APP_IDS).not.toContain('docs');
    expect(WORKSPACE_AI_TOOL_APP_IDS).not.toContain('retrieval-search');
  });

  it('derives feature guides only from explicit app-local opt-ins', () => {
    expect([...APP_FEATURE_GUIDE_TOOL_IDS]).toEqual([
      'chatbot',
      'search',
      'drafting',
      'translate',
      'spec-compare',
      'image-wizard',
      'email-assistant',
    ]);
  });

  it('derives launcher policy from app-owned manifests', () => {
    expect([...APP_LAUNCHER_GLOBAL_PATHS]).toEqual([
      ['community', '/community'],
      ['mail', '/mail'],
      ['planner', '/planner'],
    ]);
    expect(APP_BAR_FIXED_APP_IDS).toEqual(['home']);
    expect(APP_BAR_PINNED_BY_DEFAULT_APP_IDS).toEqual([
      'pms',
      'docs',
      'whiteboard',
    ]);
  });

  it('routes each workspace path through its registered leaf app prefix', () => {
    for (const route of workspaceRouteDefinitions) {
      const routeAppId = route.bootstrapAppId ?? route.appId;
      expect(isWorkspaceRoutePathForApp(route.path, routeAppId)).toBe(true);
    }
  });

  it('keeps manifest workspace paths aligned with registered route identities', () => {
    for (const manifest of APP_MODULE_MANIFESTS) {
      for (const routePath of manifest.workspaceRoutePaths) {
        const route = APP_WORKSPACE_ROUTES.find(
          (candidate) => candidate.path === routePath,
        );
        expect(route).toBeDefined();
        const routeAppId = route?.bootstrapAppId ?? route?.appId;
        expect(
          routeAppId
            ? isWorkspaceRoutePathForApp(routePath, routeAppId)
            : false,
        ).toBe(true);
      }
    }
  });

  it('keeps workspace route registry paths declared in manifests', () => {
    const manifestsByAppId = new Map(
      APP_MODULE_MANIFESTS.map((manifest) => [
        manifest.appBarItem.id,
        manifest,
      ]),
    );

    for (const route of workspaceRouteDefinitions) {
      expect(manifestsByAppId.get(route.appId)?.workspaceRoutePaths).toContain(
        route.path,
      );
    }
  });

  it('keeps app-owned global route registry paths declared in manifests', () => {
    const globalRoutesByAppId = {
      ai: aiGlobalRoutes,
      collaboration: [
        ...staticDocsGlobalRoutes,
        ...staticWhiteboardGlobalRoutes,
      ],
      community: communityGlobalRoutes,
    } as const;

    for (const [appId, routes] of Object.entries(globalRoutesByAppId)) {
      const manifest = APP_MODULE_MANIFESTS.find(
        (item) => item.appBarItem.id === appId,
      );
      expect(manifest).toBeDefined();
      for (const route of routes) {
        expect(manifest?.globalRoutePaths).toContain(route.path);
      }
    }
  });

  it('rejects workspace routes registered under the wrong app manifest', () => {
    const homeRegistration: AppModuleRegistration = {
      manifest: APP_MODULE_MANIFESTS[0],
      workspaceRoutes: [
        {
          appId: 'chatbot',
          element: null,
          path: '/w/:workspaceSlug/home',
        },
      ],
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Workspace route \/w\/:workspaceSlug\/home belongs to chatbot but is registered with manifest home/,
    );
  });

  it('rejects workspace routes missing from the owning app manifest', () => {
    const homeRegistration: AppModuleRegistration = {
      manifest: APP_MODULE_MANIFESTS[0],
      workspaceRoutes: [
        {
          appId: 'home',
          element: null,
          path: '/w/:workspaceSlug/home/missing',
        },
      ],
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Workspace route path \/w\/:workspaceSlug\/home\/missing is not declared in manifest home/,
    );
  });

  it('rejects manifest workspace paths missing from registered routes', () => {
    const homeRegistration: AppModuleRegistration = {
      manifest: APP_MODULE_MANIFESTS[0],
      workspaceRoutes: [],
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Workspace route path \/w\/:workspaceSlug\/home is declared in manifest home but not registered/,
    );
  });

  it('rejects manifest workspace paths when workspace route registration is omitted', () => {
    const homeRegistration: AppModuleRegistration = {
      manifest: APP_MODULE_MANIFESTS[0],
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Workspace route path \/w\/:workspaceSlug\/home is declared in manifest home but not registered/,
    );
  });

  it('rejects app global routes missing from the owning app manifest', () => {
    const collaborationManifest = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'collaboration',
    );
    expect(collaborationManifest).toBeDefined();
    if (!collaborationManifest) {
      throw new Error('collaboration manifest is required for this test');
    }

    const collaborationRegistration: AppModuleRegistration = {
      manifest: { ...collaborationManifest, workspaceRoutePaths: [] },
      globalRoutes: [
        {
          element: null,
          path: '/docs/missing',
        },
      ],
    };

    expect(() => createAppModuleRegistry([collaborationRegistration])).toThrow(
      /Global route path \/docs\/missing is not declared in manifest collaboration/,
    );
  });

  it('rejects manifest global paths missing from registered routes', () => {
    const collaborationManifest = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'collaboration',
    );
    expect(collaborationManifest).toBeDefined();
    if (!collaborationManifest) {
      throw new Error('collaboration manifest is required for this test');
    }

    const collaborationRegistration: AppModuleRegistration = {
      globalRoutes: [],
      manifest: { ...collaborationManifest, workspaceRoutePaths: [] },
    };

    expect(() => createAppModuleRegistry([collaborationRegistration])).toThrow(
      /Global route path \/docs\/shared\/:shareToken is declared in manifest collaboration but not registered/,
    );
  });

  it('rejects tool view routes registered under the wrong app manifest', () => {
    const homeRegistration: AppModuleRegistration = {
      manifest: manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]),
      toolViewRoutes: [
        {
          appId: 'chatbot',
          element: null,
          id: 'chatbot.wrong-registration',
          match: () => true,
          type: 'element',
        },
      ],
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Tool view route chatbot\.wrong-registration belongs to chatbot but is registered with manifest home/,
    );
  });

  it('rejects duplicate tool view route ids', () => {
    const businessManifest = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'business',
    );
    expect(businessManifest).toBeDefined();
    if (!businessManifest) {
      throw new Error('business manifest is required for this test');
    }

    const businessRegistration: AppModuleRegistration = {
      manifest: manifestWithoutRoutes(businessManifest),
      toolViewRoutes: [
        {
          appId: 'business',
          element: null,
          id: 'business.duplicate',
          match: () => true,
          type: 'element',
        },
        {
          appId: 'business',
          element: null,
          id: 'business.duplicate',
          match: () => false,
          type: 'element',
        },
      ],
    };

    expect(() => createAppModuleRegistry([businessRegistration])).toThrow(
      /Duplicate tool view route id: business\.duplicate/,
    );
  });

  it('rejects duplicate declared tool ids across tool routes', () => {
    const aiManifest = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'ai',
    );
    expect(aiManifest).toBeDefined();
    if (!aiManifest) {
      throw new Error('ai manifest is required for this test');
    }

    const aiRegistration: AppModuleRegistration = {
      manifest: {
        ...aiManifest,
        globalRoutePaths: [],
        workspaceRoutePaths: [],
      },
      toolViewRoutes: [
        {
          appId: 'ai',
          element: null,
          id: 'chatbot.first-search',
          match: ({ toolId }) => toolId === 'search',
          toolIds: ['search'],
          type: 'element',
        },
        {
          appId: 'ai',
          element: null,
          id: 'chatbot.second-search',
          match: ({ toolId }) => toolId === 'search',
          toolIds: ['search'],
          type: 'element',
        },
      ],
      workspaceRoutes: [],
    };

    expect(() => createAppModuleRegistry([aiRegistration])).toThrow(
      /Tool id search is declared by both chatbot\.first-search and chatbot\.second-search/,
    );
  });

  it('rejects declared tool ids matched by multiple route matchers', () => {
    const aiManifest = APP_MODULE_MANIFESTS.find(
      (manifest) => manifest.appBarItem.id === 'ai',
    );
    expect(aiManifest).toBeDefined();
    if (!aiManifest) {
      throw new Error('ai manifest is required for this test');
    }

    const aiRegistration: AppModuleRegistration = {
      manifest: {
        ...aiManifest,
        globalRoutePaths: [],
        workspaceRoutePaths: [],
      },
      toolViewRoutes: [
        {
          appId: 'ai',
          element: null,
          id: 'chatbot.exact-search',
          match: ({ toolId }) => toolId === 'search',
          toolIds: ['search'],
          type: 'element',
        },
        {
          appId: 'ai',
          element: null,
          id: 'chatbot.broad-search',
          match: ({ toolId }) => toolId.startsWith('s'),
          type: 'element',
        },
      ],
      workspaceRoutes: [],
    };

    expect(() => createAppModuleRegistry([aiRegistration])).toThrow(
      /Tool id search must match only tool view route chatbot\.exact-search, matched: chatbot\.exact-search, chatbot\.broad-search/,
    );
  });

  it('rejects duplicate background work source ids', () => {
    const homeRegistration: AppModuleRegistration = {
      backgroundWorkSources: [
        {
          id: 'duplicate-source',
          list: async () => [],
        },
        {
          id: 'duplicate-source',
          list: async () => [],
        },
      ],
      manifest: manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]),
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Duplicate background work source id: duplicate-source/,
    );
  });

  it('attaches the owning app id to background work sources', () => {
    const homeRegistration: AppModuleRegistration = {
      backgroundWorkSources: [
        {
          id: 'home-background',
          list: async () => [],
        },
      ],
      manifest: manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]),
    };

    expect(
      createAppModuleRegistry([homeRegistration]).backgroundWorkSources[0]
        .appId,
    ).toBe('home');
  });

  it('rejects background work sources registered under the wrong app manifest', () => {
    const homeRegistration: AppModuleRegistration = {
      backgroundWorkSources: [
        {
          appId: 'chatbot',
          id: 'wrong-owner',
          list: async () => [],
        },
      ],
      manifest: manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]),
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Background work source wrong-owner belongs to chatbot but is registered with manifest home/,
    );
  });

  it('rejects background work sources gated by undeclared nav items', () => {
    const homeRegistration: AppModuleRegistration = {
      backgroundWorkSources: [
        {
          id: 'missing-nav-gate',
          list: async () => [],
          requiredNavItemId: 'missing-nav',
        },
      ],
      manifest: manifestWithoutRoutes(APP_MODULE_MANIFESTS[0]),
    };

    expect(() => createAppModuleRegistry([homeRegistration])).toThrow(
      /Background work source missing-nav-gate requires nav item missing-nav that is not declared in manifest home/,
    );
  });

  it('keeps manifest nav items owned by their declaring app', () => {
    for (const manifest of APP_MODULE_MANIFESTS) {
      const appId = manifest.appBarItem.id;
      for (const navItem of manifest.navItems) {
        expect(navItem.appId).toBe(appId);
      }
    }
  });

  it('exposes nav items through the registry public API', () => {
    expect(getNavItem('search')).toBeNull();
    expect(getNavItem('drafting')?.appId).toBe('business');
    expect(getNavItem('retrieval-search')?.appId).toBe('business');
    expect(getNavItem('pms-tasks-assigned')?.appId).toBe('collaboration');
    expect(getNavItem('missing-tool')).toBeNull();
  });

  it('exposes app sidebars through the shell sidebar registry', () => {
    expect(getAppSidebarConfig('ai')).not.toBeNull();
    expect(getAppSidebarConfig('collaboration')).not.toBeNull();
    expect(getAppSidebarConfig('home')).toBeNull();
    expect(getAppSidebarConfig('settings')).toBeNull();
  });

  it('exposes shell providers through the app module registry', () => {
    expect(APP_SHELL_PROVIDERS.map((Provider) => Provider.name)).toEqual([
      'FileUploadProvider',
    ]);
  });
});
