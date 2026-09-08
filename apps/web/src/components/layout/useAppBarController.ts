import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { EMPTY_LAUNCHER_GLOBAL_PATHS } from '@/src/app/shell/navigation-types';
import {
  useShellRealtime,
  useShellRealtimeEvent,
} from '@/src/app/shell/shell-realtime-context';
import { type ShellAppId } from '@/src/platform/apps/app-links';
import { type AppBarAppId } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  INITIAL_APP_BAR_STATE,
  appBarReducer,
  buildAppBarItemsProjection,
  buildNotificationIssueHref,
  buildSearchHref,
  buildVisibleAppBarItems,
  resolveDefaultDraftPinnedAppIds,
  resolveEditorDraftPinnedAppIds,
  resolvePinnedAppIds,
  resolveSavablePinnedAppIds,
  type AppBarProps,
  type AppBarTranslator,
} from './app-bar-model';

export function useAppBarController({
  activeAppId,
  appBarFixedAppIds = [],
  appBarItems,
  appBarPinnedByDefaultAppIds = [],
  canOpenSearch = false,
  currentPathname,
  currentUser,
  launcherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
  notificationIssueAppId = null,
  notificationRealtimeEventTypes = new Set(),
  notificationUnreadCountLoader = null,
  notificationsEnabled = false,
  appBarCategories,
  apps,
}: AppBarProps) {
  const { token, updatePreferences } = useAuth();
  const { reconnectSeq } = useShellRealtime();
  const { t } = useTranslation(['common', 'shell', 'auth']);
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(appBarReducer, INITIAL_APP_BAR_STATE);
  const moreMenuRef = useRef<HTMLDivElement>(null);
  const previousPathnameRef = useRef(currentPathname);
  const translate = t as AppBarTranslator;
  const launcherPolicy = useMemo(
    () => ({
      fixedAppIds: new Set(appBarFixedAppIds),
      pinnedByDefaultAppIds: appBarPinnedByDefaultAppIds,
    }),
    [appBarFixedAppIds, appBarPinnedByDefaultAppIds],
  );

  useEffect(() => {
    if (!notificationsEnabled || !notificationUnreadCountLoader || !token) {
      dispatch({ type: 'patch', patch: { unreadCount: 0 } });
      return;
    }

    let active = true;

    const syncUnreadCount = async () => {
      try {
        const res = await notificationUnreadCountLoader(token);
        if (active) {
          dispatch({ type: 'patch', patch: { unreadCount: res.count } });
        }
      } catch {
        return;
      }
    };

    void syncUnreadCount();

    return () => {
      active = false;
    };
  }, [
    notificationUnreadCountLoader,
    notificationsEnabled,
    reconnectSeq,
    token,
  ]);

  useShellRealtimeEvent(
    '*',
    useCallback(
      (event) => {
        if (
          !notificationsEnabled ||
          !token ||
          !notificationRealtimeEventTypes.has(event.type)
        ) {
          return;
        }
        const data = event.data as { unread_count?: unknown } | undefined;
        dispatch({
          type: 'patch',
          patch: {
            notificationRefreshSeq: state.notificationRefreshSeq + 1,
            unreadCount:
              typeof data?.unread_count === 'number'
                ? data.unread_count
                : state.unreadCount,
          },
        });
      },
      [
        notificationRealtimeEventTypes,
        notificationsEnabled,
        state.notificationRefreshSeq,
        state.unreadCount,
        token,
      ],
    ),
  );

  useEffect(() => {
    if (previousPathnameRef.current === currentPathname) {
      return;
    }
    previousPathnameRef.current = currentPathname;
    if (state.favoritesOpen || state.categoryMenuId || state.appBarEditorOpen) {
      dispatch({
        type: 'patch',
        patch: {
          appBarEditorOpen: false,
          categoryMenuId: null,
          favoritesOpen: false,
        },
      });
    }
  }, [
    currentPathname,
    state.appBarEditorOpen,
    state.categoryMenuId,
    state.favoritesOpen,
  ]);

  useEffect(() => {
    if (
      !state.favoritesOpen &&
      !state.categoryMenuId &&
      !state.appBarEditorOpen
    ) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (
        moreMenuRef.current &&
        !moreMenuRef.current.contains(event.target as Node)
      ) {
        dispatch({
          type: 'patch',
          patch: {
            appBarEditorOpen: false,
            categoryMenuId: null,
            favoritesOpen: false,
          },
        });
      }
    }

    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, [state.appBarEditorOpen, state.categoryMenuId, state.favoritesOpen]);

  const handleCountChange = useCallback(
    (delta: number) => {
      dispatch({
        type: 'patch',
        patch: {
          unreadCount: Math.max(0, state.unreadCount + delta),
        },
      });
    },
    [state.unreadCount],
  );

  const handleNavigateToIssue = useCallback(
    (taskId: string) => {
      const issueHref = buildNotificationIssueHref({
        appId: notificationIssueAppId,
        launcherGlobalPaths,
        taskId,
      });
      if (!issueHref) {
        return;
      }
      navigate(issueHref);
    },
    [launcherGlobalPaths, navigate, notificationIssueAppId],
  );

  const visibleItems = useMemo(
    () =>
      buildVisibleAppBarItems(
        apps,
        appBarCategories,
        translate,
        appBarItems,
        launcherPolicy,
      ),
    [appBarItems, launcherPolicy, translate, appBarCategories, apps],
  );
  const pinnedAppIds = useMemo(
    () =>
      resolvePinnedAppIds(
        currentUser.app_bar_layout,
        visibleItems,
        launcherPolicy,
      ),
    [currentUser.app_bar_layout, launcherPolicy, visibleItems],
  );
  const itemProjection = useMemo(
    () =>
      buildAppBarItemsProjection({
        activeAppId,
        appBarItems,
        draftPinnedAppIds: state.draftPinnedAppIds,
        launcherPolicy,
        pinnedAppIds,
        translate,
        visibleItems,
      }),
    [
      activeAppId,
      appBarItems,
      launcherPolicy,
      pinnedAppIds,
      state.draftPinnedAppIds,
      translate,
      visibleItems,
    ],
  );
  const {
    activeAppTitle,
    draftItems,
    fixedItems,
    pinnedEligibleAppIds,
    pinnedItems,
  } = itemProjection;
  const workspaceSearchHref = buildSearchHref();
  const openAppBarEditor = useCallback(() => {
    dispatch({
      type: 'patch',
      patch: {
        appBarEditorOpen: true,
        appBarLayoutError: null,
        draftPinnedAppIds: resolveEditorDraftPinnedAppIds(
          pinnedAppIds,
          pinnedEligibleAppIds,
          launcherPolicy,
        ),
        categoryMenuId: null,
        favoritesOpen: false,
      },
    });
  }, [launcherPolicy, pinnedAppIds, pinnedEligibleAppIds]);

  const resetDraftPinnedApps = useCallback(() => {
    dispatch({
      type: 'patch',
      patch: {
        appBarLayoutError: null,
        draftPinnedAppIds: resolveDefaultDraftPinnedAppIds(
          pinnedEligibleAppIds,
          launcherPolicy,
        ),
      },
    });
  }, [launcherPolicy, pinnedEligibleAppIds]);

  const saveAppBarLayout = useCallback(async () => {
    const nextPinnedAppIds = resolveSavablePinnedAppIds(
      state.draftPinnedAppIds,
      pinnedEligibleAppIds,
      launcherPolicy,
    );

    dispatch({
      type: 'patch',
      patch: { appBarLayoutError: null, appBarLayoutSaving: true },
    });
    try {
      await updatePreferences({
        app_bar_layout: {
          pinned_app_ids: nextPinnedAppIds as AppBarAppId[],
        },
      });
      dispatch({
        type: 'patch',
        patch: { appBarEditorOpen: false },
      });
    } catch (caughtError) {
      dispatch({
        type: 'patch',
        patch: {
          appBarLayoutError:
            caughtError instanceof Error && caughtError.message
              ? caughtError.message
              : translate('shell:appBarEditor.saveFailed'),
        },
      });
    } finally {
      dispatch({
        type: 'patch',
        patch: { appBarLayoutSaving: false },
      });
    }
  }, [
    pinnedEligibleAppIds,
    launcherPolicy,
    state.draftPinnedAppIds,
    translate,
    updatePreferences,
  ]);

  return {
    activeAppTitle,
    canOpenSearch,
    draftItems,
    fixedItems,
    handleCountChange,
    handleNavigateToIssue,
    moreMenuRef,
    onCloseEditor: () =>
      dispatch({ type: 'patch', patch: { appBarEditorOpen: false } }),
    onCloseLauncherMenus: () => dispatch({ type: 'closeLauncherMenus' }),
    onMovePinnedApp: (appId: ShellAppId, direction: -1 | 1) =>
      dispatch({ type: 'moveDraftPinned', appId, direction }),
    onOpenEditor: openAppBarEditor,
    onOpenSearch: () => {
      dispatch({
        type: 'patch',
        patch: {
          categoryMenuId: null,
          favoritesOpen: false,
        },
      });
      navigate(workspaceSearchHref);
    },
    onResetDraft: resetDraftPinnedApps,
    onSaveLayout: () => {
      void saveAppBarLayout();
    },
    onToggleCategoryMenu: (categoryId: string) =>
      dispatch({ type: 'toggleCategoryMenu', categoryId }),
    onToggleFavorites: () => dispatch({ type: 'toggleFavorites' }),
    onToggleNotifications: () => {
      if (notificationsEnabled) {
        dispatch({ type: 'toggleNotifications' });
      }
    },
    onTogglePinnedApp: (appId: ShellAppId, checked: boolean) => {
      dispatch({ type: 'toggleDraftPinned', appId, checked });
    },
    pinnedEligibleAppIds,
    pinnedItems,
    state,
    t: translate,
    workspaceSearchHref,
  };
}
