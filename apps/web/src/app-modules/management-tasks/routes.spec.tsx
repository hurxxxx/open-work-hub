import { describe, expect, it } from 'vitest';

import { HEALTH_CHECKUP_ROUTE } from './manifest';
import { managementTasksWorkspaceRoutes } from './routes';

describe('management tasks workspace routes', () => {
  it('publishes the health-checkup surface only inside a workspace', () => {
    expect(managementTasksWorkspaceRoutes).toMatchObject([
      {
        appId: 'management-tasks',
        chrome: 'fullSurface',
        path: HEALTH_CHECKUP_ROUTE,
        subSidebar: 'hidden',
      },
    ]);
  });
});
