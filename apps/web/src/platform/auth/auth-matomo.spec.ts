import { describe, expect, it } from 'vitest';

import type { AuthUser } from './auth-api';
import { resolveMatomoUserIdentity } from './auth-matomo';

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    app_bar_layout: { pinned_app_ids: [] },
    date_format: 'korean',
    display_name: 'AI-DO Member',
    email: 'member@ai-do.local',
    full_name: 'AI-DO Member',
    id: 'internal-user-1',
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

describe('resolveMatomoUserIdentity', () => {
  it('uses the login id as the Matomo user id', () => {
    expect(resolveMatomoUserIdentity(user())).toEqual({
      userId: 'member',
      userLoginId: 'member',
      userName: 'AI-DO Member',
    });
  });

  it('falls back to the internal id when a legacy user has no login id', () => {
    expect(
      resolveMatomoUserIdentity(
        user({
          display_name: '',
          email: '',
          full_name: '',
          id: 'internal-user-1',
          login_id: '',
        }),
      ),
    ).toEqual({
      userId: 'internal-user-1',
      userLoginId: 'internal-user-1',
      userName: 'internal-user-1',
    });
  });
});
