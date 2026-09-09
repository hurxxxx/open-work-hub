import { describe, expect, it } from 'vitest';

import { resolveShellDisplayAppId } from './shell-display-app-model';

describe('resolveShellDisplayAppId', () => {
  it('uses the leaf app identity instead of its shell owner', () => {
    expect(
      resolveShellDisplayAppId({
        activeAppId: 'business',
        pathname: '/apps/retrieval-search',
      }),
    ).toBe('retrieval-search');
  });

  it('keeps the shell identity outside leaf app routes', () => {
    expect(
      resolveShellDisplayAppId({
        activeAppId: 'settings',
        pathname: '/admin/general',
      }),
    ).toBe('settings');
  });
});
