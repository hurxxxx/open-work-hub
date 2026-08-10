import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  workspaceRoleAllows,
  type AppBarAppId,
} from '@/src/platform/auth/auth-api';
import {
  useShellRealtime,
  useShellRealtimeEvent,
} from '@/src/app/shell/shell-realtime-context';
import {
  persistLastWorkspaceSlug,
  resolveWorkspaceSwitchPath,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';
import { EMPTY_LAUNCHER_GLOBAL_PATHS } from '@/src/app/shell/navigation-types';
import {
  INITIAL_APP_BAR_STATE,
  appBarReducer,
  buildAppBarItemsProjection,
  buildAppBarWorkspaceProjection,
  buildNotificationIssueHref,
  buildVisibleAppBarItems,
  buildWorkspaceSearchHref,
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
  canOpenWorkspaceSearch = false,
  currentPathname,
  currentUser,
  launcherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
  notificationIssueAppId = null,
  notificationRealtimeEventTypes = new Set(),
  notificationUnreadCountLoader = null,
  notificationsEnabled = false,
  onShellWorkspaceChange,
  shellWorkspaceSlug,
  workspaceAppBarCategories,
  workspaceApps,
}: AppBarProps) {
  const { hasPermission, token, updatePreferences } = useAuth();
  const { reconnectSeq } = useShellRealtime();
  const { t, i18n } = useTranslation(['common', 'shell', 'auth']);
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(appBarReducer, INITIAL_APP_BAR_STATE);
  const workspaceSwitcherRef = useRef<HTMLDivElement>(null);
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

  const canCreateWorkspace = hasPermission('workspace.write');
  const defaultWorkspaceId =
    state.optimisticDefaultWorkspaceId === undefined
      ? (currentUser.default_workspace_id ?? null)
      : state.optimisticDefaultWorkspaceId;
  const workspaceProjection = useMemo(
    () =>
      buildAppBarWorkspaceProjection({
        defaultWorkspaceId,
        locale: i18n.language,
        shellWorkspaceSlug,
        workspaceFallbackLabel: translate('common:labels.workspace'),
        workspaceQuery: state.workspaceQuery,
        workspaces: currentUser.workspaces,
      }),
    [
      currentUser.workspaces,
      defaultWorkspaceId,
      i18n.language,
      shellWorkspaceSlug,
      state.workspaceQuery,
      translate,
    ],
  );
  const {
    currentWorkspace,
    currentWorkspaceName,
    defaultWorkspaceOptions,
    normalizedDefaultWorkspaceId,
    otherWorkspaces,
    pinnedWorkspace,
  } = workspaceProjection;
  const canManageCurrentWorkspace = workspaceRoleAllows(
    currentWorkspace?.role,
    'admin',
  );

  useEffect(() => {
    if (!notificationsEnabled || !notificationUnreadCountLoader || !token) {
      dispatch({ type: 'patch', patch: { unreadCount: 0 } });
      return;
    }

    let active = true;

    const syncUnreadCount = async () => {
      try {
        const res = await notificationUnreadCountLoader(
          token,
          shellWorkspaceSlug,
        );
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
    shellWorkspaceSlug,
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
            notificationRefreshSeq:
              event.type === 'notification.snapshot'
                ? state.notificationRefreshSeq
                : state.notificationRefreshSeq + 1,
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
    if (
      state.favoritesOpen ||
      state.categoryMenuId ||
      state.appBarEditorOpen
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
  }, [
    currentPathname,
    state.appBarEditorOpen,
    state.categoryMenuId,
    state.favoritesOpen,
  ]);

  useEffect(() => {
    if (!state.workspaceSwitcherOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (
        workspaceSwitcherRef.current &&
        !workspaceSwitcherRef.current.contains(event.target as Node)
      ) {
        dispatch({
          type: 'patch',
          patch: { workspaceSwitcherOpen: false },
        });
      }
    }

    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, [state.workspaceSwitcherOpen]);

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
        currentUser,
        launcherGlobalPaths,
        shellWorkspaceSlug,
        taskId,
      });
      if (!issueHref) {
        return;
      }
      navigate(issueHref);
    },
    [
      currentUser,
      launcherGlobalPaths,
      navigate,
      notificationIssueAppId,
      shellWorkspaceSlug,
    ],
  );

  const handleWorkspaceSelect = useCallback(
    (nextWorkspaceSlug: string) => {
      if (nextWorkspaceSlug === shellWorkspaceSlug) {
        dispatch({
          type: 'patch',
          patch: { workspaceSwitcherOpen: false },
        });
        return;
      }

      persistLastWorkspaceSlug(nextWorkspaceSlug);
      onShellWorkspaceChange(nextWorkspaceSlug);
      dispatch({
        type: 'patch',
        patch: { workspaceQuery: '', workspaceSwitcherOpen: false },
      });
      navigate(
        resolveWorkspaceSwitchPath(
          currentUser,
          currentPathname,
          nextWorkspaceSlug,
          workspaceApps.flatMap((app) => (app.enabled ? [app.app_id] : [])),
        ),
      );
    },
    [
      currentPathname,
      currentUser,
      navigate,
      onShellWorkspaceChange,
      shellWorkspaceSlug,
      workspaceApps,
    ],
  );

  const handleSetDefaultWorkspace = useCallback(
    async (workspaceId: string | null) => {
      if (workspaceId === defaultWorkspaceId || state.defaultWorkspaceSaving) {
        return;
      }

      const previousDefaultWorkspaceId = defaultWorkspaceId;
      dispatch({
        type: 'patch',
        patch: {
          defaultWorkspaceSaving: true,
          optimisticDefaultWorkspaceId: workspaceId,
          workspacePreferenceError: null,
        },
      });
      try {
        await updatePreferences({ default_workspace_id: workspaceId });
      } catch (caughtError) {
        dispatch({
          type: 'patch',
          patch: {
            optimisticDefaultWorkspaceId: previousDefaultWorkspaceId,
            workspacePreferenceError:
              caughtError instanceof Error
                ? caughtError.message
                : translate('shell:workspaceSwitcher.defaultSaveFailed'),
          },
        });
      } finally {
        dispatch({
          type: 'patch',
          patch: { defaultWorkspaceSaving: false },
        });
      }
    },
    [
      defaultWorkspaceId,
      state.defaultWorkspaceSaving,
      translate,
      updatePreferences,
    ],
  );

  const visibleItems = useMemo(
    () =>
      buildVisibleAppBarItems(
        workspaceApps,
        workspaceAppBarCategories,
        translate,
        appBarItems,
        launcherPolicy,
      ),
    [
      appBarItems,
      launcherPolicy,
      translate,
      workspaceAppBarCategories,
      workspaceApps,
    ],
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
  const workspaceSearchHref = buildWorkspaceSearchHref(shellWorkspaceSlug);
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
    canCreateWorkspace,
    canManageCurrentWorkspace,
    canOpenWorkspaceSearch,
    currentWorkspace,
    currentWorkspaceName,
    defaultWorkspaceOptions,
    draftItems,
    fixedItems,
    handleCountChange,
    handleNavigateToIssue,
    handleSetDefaultWorkspace,
    handleWorkspaceSelect,
    moreMenuRef,
    normalizedDefaultWorkspaceId,
    onCloseEditor: () =>
      dispatch({ type: 'patch', patch: { appBarEditorOpen: false } }),
    onCloseLauncherMenus: () => dispatch({ type: 'closeLauncherMenus' }),
    onCreateWorkspace: () => {
      dispatch({
        type: 'patch',
        patch: {
          categoryMenuId: null,
          favoritesOpen: false,
          workspaceSwitcherOpen: false,
        },
      });
      navigate('/admin/workspaces');
    },
    onManageCurrentWorkspace: () => {
      if (!currentWorkspace) {
        return;
      }
      dispatch({
        type: 'patch',
        patch: {
          categoryMenuId: null,
          favoritesOpen: false,
          workspaceSwitcherOpen: false,
        },
      });
      navigate(`/w/${encodeURIComponent(currentWorkspace.slug)}/settings`);
    },
    onMovePinnedApp: (appId: WorkspaceAppId, direction: -1 | 1) =>
      dispatch({ type: 'moveDraftPinned', appId, direction }),
    onOpenEditor: openAppBarEditor,
    onOpenWorkspaceSearch: () => {
      dispatch({
        type: 'patch',
        patch: {
          categoryMenuId: null,
          favoritesOpen: false,
          workspaceSwitcherOpen: false,
        },
      });
      navigate(workspaceSearchHref);
    },
    onResetDraft: resetDraftPinnedApps,
    onSaveLayout: () => {
      void saveAppBarLayout();
    },
    onSearchQueryChange: (workspaceQuery: string) =>
      dispatch({ type: 'patch', patch: { workspaceQuery } }),
    onToggleCategoryMenu: (categoryId: string) =>
      dispatch({ type: 'toggleCategoryMenu', categoryId }),
    onToggleFavorites: () => dispatch({ type: 'toggleFavorites' }),
    onToggleNotifications: () => {
      if (notificationsEnabled) {
        dispatch({ type: 'toggleNotifications' });
      }
    },
    onToggleWorkspaceSwitcher: () =>
      dispatch({ type: 'toggleWorkspaceSwitcher' }),
    onTogglePinnedApp: (appId: WorkspaceAppId, checked: boolean) => {
      dispatch({ type: 'toggleDraftPinned', appId, checked });
    },
    otherWorkspaces,
    pinnedEligibleAppIds,
    pinnedItems,
    pinnedWorkspace,
    state,
    t: translate,
    workspaceSearchHref,
    workspaceSwitcherRef,
  };
}
