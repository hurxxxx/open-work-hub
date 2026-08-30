import { useEffect } from 'react';
import { AnimatePresence } from 'motion/react';

import { AppBarDesktopRail } from './AppBarDesktopRail';
import { AppBarMobileHeader } from './AppBarMobileHeader';
import {
  buildAppLink,
  type AppBarAppLinkResolver,
  type AppBarProps,
} from './app-bar-model';
import { useAppBarController } from './useAppBarController';
import { useNotificationPanelFocus } from './useNotificationPanelFocus';
import { EMPTY_LAUNCHER_GLOBAL_PATHS } from '@/src/app/shell/navigation-types';

export function AppBar(props: AppBarProps) {
  const {
    activeAppId,
    canOpenMobileAppMenu,
    currentUser,
    launcherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
    onDesktopMenuOpenChange,
    onDesktopRailMouseEnter,
    onDesktopRailMouseLeave,
    onOpenAccount,
    onOpenHelp,
    onOpenMobileAppMenu,
    onOpenMobileNavigation,
    shellWorkspaceSlug,
    workspaceAppBarCategories,
  } = props;
  const NotificationPanel = props.notificationPanel ?? null;
  const notificationsEnabled =
    props.notificationsEnabled ?? Boolean(NotificationPanel);
  const controller = useAppBarController({ ...props, notificationsEnabled });
  const resolveAppLink: AppBarAppLinkResolver = (appId) =>
    buildAppLink(
      appId,
      currentUser,
      props.currentWorkspaceAppIds?.includes(appId) ? shellWorkspaceSlug : null,
      launcherGlobalPaths,
    );
  const {
    activeAppTitle,
    canOpenWorkspaceSearch,
    draftItems,
    fixedItems,
    handleCountChange,
    handleNavigateToIssue,
    moreMenuRef,
    onCloseEditor,
    onCloseLauncherMenus,
    onMovePinnedApp,
    onOpenEditor,
    onOpenWorkspaceSearch,
    onResetDraft,
    onSaveLayout,
    onToggleCategoryMenu,
    onToggleFavorites,
    onToggleNotifications,
    onTogglePinnedApp,
    pinnedEligibleAppIds,
    pinnedItems,
    state,
    t,
  } = controller;
  const desktopMenuOpen =
    state.favoritesOpen ||
    Boolean(state.categoryMenuId) ||
    state.appBarEditorOpen;
  const notificationPanelFocus = useNotificationPanelFocus(
    state.notifOpen,
    onToggleNotifications,
  );

  useEffect(() => {
    onDesktopMenuOpenChange?.(desktopMenuOpen);
  }, [desktopMenuOpen, onDesktopMenuOpenChange]);

  return (
    <>
      <AppBarMobileHeader
        activeAppTitle={activeAppTitle}
        canOpenMobileAppMenu={canOpenMobileAppMenu}
        canOpenWorkspaceSearch={canOpenWorkspaceSearch}
        currentUser={currentUser}
        labels={{
          accountTitle: t('auth:settings.mySettings'),
          mobileMenuTitle: t('shell:mobileAppMenu.title', {
            title: activeAppTitle,
          }),
          mobileNavigationOpen: t('shell:mobileNavigation.open'),
          notificationsTitle: t('shell:notifications.title'),
          primaryNavigation: t('shell:appBar.primaryNavigation'),
          searchOpen: t('shell:search.open'),
          searchTitle: t('shell:search.title'),
        }}
        onOpenAccount={onOpenAccount}
        onOpenMobileAppMenu={onOpenMobileAppMenu}
        onOpenMobileNavigation={onOpenMobileNavigation}
        onOpenWorkspaceSearch={onOpenWorkspaceSearch}
        onToggleNotifications={notificationPanelFocus.onToggle}
        notificationPanelOpen={state.notifOpen}
        notificationsEnabled={notificationsEnabled}
        unreadCount={state.unreadCount}
      />

      <AppBarDesktopRail
        activeAppId={activeAppId}
        appBarEditorOpen={state.appBarEditorOpen}
        appBarLayoutError={state.appBarLayoutError}
        appBarLayoutSaving={state.appBarLayoutSaving}
        appBarItems={props.appBarItems}
        canOpenWorkspaceSearch={canOpenWorkspaceSearch}
        currentUser={currentUser}
        currentPathname={props.currentPathname}
        draftItems={draftItems}
        draftPinnedAppIds={state.draftPinnedAppIds}
        fixedItems={fixedItems}
        categoryMenuId={state.categoryMenuId}
        favoritesOpen={state.favoritesOpen}
        moreMenuRef={moreMenuRef}
        onCloseEditor={onCloseEditor}
        onCloseLauncherMenus={onCloseLauncherMenus}
        onMouseEnter={onDesktopRailMouseEnter}
        onMouseLeave={onDesktopRailMouseLeave}
        onMovePinnedApp={onMovePinnedApp}
        onOpenAccount={onOpenAccount}
        onOpenEditor={onOpenEditor}
        onOpenHelp={onOpenHelp}
        onOpenWorkspaceSearch={onOpenWorkspaceSearch}
        onResetDraft={onResetDraft}
        onSaveLayout={onSaveLayout}
        onToggleCategoryMenu={onToggleCategoryMenu}
        onToggleFavorites={onToggleFavorites}
        onToggleNotifications={notificationPanelFocus.onToggle}
        notificationPanelOpen={state.notifOpen}
        onTogglePinnedApp={onTogglePinnedApp}
        notificationsEnabled={notificationsEnabled}
        pinnedEligibleAppIds={pinnedEligibleAppIds}
        pinnedItems={pinnedItems}
        resolveAppLink={resolveAppLink}
        t={t}
        unreadCount={state.unreadCount}
        workspaceAppBarCategories={workspaceAppBarCategories}
      />

      <AnimatePresence>
        {notificationsEnabled && NotificationPanel && state.notifOpen ? (
          <NotificationPanel
            onClose={notificationPanelFocus.onClose}
            onCountChange={handleCountChange}
            onNavigateToIssue={handleNavigateToIssue}
            refreshKey={state.notificationRefreshSeq}
            workspaceSlug={shellWorkspaceSlug}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}
