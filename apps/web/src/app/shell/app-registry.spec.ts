import { describe, expect, it } from 'vitest';
import { Home } from 'lucide-react';

import {
  APP_MODULE_MANIFESTS,
  createAppModuleRegistry,
  getNavItem,
} from './app-registry';
import { getAppSidebarConfig } from './app-sidebar-registry';
import { workspaceRouteDefinitions } from './workspace-route-registry';
import type { AppModuleManifest } from './navigation-types';

describe('app module registry', () => {
  it('rejects duplicate app ids', () => {
    const duplicateHome: AppModuleManifest = {
      appBarItem: { id: 'home', title: 'Duplicate Home', icon: Home },
      defaultActiveNavItemId: '',
      navItems: [],
      workspaceRoutePaths: [],
    };

    expect(() => createAppModuleRegistry([
      APP_MODULE_MANIFESTS[0],
      duplicateHome,
    ])).toThrow(/Duplicate app module id: home/);
  });

  it('rejects duplicate nav item ids', () => {
    const [homeManifest, aiManifest] = APP_MODULE_MANIFESTS;
    const duplicateAiNav: AppModuleManifest = {
      ...aiManifest,
      appBarItem: { id: 'learning', title: 'Duplicate Learning', icon: Home },
      navItems: [
        ...aiManifest.navItems,
        { ...aiManifest.navItems[0] },
      ],
    };

    expect(() => createAppModuleRegistry([
      homeManifest,
      duplicateAiNav,
    ])).toThrow(/Duplicate nav item id: chatbot/);
  });

  it('routes each workspace path through the owning app prefix', () => {
    for (const route of workspaceRouteDefinitions) {
      expect(route.path).toMatch(new RegExp(`^/w/:workspaceSlug/${route.appId}(?:/|$)`));
    }
  });

  it('keeps manifest workspace paths under their owning app prefix', () => {
    for (const manifest of APP_MODULE_MANIFESTS) {
      const appId = manifest.appBarItem.id;
      for (const routePath of manifest.workspaceRoutePaths) {
        expect(routePath).toMatch(new RegExp(`^/w/:workspaceSlug/${appId}(?:/|$)`));
      }
    }
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
    expect(getNavItem('search')?.appId).toBe('ai');
    expect(getNavItem('pms-tasks-assigned')?.appId).toBe('pms');
    expect(getNavItem('missing-tool')).toBeNull();
  });

  it('exposes app sidebars through the shell sidebar registry', () => {
    expect(getAppSidebarConfig('ai')).not.toBeNull();
    expect(getAppSidebarConfig('pms')).not.toBeNull();
    expect(getAppSidebarConfig('docs')).not.toBeNull();
    expect(getAppSidebarConfig('whiteboard')).not.toBeNull();
    expect(getAppSidebarConfig('learning')).not.toBeNull();
    expect(getAppSidebarConfig('home')).toBeNull();
    expect(getAppSidebarConfig('settings')).toBeNull();
  });
});
