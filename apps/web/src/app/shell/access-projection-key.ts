import type { AppsBootstrapResponse } from '@/src/platform/apps/apps-api';
import type { AuthUser } from '@/src/platform/auth/auth-api';

export function createAccessProjectionKey(
  user: AuthUser,
  bootstrap: AppsBootstrapResponse | null,
): string {
  return JSON.stringify({
    userId: user.id,
    systemRoles: [...user.system_roles].sort(),
    groupIds: [...user.group_ids].sort(),
    managedOrganizationIds: [...user.managed_organization_unit_ids].sort(),
    apps: (bootstrap?.apps ?? [])
      .filter((app) => app.enabled)
      .map((app) => app.app_id)
      .sort(),
  });
}
