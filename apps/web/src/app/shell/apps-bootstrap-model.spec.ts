import { describe, expect, it } from 'vitest';

import type {
  AppsBootstrapResponse,
  WorkspaceBootstrapApp,
} from '@/src/platform/workspaces/workspaces-api';
import {
  PERSONAL_TOOLS_CATEGORY_ID,
  projectShellAppsBootstrap,
} from './apps-bootstrap-model';

function workspaceApp(appId: string): WorkspaceBootstrapApp {
  return {
    app_id: appId,
    title: appId,
    route_base: `/${appId}`,
    icon_key: 'box',
    enabled: true,
    coming_soon: false,
    nav_items: [],
  };
}

function globalBootstrap(
  personalToolIds: string[] = ['mail', 'planner'],
): AppsBootstrapResponse {
  const personalTools = personalToolIds.map((appId) => ({
    app_id: appId,
    title: appId,
    route_base: `/${appId}`,
    icon_key: appId === 'mail' ? 'mail' : 'calendar',
    availability_scope: 'platform' as const,
    enabled: true,
    coming_soon: false,
  }));
  const community = {
    app_id: 'community',
    title: 'Community',
    route_base: '/community',
    icon_key: 'messages-square',
    availability_scope: 'platform' as const,
    enabled: true,
    coming_soon: false,
  };
  return {
    apps: [community, ...personalTools],
    app_bar_categories: [
      {
        id: 'collaboration',
        key: 'collaboration',
        title: 'Collaboration',
        icon_key: 'users',
        position: 2,
        items: [
          {
            ...community,
            position: 2,
          },
        ],
      },
    ],
    personal_tools: personalTools,
    platform_enabled_app_ids: ['community', ...personalToolIds],
    principal: {
      kind: 'user',
      scope: 'personal',
      workspace_id: null,
      source: 'test',
      user_id: 'user-1',
    },
  };
}

describe('projectShellAppsBootstrap', () => {
  it('merges platform apps and creates a fixed non-pinnable personal tools launcher', () => {
    const projection = projectShellAppsBootstrap({
      globalBootstrap: globalBootstrap(),
      personalToolsScope: 'All workspaces',
      personalToolsTitle: 'Personal',
      workspaceApps: [workspaceApp('home'), workspaceApp('docs')],
      workspaceCategories: [
        {
          id: 'collaboration',
          key: 'collaboration',
          title: 'Collaboration',
          icon_key: 'users',
          position: 2,
          items: [
            {
              app_id: 'docs',
              title: 'Docs',
              route_base: '/docs',
              icon_key: 'file-text',
              enabled: true,
              position: 1,
            },
          ],
        },
      ],
    });

    expect(projection.enabledAppIds).toEqual([
      'home',
      'docs',
      'community',
      'mail',
      'planner',
    ]);
    expect(projection.appBarCategories[0]).toMatchObject({
      id: PERSONAL_TOOLS_CATEGORY_ID,
      title: 'Personal',
      contextLabel: 'All workspaces',
      pinnable: false,
    });
    expect(
      projection.appBarCategories[0]?.items.map((item) => item.app_id),
    ).toEqual(['mail', 'planner']);
    expect(
      projection.appBarCategories[1]?.items.map((item) => item.app_id),
    ).toEqual(['docs', 'community']);
  });

  it('omits the personal tools launcher when every personal app is disabled', () => {
    const projection = projectShellAppsBootstrap({
      globalBootstrap: globalBootstrap([]),
      personalToolsScope: 'All workspaces',
      personalToolsTitle: 'Personal',
      workspaceApps: [],
      workspaceCategories: [],
    });

    expect(
      projection.appBarCategories.some(
        (category) => category.id === PERSONAL_TOOLS_CATEGORY_ID,
      ),
    ).toBe(false);
  });
});
