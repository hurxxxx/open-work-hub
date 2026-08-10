import type {
  AuthUser,
  BootstrapStatusResponse,
  DevLoginAccount,
} from './auth-api';
import type { AuthSessionStatus } from './auth-context';

export interface AuthState {
  status: AuthSessionStatus;
  user: AuthUser | null;
  token: string | null;
  requiresSetup: boolean;
  devAdminLoginAvailable: boolean;
  devLoginAccounts: DevLoginAccount[];
  bootstrapError: string | null;
}

export interface AuthSessionToSync {
  token: string;
  user: AuthUser;
}

export interface ToAuthenticatedAuthStateInput {
  user: AuthUser;
  token: string;
  requiresSetup?: boolean;
  devAdminLoginAvailable: boolean;
  devLoginAccounts: DevLoginAccount[];
}

export interface ProjectRefreshSessionInput {
  storedToken: string | null;
  bootstrapStatus: BootstrapStatusResponse | null;
  bootstrapError: string | null;
  currentUser: AuthUser | null;
}

export interface RefreshSessionProjection {
  state: AuthState;
  shouldClearStoredToken: boolean;
  sessionToSync: AuthSessionToSync | null;
}

export function initialAuthState(): AuthState {
  return {
    status: 'bootstrapping',
    user: null,
    token: null,
    requiresSetup: false,
    devAdminLoginAvailable: false,
    devLoginAccounts: [],
    bootstrapError: null,
  };
}

export function toAuthenticatedAuthState({
  user,
  token,
  requiresSetup = false,
  devAdminLoginAvailable,
  devLoginAccounts,
}: ToAuthenticatedAuthStateInput): AuthState {
  return {
    status: 'authenticated',
    user,
    token,
    requiresSetup,
    devAdminLoginAvailable,
    devLoginAccounts,
    bootstrapError: null,
  };
}

export function projectRefreshSession({
  storedToken,
  bootstrapStatus,
  bootstrapError,
  currentUser,
}: ProjectRefreshSessionInput): RefreshSessionProjection {
  const requiresSetup = bootstrapStatus?.requires_setup ?? false;
  const devAdminLoginAvailable = Boolean(
    bootstrapStatus?.dev_admin_login_available,
  );
  const devLoginAccounts = bootstrapStatus?.dev_login_accounts ?? [];

  if (storedToken && currentUser) {
    return {
      state: toAuthenticatedAuthState({
        user: currentUser,
        token: storedToken,
        requiresSetup,
        devAdminLoginAvailable,
        devLoginAccounts,
      }),
      shouldClearStoredToken: false,
      sessionToSync: {
        token: storedToken,
        user: currentUser,
      },
    };
  }

  return {
    state: {
      status: 'unauthenticated',
      user: null,
      token: null,
      requiresSetup,
      devAdminLoginAvailable,
      devLoginAccounts,
      bootstrapError,
    },
    shouldClearStoredToken: Boolean(storedToken),
    sessionToSync: null,
  };
}
