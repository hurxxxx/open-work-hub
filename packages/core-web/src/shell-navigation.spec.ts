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
    globalRoutePaths: ['/research/public/:shareId'],
    staticGlobalRoutePaths: ['/research/help'],
    workspaceRoutePaths: [
      '/w/:workspaceSlug/research',
      '/w/:workspaceSlug/research/articles/:articleId',
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
      getCoreShellPathname('/w/lab/research/doc-1?view=recent#page-2'),
    ).toBe('/w/lab/research/doc-1');
    expect(getCoreShellPathname('?view=recent')).toBe('/');

    const params = getCoreShellSearchParams(
      '/w/lab/research/doc-1?view=recent&page=page-1#page-2',
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
        path: '/w/lab/research/articles?status=pending',
      }),
    ).toBe('research-pending');

    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/w/lab/research?view=archived',
      }),
    ).toBe('research-archived');

    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/w/lab/research?view=unknown',
      }),
    ).toBe('research-all');
  });

  it('resolves app ids from workspace and global manifest route paths', () => {
    expect(
      resolveCoreWorkspaceRouteAppId({
        manifests,
        pathname: '/w/lab/research/articles/article-1',
      }),
    ).toBe('research');
    expect(
      resolveCoreWorkspaceRouteAppId({
        manifests,
        pathname: '/w/lab/unknown',
      }),
    ).toBeNull();

    expect(
      resolveCoreGlobalRouteAppId({
        manifests,
        pathname: '/research/public/share-1',
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
        '/research/public/:shareId',
        '/research/public/share-1',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/research/public/:shareId',
        '/research/public/share-1/extra',
      ),
    ).toBe(false);
    expect(
      coreRoutePathMatchesPathname(
        '/w/:workspaceSlug/research/articles/*',
        '/w/lab/research/articles',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/w/:workspaceSlug/research/articles/*',
        '/w/lab/research/articles/article-1/page-2',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/w/:workspaceSlug/research/articles/*',
        '/w/lab/research',
      ),
    ).toBe(false);
    expect(
      getCoreWorkspaceAppRelativePath('/w/lab/research/articles', 'research'),
    ).toBe('/articles');
  });
});
