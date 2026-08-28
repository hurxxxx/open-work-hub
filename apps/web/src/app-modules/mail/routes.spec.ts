import { describe, expect, it } from 'vitest';

import { mailManifest } from './manifest';
import { mailGlobalRoutes } from './routes';

describe('personal Mail routes', () => {
  it('declares only the canonical global route', () => {
    expect(mailGlobalRoutes.map((route) => route.path)).toEqual(['/apps/mail']);
    expect(mailManifest.workspaceRoutePaths).toEqual([]);
    expect(mailManifest.globalRoutePaths).toEqual(['/apps/mail']);
  });
});
