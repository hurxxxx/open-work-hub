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
      getShellPathname(
        '/apps/docs/workspaces/delivery-hub/documents/doc-1?view=recent#page-2',
      ),
    ).toBe('/apps/docs/workspaces/delivery-hub/documents/doc-1');
    expect(getShellPathname('?view=recent')).toBe('/');

    const params = getShellSearchParams(
      '/apps/docs/workspaces/delivery-hub/documents/doc-1?view=recent&page=page-1#page-2',
    );
    expect(params.get('view')).toBe('recent');
    expect(params.get('page')).toBe('page-1');
  });

  it('resolves manifest query views to navigation item ids', () => {
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub?view=mine',
      ),
    ).toBe('docs-my');
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub?view=shared',
      ),
    ).toBe('docs-shared');
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub?view=private',
      ),
    ).toBe('docs-private');
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub?view=meeting_notes',
      ),
    ).toBe('docs-notes');
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub/documents/doc-1?view=recent',
      ),
    ).toBe('docs-recent');
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub?view=archived',
      ),
    ).toBe('docs-archived');
    expect(
      resolveManifestNavItem(
        'docs',
        '/apps/docs/workspaces/delivery-hub?view=unknown',
      ),
    ).toBe('docs-all');

    expect(
      resolveManifestNavItem('mail', '/apps/mail?view=settings&unread=true'),
    ).toBe('mail-settings');
    expect(resolveManifestNavItem('mail', '/apps/mail?view=drafts')).toBe(
      'mail-drafts',
    );
    expect(resolveManifestNavItem('mail', '/apps/mail?starred=true')).toBe(
      'mail-starred',
    );
    expect(resolveManifestNavItem('mail', '/apps/mail?unread=true')).toBe(
      'mail-unread',
    );
    expect(resolveManifestNavItem('mail', '/apps/mail')).toBe('mail-inbox');

    expect(
      resolveManifestNavItem('planner', '/apps/planner?view=timeline'),
    ).toBe('planner-timeline');
    expect(resolveManifestNavItem('planner', '/apps/planner')).toBe(
      'planner-calendar',
    );
  });

  it('resolves workspace app ids from manifest route paths', () => {
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/docs/workspaces/delivery-hub/documents/doc-1',
      }),
    ).toBe('docs');
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/meeting/workspaces/delivery-hub/meetings/meeting-1',
      }),
    ).toBe('meeting');
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname:
          '/apps/not-registered/workspaces/delivery-hub/documents/doc-1',
      }),
    ).toBeNull();
    expect(
      resolveWorkspaceRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/not-registered/workspaces/delivery-hub',
      }),
    ).toBeNull();
    expect(
      getWorkspaceAppRelativePath(
        '/apps/pms/workspaces/delivery-hub/assigned',
        'pms',
      ),
    ).toBe('/assigned');
    expect(
      getWorkspaceAppRelativePath(
        '/apps/not-registered/workspaces/delivery-hub/pms/assigned',
        'not-registered',
      ),
    ).toBe('/pms/assigned');
  });

  it('resolves global app ids from manifest route paths', () => {
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/docs/shared/share-1',
      }),
    ).toBe('docs');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/docs/shared/share-1/html/page-1',
      }),
    ).toBe('docs');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/whiteboard/shared/share-1',
      }),
    ).toBe('whiteboard');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/community',
      }),
    ).toBe('community');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/community/posts/post-1',
      }),
    ).toBe('community');
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/admin/unknown',
      }),
    ).toBeNull();
    expect(
      resolveGlobalRouteAppId({
        manifests: APP_MODULE_MANIFESTS,
        pathname: '/apps/docs/shared/share-1/extra',
      }),
    ).toBeNull();
  });
});
