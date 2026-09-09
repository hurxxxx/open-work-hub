import { createBootstrapApp } from '../../../tests/fixtures/company';
import { createAppsBootstrap } from '../../../tests/fixtures/company';
import { describe, expect, it } from 'vitest';

import { isBootstrapAppEnabled } from './app-bootstrap-context';

describe('app bootstrap context', () => {
  it('uses apps for access while categories remain presentation-only', () => {
    const data = createAppsBootstrap({
      apps: [
        {
          ...createBootstrapApp('docs'),
          app_id: 'docs',
          enabled: true,
          icon_key: 'file-text',
          nav_items: [],
          route_base: '/apps/docs',
          title: 'Docs',
        },
        {
          ...createBootstrapApp('mail'),
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
              coming_soon: false,
              position: 0,
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
    });

    expect(isBootstrapAppEnabled(data, 'docs')).toBe(true);
    expect(isBootstrapAppEnabled(data, 'mail')).toBe(false);
    expect(isBootstrapAppEnabled(data, 'missing')).toBe(false);
  });
});
