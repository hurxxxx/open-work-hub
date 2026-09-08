import type { AppBarItem } from '@/src/app/shell/navigation-types';
import type { BootstrapApp } from '@/src/platform/apps/apps-api';

type TranslateSubSidebarTitle = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function resolveSubSidebarTitle({
  activeAppId,
  appBarItems,
  t,
  appRegistry,
}: {
  activeAppId: string;
  appBarItems: readonly AppBarItem[];
  t: TranslateSubSidebarTitle;
  appRegistry: ReadonlyMap<string, BootstrapApp>;
}): string {
  if (activeAppId === 'settings') {
    return t('sidebar.allSettings');
  }

  const appBarItemById = new Map(appBarItems.map((item) => [item.id, item]));
  return t(`apps.${activeAppId}`, {
    defaultValue:
      appRegistry.get(activeAppId)?.title ??
      appBarItemById.get(activeAppId as AppBarItem['id'])?.title ??
      activeAppId,
  });
}
