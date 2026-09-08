export interface CoreAccessUser {
  id: string;
}
export interface CoreBootstrapApp {
  app_id: string;
  enabled: boolean;
}
export type CoreAppGateStatus =
  | 'allowed'
  | 'principal_denied'
  | 'loading'
  | 'bootstrap_error'
  | 'app_disabled';
export type CoreAppGateResult =
  | { status: Exclude<CoreAppGateStatus, 'bootstrap_error'> }
  | { status: 'bootstrap_error'; error: string };

export function getCoreEnabledAppIds(
  apps: readonly CoreBootstrapApp[] | null | undefined,
): Set<string> {
  return new Set(
    (apps ?? []).filter((app) => app.enabled).map((app) => app.app_id),
  );
}
export function isCoreAppEnabled(
  apps: readonly CoreBootstrapApp[] | null | undefined,
  appId: string,
): boolean {
  return getCoreEnabledAppIds(apps).has(appId);
}
export function canAccessCoreApp({
  appId,
  enabledAppIds,
  user,
}: {
  appId: string;
  enabledAppIds?: readonly string[] | null;
  user: CoreAccessUser | null | undefined;
}): boolean {
  return Boolean(user && enabledAppIds?.includes(appId));
}
export function resolveCoreAppGate({
  appId,
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
  user,
}: {
  appId: string;
  bootstrapAppIds: readonly string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  user: CoreAccessUser | null | undefined;
}): CoreAppGateResult {
  if (!user) return { status: 'principal_denied' };
  if (bootstrapError)
    return { status: 'bootstrap_error', error: bootstrapError };
  if (bootstrapLoading || bootstrapAppIds === null)
    return { status: 'loading' };
  return {
    status: bootstrapAppIds.includes(appId) ? 'allowed' : 'app_disabled',
  };
}
