import { describe, expect, it } from 'vitest';

import { isWorkspaceBootstrapAppEnabled } from './workspace-bootstrap-context';
import type { WorkspaceBootstrapResponse } from './workspaces-api';

describe('workspace bootstrap context', () => {
  it('uses apps for access while categories remain presentation-only', () => {
    const data = {
      apps: [
        {
          app_id: 'docs',
          enabled: true,
          icon_key: 'file-text',
          nav_items: [],
          route_base: '/docs',
          title: 'Docs',
        },
        {
          app_id: 'mail',
          enabled: false,
          icon_key: 'mail',
          nav_items: [],
          route_base: '/mail',
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
              route_base: '/mail',
              title: 'Mail',
            },
          ],
          key: 'team-tools',
          position: 0,
          title: 'Team tools',
        },
      ],
    } as WorkspaceBootstrapResponse;

    expect(isWorkspaceBootstrapAppEnabled(data, 'docs')).toBe(true);
    expect(isWorkspaceBootstrapAppEnabled(data, 'mail')).toBe(false);
    expect(isWorkspaceBootstrapAppEnabled(data, 'missing')).toBe(false);
  });
});
