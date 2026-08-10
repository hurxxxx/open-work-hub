import { describe, expect, it } from 'vitest';

import type {
  AuthUser,
  BootstrapStatusResponse,
  DevLoginAccount,
} from './auth-api';
import {
  initialAuthState,
  projectRefreshSession,
  toAuthenticatedAuthState,
} from './auth-session-model';

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    app_bar_layout: { pinned_app_ids: [] },
    date_format: 'korean',
    display_name: 'AI-DO Member',
    email: 'member@ai-do.local',
    full_name: 'AI-DO Member',
    id: 'user-1',
    job_title: null,
    last_login_at: null,
    locale: 'ko-KR',
    login_id: 'member',
    must_change_password: false,
    primary_org_unit: null,
    status: 'active',
    system_roles: [],
    theme_preference: 'system',
    time_zone: 'Asia/Seoul',
    workspaces: [],
    workspace_roles: [],
    ...overrides,
  };
}

function bootstrap(
  overrides: Partial<BootstrapStatusResponse> = {},
): BootstrapStatusResponse {
  return {
    dev_admin_login_available: false,
    dev_login_accounts: [],
    requires_setup: false,
    ...overrides,
  };
}

function devAccount(overrides: Partial<DevLoginAccount> = {}): DevLoginAccount {
  return {
    account_key: 'platform-admin',
    category: 'Administrators',
    description: 'Platform administrator account.',
    email: 'platform-admin@ai-do.local',
    label: 'Platform Admin',
    ...overrides,
  };
}

describe('auth session model', () => {
  it('creates the initial bootstrapping state', () => {
    expect(initialAuthState()).toEqual({
      bootstrapError: null,
      devAdminLoginAvailable: false,
      devLoginAccounts: [],
      requiresSetup: false,
      status: 'bootstrapping',
      token: null,
      user: null,
    });
  });

  it('projects valid stored token recovery as authenticated state with sync metadata', () => {
    const currentUser = user({
      date_format: 'iso',
      email: 'saved@ai-do.local',
      locale: 'en-US',
    });
    const accounts = [devAccount()];

    const projection = projectRefreshSession({
      bootstrapError: null,
      bootstrapStatus: bootstrap({
        dev_admin_login_available: true,
        dev_login_accounts: accounts,
      }),
      currentUser,
      storedToken: 'saved-token',
    });

    expect(projection).toEqual({
      sessionToSync: {
        token: 'saved-token',
        user: currentUser,
      },
      shouldClearStoredToken: false,
      state: {
        bootstrapError: null,
        devAdminLoginAvailable: true,
        devLoginAccounts: accounts,
        requiresSetup: false,
        status: 'authenticated',
        token: 'saved-token',
        user: currentUser,
      },
    });
  });

  it('decides to clear stale stored tokens and returns unauthenticated state', () => {
    const projection = projectRefreshSession({
      bootstrapError: null,
      bootstrapStatus: bootstrap({ dev_admin_login_available: true }),
      currentUser: null,
      storedToken: 'stale-token',
    });

    expect(projection).toEqual({
      sessionToSync: null,
      shouldClearStoredToken: true,
      state: {
        bootstrapError: null,
        devAdminLoginAvailable: true,
        devLoginAccounts: [],
        requiresSetup: false,
        status: 'unauthenticated',
        token: null,
        user: null,
      },
    });
  });

  it('preserves bootstrap failure errors for unauthenticated refreshes', () => {
    const projection = projectRefreshSession({
      bootstrapError: 'Auth service unavailable.',
      bootstrapStatus: null,
      currentUser: null,
      storedToken: null,
    });

    expect(projection).toEqual({
      sessionToSync: null,
      shouldClearStoredToken: false,
      state: {
        bootstrapError: 'Auth service unavailable.',
        devAdminLoginAvailable: false,
        devLoginAccounts: [],
        requiresSetup: false,
        status: 'unauthenticated',
        token: null,
        user: null,
      },
    });
  });

  it('keeps restored-session bootstrap failure semantics unchanged', () => {
    const currentUser = user();

    const projection = projectRefreshSession({
      bootstrapError: 'Auth service unavailable.',
      bootstrapStatus: null,
      currentUser,
      storedToken: 'saved-token',
    });

    expect(projection.state).toEqual({
      bootstrapError: null,
      devAdminLoginAvailable: false,
      devLoginAccounts: [],
      requiresSetup: false,
      status: 'authenticated',
      token: 'saved-token',
      user: currentUser,
    });
    expect(projection.shouldClearStoredToken).toBe(false);
    expect(projection.sessionToSync).toEqual({
      token: 'saved-token',
      user: currentUser,
    });
  });

  it('projects setup-required development accounts into unauthenticated state', () => {
    const accounts = [
      devAccount(),
      devAccount({
        account_key: 'workspace-member',
        category: 'Workspaces',
        email: 'workspace-member@ai-do.local',
        label: 'Workspace Member',
      }),
    ];

    const projection = projectRefreshSession({
      bootstrapError: null,
      bootstrapStatus: bootstrap({
        dev_admin_login_available: true,
        dev_login_accounts: accounts,
        requires_setup: true,
      }),
      currentUser: null,
      storedToken: null,
    });

    expect(projection).toEqual({
      sessionToSync: null,
      shouldClearStoredToken: false,
      state: {
        bootstrapError: null,
        devAdminLoginAvailable: true,
        devLoginAccounts: accounts,
        requiresSetup: true,
        status: 'unauthenticated',
        token: null,
        user: null,
      },
    });
  });

  it('builds authenticated state from explicit session data', () => {
    const currentUser = user();
    const accounts = [devAccount()];

    expect(
      toAuthenticatedAuthState({
        devAdminLoginAvailable: true,
        devLoginAccounts: accounts,
        token: 'login-token',
        user: currentUser,
      }),
    ).toEqual({
      bootstrapError: null,
      devAdminLoginAvailable: true,
      devLoginAccounts: accounts,
      requiresSetup: false,
      status: 'authenticated',
      token: 'login-token',
      user: currentUser,
    });
  });
});
