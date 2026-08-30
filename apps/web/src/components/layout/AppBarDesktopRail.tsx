import { HelpCircle, Search, Settings as SettingsIcon } from 'lucide-react';
import { useMemo, type MouseEventHandler, type RefObject } from 'react';

import {
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
} from '@/src/platform/admin/admin-permissions';
import {
  hasAdminConsoleAccess,
  type AuthUser,
} from '@/src/platform/auth/auth-api';
import type { WorkspaceBootstrapAppBarCategory } from '@/src/platform/workspaces/workspaces-api';
import {
  appBarRailControlClassName,
  AppBarIconLink,
  AppBarRailActiveIndicator,
  AppBarRailTooltip,
} from './AppBarIconLink';
import { AppBarLauncherMenus } from './AppBarLauncherMenus';
import { AppBarNotificationButton } from './AppBarNotificationButton';
import {
  createAppBarItemById,
  getInitials,
  type AppBarAppLinkResolver,
  type AppBarTranslator,
  type AppBarWorkspaceItem,
} from './app-bar-model';
import type { AppBarItem } from '@/src/app/shell/navigation-types';
import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';

export function AppBarDesktopRail({
  activeAppId,
  appBarEditorOpen,
  appBarLayoutError,
  appBarLayoutSaving,
  appBarItems = [],
  canOpenWorkspaceSearch,
  currentUser,
  currentPathname,
  draftItems,
  draftPinnedAppIds,
  fixedItems,
  categoryMenuId,
  favoritesOpen,
  moreMenuRef,
  onCloseEditor,
  onCloseLauncherMenus,
  onMovePinnedApp,
  onMouseEnter,
  onMouseLeave,
  onOpenAccount,
  onOpenEditor,
  onOpenHelp,
  onOpenWorkspaceSearch,
  onResetDraft,
  onSaveLayout,
  onToggleCategoryMenu,
  onToggleFavorites,
  onToggleNotifications,
  notificationPanelOpen,
  onTogglePinnedApp,
  notificationsEnabled,
  pinnedEligibleAppIds,
  pinnedItems,
  resolveAppLink,
  t,
  unreadCount,
  workspaceAppBarCategories,
}: {
  activeAppId: string;
  appBarEditorOpen: boolean;
  appBarLayoutError: string | null;
  appBarLayoutSaving: boolean;
  appBarItems?: readonly AppBarItem[];
  canOpenWorkspaceSearch: boolean;
  currentUser: AuthUser;
  currentPathname: string;
  draftItems: AppBarWorkspaceItem[];
  draftPinnedAppIds: WorkspaceAppId[];
  fixedItems: AppBarWorkspaceItem[];
  categoryMenuId: string | null;
  favoritesOpen: boolean;
  moreMenuRef: RefObject<HTMLDivElement | null>;
  onCloseEditor: () => void;
  onCloseLauncherMenus: () => void;
  onMovePinnedApp: (appId: WorkspaceAppId, direction: -1 | 1) => void;
  onMouseEnter?: MouseEventHandler<HTMLElement>;
  onMouseLeave?: MouseEventHandler<HTMLElement>;
  onOpenAccount: () => void;
  onOpenEditor: () => void;
  onOpenHelp: () => void;
  onOpenWorkspaceSearch: () => void;
  onResetDraft: () => void;
  onSaveLayout: () => void;
  onToggleCategoryMenu: (categoryId: string) => void;
  onToggleFavorites: () => void;
  onToggleNotifications: MouseEventHandler<HTMLButtonElement>;
  notificationPanelOpen: boolean;
  onTogglePinnedApp: (appId: WorkspaceAppId, checked: boolean) => void;
  notificationsEnabled: boolean;
  pinnedEligibleAppIds: ReadonlySet<WorkspaceAppId>;
  pinnedItems: AppBarWorkspaceItem[];
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
  unreadCount: number;
  workspaceAppBarCategories: WorkspaceBootstrapAppBarCategory[];
}) {
  const appBarItemById = useMemo(
    () => createAppBarItemById(appBarItems),
    [appBarItems],
  );
  const canShowSettings =
    hasAdminConsoleAccess(currentUser) ||
    hasAnyAdminReadPermission(currentUser.system_roles);
  const settingsItem = appBarItemById.get('settings');
  const pinnedItemActive = pinnedItems.some((item) =>
    isAppBarItemPathActive(currentPathname, resolveAppLink(item.id)),
  );

  return (
    <nav
      aria-label={t('shell:appBar.primaryNavigation')}
      className="z-50 hidden h-full w-16 flex-col items-center gap-2 border-r border-app-border bg-app-bg-strong py-3 lg:flex"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {canOpenWorkspaceSearch ? (
        <DesktopRailSearchButton
          active={activeAppId === 'search'}
          onOpenWorkspaceSearch={onOpenWorkspaceSearch}
          t={t}
        />
      ) : null}

      {fixedItems.map((item) => (
        <AppBarIconLink
          active={isAppBarItemPathActive(
            currentPathname,
            resolveAppLink(item.id),
          )}
          icon={item.icon}
          key={item.id}
          tone="fixed"
          title={item.title}
          to={resolveAppLink(item.id)}
        />
      ))}

      <AppBarLauncherMenus
        appBarEditorOpen={appBarEditorOpen}
        appBarLayoutError={appBarLayoutError}
        appBarLayoutSaving={appBarLayoutSaving}
        categoryMenuId={categoryMenuId}
        currentPathname={currentPathname}
        currentWorkspaceName={t('shell:launcher.title')}
        draftItems={draftItems}
        draftPinnedAppIds={draftPinnedAppIds}
        favoritesActive={pinnedItemActive}
        favoritesOpen={favoritesOpen}
        launcherCategories={workspaceAppBarCategories}
        menuRef={moreMenuRef}
        onCloseEditor={onCloseEditor}
        onCloseLauncherMenus={onCloseLauncherMenus}
        onMovePinnedApp={onMovePinnedApp}
        onOpenEditor={onOpenEditor}
        onResetDraft={onResetDraft}
        onSaveLayout={onSaveLayout}
        onToggleCategoryMenu={onToggleCategoryMenu}
        onToggleFavorites={onToggleFavorites}
        onTogglePinnedApp={onTogglePinnedApp}
        pinnedEligibleAppIds={pinnedEligibleAppIds}
        pinnedItems={pinnedItems}
        resolveAppLink={resolveAppLink}
        t={t}
      />

      {canShowSettings ? (
        <DesktopRailSettingsLink
          active={activeAppId === 'settings'}
          currentUser={currentUser}
          settingsIcon={settingsItem?.icon ?? SettingsIcon}
          t={t}
        />
      ) : null}

      <DesktopRailAccountControls
        currentUser={currentUser}
        onOpenAccount={onOpenAccount}
        onOpenHelp={onOpenHelp}
        onToggleNotifications={onToggleNotifications}
        notificationPanelOpen={notificationPanelOpen}
        notificationsEnabled={notificationsEnabled}
        t={t}
        unreadCount={unreadCount}
      />
    </nav>
  );
}

function isAppBarItemPathActive(
  currentPathname: string,
  link: string,
): boolean {
  const pathname = link.split(/[?#]/)[0] || '/';
  return (
    currentPathname === pathname || currentPathname.startsWith(`${pathname}/`)
  );
}

function DesktopRailSearchButton({
  active,
  onOpenWorkspaceSearch,
  t,
}: {
  active: boolean;
  onOpenWorkspaceSearch: () => void;
  t: AppBarTranslator;
}) {
  const label = t('shell:search.title');
  return (
    <button
      aria-label={label}
      className={appBarRailControlClassName(active, undefined, 'fixed')}
      onClick={onOpenWorkspaceSearch}
      title={label}
      type="button"
    >
      <Search aria-hidden size={22} strokeWidth={2.25} />
      <AppBarRailTooltip title={label} />
      {active ? <AppBarRailActiveIndicator /> : null}
    </button>
  );
}

function DesktopRailSettingsLink({
  active,
  currentUser,
  settingsIcon,
  t,
}: {
  active: boolean;
  currentUser: AuthUser;
  settingsIcon: typeof SettingsIcon;
  t: AppBarTranslator;
}) {
  return (
    <AppBarIconLink
      active={active}
      icon={settingsIcon}
      tone="fixed"
      title={t('shell:apps.settings')}
      to={getDefaultAdminPath(currentUser.system_roles)}
    />
  );
}

function DesktopRailAccountControls({
  currentUser,
  onOpenAccount,
  onOpenHelp,
  onToggleNotifications,
  notificationPanelOpen,
  notificationsEnabled,
  t,
  unreadCount,
}: {
  currentUser: AuthUser;
  onOpenAccount: () => void;
  onOpenHelp: () => void;
  onToggleNotifications: MouseEventHandler<HTMLButtonElement>;
  notificationPanelOpen: boolean;
  notificationsEnabled: boolean;
  t: AppBarTranslator;
  unreadCount: number;
}) {
  const displayName = currentUser.display_name || currentUser.full_name;
  const accountLabel = t('auth:settings.mySettings');
  const helpLabel = t('shell:helpCenter.open');

  return (
    <div className="relative flex shrink-0 flex-col items-center gap-2">
      <div aria-hidden className="h-px w-8 shrink-0 bg-white/20" />

      {notificationsEnabled ? (
        <AppBarNotificationButton
          className={appBarRailControlClassName(false, undefined, 'fixed')}
          iconSize={22}
          label={t('shell:notifications.title')}
          onClick={onToggleNotifications}
          open={notificationPanelOpen}
          unreadCount={unreadCount}
        />
      ) : null}

      <button
        aria-label={helpLabel}
        className={appBarRailControlClassName(false, undefined, 'fixed')}
        onClick={onOpenHelp}
        title={helpLabel}
        type="button"
      >
        <HelpCircle aria-hidden size={22} strokeWidth={2.25} />
        <AppBarRailTooltip title={helpLabel} />
      </button>

      <button
        aria-label={accountLabel}
        className="app-text-body-sm flex size-10 cursor-pointer items-center justify-center rounded-full bg-app-accent font-bold text-app-accent-fg shadow-sm outline-none ring-2 ring-transparent transition-all hover:ring-app-accent/40"
        onClick={onOpenAccount}
        title={`${displayName} · ${accountLabel}`}
        type="button"
      >
        {getInitials(displayName, 'ID')}
      </button>
    </div>
  );
}
