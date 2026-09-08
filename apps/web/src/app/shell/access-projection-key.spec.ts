import {
  createAuthUser,
  createAppsBootstrap,
  createBootstrapApp,
} from '../../../tests/fixtures/company';
import { describe, expect, it } from 'vitest';

import { createAccessProjectionKey } from './access-projection-key';

const user = createAuthUser({
  id: 'user-1',
  system_roles: [],
  group_ids: ['group-1'],
  managed_organization_unit_ids: ['org-1'],
});

const apps = createAppsBootstrap({
  apps: [],
  app_bar_categories: [],
  personal_tool_app_ids: ['planner'],
  principal: {
    kind: 'user',
    source: 'test',
    user_id: 'user-1',
  },
});

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
        apps: [createBootstrapApp('mail')],
      }),
    ).not.toBe(baseline);
    expect(createAccessProjectionKey({ ...user, id: 'user-2' }, apps)).not.toBe(
      baseline,
    );
  });
});
