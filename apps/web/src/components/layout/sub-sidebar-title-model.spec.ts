import { describe, expect, it } from 'vitest';
import { FileText } from 'lucide-react';

import { resolveSubSidebarTitle } from './sub-sidebar-title-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (key === 'sidebar.allSettings') return 'All settings';
  if (key === 'apps.docs') return '문서';
  if (key === 'apps.community') return '커뮤니티';
  return String(options?.defaultValue ?? key);
}

describe('sub sidebar title model', () => {
  it('uses the active leaf app title from workspace bootstrap', () => {
    expect(
      resolveSubSidebarTitle({
        activeAppId: 'docs',
        appBarItems: [],
        t,
        appRegistry: new Map([
          [
            'docs',
            {
              app_id: 'docs',
              enabled: true,
              icon_key: 'docs',
              nav_items: [],
              route_base: '/apps/docs',
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
        appBarItems: [{ id: 'community', title: 'community', icon: FileText }],
        t,
        appRegistry: new Map(),
      }),
    ).toBe('커뮤니티');
  });
});
