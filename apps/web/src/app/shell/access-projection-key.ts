import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { AppsBootstrapResponse } from '@/src/platform/workspaces/workspaces-api';

export function createAccessProjectionKey(
  user: AuthUser,
  appsBootstrap: AppsBootstrapResponse | null,
): string {
  return JSON.stringify({
    userId: user.id,
    systemRoles: [...user.system_roles].sort(),
    workspaces: user.workspaces
      .map((workspace) => ({
        id: workspace.id,
        role: workspace.role,
        slug: workspace.slug,
      }))
      .sort((left, right) => left.id.localeCompare(right.id)),
    apps: (appsBootstrap?.apps ?? [])
      .map((app) => ({
        appId: app.app_id,
        availabilityScope: app.availability_scope,
        eligibleWorkspaceCount: app.eligible_workspace_count,
        executionContextKind: app.execution_context_kind,
        preferredWorkspaceId: app.preferred_workspace?.id ?? null,
        resourceScope: app.resource_scope,
        singleEligibleWorkspaceId: app.single_eligible_workspace?.id ?? null,
      }))
      .sort((left, right) => left.appId.localeCompare(right.appId)),
    globalRouteAppIds: [...(appsBootstrap?.global_route_app_ids ?? [])].sort(),
  });
}
