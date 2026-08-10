import type { AppBarItem } from '@/src/app/shell/navigation-types';
import type { WorkspaceBootstrapApp } from '@/src/platform/workspaces/workspaces-api';

type TranslateSubSidebarTitle = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function resolveSubSidebarTitle({
  activeAppId,
  activeFeatureAppId,
  appBarItems,
  t,
  workspaceAppRegistry,
}: {
  activeAppId: string;
  activeFeatureAppId?: string | null;
  appBarItems: readonly AppBarItem[];
  t: TranslateSubSidebarTitle;
  workspaceAppRegistry: ReadonlyMap<string, WorkspaceBootstrapApp>;
}): string {
  const titleAppId = activeFeatureAppId ?? activeAppId;
  if (titleAppId === 'settings') {
    return t('sidebar.allSettings');
  }

  const appBarItemById = new Map(appBarItems.map((item) => [item.id, item]));
  return t(`apps.${titleAppId}`, {
    defaultValue:
      workspaceAppRegistry.get(titleAppId)?.title ??
      appBarItemById.get(titleAppId as AppBarItem['id'])?.title ??
      titleAppId,
  });
}
