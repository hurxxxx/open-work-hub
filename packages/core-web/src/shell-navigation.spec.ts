import { describe, expect, it } from 'vitest';

import {
  coreRoutePathMatchesPathname,
  getCoreShellPathname,
  getCoreShellSearchParams,
  getCoreAppRelativePath,
  resolveCoreGlobalRouteAppId,
  resolveCoreManifestNavItemId,
  resolveCoreAppRouteAppId,
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
    appRoutePaths: ['/apps/research', '/apps/research/articles/:articleId'],
  },
  {
    appBarItem: { id: 'settings' },
    staticGlobalRoutePaths: ['/admin/general'],
    appRoutePaths: [],
  },
];

describe('core shell navigation model', () => {
  it('separates pathname and query parameters from shell paths', () => {
    expect(
      getCoreShellPathname('/apps/research/doc-1?view=recent#page-2'),
    ).toBe('/apps/research/doc-1');
    expect(getCoreShellPathname('?view=recent')).toBe('/');

    const params = getCoreShellSearchParams(
      '/apps/research/doc-1?view=recent&page=page-1#page-2',
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
        path: '/apps/research/articles?status=pending',
      }),
    ).toBe('research-pending');

    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/apps/research?view=archived',
      }),
    ).toBe('research-archived');

    expect(
      resolveCoreManifestNavItemId({
        appId: 'research',
        fallbackNavItemId: 'research-all',
        navItems,
        path: '/apps/research?view=unknown',
      }),
    ).toBe('research-all');
  });

  it('resolves app ids from app and global manifest route paths', () => {
    expect(
      resolveCoreAppRouteAppId({
        manifests,
        pathname: '/apps/research/articles/article-1',
      }),
    ).toBe('research');
    expect(
      resolveCoreAppRouteAppId({
        manifests,
        pathname: '/apps/unknown',
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

  it('matches route path patterns and app relative paths', () => {
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
        '/apps/research/articles/*',
        '/apps/research/articles',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/articles/*',
        '/apps/research/articles/article-1/page-2',
      ),
    ).toBe(true);
    expect(
      coreRoutePathMatchesPathname(
        '/apps/research/articles/*',
        '/apps/research',
      ),
    ).toBe(false);
    expect(getCoreAppRelativePath('/apps/research/articles', 'research')).toBe(
      '/articles',
    );
  });
});
