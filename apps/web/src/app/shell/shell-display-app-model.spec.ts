import { describe, expect, it } from 'vitest';

import { resolveShellDisplayAppId } from './shell-display-app-model';

describe('resolveShellDisplayAppId', () => {
  it('uses the leaf workspace app identity instead of its shell owner', () => {
    expect(
      resolveShellDisplayAppId({
        activeAppId: 'business',
        pathname: '/w/delivery-hub/image-wizard',
      }),
    ).toBe('image-wizard');
  });

  it('keeps the shell identity outside leaf workspace routes', () => {
    expect(
      resolveShellDisplayAppId({
        activeAppId: 'settings',
        pathname: '/admin/general',
      }),
    ).toBe('settings');
  });
});
