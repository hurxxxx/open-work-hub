import { describe, expect, it } from 'vitest';

import type { WorkspaceBootstrapResponse } from '@/src/platform/workspaces/workspaces-api';
import {
  workspaceBootstrapEnabledAppIds,
  workspaceFeatureComingSoonItem,
} from './gates';

function bootstrapData(): WorkspaceBootstrapResponse {
  return {
    apps: [
      {
        app_id: 'docs',
        coming_soon: true,
        enabled: true,
        icon_key: 'file-text',
        nav_items: [],
        route_base: '/apps/docs',
        title: 'Docs from apps',
      },
      {
        app_id: 'mail',
        enabled: false,
        icon_key: 'mail',
        nav_items: [],
        route_base: '/apps/mail',
        title: 'Mail',
      },
    ],
    nav: [],
    workspace: {
      id: 'workspace-1',
      name: 'Workspace 1',
      role: 'member',
      slug: 'workspace-1',
    },
  } as WorkspaceBootstrapResponse;
}

describe('workspace feature gates', () => {
  it('derives enabled IDs exclusively from bootstrap apps', () => {
    expect(workspaceBootstrapEnabledAppIds(bootstrapData())).toEqual(['docs']);
  });

  it('projects coming-soon content from the bootstrap app entry', () => {
    expect(
      workspaceFeatureComingSoonItem(bootstrapData(), 'docs'),
    ).toMatchObject({
      appId: 'docs',
      comingSoon: true,
      id: 'docs',
      absolutePath: '/apps/docs',
      title: 'Docs from apps',
    });
    expect(workspaceFeatureComingSoonItem(bootstrapData(), 'mail')).toBeNull();
  });
});
