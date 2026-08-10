import { describe, expect, it } from 'vitest';

import { NAV_ITEMS, getAppModuleManifest } from './app/shell/app-registry';
import type { AppModuleId } from './app/shell/navigation-types';
import {
  getShellPathname,
  getShellSearchParams,
  getWorkspaceAppRelativePath,
  resolveGlobalRouteAppId,
  resolveManifestNavItemId,
  resolveWorkspaceRouteAppId,
} from './app-shell-navigation-model';
import { APP_MODULE_MANIFESTS } from './app/shell/app-registry';

function resolveManifestNavItem(appId: AppModuleId, path: string): string {
  const manifest = getAppModuleManifest(appId);
  if (!manifest) {
    throw new Error(`Missing test manifest: ${appId}`);
  }
  return resolveManifestNavItemId({
    appId,
    fallbackNavItemId: manifest.defaultActiveNavItemId,
    navItems: NAV_ITEMS,
    path,
  });
}

describe('app shell navigation model', () => {
  it('separates pathname and query parameters from shell paths', () => {
    expect(
      getShellPathname('/w/delivery-hub/docs/doc-1?view=recent#page-2'),
    ).toBe('/w/delivery-hub/docs/doc-1');
    expect(getShellPathname('?view=recent')).toBe('/');

    const params = getShellSearchParams(
      '/w/delivery-hub/docs/doc-1?view=recent&page=page-1#page-2',
    );
    expect(params.get('view')).toBe('recent');
    expect(params.get('page')).toBe('page-1');
  });

  it('resolves manifest query views to navigation item ids', () => {
    expect(
      resolveManifestNavItem('collaboration', '/w/delivery-hub/docs?view=mine'),
    ).toBe('docs-my');
    expect(
      resolveManifestNavItem(
        'collaboration',
        '/w/delivery-hub/docs?view=shared',
      ),
    ).toBe('docs-shared');
    expect(
      resolveManifestNavItem(
        'collaboration',
        '/w/delivery-hub/docs?view=private',
      ),
    ).toBe('docs-private');
    expect(
      resolveManifestNavItem(
        'collaboration',
        '/w/delivery-hub/docs?view=meeting_notes',
      ),
    ).toBe('docs-notes');
    expect(
      resolveManifestNavItem(
        'collaboration',
        '/w/delivery-hub/docs/doc-1?view=recent',
      ),
    ).toBe('docs-recent');
    expect(
      resolveManifestNavItem(
        'collaboration',
        '/w/delivery-hub/docs?view=archived',
      ),
    ).toBe('docs-archived');
    expect(
      resolveManifestNavItem(
        'collaboration',
        '/w/delivery-hub/docs?view=unknown',
      ),
    ).toBe('docs-all');

    expect(
      resolveManifestNavItem('mail', '/mail?view=settings&unread=true'),
    ).toBe('mail-settings');
    expect(resolveManifestNavItem('mail', '/mail?view=drafts')).toBe(
      'mail-drafts',
    );
    expect(resolveManifestNavItem('mail', '/mail?starred=true')).toBe(
      'mail-starred',
    );
    expect(resolveManifestNavItem('mail', '/mail?unread=true')).toBe(
      'mail-unread',
    );
    expect(resolveManifestNavItem('mail', '/mail')).toBe('mail-inbox');

    expect(
      resolveManifestNavItem('business', '/w/delivery-hub/plm?tab=sql'),
    ).toBe('plm-raw-sql');
    expect(resolveManifestNavItem('business', '/w/delivery-hub/plm')).toBe(
      'plm-raw-tables',
    );

    expect(resolveManifestNavItem('planner', '/planner?view=timeline')).toBe(
      'planner-timeline',
    );
    expect(resolveManifestNavItem('planner', '/planner')).toBe(
      'planner-calendar',
    );
  });

  it('resolves workspace app ids from manifest route paths', () => {
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/w/delivery-hub/docs/doc-1',
      }),
    ).toBe('collaboration');
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/w/delivery-hub/meeting/meeting-1',
      }),
    ).toBe('collaboration');
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/w/delivery-hub/not-registered/docs/doc-1',
      }),
    ).toBeNull();
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/w/delivery-hub/not-registered',
      }),
    ).toBeNull();
    expect(
      getWorkspaceAppRelativePath('/w/delivery-hub/pms/assigned', 'pms'),
    ).toBe('/assigned');
    expect(
      getWorkspaceAppRelativePath(
        '/w/delivery-hub/not-registered/pms/assigned',
        'not-registered',
      ),
    ).toBe('/pms/assigned');
  });

  it('resolves global app ids from manifest route paths', () => {
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/docs/shared/share-1',
      }),
    ).toBe('collaboration');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/docs/shared/share-1/html/page-1',
      }),
    ).toBe('collaboration');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/whiteboard/shared/share-1',
      }),
    ).toBe('collaboration');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/community',
      }),
    ).toBe('community');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/community/posts/post-1',
      }),
    ).toBe('community');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/admin/users',
      }),
    ).toBe('settings');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/admin/unknown',
      }),
    ).toBeNull();
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/docs/shared/share-1/extra',
      }),
    ).toBeNull();
  });
});
