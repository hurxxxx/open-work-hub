import { useEffect } from 'react';
import { AnimatePresence } from 'motion/react';

import { AppBarDesktopRail } from './AppBarDesktopRail';
import { AppBarMobileHeader } from './AppBarMobileHeader';
import { type AppBarAppLinkResolver, type AppBarProps } from './app-bar-model';
import { useAppBarController } from './useAppBarController';
import { useNotificationPanelFocus } from './useNotificationPanelFocus';
import {
  translateAppLaunchContext,
  translateAppLaunchLabel,
} from '@/src/app/shell/app-launch-destination';

export function AppBar(props: AppBarProps) {
  const {
    activeAppId,
    activeContextLabel,
    canOpenMobileAppMenu,
    currentWorkspaceName,
    currentUser,
    onDesktopMenuOpenChange,
    onDesktopRailMouseEnter,
    onDesktopRailMouseLeave,
    onOpenAccount,
    onOpenHelp,
    onOpenMobileAppMenu,
    onOpenMobileNavigation,
    resolveAppDestination,
    shellWorkspaceSlug,
    workspaceAppBarCategories,
  } = props;
  const NotificationPanel = props.notificationPanel ?? null;
  const notificationsEnabled =
    props.notificationsEnabled ?? Boolean(NotificationPanel);
  const controller = useAppBarController({ ...props, notificationsEnabled });
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
  const resolveAppLink: AppBarAppLinkResolver = (appId) =>
    resolveAppDestination(appId).href;
  const resolveAppContextLabel = (appId: string) =>
    translateAppLaunchContext(resolveAppDestination(appId), t);
  const resolveAppLabel = (appId: string, title: string) =>
    translateAppLaunchLabel(title, resolveAppDestination(appId), t);
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
        activeContextLabel={activeContextLabel}
        activeAppTitle={activeAppTitle}
        canOpenMobileAppMenu={canOpenMobileAppMenu}
        canOpenWorkspaceSearch={canOpenWorkspaceSearch}
        currentUser={currentUser}
        labels={{
          accountTitle: t('auth:settings.mySettings'),
          mobileMenuTitle: activeContextLabel
            ? t('shell:mobileAppMenu.titleWithContext', {
                context: activeContextLabel,
                title: activeAppTitle,
              })
            : t('shell:mobileAppMenu.title', {
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
        currentWorkspaceName={currentWorkspaceName}
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
        resolveAppContextLabel={resolveAppContextLabel}
        resolveAppLabel={resolveAppLabel}
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
