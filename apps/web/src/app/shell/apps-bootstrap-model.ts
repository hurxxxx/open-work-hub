import type {
  AppsBootstrapResponse,
  WorkspaceBootstrapApp,
  WorkspaceBootstrapAppBarCategory,
  WorkspaceBootstrapAppBarCategoryItem,
} from '@/src/platform/workspaces/workspaces-api';

export const PERSONAL_TOOLS_CATEGORY_ID = 'personal-tools';

export interface ShellAppsBootstrapProjection {
  apps: WorkspaceBootstrapApp[];
  appBarCategories: WorkspaceBootstrapAppBarCategory[];
  enabledAppIds: string[];
}

function categoryItemPosition(
  item: WorkspaceBootstrapAppBarCategoryItem,
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
  workspaceApps?: readonly WorkspaceBootstrapApp[];
  workspaceCategories?: readonly WorkspaceBootstrapAppBarCategory[];
}): ShellAppsBootstrapProjection {
  const appById = new Map<string, WorkspaceBootstrapApp>(
    (globalBootstrap?.apps ?? []).map((app) => [
      app.app_id,
      { ...app, enabled: true, nav_items: [] } as WorkspaceBootstrapApp,
    ]),
  );

  const personalToolIds = new Set(globalBootstrap?.personal_tool_app_ids ?? []);
  const categoryById = new Map<
    string,
    WorkspaceBootstrapAppBarCategory & {
      itemById: Map<string, WorkspaceBootstrapAppBarCategoryItem>;
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

  const personalTools = (globalBootstrap?.apps ?? []).filter((app) =>
    personalToolIds.has(app.app_id),
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
      showWorkspaceContext: false,
      items: personalTools.map((app, position) => ({
        app_id: app.app_id,
        title: app.title,
        route_base: app.route_base,
        icon_key: app.icon_key,
        availability_scope: 'platform',
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
  };
}
