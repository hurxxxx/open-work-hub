export function resolveAppSidebarConfig<T>({
  activeAppId,
  canReadWorkspace,
  enabledWorkspaceAppIds,
  globalAppIds,
  load,
}: {
  activeAppId: string;
  canReadWorkspace: boolean;
  enabledWorkspaceAppIds: readonly string[];
  globalAppIds: readonly string[];
  load: (appId: string) => T;
}): T | null {
  const enabled =
    globalAppIds.includes(activeAppId) ||
    (canReadWorkspace && enabledWorkspaceAppIds.includes(activeAppId));
  return enabled ? load(activeAppId) : null;
}
