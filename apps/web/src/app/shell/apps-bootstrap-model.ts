import type {
  AppsBootstrapResponse,
  BootstrapApp,
  BootstrapAppBarCategory,
  BootstrapAppBarCategoryItem,
} from '@/src/platform/apps/apps-api';

export const PERSONAL_TOOLS_CATEGORY_ID = 'personal-tools';

export interface ShellAppsBootstrapProjection {
  apps: BootstrapApp[];
  appBarCategories: BootstrapAppBarCategory[];
  enabledAppIds: string[];
  globalRouteAppIds: string[] | null;
}

function categoryItemPosition(
  item: BootstrapAppBarCategoryItem,
  fallback: number,
): number {
  return item.position ?? fallback;
}

export function projectShellAppsBootstrap({
  globalBootstrap,
  personalToolsScope,
  personalToolsTitle,
}: {
  globalBootstrap: AppsBootstrapResponse | null;
  personalToolsScope: string;
  personalToolsTitle: string;
}): ShellAppsBootstrapProjection {
  const appById = new Map<string, BootstrapApp>(
    (globalBootstrap?.apps ?? []).map((app) => [app.app_id, app]),
  );

  const personalToolIds = new Set(globalBootstrap?.personal_tool_app_ids ?? []);
  const categoryById = new Map<
    string,
    BootstrapAppBarCategory & {
      itemById: Map<string, BootstrapAppBarCategoryItem>;
    }
  >();
  for (const category of [...(globalBootstrap?.app_bar_categories ?? [])]) {
    const existing = categoryById.get(category.id);
    const itemById = existing?.itemById ?? new Map();
    category.items.forEach((item, index) => {
      if (!personalToolIds.has(item.app_id)) {
        itemById.set(item.app_id, {
          ...item,
          position: categoryItemPosition(item, index),
        });
      }
    });
    categoryById.set(category.id, {
      ...(existing ?? category),
      ...category,
      itemById,
    });
  }

  const appBarCategories = [...categoryById.values()]
    .map(({ itemById, ...category }) => ({
      ...category,
      items: [...itemById.values()].sort(
        (left, right) =>
          categoryItemPosition(left, 0) - categoryItemPosition(right, 0),
      ),
    }))
    .filter((category) => category.items.length > 0)
    .sort((left, right) => left.position - right.position);

  const personalTools = (globalBootstrap?.apps ?? []).filter(
    (app) => personalToolIds.has(app.app_id) && app.enabled,
  );
  if (personalTools.length > 0) {
    appBarCategories.unshift({
      id: PERSONAL_TOOLS_CATEGORY_ID,
      key: PERSONAL_TOOLS_CATEGORY_ID,
      title: personalToolsTitle,
      icon_key: 'user',
      position: Number.MIN_SAFE_INTEGER,
      pinnable: false,
      contextLabel: personalToolsScope,
      items: personalTools.map((app, position) => ({
        app_id: app.app_id,
        title: app.title,
        route_base: app.route_base,
        icon_key: app.icon_key,
        enabled: true,
        coming_soon: app.coming_soon,
        position,
      })),
    });
  }

  const apps = [...appById.values()];
  return {
    apps,
    appBarCategories,
    enabledAppIds: apps.filter((app) => app.enabled).map((app) => app.app_id),
    globalRouteAppIds:
      globalBootstrap?.apps
        .filter((app) => app.enabled)
        .map((app) => app.app_id) ?? null,
  };
}
