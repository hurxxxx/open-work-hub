import { AnimatePresence } from 'motion/react';
import { useEffect } from 'react';

import {
  translateAppLaunchContext,
  translateAppLaunchLabel,
} from '@/src/app/shell/app-launch-destination';
import { AppBarDesktopRail } from './AppBarDesktopRail';
import { AppBarMobileHeader } from './AppBarMobileHeader';
import { type AppBarAppLinkResolver, type AppBarProps } from './app-bar-model';
import { useAppBarController } from './useAppBarController';
import { useNotificationPanelFocus } from './useNotificationPanelFocus';

export function AppBar(props: AppBarProps) {
  const {
    activeAppId,
    canOpenMobileAppMenu,
    currentCompanyLabel,
    currentUser,
    onDesktopMenuOpenChange,
    onDesktopRailMouseEnter,
    onDesktopRailMouseLeave,
    onOpenAccount,
    onOpenHelp,
    onOpenMobileAppMenu,
    onOpenMobileNavigation,
    resolveAppDestination,
    appBarCategories,
  } = props;
  const NotificationPanel = props.notificationPanel ?? null;
  const notificationsEnabled =
    props.notificationsEnabled ?? Boolean(NotificationPanel);
  const controller = useAppBarController({ ...props, notificationsEnabled });
  const {
    activeAppTitle,
    canOpenSearch,
    draftItems,
    fixedItems,
    handleCountChange,
    handleNavigateToIssue,
    moreMenuRef,
    onCloseEditor,
    onCloseLauncherMenus,
    onMovePinnedApp,
    onOpenEditor,
    onOpenSearch,
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
        activeAppTitle={activeAppTitle}
        canOpenMobileAppMenu={canOpenMobileAppMenu}
        canOpenSearch={canOpenSearch}
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
        onOpenSearch={onOpenSearch}
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
        canOpenSearch={canOpenSearch}
        currentUser={currentUser}
        currentPathname={props.currentPathname}
        currentCompanyLabel={currentCompanyLabel}
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
        onOpenSearch={onOpenSearch}
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
        appBarCategories={appBarCategories}
      />

      <AnimatePresence>
        {notificationsEnabled && NotificationPanel && state.notifOpen ? (
          <NotificationPanel
            onClose={notificationPanelFocus.onClose}
            onCountChange={handleCountChange}
            onNavigateToIssue={handleNavigateToIssue}
            refreshKey={state.notificationRefreshSeq}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}
