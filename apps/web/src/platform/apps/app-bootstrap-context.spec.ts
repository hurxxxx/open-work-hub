import { describe, expect, it } from 'vitest';

import { isBootstrapAppEnabled } from './app-bootstrap-context';
import type { AppsBootstrapResponse } from './apps-api';

describe('workspace bootstrap context', () => {
  it('uses apps for access while categories remain presentation-only', () => {
    const data = {
      apps: [
        {
          app_id: 'docs',
          enabled: true,
          icon_key: 'file-text',
          nav_items: [],
          route_base: '/apps/docs',
          title: 'Docs',
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
      app_bar_categories: [
        {
          icon_key: 'users',
          id: 'team-tools',
          items: [
            {
              app_id: 'mail',
              enabled: true,
              icon_key: 'mail',
              route_base: '/apps/mail',
              title: 'Mail',
            },
          ],
          key: 'team-tools',
          position: 0,
          title: 'Team tools',
        },
      ],
    } as AppsBootstrapResponse;

    expect(isBootstrapAppEnabled(data, 'docs')).toBe(true);
    expect(isBootstrapAppEnabled(data, 'mail')).toBe(false);
    expect(isBootstrapAppEnabled(data, 'missing')).toBe(false);
  });
});
