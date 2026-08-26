import { describe, expect, it } from 'vitest';

import {
  getLoginErrorMessage,
  getLoginModeFlags,
  groupDevLoginAccounts,
  INITIAL_LOGIN_FORM_STATE,
  loginFormReducer,
  type DevLoginAccountLike,
} from './login-screen-model';

function account(overrides: Partial<DevLoginAccountLike>): DevLoginAccountLike {
  return {
    account_key: 'account-1',
    category: 'Ops',
    description: 'Seed account',
    email: 'seed@example.test',
    label: 'Seed',
    ...overrides,
  };
}

describe('login screen model', () => {
  it('updates fields, mode, and submitting state', () => {
    const withLoginId = loginFormReducer(INITIAL_LOGIN_FORM_STATE, {
      type: 'fieldChanged',
      field: 'loginId',
      value: 'admin',
    });

    expect(withLoginId).toMatchObject({
      loginId: 'admin',
    });
    expect(
      loginFormReducer(withLoginId, { type: 'submitStarted' }),
    ).toMatchObject({
      submitting: true,
    });
    expect(
      loginFormReducer(withLoginId, { type: 'modeChanged', mode: 'signup' }),
    ).toMatchObject({
      mode: 'signup',
    });
  });

  it('keeps grouped development accounts in first-seen category order', () => {
    const opsAdmin = account({
      account_key: 'ops-admin',
      category: 'Ops',
      email: 'ops-admin@example.test',
    });
    const salesAdmin = account({
      account_key: 'sales-admin',
      category: 'Sales',
      email: 'sales-admin@example.test',
    });
    const opsMember = account({
      account_key: 'ops-member',
      category: 'Ops',
      email: 'ops-member@example.test',
    });

    expect(groupDevLoginAccounts([opsAdmin, salesAdmin, opsMember])).toEqual([
      { category: 'Ops', accounts: [opsAdmin, opsMember] },
      { category: 'Sales', accounts: [salesAdmin] },
    ]);
  });

  it('derives setup, sign-up, and login mode flags', () => {
    expect(
      getLoginModeFlags({
        devAccountGroupCount: 2,
        mode: 'login',
        requiresSetup: true,
      }),
    ).toEqual({
      isSetupMode: true,
      isSignupMode: false,
      hasDevAccountButtons: false,
    });

    expect(
      getLoginModeFlags({
        devAccountGroupCount: 2,
        mode: 'signup',
        requiresSetup: false,
      }),
    ).toEqual({
      isSetupMode: false,
      isSignupMode: true,
      hasDevAccountButtons: false,
    });

    expect(
      getLoginModeFlags({
        devAccountGroupCount: 2,
        mode: 'login',
        requiresSetup: false,
      }),
    ).toEqual({
      isSetupMode: false,
      isSignupMode: false,
      hasDevAccountButtons: true,
    });
  });

  it('uses thrown error messages before fallback text', () => {
    expect(
      getLoginErrorMessage(new Error('Network unavailable'), 'Fallback'),
    ).toBe('Network unavailable');
    expect(getLoginErrorMessage(new Error(''), 'Fallback')).toBe('Fallback');
    expect(getLoginErrorMessage('not an error', 'Fallback')).toBe('Fallback');
  });
});
