import { describe, expect, it } from 'vitest';

import { adminRedirectRoutes, adminSectionRoutes } from './routes';

describe('settings admin app routes', () => {
  it('publishes distinct pages under the shared apps permission section', () => {
    expect(
      adminSectionRoutes
        .filter((route) => route.section === 'apps')
        .map((route) => route.path),
    ).toEqual(['/admin/apps/access', '/admin/apps/app-bar']);
  });

  it('publishes people management without legacy route aliases', () => {
    expect(
      adminSectionRoutes.find((route) => route.section === 'people'),
    ).toMatchObject({
      path: '/admin/people',
      section: 'people',
    });
    expect(adminRedirectRoutes).toEqual([]);
    expect(
      adminSectionRoutes.some((route) => route.path === '/admin/organization'),
    ).toBe(false);
  });

  it('publishes unified groups and API integration administration', () => {
    expect(
      adminSectionRoutes
        .filter((route) =>
          ['api-integrations', 'groups'].includes(route.section),
        )
        .map((route) => route.path),
    ).toEqual(['/admin/api-integrations', '/admin/groups']);
  });
});
