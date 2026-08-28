import type { AppBarItem } from '@/src/app/shell/navigation-types';
import type { WorkspaceBootstrapApp } from '@/src/platform/workspaces/workspaces-api';

type TranslateSubSidebarTitle = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function resolveSubSidebarTitle({
  activeAppId,
  appBarItems,
  t,
  workspaceAppRegistry,
}: {
  activeAppId: string;
  appBarItems: readonly AppBarItem[];
  t: TranslateSubSidebarTitle;
  workspaceAppRegistry: ReadonlyMap<string, WorkspaceBootstrapApp>;
}): string {
  if (activeAppId === 'settings') {
    return t('sidebar.allSettings');
  }

  const appBarItemById = new Map(appBarItems.map((item) => [item.id, item]));
  return t(`apps.${activeAppId}`, {
    defaultValue:
      workspaceAppRegistry.get(activeAppId)?.title ??
      appBarItemById.get(activeAppId as AppBarItem['id'])?.title ??
      activeAppId,
  });
}
