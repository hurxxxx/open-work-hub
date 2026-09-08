import { describe, expect, it } from 'vitest';
import {
  canAccessCoreApp,
  getCoreEnabledAppIds,
  isCoreAppEnabled,
  resolveCoreAppGate,
} from './app-access';

const user = { id: 'account' };
describe('current app admission projection', () => {
  it('denies when bootstrap is absent instead of inferring access from account existence', () => {
    expect(canAccessCoreApp({ appId: 'docs', user })).toBe(false);
    expect(canAccessCoreApp({ appId: 'docs', user, enabledAppIds: [] })).toBe(
      false,
    );
    expect(
      canAccessCoreApp({ appId: 'docs', user: null, enabledAppIds: ['docs'] }),
    ).toBe(false);
  });
  it('uses only enabled app rows and reflects revocation', () => {
    const apps = [
      { app_id: 'docs', enabled: true },
      { app_id: 'pms', enabled: false },
    ];
    expect([...getCoreEnabledAppIds(apps)]).toEqual(['docs']);
    expect(isCoreAppEnabled(apps, 'pms')).toBe(false);
    expect(
      canAccessCoreApp({
        appId: 'docs',
        user,
        enabledAppIds: [...getCoreEnabledAppIds(apps)],
      }),
    ).toBe(true);
    apps[0].enabled = false;
    expect(
      canAccessCoreApp({
        appId: 'docs',
        user,
        enabledAppIds: [...getCoreEnabledAppIds(apps)],
      }),
    ).toBe(false);
  });
  it.each([
    [null, null, false, null, { status: 'principal_denied' }],
    [user, null, false, null, { status: 'loading' }],
    [user, ['docs'], true, null, { status: 'loading' }],
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
    'projects principal/loading/error/allowed state',
    (currentUser, ids, loading, error, expected) => {
      expect(
        resolveCoreAppGate({
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
