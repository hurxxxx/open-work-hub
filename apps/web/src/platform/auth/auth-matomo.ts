import type { MatomoUserIdentity } from '@/src/platform/analytics/matomo';

import type { AuthUser } from './auth-api';

export function resolveMatomoUserIdentity(user: AuthUser): MatomoUserIdentity {
  const loginId = user.login_id || user.id;

  return {
    userId: loginId,
    userLoginId: loginId,
    userName: user.display_name || user.full_name || user.email || loginId,
  };
}
