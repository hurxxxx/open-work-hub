import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { AppsBootstrapResponse } from '@/src/platform/apps/apps-api';
import { createAccessProjectionKey } from './access-projection-key';

const user = {
  id: 'user-1',
  system_roles: [],
  group_ids: ['group-1'],
  managed_organization_unit_ids: ['org-1'],
} as AuthUser;

const apps = {
  apps: [],
  app_bar_categories: [],
  global_route_app_ids: ['planner'],
  personal_tool_app_ids: ['planner'],
  principal: {
    kind: 'user',
    scope: 'personal',
    source: 'test',
    user_id: 'user-1',
  },
} as AppsBootstrapResponse;

describe('createAccessProjectionKey', () => {
  it('is order-stable but changes for membership, role, app, or identity changes', () => {
    const baseline = createAccessProjectionKey(user, apps);
    expect(
      createAccessProjectionKey(
        { ...user, system_roles: ['auditor', 'platform_admin'] },
        apps,
      ),
    ).toBe(
      createAccessProjectionKey(
        { ...user, system_roles: ['platform_admin', 'auditor'] },
        apps,
      ),
    );
    expect(
      createAccessProjectionKey(
        { ...user, managed_organization_unit_ids: ['org-2'] },
        apps,
      ),
    ).not.toBe(baseline);
    expect(
      createAccessProjectionKey({ ...user, group_ids: [] }, apps),
    ).not.toBe(baseline);
    expect(
      createAccessProjectionKey(user, {
        ...apps,
        apps: [
          { app_id: 'mail', enabled: true },
        ] as AppsBootstrapResponse['apps'],
      }),
    ).not.toBe(baseline);
    expect(createAccessProjectionKey({ ...user, id: 'user-2' }, apps)).not.toBe(
      baseline,
    );
  });
});
