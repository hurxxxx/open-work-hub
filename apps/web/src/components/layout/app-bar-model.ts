import type { ComponentType } from 'react';

import type {
  AppBarItem,
  LauncherGlobalPaths,
} from '@/src/app/shell/navigation-types';
import type {
  AppBarLayoutPreference,
  AuthUser,
} from '@/src/platform/auth/auth-api';
import {
  buildWorkspaceAppPath,
  getPreferredWorkspace,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';
import type {
  WorkspaceBootstrapAppBarCategory,
  WorkspaceBootstrapApp,
} from '@/src/platform/workspaces/workspaces-api';
import { workspaceAppIconForKey } from '@/src/platform/workspaces/workspace-app-icons';

export interface AppBarLauncherPolicy {
  fixedAppIds: ReadonlySet<string>;
  pinnedByDefaultAppIds: readonly string[];
}

const EMPTY_APP_BAR_LAUNCHER_POLICY: AppBarLauncherPolicy = {
  fixedAppIds: new Set(),
  pinnedByDefaultAppIds: [],
};

function normalizeAppBarAppId(appId: string): WorkspaceAppId {
  return appId as WorkspaceAppId;
}

export function createAppBarItemById(appBarItems: readonly AppBarItem[]) {
  return new Map(appBarItems.map((item) => [item.id, item]));
}

export type AppBarTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export type AppBarWorkspaceItem = {
  id: WorkspaceAppId;
  title: string;
  icon: AppBarItem['icon'];
  pinnable?: boolean;
};

export type AppBarState = {
  appBarEditorOpen: boolean;
  appBarLayoutError: string | null;
  appBarLayoutSaving: boolean;
  businessSitesOpen: boolean;
  categoryMenuId: string | null;
  defaultWorkspaceSaving: boolean;
  draftPinnedAppIds: WorkspaceAppId[];
  favoritesOpen: boolean;
  notificationRefreshSeq: number;
  notifOpen: boolean;
  optimisticDefaultWorkspaceId: string | null | undefined;
  unreadCount: number;
  workspacePreferenceError: string | null;
  workspaceQuery: string;
  workspaceSwitcherOpen: boolean;
};

export type AppBarAction =
  | { type: 'patch'; patch: Partial<AppBarState> }
  | { type: 'toggleBusinessSites' }
  | { type: 'closeBusinessSites' }
  | { type: 'toggleNotifications' }
  | { type: 'toggleWorkspaceSwitcher' }
  | { type: 'toggleFavorites' }
  | { type: 'toggleCategoryMenu'; categoryId: string }
  | { type: 'closeLauncherMenus' }
  | { type: 'toggleDraftPinned'; appId: WorkspaceAppId; checked: boolean }
  | { type: 'moveDraftPinned'; appId: WorkspaceAppId; direction: -1 | 1 };

export const INITIAL_APP_BAR_STATE: AppBarState = {
  appBarEditorOpen: false,
  appBarLayoutError: null,
  appBarLayoutSaving: false,
  businessSitesOpen: false,
  categoryMenuId: null,
  defaultWorkspaceSaving: false,
  draftPinnedAppIds: [],
  favoritesOpen: false,
  notificationRefreshSeq: 0,
  notifOpen: false,
  optimisticDefaultWorkspaceId: undefined,
  unreadCount: 0,
  workspacePreferenceError: null,
  workspaceQuery: '',
  workspaceSwitcherOpen: false,
};

export type AppBarProps = {
  activeAppId: string;
  appBarFixedAppIds?: readonly string[];
  appBarItems?: readonly AppBarItem[];
  appBarPinnedByDefaultAppIds?: readonly string[];
  canOpenWorkspaceSearch?: boolean;
  canOpenMobileAppMenu?: boolean;
  currentPathname: string;
  currentUser: AuthUser;
  launcherGlobalPaths?: LauncherGlobalPaths;
  /** App that owns issue destinations surfaced by the notification adapter. */
  notificationIssueAppId?: string | null;
  notificationPanel?: AppBarNotificationPanelComponent | null;
  notificationRealtimeEventTypes?: ReadonlySet<string>;
  notificationUnreadCountLoader?: AppBarNotificationUnreadCountLoader | null;
  notificationsEnabled?: boolean;
  onDesktopMenuOpenChange?: (open: boolean) => void;
  onDesktopRailMouseEnter?: () => void;
  onDesktopRailMouseLeave?: () => void;
  onOpenHelp: () => void;
  onOpenMobileAppMenu?: () => void;
  onShellWorkspaceChange: (workspaceSlug: string | null) => void;
  shellWorkspaceSlug: string | null;
  workspaceAppBarCategories: WorkspaceBootstrapAppBarCategory[];
  workspaceApps: WorkspaceBootstrapApp[];
  onOpenAccount: () => void;
  onOpenMobileNavigation: () => void;
};

export type AppBarNotificationPanelComponent = ComponentType<{
  onClose: () => void;
  onCountChange?: (count: number) => void;
  onNavigateToIssue?: (taskId: string) => void;
  refreshKey?: number;
  workspaceSlug: string | null;
}>;

export type AppBarNotificationUnreadCountLoader = (
  token: string,
  workspaceSlug: string | null,
) => Promise<{ count: number }>;

export function appBarReducer(
  state: AppBarState,
  action: AppBarAction,
): AppBarState {
  switch (action.type) {
    case 'patch':
      return { ...state, ...action.patch };
    case 'toggleBusinessSites':
      return {
        ...state,
        appBarEditorOpen: false,
        businessSitesOpen: !state.businessSitesOpen,
        categoryMenuId: null,
        favoritesOpen: false,
        workspaceSwitcherOpen: false,
      };
    case 'closeBusinessSites':
      return {
        ...state,
        businessSitesOpen: false,
      };
    case 'toggleNotifications':
      return {
        ...state,
        businessSitesOpen: false,
        notifOpen: !state.notifOpen,
      };
    case 'toggleWorkspaceSwitcher':
      return {
        ...state,
        appBarEditorOpen: false,
        businessSitesOpen: false,
        categoryMenuId: null,
        favoritesOpen: false,
        workspaceSwitcherOpen: !state.workspaceSwitcherOpen,
      };
    case 'toggleFavorites':
      return {
        ...state,
        appBarEditorOpen: false,
        businessSitesOpen: false,
        categoryMenuId: null,
        favoritesOpen: !state.favoritesOpen,
        workspaceSwitcherOpen: false,
      };
    case 'toggleCategoryMenu':
      return {
        ...state,
        appBarEditorOpen: false,
        businessSitesOpen: false,
        categoryMenuId:
          state.categoryMenuId === action.categoryId ? null : action.categoryId,
        favoritesOpen: false,
        workspaceSwitcherOpen: false,
      };
    case 'closeLauncherMenus':
      return {
        ...state,
        appBarEditorOpen: false,
        categoryMenuId: null,
        favoritesOpen: false,
      };
    case 'toggleDraftPinned':
      if (action.checked) {
        return state.draftPinnedAppIds.includes(action.appId)
          ? state
          : {
              ...state,
              appBarLayoutError: null,
              draftPinnedAppIds: [...state.draftPinnedAppIds, action.appId],
            };
      }
      return {
        ...state,
        appBarLayoutError: null,
        draftPinnedAppIds: state.draftPinnedAppIds.filter(
          (item) => item !== action.appId,
        ),
      };
    case 'moveDraftPinned': {
      const index = state.draftPinnedAppIds.indexOf(action.appId);
      const nextIndex = index + action.direction;
      if (
        index < 0 ||
        nextIndex < 0 ||
        nextIndex >= state.draftPinnedAppIds.length
      ) {
        return state;
      }

      const next = [...state.draftPinnedAppIds];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return { ...state, draftPinnedAppIds: next };
    }
  }
}

export function resolvePinnedAppIds(
  layout: AppBarLayoutPreference | null | undefined,
  visibleItems: readonly { id: string; pinnable?: boolean }[] = [],
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): WorkspaceAppId[] {
  const knownAppIds = new Set<string>(
    visibleItems
      .filter((item) => item.pinnable !== false)
      .map((item) => item.id),
  );
  const rawPinnedIds = Array.isArray(layout?.pinned_app_ids)
    ? layout.pinned_app_ids
    : launcherPolicy.pinnedByDefaultAppIds;
  const normalizedRawPinnedIds = rawPinnedIds
    .map((appId) => normalizeAppBarAppId(appId))
    .filter((appId) => !launcherPolicy.fixedAppIds.has(appId));

  const pinnedIds: WorkspaceAppId[] = [];
  const pinnedIdSet = new Set<WorkspaceAppId>();

  for (const workspaceAppId of normalizedRawPinnedIds) {
    if (!knownAppIds.has(workspaceAppId)) {
      continue;
    }
    if (!pinnedIdSet.has(workspaceAppId)) {
      pinnedIdSet.add(workspaceAppId);
      pinnedIds.push(workspaceAppId);
    }
  }

  return pinnedIds;
}

export function orderItemsByPinnedIds(
  visibleItems: AppBarWorkspaceItem[],
  pinnedAppIds: WorkspaceAppId[],
): AppBarWorkspaceItem[] {
  const itemById = new Map(visibleItems.map((item) => [item.id, item]));
  return pinnedAppIds.flatMap((appId) => {
    const item = itemById.get(appId);
    return item ? [item] : [];
  });
}

export function getInitials(label: string, fallback: string): string {
  const initials = label
    .trim()
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return initials || fallback;
}

export function buildAppLink(
  appId: WorkspaceAppId,
  currentUser: AuthUser,
  shellWorkspaceSlug: string | null,
  launcherGlobalPaths: LauncherGlobalPaths,
): string {
  const globalPath = launcherGlobalPaths.get(appId);
  if (globalPath) {
    return globalPath;
  }

  const workspaceForShellSlug = shellWorkspaceSlug
    ? currentUser.workspaces.find(
        (workspace) => workspace.slug === shellWorkspaceSlug,
      )
    : undefined;
  const selectedWorkspace =
    workspaceForShellSlug ?? getPreferredWorkspace(currentUser, appId);

  return selectedWorkspace
    ? buildWorkspaceAppPath(selectedWorkspace.slug, appId)
    : '/';
}

export function buildNotificationIssueHref({
  appId,
  currentUser,
  launcherGlobalPaths,
  shellWorkspaceSlug,
  taskId,
}: {
  appId: string | null | undefined;
  currentUser: AuthUser;
  launcherGlobalPaths: LauncherGlobalPaths;
  shellWorkspaceSlug: string | null;
  taskId: string;
}): string | null {
  if (!appId) {
    return null;
  }
  const appPath = buildAppLink(
    appId as WorkspaceAppId,
    currentUser,
    shellWorkspaceSlug,
    launcherGlobalPaths,
  );
  return appPath === '/'
    ? null
    : `${appPath}?task=${encodeURIComponent(taskId)}`;
}

export type AppBarAppLinkResolver = (appId: WorkspaceAppId) => string;

type AppBarWorkspace = AuthUser['workspaces'][number];

export function sortAppBarWorkspacesByName(
  workspaces: AuthUser['workspaces'],
  locale: string,
): AuthUser['workspaces'] {
  const sorted = Array.from(workspaces);
  sorted.sort((left, right) => left.name.localeCompare(right.name, locale));
  return sorted;
}

export interface AppBarWorkspaceProjection {
  currentWorkspace: AppBarWorkspace | null;
  currentWorkspaceName: string;
  defaultWorkspaceOptions: AuthUser['workspaces'];
  normalizedDefaultWorkspaceId: string | null;
  otherWorkspaces: AuthUser['workspaces'];
  pinnedWorkspace: AppBarWorkspace | null;
}

export function buildAppBarWorkspaceProjection({
  defaultWorkspaceId,
  locale,
  shellWorkspaceSlug,
  workspaceFallbackLabel,
  workspaceQuery,
  workspaces,
}: {
  defaultWorkspaceId: string | null | undefined;
  locale: string;
  shellWorkspaceSlug: string | null;
  workspaceFallbackLabel: string;
  workspaceQuery: string;
  workspaces: AuthUser['workspaces'];
}): AppBarWorkspaceProjection {
  const currentWorkspace =
    workspaces.find((workspace) => workspace.slug === shellWorkspaceSlug) ??
    null;
  const normalizedWorkspaceQuery = workspaceQuery.trim().toLowerCase();
  const matchingWorkspaces = workspaces.filter((workspace) => {
    if (!normalizedWorkspaceQuery) {
      return true;
    }

    const haystack = `${workspace.name} ${workspace.slug}`.toLowerCase();
    return haystack.includes(normalizedWorkspaceQuery);
  });
  const matchingWorkspaceIds = new Set(
    matchingWorkspaces.map((workspace) => workspace.id),
  );
  const defaultWorkspaceOptions = sortAppBarWorkspacesByName(
    workspaces,
    locale,
  );

  return {
    currentWorkspace,
    currentWorkspaceName: currentWorkspace?.name ?? workspaceFallbackLabel,
    defaultWorkspaceOptions,
    normalizedDefaultWorkspaceId: defaultWorkspaceOptions.some(
      (workspace) => workspace.id === defaultWorkspaceId,
    )
      ? (defaultWorkspaceId ?? null)
      : null,
    otherWorkspaces: sortAppBarWorkspacesByName(
      matchingWorkspaces.filter(
        (workspace) => workspace.id !== currentWorkspace?.id,
      ),
      locale,
    ),
    pinnedWorkspace:
      currentWorkspace && matchingWorkspaceIds.has(currentWorkspace.id)
        ? currentWorkspace
        : null,
  };
}

export function buildVisibleAppBarItems(
  workspaceApps: WorkspaceBootstrapApp[],
  appBarCategories: WorkspaceBootstrapAppBarCategory[],
  translate: AppBarTranslator,
  appBarItems: readonly AppBarItem[] = [],
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): AppBarWorkspaceItem[] {
  const appBarItemById = createAppBarItemById(appBarItems);
  const items: AppBarWorkspaceItem[] = [];
  const itemIds = new Set<WorkspaceAppId>();

  for (const item of workspaceApps) {
    if (!item.enabled) {
      continue;
    }
    const id = item.app_id as WorkspaceAppId;
    if (!launcherPolicy.fixedAppIds.has(id)) {
      continue;
    }
    const localItem = appBarItemById.get(item.app_id as AppBarItem['id']);
    if (itemIds.has(id)) {
      continue;
    }
    itemIds.add(id);
    items.push({
      id,
      title: translate(`shell:apps.${item.app_id}`, {
        defaultValue: item.title,
      }),
      icon: localItem?.icon ?? workspaceAppIconForKey(item.icon_key),
    });
  }

  for (const category of appBarCategories) {
    for (const launcherItem of category.items) {
      if (!launcherItem.enabled) {
        continue;
      }
      const id = launcherItem.app_id as WorkspaceAppId;
      if (itemIds.has(id)) {
        continue;
      }
      itemIds.add(id);
      items.push({
        id,
        title: translate(`shell:apps.${launcherItem.app_id}`, {
          defaultValue: launcherItem.title,
        }),
        icon: workspaceAppIconForKey(launcherItem.icon_key),
        pinnable: category.pinnable !== false,
      });
    }
  }

  return items;
}

export interface AppBarItemsProjection {
  activeAppTitle: string;
  draftItems: AppBarWorkspaceItem[];
  fixedItems: AppBarWorkspaceItem[];
  pinnedEligibleAppIds: Set<WorkspaceAppId>;
  pinnedItems: AppBarWorkspaceItem[];
}

export function buildAppBarItemsProjection({
  activeAppId,
  appBarItems = [],
  draftPinnedAppIds,
  launcherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
  pinnedAppIds,
  translate,
  visibleItems,
}: {
  activeAppId: string;
  appBarItems?: readonly AppBarItem[];
  draftPinnedAppIds: WorkspaceAppId[];
  launcherPolicy?: AppBarLauncherPolicy;
  pinnedAppIds: WorkspaceAppId[];
  translate: AppBarTranslator;
  visibleItems: AppBarWorkspaceItem[];
}): AppBarItemsProjection {
  const appBarItemById = createAppBarItemById(appBarItems);
  const fixedItems = visibleItems.filter((item) =>
    launcherPolicy.fixedAppIds.has(item.id),
  );
  const customizableItems = visibleItems.filter(
    (item) =>
      !launcherPolicy.fixedAppIds.has(item.id) && item.pinnable !== false,
  );
  const pinnedItems = orderItemsByPinnedIds(customizableItems, pinnedAppIds);
  const pinnedEligibleAppIds = new Set(
    customizableItems.map((item) => item.id),
  );
  const draftPinnedAppIdSet = new Set(draftPinnedAppIds);
  const draftItems = [
    ...orderItemsByPinnedIds(customizableItems, draftPinnedAppIds),
    ...customizableItems.filter((item) => !draftPinnedAppIdSet.has(item.id)),
  ];
  const activeWorkspaceApp = visibleItems.find(
    (item) => item.id === activeAppId,
  );

  return {
    activeAppTitle:
      activeAppId === 'settings'
        ? translate('shell:apps.settings')
        : activeAppId === 'search'
          ? translate('shell:search.title')
          : (activeWorkspaceApp?.title ??
            translate(`shell:apps.${activeAppId}`, {
              defaultValue:
                appBarItemById.get(activeAppId as AppBarItem['id'])?.title ??
                'Open ALM',
            })),
    draftItems,
    fixedItems,
    pinnedEligibleAppIds,
    pinnedItems,
  };
}

export function resolveEditorDraftPinnedAppIds(
  pinnedAppIds: WorkspaceAppId[],
  pinnedEligibleAppIds: Set<WorkspaceAppId>,
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): WorkspaceAppId[] {
  return pinnedAppIds.filter(
    (appId) =>
      pinnedEligibleAppIds.has(appId) && !launcherPolicy.fixedAppIds.has(appId),
  );
}

export function resolveDefaultDraftPinnedAppIds(
  pinnedEligibleAppIds: Set<WorkspaceAppId>,
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): WorkspaceAppId[] {
  return launcherPolicy.pinnedByDefaultAppIds.filter((appId) =>
    pinnedEligibleAppIds.has(appId),
  ) as WorkspaceAppId[];
}

export function resolveSavablePinnedAppIds(
  draftPinnedAppIds: WorkspaceAppId[],
  pinnedEligibleAppIds: Set<WorkspaceAppId>,
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): WorkspaceAppId[] {
  return draftPinnedAppIds.filter(
    (appId) =>
      pinnedEligibleAppIds.has(appId) && !launcherPolicy.fixedAppIds.has(appId),
  );
}

export function buildWorkspaceSearchHref(
  shellWorkspaceSlug: string | null,
): string {
  return shellWorkspaceSlug
    ? `/tool/search?workspace=${encodeURIComponent(shellWorkspaceSlug)}`
    : '/tool/search';
}
