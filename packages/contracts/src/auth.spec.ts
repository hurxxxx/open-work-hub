import { describe, expect, it } from 'vitest';

import { AUTH_API_PREFIX, authRoutes } from './auth';

describe('auth route contract', () => {
  it('exports every auth path used by web and desktop clients', () => {
    expect(AUTH_API_PREFIX).toBe('/api/v1/auth');
    expect(authRoutes.bootstrapStatus()).toBe('/api/v1/auth/bootstrap-status');
    expect(authRoutes.login()).toBe('/api/v1/auth/login');
    expect(authRoutes.signup()).toBe('/api/v1/auth/signup');
    expect(authRoutes.developmentAdminLogin()).toBe(
      '/api/v1/auth/dev-admin-login',
    );
    expect(authRoutes.developmentAccountLogin()).toBe('/api/v1/auth/dev-login');
    expect(authRoutes.setup()).toBe('/api/v1/auth/setup');
    expect(authRoutes.impersonateUser('user 1')).toBe(
      '/api/v1/auth/impersonations/user%201',
    );
    expect(authRoutes.currentUser()).toBe('/api/v1/auth/me');
    expect(authRoutes.logout()).toBe('/api/v1/auth/logout');
    expect(authRoutes.desktopSessionLinks()).toBe(
      '/api/v1/auth/desktop-session-links',
    );
    expect(authRoutes.desktopSessionLinkExchange()).toBe(
      '/api/v1/auth/desktop-session-links/exchange',
    );
    expect(authRoutes.preferences()).toBe('/api/v1/auth/preferences');
    expect(authRoutes.changePassword()).toBe('/api/v1/auth/change-password');
    expect(authRoutes.sessions()).toBe('/api/v1/auth/sessions');
    expect(authRoutes.revokeSession('session 1')).toBe(
      '/api/v1/auth/sessions/session%201/revoke',
    );
  });
});
