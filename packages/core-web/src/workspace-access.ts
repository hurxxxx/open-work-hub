export interface CoreWorkspaceMembershipUser {
  workspaces?: readonly {
    slug: string;
  }[];
}

export interface CoreWorkspaceBootstrapApp {
  app_id: string;
  enabled: boolean;
}

export type CoreWorkspaceAppGateStatus =
  | 'allowed'
  | 'workspace_denied'
  | 'loading'
  | 'bootstrap_error'
  | 'app_disabled';

export type CoreWorkspaceAppGateResult =
  | { status: 'allowed' }
  | { status: 'workspace_denied' }
  | { status: 'loading' }
  | { status: 'bootstrap_error'; error: string }
  | { status: 'app_disabled' };

export function hasCoreWorkspaceMembership(
  user: CoreWorkspaceMembershipUser | null | undefined,
  workspaceSlug?: string | null,
): boolean {
  if (!workspaceSlug) {
    return (user?.workspaces?.length ?? 0) > 0;
  }
  return (
    user?.workspaces?.some((workspace) => workspace.slug === workspaceSlug) ??
    false
  );
}

export function getCoreEnabledWorkspaceAppIds(
  apps: readonly CoreWorkspaceBootstrapApp[] | null | undefined,
): Set<string> {
  const enabledAppIds = new Set<string>();
  for (const app of apps ?? []) {
    if (app.enabled) {
      enabledAppIds.add(app.app_id);
    }
  }
  return enabledAppIds;
}

export function isCoreWorkspaceAppEnabled(
  apps: readonly CoreWorkspaceBootstrapApp[] | null | undefined,
  appId: string,
): boolean {
  return getCoreEnabledWorkspaceAppIds(apps).has(appId);
}

export function canAccessCoreWorkspaceApp({
  appId,
  enabledWorkspaceAppIds,
  user,
  workspaceSlug,
}: {
  appId: string;
  enabledWorkspaceAppIds?: readonly string[] | null;
  user: CoreWorkspaceMembershipUser | null | undefined;
  workspaceSlug?: string | null;
}): boolean {
  if (!hasCoreWorkspaceMembership(user, workspaceSlug)) {
    return false;
  }
  return (
    enabledWorkspaceAppIds == null || enabledWorkspaceAppIds.includes(appId)
  );
}

export function resolveCoreWorkspaceAppGate({
  appId,
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
  user,
  workspaceSlug,
}: {
  appId: string;
  bootstrapAppIds: readonly string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  user: CoreWorkspaceMembershipUser | null | undefined;
  workspaceSlug?: string | null;
}): CoreWorkspaceAppGateResult {
  if (!hasCoreWorkspaceMembership(user, workspaceSlug)) {
    return { status: 'workspace_denied' };
  }

  if (!workspaceSlug) {
    return { status: 'allowed' };
  }

  if (bootstrapLoading || bootstrapAppIds === null) {
    return { status: 'loading' };
  }

  if (bootstrapError) {
    return { status: 'bootstrap_error', error: bootstrapError };
  }

  if (!bootstrapAppIds.includes(appId)) {
    return { status: 'app_disabled' };
  }

  return { status: 'allowed' };
}
