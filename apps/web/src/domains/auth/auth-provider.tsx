import type { ReactNode } from 'react';
import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import {
  changePassword as changePasswordRequest,
  developmentAdminLogin as developmentAdminLoginRequest,
  getBootstrapStatus,
  getCurrentUser,
  login as loginRequest,
  listSessions as listSessionsRequest,
  logout as logoutRequest,
  revokeSession as revokeSessionRequest,
  setupFirstUser as setupFirstUserRequest,
  updatePreferences as updatePreferencesRequest,
  type AuthSessionItem,
  type AuthUser,
  type ChangePasswordPayload,
  type LoginPayload,
  type SetupFirstUserPayload,
  type UpdatePreferencesPayload,
} from './auth-api';
import {
  clearStoredAuthToken,
  persistAuthToken,
  readStoredAuthToken,
} from './auth-storage';
import { LoginScreen } from './login-screen';

export type AuthSessionStatus =
  | 'bootstrapping'
  | 'authenticated'
  | 'unauthenticated';

export interface AuthContextValue {
  status: AuthSessionStatus;
  user: AuthUser | null;
  token: string | null;
  requiresSetup: boolean;
  bootstrapError: string | null;
  login: (payload: LoginPayload) => Promise<void>;
  loginAsDevelopmentAdmin: () => Promise<void>;
  setupFirstUser: (payload: SetupFirstUserPayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  updatePreferences: (payload: UpdatePreferencesPayload) => Promise<void>;
  changePassword: (payload: ChangePasswordPayload) => Promise<void>;
  listSessions: () => Promise<AuthSessionItem[]>;
  revokeSession: (sessionId: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasFeature: (featureCode: string) => boolean;
}

interface AuthState {
  status: AuthSessionStatus;
  user: AuthUser | null;
  token: string | null;
  requiresSetup: boolean;
  bootstrapError: string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function errorMessage(caughtError: unknown, fallback: string): string {
  if (caughtError instanceof Error && caughtError.message) {
    return caughtError.message;
  }

  return fallback;
}

function nextAuthenticatedState(user: AuthUser, token: string): AuthState {
  return {
    status: 'authenticated',
    user,
    token,
    requiresSetup: false,
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
          Session
        </p>
        <strong className="text-[1rem] text-[var(--ui-color-ink)]">세션 확인 중</strong>
        <p className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">
          저장된 로그인 정보와 초기 설정 상태를 확인하고 있습니다.
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

    if (bootstrapResult.status === 'fulfilled') {
      requiresSetup = bootstrapResult.value.requires_setup;
    } else {
      bootstrapError = errorMessage(
        bootstrapResult.reason,
        '초기 인증 상태를 확인하지 못했습니다.',
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
    setState(nextAuthenticatedState(session.user, session.token));
  }

  async function loginAsDevelopmentAdmin() {
    const requestId = ++requestIdRef.current;
    const session = await developmentAdminLoginRequest();

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    persistAuthToken(session.token);
    setState(nextAuthenticatedState(session.user, session.token));
  }

  async function setupFirstUser(payload: SetupFirstUserPayload) {
    const requestId = ++requestIdRef.current;
    const session = await setupFirstUserRequest(payload);

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    persistAuthToken(session.token);
    setState(nextAuthenticatedState(session.user, session.token));
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
    }

    if (!mountedRef.current || requestIdRef.current !== requestId) {
      return;
    }

    setState({
      status: 'unauthenticated',
      user: null,
      token: null,
      requiresSetup: false,
      bootstrapError: null,
    });
  }

  async function updatePreferences(payload: UpdatePreferencesPayload) {
    if (!state.token) {
      throw new Error('No active session.');
    }

    const user = await updatePreferencesRequest(state.token, payload);
    if (!mountedRef.current) {
      return;
    }

    setState((current) => nextAuthenticatedState(user, current.token ?? state.token ?? ''));
  }

  async function changePassword(payload: ChangePasswordPayload) {
    if (!state.token) {
      throw new Error('No active session.');
    }

    await changePasswordRequest(state.token, payload);
    if (!mountedRef.current) {
      return;
    }

    await refreshSession();
  }

  async function listSessions() {
    if (!state.token) {
      throw new Error('No active session.');
    }

    const response = await listSessionsRequest(state.token);
    return response.items;
  }

  async function revokeSession(sessionId: string) {
    if (!state.token) {
      throw new Error('No active session.');
    }

    await revokeSessionRequest(state.token, sessionId);

    if (!mountedRef.current) {
      return;
    }

    await refreshSession();
  }

  function hasPermission(permission: string) {
    return state.user?.permissions.includes(permission) ?? false;
  }

  function hasFeature(featureCode: string) {
    return state.user?.visible_features.includes(featureCode) ?? false;
  }

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        loginAsDevelopmentAdmin,
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

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }

  return context;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
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

  return <>{children}</>;
}

export function LoginRoute() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === 'bootstrapping') {
    return <AuthLoadingScreen />;
  }

  if (auth.status === 'authenticated') {
    return (
      <Navigate
        replace
        to={sanitizeRedirectTarget(location.state)}
      />
    );
  }

  return <LoginScreen />;
}
