import { createContext, use } from 'react';
import { i18n } from '@/src/platform/i18n';

import type {
  AuthSessionResponse,
  AuthSessionItem,
  AuthUser,
  ChangePasswordPayload,
  DevLoginAccount,
  LoginPayload,
  SetupFirstUserPayload,
  SignupPayload,
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
  signup: (payload: SignupPayload) => Promise<void>;
  loginAsDevelopmentAdmin: () => Promise<void>;
  loginAsDevelopmentAccount: (accountKey: string) => Promise<void>;
  setupFirstUser: (payload: SetupFirstUserPayload) => Promise<void>;
  switchSession: (session: AuthSessionResponse) => void;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  refreshAccessUser: () => Promise<AuthUser>;
  updatePreferences: (payload: UpdatePreferencesPayload) => Promise<void>;
  changePassword: (payload: ChangePasswordPayload) => Promise<void>;
  listSessions: () => Promise<AuthSessionItem[]>;
  revokeSession: (sessionId: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasFeature: (featureCode: string, workspaceSlug?: string | null) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const context = use(AuthContext);

  if (!context) {
    throw new Error(i18n.t('auth:errors.authProviderMissing'));
  }

  return context;
}
