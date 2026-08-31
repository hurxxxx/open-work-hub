import type { AppBarItem } from '@/src/app/shell/navigation-types';
import type {
  WorkspaceBootstrapAppBarCategory,
  WorkspaceBootstrapApp,
} from '@/src/platform/workspaces/workspaces-api';
import { workspaceAppIconForKey } from '@/src/platform/workspaces/workspace-app-icons';
import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';

export interface MobileNavigationItem {
  id: string;
  activeAppIds: readonly WorkspaceAppId[];
  title: string;
  icon: AppBarItem['icon'];
  linkAppId: WorkspaceAppId;
  type: 'app';
}

export function projectMobileNavigationItems({
  appBarCategories,
  fixedAppIds,
  appBarItems,
  workspaceApps,
}: {
  appBarCategories: readonly WorkspaceBootstrapAppBarCategory[];
  fixedAppIds: readonly string[];
  appBarItems: readonly AppBarItem[];
  workspaceApps: readonly WorkspaceBootstrapApp[];
}): MobileNavigationItem[] {
  const appBarItemById = new Map(
    appBarItems.map((item) => [item.id, item] as const),
  );
  const workspaceAppById = new Map(
    workspaceApps.map((item) => [item.app_id, item] as const),
  );
  const items: MobileNavigationItem[] = [];
  const projectedAppIds = new Set<string>();

  for (const fixedAppId of fixedAppIds) {
    const fixedApp = workspaceAppById.get(fixedAppId);
    if (!fixedApp?.enabled || fixedApp.coming_soon) {
      continue;
    }
    projectedAppIds.add(fixedAppId);
    items.push({
      id: fixedAppId,
      activeAppIds: [fixedAppId],
      title: fixedApp.title,
      icon:
        appBarItemById.get(fixedAppId)?.icon ??
        workspaceAppIconForKey(fixedApp.icon_key),
      linkAppId: fixedAppId,
      type: 'app',
    });
  }

  for (const category of [...appBarCategories].sort(
    (left, right) => left.position - right.position,
  )) {
    const enabledItems = category.items.filter((categoryItem) => {
      const app = workspaceAppById.get(categoryItem.app_id);
      return Boolean(
        app?.enabled &&
          !app.coming_soon &&
          !projectedAppIds.has(categoryItem.app_id),
      );
    });
    for (const categoryItem of enabledItems) {
      const app = workspaceAppById.get(categoryItem.app_id);
      if (!app) continue;
      projectedAppIds.add(app.app_id);
      items.push({
        id: app.app_id,
        activeAppIds: [app.app_id],
        title: app.title,
        icon: workspaceAppIconForKey(app.icon_key),
        linkAppId: app.app_id,
        type: 'app',
      });
    }
  }

  return items;
}
