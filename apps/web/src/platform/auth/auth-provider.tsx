import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
  signup as signupRequest,
  updatePreferences as updatePreferencesRequest,
  type AuthSessionResponse,
  type AuthUser,
  type ChangePasswordPayload,
  type LoginPayload,
  type SetupFirstUserPayload,
  type SignupPayload,
  type UpdatePreferencesPayload,
} from './auth-api';
import { AuthContext } from './auth-context';
import {
  initialAuthState,
  projectRefreshSession,
  toAuthenticatedAuthState,
  type AuthState,
} from './auth-session-model';
import {
  clearStoredAuthToken,
  markPostLogoutHomeRedirect,
  persistAuthToken,
  readStoredAuthToken,
} from './auth-storage';
import { resolveMatomoUserIdentity } from './auth-matomo';
import {
  syncDesktopLoginSession,
  syncDesktopLogoutSession,
} from './desktop-session-sync';
import { i18n, syncLocale } from '@/src/platform/i18n';
import {
  syncDateFormatPreference,
  syncTimeZonePreference,
} from '@/src/platform/time/time-utils';
import {
  clearMatomoUser,
  identifyMatomoUser,
} from '@/src/platform/analytics/matomo';

export { useAuth } from './auth-context';
export { AuthLoadingScreen } from './auth-loading-screen';
export { LoginRoute } from './login-route';
export { RequireAuth } from './require-auth';

const PERMISSION_ROLE_MAP: Record<string, string[]> = {
  'admin.access': ['platform_admin'],
  'user.read': ['platform_admin'],
  'user.write': ['platform_admin'],
  'org_unit.read': ['platform_admin'],
  'org_unit.write': ['platform_admin'],
  'workspace.read': ['platform_admin'],
  'workspace.write': ['platform_admin'],
  'team.read': ['platform_admin'],
  'team.write': ['platform_admin'],
  'audit.read': ['platform_admin'],
  'session.revoke': ['platform_admin'],
  'user.impersonate': ['platform_admin'],
};

function errorMessage(caughtError: unknown, fallback: string): string {
  if (caughtError instanceof Error && caughtError.message) {
    return caughtError.message;
  }

  return fallback;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return useAuthProviderElement(children);
}

function useAuthProviderElement(children: ReactNode) {
  const [state, setState] = useState<AuthState>(() => initialAuthState());
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  const requestIsCurrent = useCallback(
    (requestId: number) =>
      mountedRef.current && requestIdRef.current === requestId,
    [],
  );

  const applyAuthenticatedSession = useCallback(
    (session: { token: string; user: AuthUser }) => {
      persistAuthToken(session.token);
      void syncDesktopLoginSession(session.token).catch(() => undefined);
      syncLocale(session.user.locale);
      syncDateFormatPreference(session.user.date_format);
      syncTimeZonePreference(session.user.time_zone);
      identifyMatomoUser(resolveMatomoUserIdentity(session.user));
      setState((current) =>
        toAuthenticatedAuthState({
          user: session.user,
          token: session.token,
          devAdminLoginAvailable: current.devAdminLoginAvailable,
          devLoginAccounts: current.devLoginAccounts,
        }),
      );
    },
    [],
  );

  const refreshSession = useCallback(async () => {
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

    if (requestIsCurrent(requestId)) {
      let bootstrapError: string | null = null;
      const bootstrapStatus =
        bootstrapResult.status === 'fulfilled' ? bootstrapResult.value : null;

      if (bootstrapResult.status === 'rejected') {
        bootstrapError = errorMessage(
          bootstrapResult.reason,
          i18n.t('auth:errors.bootstrap'),
        );
      }

      const projection = projectRefreshSession({
        storedToken,
        bootstrapStatus,
        bootstrapError,
        currentUser:
          currentUserResult.status === 'fulfilled'
            ? currentUserResult.value
            : null,
      });

      if (projection.sessionToSync) {
        syncLocale(projection.sessionToSync.user.locale);
        syncDateFormatPreference(projection.sessionToSync.user.date_format);
        syncTimeZonePreference(projection.sessionToSync.user.time_zone);
        identifyMatomoUser(
          resolveMatomoUserIdentity(projection.sessionToSync.user),
        );
      }

      if (projection.shouldClearStoredToken) {
        clearStoredAuthToken();
        clearMatomoUser();
      }

      setState(projection.state);
    }
  }, [requestIsCurrent]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const login = useCallback(
    async (payload: LoginPayload) => {
      const requestId = ++requestIdRef.current;
      const session = await loginRequest(payload);

      if (requestIsCurrent(requestId)) {
        applyAuthenticatedSession(session);
      }
    },
    [applyAuthenticatedSession, requestIsCurrent],
  );

  const signup = useCallback(
    async (payload: SignupPayload) => {
      const requestId = ++requestIdRef.current;
      const session = await signupRequest(payload);

      if (requestIsCurrent(requestId)) {
        applyAuthenticatedSession(session);
      }
    },
    [applyAuthenticatedSession, requestIsCurrent],
  );

  const loginAsDevelopmentAdmin = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    const session = await developmentAdminLoginRequest();

    if (requestIsCurrent(requestId)) {
      applyAuthenticatedSession(session);
    }
  }, [applyAuthenticatedSession, requestIsCurrent]);

  const loginAsDevelopmentAccount = useCallback(
    async (accountKey: string) => {
      const requestId = ++requestIdRef.current;
      const session = await developmentAccountLoginRequest(accountKey);

      if (requestIsCurrent(requestId)) {
        applyAuthenticatedSession(session);
      }
    },
    [applyAuthenticatedSession, requestIsCurrent],
  );

  const setupFirstUser = useCallback(
    async (payload: SetupFirstUserPayload) => {
      const requestId = ++requestIdRef.current;
      const session = await setupFirstUserRequest(payload);

      if (requestIsCurrent(requestId)) {
        applyAuthenticatedSession(session);
      }
    },
    [applyAuthenticatedSession, requestIsCurrent],
  );

  const switchSession = useCallback(
    (session: AuthSessionResponse) => {
      requestIdRef.current += 1;
      applyAuthenticatedSession(session);
    },
    [applyAuthenticatedSession],
  );

  const logout = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    const sessionToken = state.token;

    try {
      if (sessionToken) {
        await logoutRequest(sessionToken);
      }
    } finally {
      clearStoredAuthToken();
      markPostLogoutHomeRedirect();
      syncDesktopLogoutSession();
      clearMatomoUser();
    }

    if (requestIsCurrent(requestId)) {
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
  }, [
    requestIsCurrent,
    state.devAdminLoginAvailable,
    state.devLoginAccounts,
    state.token,
  ]);

  const updatePreferences = useCallback(
    async (payload: UpdatePreferencesPayload) => {
      if (!state.token) {
        throw new Error(i18n.t('auth:errors.noActiveSession'));
      }

      const user = await updatePreferencesRequest(state.token, payload);
      if (mountedRef.current) {
        syncLocale(user.locale);
        syncDateFormatPreference(user.date_format);
        syncTimeZonePreference(user.time_zone);
        identifyMatomoUser(resolveMatomoUserIdentity(user));
        setState((current) =>
          toAuthenticatedAuthState({
            user,
            token: current.token ?? state.token ?? '',
            devAdminLoginAvailable: current.devAdminLoginAvailable,
            devLoginAccounts: current.devLoginAccounts,
          }),
        );
      }
    },
    [state.token],
  );

  const changePassword = useCallback(
    async (payload: ChangePasswordPayload) => {
      if (!state.token) {
        throw new Error(i18n.t('auth:errors.noActiveSession'));
      }

      await changePasswordRequest(state.token, payload);
      if (mountedRef.current) {
        await refreshSession();
      }
    },
    [refreshSession, state.token],
  );

  const listSessions = useCallback(async () => {
    if (!state.token) {
      throw new Error(i18n.t('auth:errors.noActiveSession'));
    }

    const response = await listSessionsRequest(state.token);
    return response.items;
  }, [state.token]);

  const revokeSession = useCallback(
    async (sessionId: string) => {
      if (!state.token) {
        throw new Error(i18n.t('auth:errors.noActiveSession'));
      }

      await revokeSessionRequest(state.token, sessionId);

      if (mountedRef.current) {
        await refreshSession();
      }
    },
    [refreshSession, state.token],
  );

  const hasPermission = useCallback(
    (permission: string) => {
      const roles = PERMISSION_ROLE_MAP[permission];
      if (!roles) {
        return false;
      }
      return hasAnySystemRole(state.user, roles);
    },
    [state.user],
  );

  const hasFeature = useCallback(
    (featureCode: string, workspaceSlug?: string | null) => {
      if (featureCode === 'nav.admin') {
        return hasAdminConsoleAccess(state.user);
      }
      return hasWorkspaceMembership(state.user, workspaceSlug);
    },
    [state.user],
  );

  const value = useMemo(
    () => ({
      ...state,
      login,
      signup,
      loginAsDevelopmentAdmin,
      loginAsDevelopmentAccount,
      setupFirstUser,
      switchSession,
      logout,
      refreshSession,
      updatePreferences,
      changePassword,
      listSessions,
      revokeSession,
      hasPermission,
      hasFeature,
    }),
    [
      state,
      login,
      signup,
      loginAsDevelopmentAdmin,
      loginAsDevelopmentAccount,
      setupFirstUser,
      switchSession,
      logout,
      refreshSession,
      updatePreferences,
      changePassword,
      listSessions,
      revokeSession,
      hasPermission,
      hasFeature,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
