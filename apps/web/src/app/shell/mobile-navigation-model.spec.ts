import { Home, Settings, Users } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import type { AppBarItem } from './navigation-types';
import { projectMobileNavigationItems } from './mobile-navigation-model';

const appBarItems: readonly AppBarItem[] = [
  { id: 'home', title: 'Home', icon: Home },
  { id: 'settings', title: 'Settings', icon: Settings },
];

describe('mobile navigation model', () => {
  it('uses ordered dynamic categories and links the first enabled ready leaf', () => {
    const items = projectMobileNavigationItems({
      appBarItems,
      fixedAppIds: ['home'],
      workspaceApps: [
        {
          app_id: 'home',
          enabled: true,
          icon_key: 'home',
          nav_items: [],
          route_base: '/home',
          title: 'Home',
        },
        {
          app_id: 'docs',
          enabled: true,
          icon_key: 'file-text',
          nav_items: [],
          route_base: '/docs',
          title: 'Docs',
        },
        {
          app_id: 'pms',
          coming_soon: true,
          enabled: true,
          icon_key: 'list-checks',
          nav_items: [],
          route_base: '/pms',
          title: 'PMS',
        },
        {
          app_id: 'web-search',
          enabled: true,
          icon_key: 'globe',
          nav_items: [],
          route_base: '/web-search',
          title: 'Web Search',
        },
      ],
      appBarCategories: [
        {
          id: 'custom-business-id',
          icon_key: 'briefcase',
          items: [
            {
              app_id: 'web-search',
              enabled: true,
              icon_key: 'globe',
              route_base: '/web-search',
              title: 'Web Search',
            },
          ],
          key: 'custom-business',
          position: 20,
          title: 'Custom business tools',
        },
        {
          id: 'team-space-id',
          icon_key: 'users',
          items: [
            {
              app_id: 'pms',
              enabled: true,
              icon_key: 'list-checks',
              route_base: '/pms',
              title: 'PMS',
            },
            {
              app_id: 'docs',
              enabled: true,
              icon_key: 'file-text',
              route_base: '/docs',
              title: 'Docs',
            },
          ],
          key: 'team-space',
          position: 10,
          title: 'Team space',
        },
        {
          id: 'empty-id',
          icon_key: 'folder',
          items: [],
          key: 'empty',
          position: 0,
          title: 'Empty',
        },
      ],
    });

    expect(
      items.map(({ activeAppIds, id, linkAppId, title, type }) => ({
        activeAppIds,
        id,
        linkAppId,
        title,
        type,
      })),
    ).toEqual([
      {
        activeAppIds: ['home'],
        id: 'home',
        linkAppId: 'home',
        title: 'Home',
        type: 'app',
      },
      {
        activeAppIds: ['docs'],
        id: 'team-space-id',
        linkAppId: 'docs',
        title: 'Team space',
        type: 'category',
      },
      {
        activeAppIds: ['web-search'],
        id: 'custom-business-id',
        linkAppId: 'web-search',
        title: 'Custom business tools',
        type: 'category',
      },
    ]);
    expect(items[1]?.icon).toBe(Users);
  });

  it('projects every registry-derived fixed app without duplicating categories', () => {
    const items = projectMobileNavigationItems({
      appBarCategories: [
        {
          id: 'tools',
          icon_key: 'briefcase',
          items: [
            {
              app_id: 'fixed-feature',
              enabled: true,
              icon_key: 'sparkles',
              route_base: '/fixed-feature',
              title: 'Fixed feature',
            },
          ],
          key: 'tools',
          position: 0,
          title: 'Tools',
        },
      ],
      appBarItems,
      fixedAppIds: ['home', 'fixed-feature'],
      workspaceApps: [
        {
          app_id: 'home',
          enabled: true,
          icon_key: 'home',
          nav_items: [],
          route_base: '/home',
          title: 'Home',
        },
        {
          app_id: 'fixed-feature',
          enabled: true,
          icon_key: 'sparkles',
          nav_items: [],
          route_base: '/fixed-feature',
          title: 'Fixed feature',
        },
      ],
    });

    expect(items.map((item) => item.id)).toEqual(['home', 'fixed-feature']);
    expect(items.every((item) => item.type === 'app')).toBe(true);
  });
});
