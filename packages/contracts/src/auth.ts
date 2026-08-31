import {
  AUTH_ACCESS_CHANGE_REASONS,
  AUTH_REALTIME_EVENT_TYPES,
} from './auth-realtime.generated.js';

export const AUTH_API_PREFIX = '/api/v1/auth';

export {
  AUTH_ACCESS_CHANGE_REASONS,
  AUTH_REALTIME_EVENT_TYPES,
} from './auth-realtime.generated.js';

export type AuthAccessChangeReason =
  (typeof AUTH_ACCESS_CHANGE_REASONS)[keyof typeof AUTH_ACCESS_CHANGE_REASONS];

export type AuthAccessChangedRealtimeEvent = {
  type: typeof AUTH_REALTIME_EVENT_TYPES.accessChanged;
  data: {
    reason: AuthAccessChangeReason;
  };
};

export function isAuthAccessChangedRealtimeEvent(
  value: unknown,
): value is AuthAccessChangedRealtimeEvent {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const record = value as Record<string, unknown>;
  if (
    record.type !== AUTH_REALTIME_EVENT_TYPES.accessChanged ||
    !record.data ||
    typeof record.data !== 'object'
  ) {
    return false;
  }
  return Object.values(AUTH_ACCESS_CHANGE_REASONS).includes(
    (record.data as Record<string, unknown>).reason as AuthAccessChangeReason,
  );
}

export const authRoutes = {
  bootstrapStatus: () => `${AUTH_API_PREFIX}/bootstrap-status`,
  login: () => `${AUTH_API_PREFIX}/login`,
  signup: () => `${AUTH_API_PREFIX}/signup`,
  developmentAdminLogin: () => `${AUTH_API_PREFIX}/dev-admin-login`,
  developmentAccountLogin: () => `${AUTH_API_PREFIX}/dev-login`,
  setup: () => `${AUTH_API_PREFIX}/setup`,
  impersonateUser: (userId: string) =>
    `${AUTH_API_PREFIX}/impersonations/${encodeURIComponent(userId)}`,
  currentUser: () => `${AUTH_API_PREFIX}/me`,
  logout: () => `${AUTH_API_PREFIX}/logout`,
  desktopSessionLinks: () => `${AUTH_API_PREFIX}/desktop-session-links`,
  desktopSessionLinkExchange: () =>
    `${AUTH_API_PREFIX}/desktop-session-links/exchange`,
  preferences: () => `${AUTH_API_PREFIX}/preferences`,
  changePassword: () => `${AUTH_API_PREFIX}/change-password`,
  sessions: () => `${AUTH_API_PREFIX}/sessions`,
  revokeSession: (sessionId: string) =>
    `${AUTH_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}/revoke`,
} as const;
