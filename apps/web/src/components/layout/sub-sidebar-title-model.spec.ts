import { describe, expect, it } from 'vitest';
import { FileText, Users } from 'lucide-react';

import { resolveSubSidebarTitle } from './sub-sidebar-title-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (key === 'sidebar.allSettings') return 'All settings';
  if (key === 'apps.docs') return '문서';
  if (key === 'apps.collaboration') return '협업';
  if (key === 'apps.community') return '커뮤니티';
  return String(options?.defaultValue ?? key);
}

describe('sub sidebar title model', () => {
  it('uses the active feature app title before the parent app title', () => {
    expect(
      resolveSubSidebarTitle({
        activeAppId: 'collaboration',
        activeFeatureAppId: 'docs',
        appBarItems: [
          { id: 'collaboration', title: 'collaboration', icon: Users },
        ],
        t,
        workspaceAppRegistry: new Map([
          [
            'docs',
            {
              app_id: 'docs',
              enabled: true,
              icon_key: 'docs',
              nav_items: [],
              route_base: '/docs',
              title: 'Docs',
            },
          ],
        ]),
      }),
    ).toBe('문서');
  });

  it('uses the active app title when there is no feature app', () => {
    expect(
      resolveSubSidebarTitle({
        activeAppId: 'community',
        activeFeatureAppId: null,
        appBarItems: [{ id: 'community', title: 'community', icon: FileText }],
        t,
        workspaceAppRegistry: new Map(),
      }),
    ).toBe('커뮤니티');
  });
});
