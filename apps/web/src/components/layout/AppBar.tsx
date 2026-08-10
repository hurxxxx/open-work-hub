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
    buildAppLink(appId, currentUser, shellWorkspaceSlug, launcherGlobalPaths);
  const {
    activeAppTitle,
    businessSitesMenuRef,
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
    onCloseEditor,
    onCloseBusinessSites,
    onCloseLauncherMenus,
    onCreateWorkspace,
    onManageCurrentWorkspace,
    onMovePinnedApp,
    onOpenEditor,
    onOpenWorkspaceSearch,
    onResetDraft,
    onSaveLayout,
    onSearchQueryChange,
    onToggleBusinessSites,
    onToggleCategoryMenu,
    onToggleFavorites,
    onToggleNotifications,
    onTogglePinnedApp,
    onToggleWorkspaceSwitcher,
    otherWorkspaces,
    pinnedEligibleAppIds,
    pinnedItems,
    pinnedWorkspace,
    state,
    t,
    workspaceSwitcherRef,
  } = controller;
  const desktopMenuOpen =
    state.favoritesOpen ||
    Boolean(state.categoryMenuId) ||
    state.appBarEditorOpen ||
    state.businessSitesOpen;

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
        currentWorkspaceName={currentWorkspaceName}
        labels={{
          accountTitle: t('auth:settings.mySettings'),
          mobileMenuTitle: t('shell:mobileAppMenu.title', {
            title: activeAppTitle,
          }),
          mobileNavigationOpen: t('shell:mobileNavigation.open'),
          notificationsTitle: t('shell:notifications.title'),
          searchOpen: t('shell:search.open'),
          searchTitle: t('shell:search.title'),
        }}
        onOpenAccount={onOpenAccount}
        onOpenMobileAppMenu={onOpenMobileAppMenu}
        onOpenMobileNavigation={onOpenMobileNavigation}
        onOpenWorkspaceSearch={onOpenWorkspaceSearch}
        onToggleNotifications={onToggleNotifications}
        notificationsEnabled={notificationsEnabled}
        unreadCount={state.unreadCount}
      />

      <AppBarDesktopRail
        activeAppId={activeAppId}
        appBarEditorOpen={state.appBarEditorOpen}
        appBarLayoutError={state.appBarLayoutError}
        appBarLayoutSaving={state.appBarLayoutSaving}
        appBarItems={props.appBarItems}
        businessSitesMenuRef={businessSitesMenuRef}
        businessSitesOpen={state.businessSitesOpen}
        canCreateWorkspace={canCreateWorkspace}
        canManageCurrentWorkspace={canManageCurrentWorkspace}
        canOpenWorkspaceSearch={canOpenWorkspaceSearch}
        currentUser={currentUser}
        currentPathname={props.currentPathname}
        currentWorkspace={currentWorkspace}
        currentWorkspaceName={currentWorkspaceName}
        defaultWorkspaceOptions={defaultWorkspaceOptions}
        defaultWorkspaceSaving={state.defaultWorkspaceSaving}
        draftItems={draftItems}
        draftPinnedAppIds={state.draftPinnedAppIds}
        fixedItems={fixedItems}
        categoryMenuId={state.categoryMenuId}
        favoritesOpen={state.favoritesOpen}
        moreMenuRef={moreMenuRef}
        normalizedDefaultWorkspaceId={normalizedDefaultWorkspaceId}
        onCloseBusinessSites={onCloseBusinessSites}
        onCloseEditor={onCloseEditor}
        onCloseLauncherMenus={onCloseLauncherMenus}
        onCreateWorkspace={onCreateWorkspace}
        onMouseEnter={onDesktopRailMouseEnter}
        onMouseLeave={onDesktopRailMouseLeave}
        onDefaultWorkspaceChange={(workspaceId) => {
          void handleSetDefaultWorkspace(workspaceId);
        }}
        onManageCurrentWorkspace={onManageCurrentWorkspace}
        onMovePinnedApp={onMovePinnedApp}
        onOpenAccount={onOpenAccount}
        onOpenEditor={onOpenEditor}
        onOpenHelp={onOpenHelp}
        onOpenWorkspaceSearch={onOpenWorkspaceSearch}
        onResetDraft={onResetDraft}
        onSaveLayout={onSaveLayout}
        onSearchQueryChange={onSearchQueryChange}
        onToggleBusinessSites={onToggleBusinessSites}
        onToggleCategoryMenu={onToggleCategoryMenu}
        onToggleFavorites={onToggleFavorites}
        onSelectWorkspace={handleWorkspaceSelect}
        onToggleNotifications={onToggleNotifications}
        onTogglePinnedApp={onTogglePinnedApp}
        notificationsEnabled={notificationsEnabled}
        onToggleWorkspaceSwitcher={onToggleWorkspaceSwitcher}
        otherWorkspaces={otherWorkspaces}
        pinnedEligibleAppIds={pinnedEligibleAppIds}
        pinnedItems={pinnedItems}
        pinnedWorkspace={pinnedWorkspace}
        resolveAppLink={resolveAppLink}
        t={t}
        unreadCount={state.unreadCount}
        workspaceAppBarCategories={workspaceAppBarCategories}
        workspacePreferenceError={state.workspacePreferenceError}
        workspaceQuery={state.workspaceQuery}
        workspaceSwitcherOpen={state.workspaceSwitcherOpen}
        workspaceSwitcherRef={workspaceSwitcherRef}
      />

      <AnimatePresence>
        {notificationsEnabled && NotificationPanel && state.notifOpen ? (
          <NotificationPanel
            onClose={onToggleNotifications}
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
