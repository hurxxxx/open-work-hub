import { describe, expect, it } from 'vitest';

import {
  coreRoutePathMatchesPathname,
  getCoreShellPathname,
  getCoreShellSearchParams,
  getCoreWorkspaceAppRelativePath,
  resolveCoreGlobalRouteAppId,
  resolveCoreManifestNavItemId,
  resolveCoreWorkspaceRouteAppId,
  type CoreShellNavigationManifest,
  type CoreShellNavigationNavItem,
} from './shell-navigation';

type TestAppId = 'research' | 'settings';

const navItems: readonly CoreShellNavigationNavItem<TestAppId>[] = [
  {
    appId: 'research',
    id: 'research-all',
  },
  {
    appId: 'research',
    id: 'research-articles',
    pathSuffix: '/articles',
  },
  {
    appId: 'research',
    id: 'research-pending',
    pathSuffix: '/articles?status=pending',
  },
  {
    appId: 'research',
    id: 'research-archived',
    pathSuffix: '?view=archived',
  },
];

const manifests: readonly CoreShellNavigationManifest<TestAppId>[] = [
  {
    appBarItem: { id: 'research' },
    globalRoutePaths: ['/apps/research/public/:shareId'],
    staticGlobalRoutePaths: ['/research/help'],
    workspaceRoutePaths: [
      '/apps/research/workspaces/:workspaceSlug',
      '/apps/research/workspaces/:workspaceSlug/articles/:articleId',
    ],
  },
  {
    appBarItem: { id: 'settings' },
    staticGlobalRoutePaths: ['/admin/general'],
    workspaceRoutePaths: [],
  },
];

describe('core shell navigation model', () => {
  it('separates pathname and query parameters from shell paths', () => {
    expect(
      getCoreShellPathname(
        '/apps/research/workspaces/lab/doc-1?view=recent#page-2',
      ),
    ).toBe('/apps/research/workspaces/lab/doc-1');
    expect(getCoreShellPathname('?view=recent')).toBe('/');

    const params = getCoreShellSearchParams(
      '/apps/research/workspaces/lab/doc-1?view=recent&page=page-1#page-2',
    );
    expect(params.get('view')).toBe('recent');
    expect(params.get('page')).toBe('page-1');
  });

  it('resolves manifest path and query suffixes to nav item ids', () => {
    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/apps/research/workspaces/lab/articles?status=pending',
      }),
    ).toBe('research-pending');

    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/apps/research/workspaces/lab?view=archived',
      }),
    ).toBe('research-archived');

    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/apps/research/workspaces/lab?view=unknown',
      }),
    ).toBe('research-all');
  });

  it('resolves app ids from workspace and global manifest route paths', () => {
    expect(
      resolveCoreWorkspaceRouteAppId({
        manifests,
        pathname: '/apps/research/workspaces/lab/articles/article-1',
      }),
    ).toBe('research');
    expect(
      resolveCoreWorkspaceRouteAppId({
        manifests,
        pathname: '/apps/unknown/workspaces/lab',
      }),
    ).toBeNull();

    expect(
      resolveCoreGlobalRouteAppId({
        manifests,
        pathname: '/apps/research/public/share-1',
      }),
    ).toBe('research');
    expect(
      resolveCoreGlobalRouteAppId({
        manifests,
        pathname: '/admin/general',
      }),
    ).toBe('settings');
    expect(
      resolveCoreGlobalRouteAppId({
        manifests,
        pathname: '/admin/unknown',
      }),
    ).toBeNull();
  });

  it('matches route path patterns and workspace app relative paths', () => {
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/public/:shareId',
        '/apps/research/public/share-1',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/public/:shareId',
        '/apps/research/public/share-1/extra',
      ),
    ).toBe(false);
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/workspaces/:workspaceSlug/articles/*',
        '/apps/research/workspaces/lab/articles',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/workspaces/:workspaceSlug/articles/*',
        '/apps/research/workspaces/lab/articles/article-1/page-2',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/workspaces/:workspaceSlug/articles/*',
        '/apps/research/workspaces/lab',
      ),
    ).toBe(false);
    expect(
      getCoreWorkspaceAppRelativePath(
        '/apps/research/workspaces/lab/articles',
        'research',
      ),
    ).toBe('/articles');
  });
});
