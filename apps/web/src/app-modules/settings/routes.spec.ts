import { describe, expect, it } from 'vitest';

import { adminRedirectRoutes, adminSectionRoutes } from './routes';

describe('settings admin app routes', () => {
  it('publishes distinct pages under the shared apps permission section', () => {
    expect(
      adminSectionRoutes
        .filter((route) => route.section === 'apps')
        .map((route) => route.path),
    ).toEqual([
      '/admin/apps/platform',
      '/admin/apps/workspace',
      '/admin/apps/app-bar',
    ]);
  });

  it('keeps the old apps URL as a redirect alias', () => {
    expect(adminRedirectRoutes.map((route) => route.path)).toContain(
      '/admin/apps',
    );
  });

});
