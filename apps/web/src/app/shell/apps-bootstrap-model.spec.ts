import {
  createAppsBootstrap,
  createBootstrapApp,
} from '../../../tests/fixtures/company';
import { describe, expect, it } from 'vitest';

import type { AppsBootstrapResponse } from '@/src/platform/apps/apps-api';
import {
  PERSONAL_TOOLS_CATEGORY_ID,
  projectShellAppsBootstrap,
} from './apps-bootstrap-model';

function globalBootstrap(
  personalToolIds: string[] = ['mail', 'planner'],
): AppsBootstrapResponse {
  const personalTools = personalToolIds.map((appId) => ({
    ...createBootstrapApp(appId),
    app_id: appId,
    title: appId,
    route_base: `/apps/${appId}`,
    icon_key: appId === 'mail' ? 'mail' : 'calendar',
    enabled: true,
    coming_soon: false,
  }));
  const community = {
    ...createBootstrapApp('community'),
    app_id: 'community',
    title: 'Community',
    route_base: '/apps/community',
    icon_key: 'messages-square',
    enabled: true,
    coming_soon: false,
  };
  return createAppsBootstrap({
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
    personal_tool_app_ids: personalToolIds,
    principal: {
      kind: 'user',
      source: 'test',
      user_id: 'user-1',
    },
  });
}

describe('projectShellAppsBootstrap', () => {
  it('projects only launchable apps and creates a fixed non-pinnable personal tools launcher', () => {
    const projection = projectShellAppsBootstrap({
      globalBootstrap: globalBootstrap(),
      personalToolsScope: 'Personal tools',
      personalToolsTitle: 'Personal',
    });

    expect(projection.enabledAppIds).toEqual(['community', 'mail', 'planner']);
    expect(projection.appBarCategories[0]).toMatchObject({
      id: PERSONAL_TOOLS_CATEGORY_ID,
      title: 'Personal',
      contextLabel: 'Personal tools',
      pinnable: false,
    });
    expect(
      projection.appBarCategories[0]?.items.map((item) => item.app_id),
    ).toEqual(['mail', 'planner']);
    expect(
      projection.appBarCategories[1]?.items.map((item) => item.app_id),
    ).toEqual(['community']);
  });

  it('omits the personal tools launcher when every personal app is disabled', () => {
    const projection = projectShellAppsBootstrap({
      globalBootstrap: globalBootstrap([]),
      personalToolsScope: 'Personal tools',
      personalToolsTitle: 'Personal',
    });

    expect(
      projection.appBarCategories.some(
        (category) => category.id === PERSONAL_TOOLS_CATEGORY_ID,
      ),
    ).toBe(false);
  });

  it('uses the same current app admission projection for every route', () => {
    const projection = projectShellAppsBootstrap({
      globalBootstrap: globalBootstrap(['mail']),
      personalToolsScope: 'Personal tools',
      personalToolsTitle: 'Personal',
    });

    expect(projection.enabledAppIds).toEqual(['community', 'mail']);
    expect(projection.globalRouteAppIds).toEqual(['community', 'mail']);
  });
});
