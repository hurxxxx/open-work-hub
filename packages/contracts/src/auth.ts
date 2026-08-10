export const AUTH_API_PREFIX = '/api/v1/auth';

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
  desktopSessionLinkExchange: () => `${AUTH_API_PREFIX}/desktop-session-links/exchange`,
  preferences: () => `${AUTH_API_PREFIX}/preferences`,
  changePassword: () => `${AUTH_API_PREFIX}/change-password`,
  sessions: () => `${AUTH_API_PREFIX}/sessions`,
  revokeSession: (sessionId: string) =>
    `${AUTH_API_PREFIX}/sessions/${encodeURIComponent(sessionId)}/revoke`,
} as const;
