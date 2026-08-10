import { describe, expect, it } from 'vitest';

import {
  createCoreAppModuleRegistryApi,
  type CoreAppBarItem,
  type CoreAppModuleManifest,
  type CoreBackgroundWorkSource,
  type CoreNavItem,
  type CoreStaticRouteDefinition,
  type CoreToolViewRouteDefinition,
  type CoreWorkspaceRouteDefinition,
} from './app-registry';

type TestAppId = 'research' | 'settings';

interface TestNavItem extends CoreNavItem<TestAppId> {
  label: string;
}

interface TestAppBarItem extends CoreAppBarItem<TestAppId> {
  label: string;
}

interface TestManifest extends CoreAppModuleManifest<TestAppId, TestNavItem> {
  appBarItem: TestAppBarItem;
  label: string;
}

interface TestStaticRoute extends CoreStaticRouteDefinition<TestAppId> {
  component: string;
}

interface TestWorkspaceRoute extends CoreWorkspaceRouteDefinition<TestAppId> {
  component: string;
}

interface TestToolViewRoute
  extends CoreToolViewRouteDefinition<TestAppId, TestNavItem> {
  component: string;
}

interface TestBackgroundWorkSource extends CoreBackgroundWorkSource {
  topic: string;
}

type TestSidebarConfig = { title: string };
type TestShellNavResolver = { id: string };
type TestShellProvider = { id: string };

function createTestRegistry() {
  return createCoreAppModuleRegistryApi<
    TestAppId,
    TestNavItem,
    TestManifest,
    TestAppBarItem,
    TestStaticRoute,
    TestWorkspaceRoute,
    TestToolViewRoute,
    TestBackgroundWorkSource,
    TestSidebarConfig,
    TestShellNavResolver,
    TestShellProvider
  >([
    {
      manifest: {
        appBarItem: { id: 'research', label: 'Research' },
        contract: {},
        globalRoutePaths: ['/research'],
        label: 'Research',
        navItems: [
          { appId: 'research', id: 'research-home', label: 'Research Home' },
        ],
        staticGlobalRoutePaths: ['/research/static'],
        staticWorkspaceRoutePaths: ['/w/:workspaceSlug/research/static'],
        workspaceRoutePaths: ['/w/:workspaceSlug/research'],
      },
      backgroundWorkSources: [
        {
          id: 'research-sync',
          requiredNavItemId: 'research-home',
          topic: 'research',
        },
      ],
      globalRoutes: [{ component: 'ResearchGlobal', path: '/research' }],
      shellNavResolver: { id: 'research-nav' },
      shellProviders: [{ id: 'research-provider' }],
      sidebarConfig: { title: 'Research' },
      toolViewRoutes: [
        {
          appId: 'research',
          component: 'ResearchTool',
          id: 'research-tool',
          match: ({ toolId }) => toolId === 'research-home',
          toolIds: ['research-home'],
        },
      ],
      workspaceRoutes: [
        {
          appId: 'research',
          component: 'ResearchWorkspace',
          path: '/w/:workspaceSlug/research',
        },
      ],
    },
    {
      manifest: {
        appBarItem: { id: 'settings', label: 'Settings' },
        contract: {},
        label: 'Settings',
        navItems: [
          {
            appId: 'settings',
            id: 'settings-profile',
            label: 'Profile',
          },
        ],
        workspaceRoutePaths: [],
      },
    },
  ]);
}

describe('createCoreAppModuleRegistryApi', () => {
  it('builds app registry projections from app module registrations', () => {
    const registry = createTestRegistry();

    expect(
      registry.APP_MODULE_MANIFESTS.map((manifest) => manifest.label),
    ).toEqual(['Research', 'Settings']);
    expect(registry.APP_BAR_ITEMS.map((item) => item.id)).toEqual([
      'research',
      'settings',
    ]);
    expect(registry.NAV_ITEMS.map((item) => item.id)).toEqual([
      'research-home',
      'settings-profile',
    ]);
    expect(registry.APP_BACKGROUND_WORK_SOURCES).toEqual([
      {
        appId: 'research',
        id: 'research-sync',
        requiredNavItemId: 'research-home',
        topic: 'research',
      },
    ]);
    expect(registry.APP_SHELL_PROVIDERS).toEqual([{ id: 'research-provider' }]);
  });

  it('exposes lookup helpers for routes and shell extension points', () => {
    const registry = createTestRegistry();
    const navItem = registry.getNavItem('research-home');

    expect(navItem?.appId).toBe('research');
    expect(registry.getAppModuleGlobalRoutes('research')).toEqual([
      {
        appId: 'research',
        component: 'ResearchGlobal',
        path: '/research',
      },
    ]);
    expect(registry.getAppModuleWorkspaceRoutes('research')).toEqual([
      {
        appId: 'research',
        component: 'ResearchWorkspace',
        path: '/w/:workspaceSlug/research',
      },
    ]);
    expect(
      registry.getToolViewRoute({ item: navItem, toolId: 'research-home' }),
    ).toMatchObject({ id: 'research-tool' });
    expect(registry.getAppModuleSidebarConfig('research')).toEqual({
      title: 'Research',
    });
    expect(registry.getAppShellNavResolver('research')).toEqual({
      id: 'research-nav',
    });
  });

  it('validates static route declarations for a registered app', () => {
    const registry = createTestRegistry();

    expect(() =>
      registry.assertAppModuleStaticRouteContract('research', {
        globalRoutes: [{ path: '/research/static' }],
        workspaceRoutes: [{ path: '/w/:workspaceSlug/research/static' }],
      }),
    ).not.toThrow();
    expect(() =>
      registry.assertAppModuleStaticRouteContract('research', {
        globalRoutes: [{ path: '/research/missing' }],
        workspaceRoutes: [{ path: '/w/:workspaceSlug/research/static' }],
      }),
    ).toThrow(
      'Static global route path /research/missing is not declared in manifest research',
    );
  });

  it('rejects registrations whose routes are not declared in the manifest', () => {
    expect(() =>
      createCoreAppModuleRegistryApi<
        TestAppId,
        TestNavItem,
        TestManifest,
        TestAppBarItem,
        TestStaticRoute,
        TestWorkspaceRoute,
        TestToolViewRoute,
        TestBackgroundWorkSource,
        TestSidebarConfig,
        TestShellNavResolver,
        TestShellProvider
      >([
        {
          manifest: {
            appBarItem: { id: 'research', label: 'Research' },
            contract: {},
            label: 'Research',
            navItems: [],
            workspaceRoutePaths: [],
          },
          workspaceRoutes: [
            {
              appId: 'research',
              component: 'ResearchWorkspace',
              path: '/w/:workspaceSlug/research',
            },
          ],
        },
      ]),
    ).toThrow(
      'Workspace route path /w/:workspaceSlug/research is not declared in manifest research',
    );
  });

  it('rejects background work sources that declare registry-owned identity', () => {
    const sourceWithExplicitOwner = {
      appId: 'research',
      id: 'research-sync',
      topic: 'research',
    };

    expect(() =>
      createCoreAppModuleRegistryApi<
        TestAppId,
        TestNavItem,
        TestManifest,
        TestAppBarItem,
        TestStaticRoute,
        TestWorkspaceRoute,
        TestToolViewRoute,
        TestBackgroundWorkSource,
        TestSidebarConfig,
        TestShellNavResolver,
        TestShellProvider
      >([
        {
          backgroundWorkSources: [sourceWithExplicitOwner],
          manifest: {
            appBarItem: { id: 'research', label: 'Research' },
            contract: {},
            label: 'Research',
            navItems: [],
            workspaceRoutePaths: [],
          },
        },
      ]),
    ).toThrow(
      'Background work source research-sync must not declare appId; the registry injects research',
    );
  });
});
