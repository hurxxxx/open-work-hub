import type { AdminAppBarCategory } from './admin-api';

export const UNCATEGORIZED_APP_VISIBILITY_GROUP_ID =
  '__app_bar_uncategorized__';
export const PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID = '__personal_tools__';

export interface AppVisibilityGroupableItem {
  app_id: string;
  kind: string;
  launcher_personal_tools?: boolean;
  title: string;
}

export interface AppVisibilityGroup<T extends AppVisibilityGroupableItem> {
  id: string;
  title: string | null;
  rows: T[];
}

export function partitionAppVisibilityItems<
  T extends AppVisibilityGroupableItem,
>(
  items: readonly T[],
): {
  configurableApps: T[];
  personalTools: T[];
} {
  const personalTools: T[] = [];
  const configurableApps: T[] = [];
  for (const item of items) {
    if (item.launcher_personal_tools) {
      personalTools.push(item);
    } else {
      configurableApps.push(item);
    }
  }
  return { configurableApps, personalTools };
}

export function buildAppVisibilityGroups<T extends AppVisibilityGroupableItem>(
  items: T[],
  appBarCategories: readonly AdminAppBarCategory[] = [],
): AppVisibilityGroup<T>[] {
  const visibilityItems = items.filter((item) => item.kind === 'launcher_app');
  const {
    configurableApps: configurableItems,
    personalTools: personalToolItems,
  } = partitionAppVisibilityItems(visibilityItems);
  if (appBarCategories.length === 0) {
    const groups: AppVisibilityGroup<T>[] = [];
    if (personalToolItems.length > 0) {
      groups.push({
        id: PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID,
        rows: personalToolItems,
        title: null,
      });
    }
    if (configurableItems.length > 0) {
      groups.push({
        id: UNCATEGORIZED_APP_VISIBILITY_GROUP_ID,
        rows: configurableItems,
        title: null,
      });
    }
    return groups;
  }

  const itemById = new Map(
    configurableItems.map((item) => [item.app_id, item]),
  );
  const categorizedAppIds = new Set<string>();
  const groups = appBarCategories.map<AppVisibilityGroup<T>>((category) => {
    const rows: T[] = [];
    for (const app of category.items) {
      const item = itemById.get(app.app_id);
      if (!item) continue;
      categorizedAppIds.add(item.app_id);
      rows.push(item);
    }
    return {
      id: `app-bar:${category.id}`,
      rows,
      title: category.title,
    };
  });

  if (personalToolItems.length > 0) {
    groups.push({
      id: PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID,
      rows: personalToolItems,
      title: null,
    });
  }

  const uncategorizedRows = configurableItems.filter(
    (item) => !categorizedAppIds.has(item.app_id),
  );
  if (uncategorizedRows.length > 0) {
    groups.push({
      id: UNCATEGORIZED_APP_VISIBILITY_GROUP_ID,
      rows: uncategorizedRows,
      title: null,
    });
  }

  return groups;
}
