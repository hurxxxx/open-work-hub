import { describe, expect, it } from 'vitest';
import {
  canAccessApp,
  getEnabledAppIds,
  isAppEnabled,
  resolveAppGate,
} from './app-access';
const user = { id: 'user-1' };
describe('current server app admission', () => {
  it('projects only enabled apps', () => {
    const apps = [
      { app_id: 'docs', enabled: true },
      { app_id: 'meeting', enabled: false },
    ];
    expect([...getEnabledAppIds(apps)]).toEqual(['docs']);
    expect(isAppEnabled(apps, 'meeting')).toBe(false);
  });
  it('denies absent bootstrap and absent principal', () => {
    expect(canAccessApp({ appId: 'docs', user })).toBe(false);
    expect(
      canAccessApp({ appId: 'docs', user: null, enabledAppIds: ['docs'] }),
    ).toBe(false);
  });
  it('applies admission and revocation without outer membership', () => {
    expect(canAccessApp({ appId: 'docs', user, enabledAppIds: ['docs'] })).toBe(
      true,
    );
    expect(canAccessApp({ appId: 'docs', user, enabledAppIds: [] })).toBe(
      false,
    );
  });
  it.each([
    [null, null, true, 'failed', { status: 'principal_denied' }],
    [user, null, false, null, { status: 'loading' }],
    [
      user,
      ['docs'],
      false,
      'failed',
      { status: 'bootstrap_error', error: 'failed' },
    ],
    [user, [], false, null, { status: 'app_disabled' }],
    [user, ['docs'], false, null, { status: 'allowed' }],
  ] as const)(
    'projects gate state',
    (currentUser, ids, loading, error, expected) => {
      expect(
        resolveAppGate({
          appId: 'docs',
          user: currentUser,
          bootstrapAppIds: ids,
          bootstrapLoading: loading,
          bootstrapError: error,
        }),
      ).toEqual(expected);
    },
  );
});
