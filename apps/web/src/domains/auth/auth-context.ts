import { createContext, useContext } from 'react';

import type {
  AuthSessionItem,
  AuthUser,
  ChangePasswordPayload,
  DevLoginAccount,
  LoginPayload,
  SetupFirstUserPayload,
  UpdatePreferencesPayload,
} from './auth-api';

export type AuthSessionStatus =
  | 'bootstrapping'
  | 'authenticated'
  | 'unauthenticated';

export interface AuthContextValue {
  status: AuthSessionStatus;
  user: AuthUser | null;
  token: string | null;
  requiresSetup: boolean;
  devAdminLoginAvailable: boolean;
  devLoginAccounts: DevLoginAccount[];
  bootstrapError: string | null;
  login: (payload: LoginPayload) => Promise<void>;
  loginAsDevelopmentAdmin: () => Promise<void>;
  loginAsDevelopmentAccount: (accountKey: string) => Promise<void>;
  setupFirstUser: (payload: SetupFirstUserPayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  updatePreferences: (payload: UpdatePreferencesPayload) => Promise<void>;
  changePassword: (payload: ChangePasswordPayload) => Promise<void>;
  listSessions: () => Promise<AuthSessionItem[]>;
  revokeSession: (sessionId: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasFeature: (featureCode: string, workspaceSlug?: string | null) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }

  return context;
}
