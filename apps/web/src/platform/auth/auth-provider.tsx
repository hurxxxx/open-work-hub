import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import {
  changePassword as changePasswordRequest,
  developmentAccountLogin as developmentAccountLoginRequest,
  developmentAdminLogin as developmentAdminLoginRequest,
  getBootstrapStatus,
  getCurrentUser,
  hasAdminConsoleAccess,
  hasAnySystemRole,
  hasWorkspaceMembership,
  login as loginRequest,
  listSessions as listSessionsRequest,
  logout as logoutRequest,
  revokeSession as revokeSessionRequest,
  setupFirstUser as setupFirstUserRequest,
  updatePreferences as updatePreferencesRequest,
  type AuthUser,
  type ChangePasswordPayload,
  type DevLoginAccount,
  type LoginPayload,
  type SetupFirstUserPayload,
  type UpdatePreferencesPayload,
} from './auth-api';
import {
  AuthContext,
  useAuth as useAuthContext,
  type AuthSessionStatus,
} from './auth-context';
import {
  clearStoredAuthToken,
  consumePostLogoutHomeRedirect,
  markPostLogoutHomeRedirect,
  persistAuthToken,
  readStoredAuthToken,
} from './auth-storage';
import { LoginScreen } from './login-screen';
import { i18n } from '@/src/platform/i18n';

export { useAuth } from './auth-context';

interface AuthState {
  status: AuthSessionStatus;
  user: AuthUser | null;
  token: string | null;
  requiresSetup: boolean;
  devAdminLoginAvailable: boolean;
  devLoginAccounts: DevLoginAccount[];
  bootstrapError: string | null;
}

const PERMISSION_ROLE_MAP: Record<string, string[]> = {
  'admin.access': ['platform_admin'],
  'user.read': ['platform_admin'],
  'user.write': ['platform_admin'],
  'group.read': ['platform_admin'],
  'group.write': ['platform_admin'],
  'org_unit.read': ['platform_admin'],
  'org_unit.write': ['platform_admin'],
  'workspace.read': ['platform_admin'],
  'workspace.write': ['platform_admin'],
  'team.read': ['platform_admin'],
  'team.write': ['platform_admin'],
  'audit.read': ['platform_admin'],
  'session.revoke': ['platform_admin'],
};

function errorMessage(caughtError: unknown, fallback: string): string {
  if (caughtError instanceof Error && caughtError.message) {
    return caughtError.message;
  }

  return fallback;
}

function nextAuthenticatedState(
  user: AuthUser,
  token: string,
  devAdminLoginAvailable: boolean,
  devLoginAccounts: DevLoginAccount[],
): AuthState {
  return {
    status: 'authenticated',
    user,
    token,
    requiresSetup: false,
    devAdminLoginAvailable,
    devLoginAccounts,
    bootstrapError: null,
  };
}

function sanitizeRedirectTarget(
  state: unknown,
  fallback = '/',
): string {
  if (
    state &&
    typeof state === 'object' &&
    'from' in state &&
    typeof state.from === 'string' &&
    state.from.startsWith('/') &&
    state.from !== '/login'
  ) {
    return state.from;
  }

  return fallback;
}

export function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--ui-color-bg)] px-6">
      <div
        aria-live="polite"
        className="grid w-full max-w-sm gap-2 rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-5 text-center shadow-[var(--ui-shadow-sm)]"
        role="status"
      >
        <p className="m-0 text-[0.72rem] font-semibold uppercase tracking-[0.1em] text-[var(--ui-color-ink-subtle)]">
          {i18n.t('auth:loading.eyebrow')}
        </p>
        <strong className="text-[1rem] text-[var(--ui-color-ink)]">{i18n.t('auth:loading.title')}</strong>
        <p className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">
          {i18n.t('auth:loading.description')}
        </p>
      </div>
    </div>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    status: 'bootstrapping',
    user: null,
    token: null,
    requiresSetup: false,
    devAdminLoginAvailable: false,
    devLoginAccounts: [],
    bootstrapError: null,
  });
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function refreshSession() {
    const requestId = ++requestIdRef.current;
    const storedToken = readStoredAuthToken();
    setState((current) => ({
      ...current,
      status: 'bootstrapping',
      bootstrapError: null,
    }));

    const [bootstrapResult, currentUserResult] = await Promise.allSettled([
      getBootstrapStatus(),
      storedToken ? getCurrentUser(storedToken) : Promise.resolve(null),
    ]);

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    let bootstrapError: string | null = null;
    let requiresSetup = false;
    let devAdminLoginAvailable = false;
    let devLoginAccounts: DevLoginAccount[] = [];

    if (bootstrapResult.status === 'fulfilled') {
      requiresSetup = bootstrapResult.value.requires_setup;
      devAdminLoginAvailable = Boolean(bootstrapResult.value.dev_admin_login_available);
      devLoginAccounts = bootstrapResult.value.dev_login_accounts ?? [];
    } else {
      bootstrapError = errorMessage(
        bootstrapResult.reason,
        i18n.t('auth:errors.bootstrap'),
      );
    }

    if (
      storedToken &&
      currentUserResult.status === 'fulfilled' &&
      currentUserResult.value
    ) {
      setState({
        status: 'authenticated',
        user: currentUserResult.value,
        token: storedToken,
        requiresSetup,
        devAdminLoginAvailable,
        devLoginAccounts,
        bootstrapError: null,
      });
      return;
    }

    if (storedToken) {
      clearStoredAuthToken();
    }

    setState({
      status: 'unauthenticated',
      user: null,
      token: null,
      requiresSetup,
      devAdminLoginAvailable,
      devLoginAccounts,
      bootstrapError,
    });
  }

  useEffect(() => {
    void refreshSession();
  }, []);

  async function login(payload: LoginPayload) {
    const requestId = ++requestIdRef.current;
    const session = await loginRequest(payload);

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    persistAuthToken(session.token);
    setState(
      nextAuthenticatedState(
        session.user,
        session.token,
        state.devAdminLoginAvailable,
        state.devLoginAccounts,
      ),
    );
  }

  async function loginAsDevelopmentAdmin() {
    const requestId = ++requestIdRef.current;
    const session = await developmentAdminLoginRequest();

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    persistAuthToken(session.token);
    setState(
      nextAuthenticatedState(
        session.user,
        session.token,
        state.devAdminLoginAvailable,
        state.devLoginAccounts,
      ),
    );
  }

  async function loginAsDevelopmentAccount(accountKey: string) {
    const requestId = ++requestIdRef.current;
    const session = await developmentAccountLoginRequest(accountKey);

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    persistAuthToken(session.token);
    setState(
      nextAuthenticatedState(
        session.user,
        session.token,
        state.devAdminLoginAvailable,
        state.devLoginAccounts,
      ),
    );
  }

  async function setupFirstUser(payload: SetupFirstUserPayload) {
    const requestId = ++requestIdRef.current;
    const session = await setupFirstUserRequest(payload);

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    persistAuthToken(session.token);
    setState(
      nextAuthenticatedState(
        session.user,
        session.token,
        state.devAdminLoginAvailable,
        state.devLoginAccounts,
      ),
    );
  }

  async function logout() {
    const requestId = ++requestIdRef.current;
    const sessionToken = state.token;

    try {
      if (sessionToken) {
        await logoutRequest(sessionToken);
      }
    } finally {
      clearStoredAuthToken();
      markPostLogoutHomeRedirect();
    }

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    setState({
      status: 'unauthenticated',
      user: null,
      token: null,
      requiresSetup: false,
      devAdminLoginAvailable: state.devAdminLoginAvailable,
      devLoginAccounts: state.devLoginAccounts,
      bootstrapError: null,
    });
  }

  async function updatePreferences(payload: UpdatePreferencesPayload) {
    if (!state.token) {
      throw new Error(i18n.t('auth:errors.noActiveSession'));
    }

    const user = await updatePreferencesRequest(state.token, payload);
    if (!mountedRef.current) {
      return;
    }

    setState((current) => (
      nextAuthenticatedState(
        user,
        current.token ?? state.token ?? '',
        current.devAdminLoginAvailable,
        current.devLoginAccounts,
      )
    ));
  }

  async function changePassword(payload: ChangePasswordPayload) {
    if (!state.token) {
      throw new Error(i18n.t('auth:errors.noActiveSession'));
    }

    await changePasswordRequest(state.token, payload);
    if (!mountedRef.current) {
      return;
    }

    await refreshSession();
  }

  async function listSessions() {
    if (!state.token) {
      throw new Error(i18n.t('auth:errors.noActiveSession'));
    }

    const response = await listSessionsRequest(state.token);
    return response.items;
  }

  async function revokeSession(sessionId: string) {
    if (!state.token) {
      throw new Error(i18n.t('auth:errors.noActiveSession'));
    }

    await revokeSessionRequest(state.token, sessionId);

    if (!mountedRef.current) {
      return;
    }

    await refreshSession();
  }

  function hasPermission(permission: string) {
    const roles = PERMISSION_ROLE_MAP[permission];
    if (!roles) {
      return false;
    }
    return hasAnySystemRole(state.user, roles);
  }

  function hasFeature(featureCode: string, workspaceSlug?: string | null) {
    if (featureCode === 'nav.admin') {
      return hasAdminConsoleAccess(state.user);
    }
    return hasWorkspaceMembership(state.user, workspaceSlug);
  }

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        loginAsDevelopmentAdmin,
        loginAsDevelopmentAccount,
        setupFirstUser,
        logout,
        refreshSession,
        updatePreferences,
        changePassword,
        listSessions,
        revokeSession,
        hasPermission,
        hasFeature,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuthContext();
  const location = useLocation();

  if (auth.status === 'bootstrapping') {
    return <AuthLoadingScreen />;
  }

  if (auth.status !== 'authenticated') {
    return (
      <Navigate
        replace
        state={{
          from: `${location.pathname}${location.search}${location.hash}`,
        }}
        to="/login"
      />
    );
  }

  return children;
}

export function LoginRoute() {
  const auth = useAuthContext();
  const location = useLocation();
  const [redirectToHomeAfterLogout] = useState(() => consumePostLogoutHomeRedirect());

  if (auth.status === 'bootstrapping') {
    return <AuthLoadingScreen />;
  }

  if (auth.status === 'authenticated') {
    return (
      <Navigate
        replace
        to={redirectToHomeAfterLogout ? '/' : sanitizeRedirectTarget(location.state)}
      />
    );
  }

  return <LoginScreen />;
}
