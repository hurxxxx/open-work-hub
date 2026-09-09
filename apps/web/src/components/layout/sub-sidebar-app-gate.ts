export function resolveAppSidebarConfig<T>({
  activeAppId,
  canReadApp,
  enabledShellAppIds,
  globalAppIds,
  load,
}: {
  activeAppId: string;
  canReadApp: boolean;
  enabledShellAppIds: readonly string[];
  globalAppIds: readonly string[];
  load: (appId: string) => T;
}): T | null {
  const enabled =
    globalAppIds.includes(activeAppId) ||
    (canReadApp && enabledShellAppIds.includes(activeAppId));
  return enabled ? load(activeAppId) : null;
}
