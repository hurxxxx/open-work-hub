import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import { buildAppEntryHref } from '@open-work-hub/contracts/app-routes';
import type { ComponentType } from 'react';

import type { AppLaunchDestinationResolver } from '@/src/app/shell/app-launch-destination';
import type {
  AppBarItem,
  LauncherGlobalPaths,
} from '@/src/app/shell/navigation-types';
import { appIconForKey } from '@/src/platform/apps/app-icons';
import { buildAppPath, type ShellAppId } from '@/src/platform/apps/app-links';
import type {
  BootstrapApp,
  BootstrapAppBarCategory,
} from '@/src/platform/apps/apps-api';
import type {
  AppBarLayoutPreference,
  AuthUser,
} from '@/src/platform/auth/auth-api';

export interface AppBarLauncherPolicy {
  fixedAppIds: ReadonlySet<string>;
  pinnedByDefaultAppIds: readonly string[];
}

const EMPTY_APP_BAR_LAUNCHER_POLICY: AppBarLauncherPolicy = {
  fixedAppIds: new Set(),
  pinnedByDefaultAppIds: [],
};

function normalizeAppBarAppId(appId: string): ShellAppId {
  return appId as ShellAppId;
}

function isExecutableAppId(appId: string): boolean {
  return APP_CONTRACT_BY_ID.has(appId as AppId);
}

export function createAppBarItemById(appBarItems: readonly AppBarItem[]) {
  return new Map(appBarItems.map((item) => [item.id, item]));
}

export type AppBarTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export type AppBarLaunchItem = {
  id: ShellAppId;
  title: string;
  icon: AppBarItem['icon'];
  pinnable?: boolean;
};

export type AppBarState = {
  appBarEditorOpen: boolean;
  appBarLayoutError: string | null;
  appBarLayoutSaving: boolean;
  categoryMenuId: string | null;
  draftPinnedAppIds: ShellAppId[];
  favoritesOpen: boolean;
  notificationRefreshSeq: number;
  notifOpen: boolean;
  unreadCount: number;
};

export type AppBarAction =
  | { type: 'patch'; patch: Partial<AppBarState> }
  | { type: 'toggleNotifications' }
  | { type: 'toggleFavorites' }
  | { type: 'toggleCategoryMenu'; categoryId: string }
  | { type: 'closeLauncherMenus' }
  | { type: 'toggleDraftPinned'; appId: ShellAppId; checked: boolean }
  | { type: 'moveDraftPinned'; appId: ShellAppId; direction: -1 | 1 };

export const INITIAL_APP_BAR_STATE: AppBarState = {
  appBarEditorOpen: false,
  appBarLayoutError: null,
  appBarLayoutSaving: false,
  categoryMenuId: null,
  draftPinnedAppIds: [],
  favoritesOpen: false,
  notificationRefreshSeq: 0,
  notifOpen: false,
  unreadCount: 0,
};

export type AppBarProps = {
  activeAppId: string;
  appBarFixedAppIds?: readonly string[];
  appBarItems?: readonly AppBarItem[];
  appBarPinnedByDefaultAppIds?: readonly string[];
  canOpenSearch?: boolean;
  canOpenMobileAppMenu?: boolean;
  currentPathname: string;
  currentUser: AuthUser;
  currentCompanyLabel: string | null;
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
  resolveAppDestination: AppLaunchDestinationResolver;

  appBarCategories: BootstrapAppBarCategory[];
  apps: BootstrapApp[];
  onOpenAccount: () => void;
  onOpenMobileNavigation: () => void;
};

export type AppBarNotificationPanelComponent = ComponentType<{
  onClose: () => void;
  onCountChange?: (count: number) => void;
  onNavigateToIssue?: (taskId: string) => void;
  refreshKey?: number;
}>;

export type AppBarNotificationUnreadCountLoader = (
  token: string,
) => Promise<{ count: number }>;

export function appBarReducer(
  state: AppBarState,
  action: AppBarAction,
): AppBarState {
  switch (action.type) {
    case 'patch':
      return { ...state, ...action.patch };
    case 'toggleNotifications':
      return {
        ...state,
        notifOpen: !state.notifOpen,
      };
    case 'toggleFavorites':
      return {
        ...state,
        appBarEditorOpen: false,
        categoryMenuId: null,
        favoritesOpen: !state.favoritesOpen,
      };
    case 'toggleCategoryMenu':
      return {
        ...state,
        appBarEditorOpen: false,
        categoryMenuId:
          state.categoryMenuId === action.categoryId ? null : action.categoryId,
        favoritesOpen: false,
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
): ShellAppId[] {
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

  const pinnedIds: ShellAppId[] = [];
  const pinnedIdSet = new Set<ShellAppId>();

  for (const appId of normalizedRawPinnedIds) {
    if (!knownAppIds.has(appId)) {
      continue;
    }
    if (!pinnedIdSet.has(appId)) {
      pinnedIdSet.add(appId);
      pinnedIds.push(appId);
    }
  }

  return pinnedIds;
}

export function orderItemsByPinnedIds(
  visibleItems: AppBarLaunchItem[],
  pinnedAppIds: ShellAppId[],
): AppBarLaunchItem[] {
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

function buildNotificationAppEntryLink(
  appId: ShellAppId,
  launcherGlobalPaths: LauncherGlobalPaths,
): string {
  const globalPath = launcherGlobalPaths.get(appId);
  if (globalPath) {
    return globalPath;
  }

  const contract = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!contract) return '/';
  return buildAppEntryHref(contract.app_id);
}

export function buildNotificationIssueHref({
  appId,
  launcherGlobalPaths,
  taskId,
}: {
  appId: string | null | undefined;
  launcherGlobalPaths: LauncherGlobalPaths;
  taskId: string;
}): string | null {
  if (!appId) {
    return null;
  }
  const appPath = buildNotificationAppEntryLink(
    appId as ShellAppId,
    launcherGlobalPaths,
  );
  return appPath === '/'
    ? null
    : `${appPath}?task=${encodeURIComponent(taskId)}`;
}

export type AppBarAppLinkResolver = (appId: ShellAppId) => string;
export type AppBarAppContextLabelResolver = (appId: ShellAppId) => string;
export type AppBarAppLabelResolver = (
  appId: ShellAppId,
  title: string,
) => string;

export function buildVisibleAppBarItems(
  apps: BootstrapApp[],
  appBarCategories: BootstrapAppBarCategory[],
  translate: AppBarTranslator,
  appBarItems: readonly AppBarItem[] = [],
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): AppBarLaunchItem[] {
  const appBarItemById = createAppBarItemById(appBarItems);
  const items: AppBarLaunchItem[] = [];
  const itemIds = new Set<ShellAppId>();

  for (const item of apps) {
    if (!item.enabled || !isExecutableAppId(item.app_id)) {
      continue;
    }
    const id = item.app_id as ShellAppId;
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
      icon: localItem?.icon ?? appIconForKey(item.icon_key),
    });
  }

  for (const category of appBarCategories) {
    for (const launcherItem of category.items) {
      if (!launcherItem.enabled || !isExecutableAppId(launcherItem.app_id)) {
        continue;
      }
      const id = launcherItem.app_id as ShellAppId;
      if (itemIds.has(id)) {
        continue;
      }
      itemIds.add(id);
      items.push({
        id,
        title: translate(`shell:apps.${launcherItem.app_id}`, {
          defaultValue: launcherItem.title,
        }),
        icon: appIconForKey(launcherItem.icon_key),
        pinnable: category.pinnable !== false,
      });
    }
  }

  return items;
}

export interface AppBarItemsProjection {
  activeAppTitle: string;
  draftItems: AppBarLaunchItem[];
  fixedItems: AppBarLaunchItem[];
  pinnedEligibleAppIds: Set<ShellAppId>;
  pinnedItems: AppBarLaunchItem[];
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
  draftPinnedAppIds: ShellAppId[];
  launcherPolicy?: AppBarLauncherPolicy;
  pinnedAppIds: ShellAppId[];
  translate: AppBarTranslator;
  visibleItems: AppBarLaunchItem[];
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
  const activeApp = visibleItems.find((item) => item.id === activeAppId);

  return {
    activeAppTitle:
      activeAppId === 'settings'
        ? translate('shell:apps.settings')
        : activeAppId === 'launcher'
          ? translate('shell:launcher.title')
          : activeAppId === 'search'
            ? translate('shell:search.title')
            : (activeApp?.title ??
              translate(`shell:apps.${activeAppId}`, {
                defaultValue:
                  appBarItemById.get(activeAppId as AppBarItem['id'])?.title ??
                  'Open Work Hub',
              })),
    draftItems,
    fixedItems,
    pinnedEligibleAppIds,
    pinnedItems,
  };
}

export function resolveEditorDraftPinnedAppIds(
  pinnedAppIds: ShellAppId[],
  pinnedEligibleAppIds: Set<ShellAppId>,
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): ShellAppId[] {
  return pinnedAppIds.filter(
    (appId) =>
      pinnedEligibleAppIds.has(appId) && !launcherPolicy.fixedAppIds.has(appId),
  );
}

export function resolveDefaultDraftPinnedAppIds(
  pinnedEligibleAppIds: Set<ShellAppId>,
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): ShellAppId[] {
  return launcherPolicy.pinnedByDefaultAppIds.filter((appId) =>
    pinnedEligibleAppIds.has(appId),
  ) as ShellAppId[];
}

export function resolveSavablePinnedAppIds(
  draftPinnedAppIds: ShellAppId[],
  pinnedEligibleAppIds: Set<ShellAppId>,
  launcherPolicy: AppBarLauncherPolicy = EMPTY_APP_BAR_LAUNCHER_POLICY,
): ShellAppId[] {
  return draftPinnedAppIds.filter(
    (appId) =>
      pinnedEligibleAppIds.has(appId) && !launcherPolicy.fixedAppIds.has(appId),
  );
}

export function buildSearchHref(): string {
  return buildAppPath('retrieval-search');
}
