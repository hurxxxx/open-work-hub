import {
  Building2,
  ExternalLink,
  Gift,
  HelpCircle,
  Link2,
  Search,
  Settings as SettingsIcon,
} from 'lucide-react';
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
import { AppBarWorkspaceSwitcher } from './AppBarWorkspaceSwitcher';
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
  businessSitesMenuRef,
  businessSitesOpen,
  canCreateWorkspace,
  canManageCurrentWorkspace,
  canOpenWorkspaceSearch,
  currentUser,
  currentPathname,
  currentWorkspace,
  currentWorkspaceName,
  defaultWorkspaceOptions,
  defaultWorkspaceSaving,
  draftItems,
  draftPinnedAppIds,
  fixedItems,
  categoryMenuId,
  favoritesOpen,
  moreMenuRef,
  normalizedDefaultWorkspaceId,
  onCloseBusinessSites,
  onCloseEditor,
  onCloseLauncherMenus,
  onCreateWorkspace,
  onDefaultWorkspaceChange,
  onManageCurrentWorkspace,
  onMovePinnedApp,
  onMouseEnter,
  onMouseLeave,
  onOpenAccount,
  onOpenEditor,
  onOpenHelp,
  onOpenWorkspaceSearch,
  onResetDraft,
  onSaveLayout,
  onSearchQueryChange,
  onSelectWorkspace,
  onToggleBusinessSites,
  onToggleCategoryMenu,
  onToggleFavorites,
  onToggleNotifications,
  onTogglePinnedApp,
  notificationsEnabled,
  onToggleWorkspaceSwitcher,
  otherWorkspaces,
  pinnedEligibleAppIds,
  pinnedItems,
  pinnedWorkspace,
  resolveAppLink,
  t,
  unreadCount,
  workspacePreferenceError,
  workspaceQuery,
  workspaceAppBarCategories,
  workspaceSwitcherRef,
  workspaceSwitcherOpen,
}: {
  activeAppId: string;
  appBarEditorOpen: boolean;
  appBarLayoutError: string | null;
  appBarLayoutSaving: boolean;
  appBarItems?: readonly AppBarItem[];
  businessSitesMenuRef: RefObject<HTMLDivElement | null>;
  businessSitesOpen: boolean;
  canCreateWorkspace: boolean;
  canManageCurrentWorkspace: boolean;
  canOpenWorkspaceSearch: boolean;
  currentUser: AuthUser;
  currentPathname: string;
  currentWorkspace: AuthUser['workspaces'][number] | null;
  currentWorkspaceName: string;
  defaultWorkspaceOptions: AuthUser['workspaces'];
  defaultWorkspaceSaving: boolean;
  draftItems: AppBarWorkspaceItem[];
  draftPinnedAppIds: WorkspaceAppId[];
  fixedItems: AppBarWorkspaceItem[];
  categoryMenuId: string | null;
  favoritesOpen: boolean;
  moreMenuRef: RefObject<HTMLDivElement | null>;
  normalizedDefaultWorkspaceId: string | null;
  onCloseBusinessSites: () => void;
  onCloseEditor: () => void;
  onCloseLauncherMenus: () => void;
  onCreateWorkspace: () => void;
  onDefaultWorkspaceChange: (workspaceId: string | null) => void;
  onManageCurrentWorkspace: () => void;
  onMovePinnedApp: (appId: WorkspaceAppId, direction: -1 | 1) => void;
  onMouseEnter?: MouseEventHandler<HTMLDivElement>;
  onMouseLeave?: MouseEventHandler<HTMLDivElement>;
  onOpenAccount: () => void;
  onOpenEditor: () => void;
  onOpenHelp: () => void;
  onOpenWorkspaceSearch: () => void;
  onResetDraft: () => void;
  onSaveLayout: () => void;
  onSearchQueryChange: (query: string) => void;
  onSelectWorkspace: (workspaceSlug: string) => void;
  onToggleBusinessSites: () => void;
  onToggleCategoryMenu: (categoryId: string) => void;
  onToggleFavorites: () => void;
  onToggleNotifications: () => void;
  onTogglePinnedApp: (appId: WorkspaceAppId, checked: boolean) => void;
  notificationsEnabled: boolean;
  onToggleWorkspaceSwitcher: () => void;
  otherWorkspaces: AuthUser['workspaces'];
  pinnedEligibleAppIds: ReadonlySet<WorkspaceAppId>;
  pinnedItems: AppBarWorkspaceItem[];
  pinnedWorkspace: AuthUser['workspaces'][number] | null;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
  unreadCount: number;
  workspacePreferenceError: string | null;
  workspaceQuery: string;
  workspaceAppBarCategories: WorkspaceBootstrapAppBarCategory[];
  workspaceSwitcherRef: RefObject<HTMLDivElement | null>;
  workspaceSwitcherOpen: boolean;
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
    <div
      className="z-50 hidden h-full w-16 flex-col items-center gap-2 border-r border-app-border bg-app-bg-strong py-3 lg:flex"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <AppBarWorkspaceSwitcher
        canCreateWorkspace={canCreateWorkspace}
        canManageCurrentWorkspace={canManageCurrentWorkspace}
        currentWorkspace={currentWorkspace}
        defaultWorkspaceOptions={defaultWorkspaceOptions}
        defaultWorkspaceSaving={defaultWorkspaceSaving}
        normalizedDefaultWorkspaceId={normalizedDefaultWorkspaceId}
        onCreateWorkspace={onCreateWorkspace}
        onDefaultWorkspaceChange={onDefaultWorkspaceChange}
        onManageCurrentWorkspace={onManageCurrentWorkspace}
        onQueryChange={onSearchQueryChange}
        onSelectWorkspace={onSelectWorkspace}
        onToggle={onToggleWorkspaceSwitcher}
        otherWorkspaces={otherWorkspaces}
        pinnedWorkspace={pinnedWorkspace}
        preferenceError={workspacePreferenceError}
        query={workspaceQuery}
        rootRef={workspaceSwitcherRef}
        t={t}
        workspaceSwitcherOpen={workspaceSwitcherOpen}
      />

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
        currentWorkspaceName={currentWorkspaceName}
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
        businessSitesMenuRef={businessSitesMenuRef}
        businessSitesOpen={businessSitesOpen}
        currentUser={currentUser}
        onCloseBusinessSites={onCloseBusinessSites}
        onOpenAccount={onOpenAccount}
        onOpenHelp={onOpenHelp}
        onToggleBusinessSites={onToggleBusinessSites}
        onToggleNotifications={onToggleNotifications}
        notificationsEnabled={notificationsEnabled}
        t={t}
        unreadCount={unreadCount}
      />
    </div>
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
  businessSitesMenuRef,
  businessSitesOpen,
  currentUser,
  onCloseBusinessSites,
  onOpenAccount,
  onOpenHelp,
  onToggleBusinessSites,
  onToggleNotifications,
  notificationsEnabled,
  t,
  unreadCount,
}: {
  businessSitesMenuRef: RefObject<HTMLDivElement | null>;
  businessSitesOpen: boolean;
  currentUser: AuthUser;
  onCloseBusinessSites: () => void;
  onOpenAccount: () => void;
  onOpenHelp: () => void;
  onToggleBusinessSites: () => void;
  onToggleNotifications: () => void;
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

      <DesktopRailBusinessSitesMenu
        menuRef={businessSitesMenuRef}
        onClose={onCloseBusinessSites}
        onToggle={onToggleBusinessSites}
        open={businessSitesOpen}
        t={t}
      />

      {notificationsEnabled ? (
        <AppBarNotificationButton
          className={appBarRailControlClassName(false, undefined, 'fixed')}
          iconSize={22}
          label={t('shell:notifications.title')}
          onClick={onToggleNotifications}
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

function DesktopRailBusinessSitesMenu({
  menuRef,
  onClose,
  onToggle,
  open,
  t,
}: {
  menuRef: RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onToggle: () => void;
  open: boolean;
  t: AppBarTranslator;
}) {
  const label = t('shell:businessSites.open');

  return (
    <div ref={menuRef} className="relative">
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={label}
        className={appBarRailControlClassName(open, undefined, 'fixed')}
        onClick={onToggle}
        title={label}
        type="button"
      >
        <Link2 aria-hidden size={22} strokeWidth={2.25} />
        <AppBarRailTooltip title={label} />
        {open ? <AppBarRailActiveIndicator /> : null}
      </button>

      {open ? (
        <div
          className="absolute bottom-0 left-full z-50 ml-3 w-72 overflow-hidden rounded-xl border border-app-border bg-app-surface shadow-2xl"
          role="menu"
        >
          <div className="border-b border-app-border px-3 py-3">
            <div className="app-text-body-sm font-semibold text-app-ink">
              {t('shell:businessSites.title')}
            </div>
            <div className="app-text-caption mt-0.5 text-app-ink/55">
              {t('shell:businessSites.description')}
            </div>
          </div>

          <a
            className="flex w-full items-center gap-3 px-3 py-3 text-left text-app-ink transition-colors hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-inset focus:ring-app-accent/35"
            href="http://gw.dwdcc.co.kr/index.aspx"
            onClick={onClose}
            rel="noreferrer"
            role="menuitem"
            target="_blank"
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-app-bg text-app-accent">
              <Building2 aria-hidden size={18} strokeWidth={2.1} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="app-text-body-sm block font-medium">
                {t('shell:businessSites.groupwareTitle')}
              </span>
              <span className="app-text-caption block truncate text-app-ink/55">
                {t('shell:businessSites.groupwareDescription')}
              </span>
            </span>
            <ExternalLink
              aria-hidden
              className="shrink-0 text-app-ink/55"
              size={15}
              strokeWidth={2.1}
            />
          </a>

          <a
            className="flex w-full items-center gap-3 border-t border-app-border px-3 py-3 text-left text-app-ink transition-colors hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-inset focus:ring-app-accent/35"
            href="https://dwdcc.ezwel.com/pc/mypage/auth/login/pc/product/main/welfare-mall"
            onClick={onClose}
            rel="noreferrer"
            role="menuitem"
            target="_blank"
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-app-bg text-app-accent">
              <Gift aria-hidden size={18} strokeWidth={2.1} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="app-text-body-sm block font-medium">
                {t('shell:businessSites.welfareMallTitle')}
              </span>
              <span className="app-text-caption block truncate text-app-ink/55">
                {t('shell:businessSites.welfareMallDescription')}
              </span>
            </span>
            <ExternalLink
              aria-hidden
              className="shrink-0 text-app-ink/55"
              size={15}
              strokeWidth={2.1}
            />
          </a>
        </div>
      ) : null}
    </div>
  );
}
