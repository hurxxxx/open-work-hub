import { describe, expect, it } from 'vitest';

import type { AppsBootstrapResponse } from '@/src/platform/apps/apps-api';
import { bootstrapEnabledAppIds, featureComingSoonItem } from './gates';

function bootstrapData(): AppsBootstrapResponse {
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
  } as AppsBootstrapResponse;
}

describe('workspace feature gates', () => {
  it('derives enabled IDs exclusively from bootstrap apps', () => {
    expect(bootstrapEnabledAppIds(bootstrapData())).toEqual(['docs']);
  });

  it('projects coming-soon content from the bootstrap app entry', () => {
    expect(featureComingSoonItem(bootstrapData(), 'docs')).toMatchObject({
      appId: 'docs',
      comingSoon: true,
      id: 'docs',
      absolutePath: '/apps/docs',
      title: 'Docs from apps',
    });
    expect(featureComingSoonItem(bootstrapData(), 'mail')).toBeNull();
  });
});
