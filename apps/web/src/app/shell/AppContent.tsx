import {
  type ComponentType,
  type ElementType,
  type ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, LayoutGrid, X } from 'lucide-react';
import { DetailDrawer } from '@open-work-hub/ui';
import {
  AnimatePresence,
  LazyMotion,
  domAnimation,
  m,
  useReducedMotion,
} from 'motion/react';

import { AppBar } from '@/src/components/layout/AppBar';
import {
  restoreSubSidebarPinned,
  resolveSubSidebarPreviewOpenAfterPinnedChange,
  serializeSubSidebarPinned,
  SUB_SIDEBAR_PINNED_STORAGE_KEY,
} from '@/src/components/layout/sub-sidebar-frame-model';
import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from '@/src/platform/auth/auth-provider';
import {
  hasAdminConsoleAccess,
  type AuthUser,
} from '@/src/platform/auth/auth-api';
import {
  ReleaseNoteBody,
  formatReleaseNoteDate,
} from '@/src/platform/auth/ReleaseNotesSettingsSection';
import type { SettingsSection } from '@/src/platform/auth/settings-page-model';
import {
  dismissReleaseNote,
  getCurrentReleaseNote,
  type ReleaseNoteItem,
} from '@/src/platform/release-notes/release-notes-api';
import {
  getDefaultAdminPath as getPlatformDefaultAdminPath,
  hasAnyAdminReadPermission as hasAnyPlatformAdminReadPermission,
  hasConfiguredAdminSectionAccess,
  type AdminSectionAccessResolver,
  type DefaultAdminPathResolver,
} from '@/src/platform/admin/admin-permissions';
import { NotFoundView, ProfilePage } from '@/src/platform/auth/settings-pages';
import {
  getWorkspaceAppIdFromPath,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';
import {
  useAppsBootstrap,
  useWorkspaceBootstrap,
  type WorkspaceBootstrapApp,
  type WorkspaceBootstrapAppBarCategory,
  type WorkspaceBootstrapNavItem,
  type WorkspaceBootstrapResponse,
} from '@/src/platform/workspaces/workspaces-api';
import {
  WorkspaceBootstrapProvider,
  type WorkspaceBootstrapContextValue,
} from '@/src/platform/workspaces/workspace-bootstrap-context';
import { projectMobileNavigationItems } from './mobile-navigation-model';
import { projectShellAppsBootstrap } from './apps-bootstrap-model';
import { BackgroundWorkProvider } from '@/src/platform/background-work/background-work-provider';
import {
  filterBackgroundWorkSourcesForWorkspace,
  type BackgroundWorkSource,
} from '@/src/platform/background-work/background-work-session';
import { syncLocale } from '@/src/platform/i18n';
import { syncDateFormatPreference } from '@/src/platform/time/time-utils';
import { recordUsageEvent } from '@/src/platform/usage/usage-api';
import {
  normalizeUsageRoutePath,
  resolveUsageEventAppId,
} from '@/src/platform/usage/usage-route';
import { trackMatomoPageView } from '@/src/platform/analytics/matomo';
import { cn } from '@/src/lib/utils';
import { AppEntryRoute } from './AppEntryRoute';
import { AppLauncherView } from './AppLauncherView';
import { AccessRefreshBoundary } from './AccessRefreshBoundary';
import { createAccessProjectionKey } from './access-projection-key';
import { resolveAppRouteContext } from './app-route-context';
import { WorkspaceContextSelector } from '@/src/platform/workspaces/WorkspaceContextSelector';
import {
  WorkspaceRouteElements,
  type ShellWorkspaceRouteDefinition,
} from './workspace-route-registry';
import {
  StaticRouteElements,
  type ShellAdminSectionRouteDefinition,
  type ShellStaticRouteDefinition,
} from './static-route-elements';
import { AppSubSidebar } from './AppSubSidebar';
import { HelpCenterModal } from './HelpCenterPage';
import { resolveShellDocumentTitle } from './document-title-model';
import {
  applyMobileAppMenuOpenChange,
  applyMobileNavOpenChange,
  createClosedMobileShellMenuState,
  createMobileShellRouteKey,
  resolveActiveMobileShellMenuState,
} from './mobile-shell-menu-model';
import {
  resolveShellChromeState,
  type ShellStateResolver,
} from './shell-chrome-model';
import {
  getSystemDarkModeSnapshot,
  resolveAppDisplayScope,
  resolveThemePreference,
  subscribeSystemDarkMode,
} from './shell-ui-model';
import { resolveShellDisplayAppId } from './shell-display-app-model';
import { LazyRouteErrorBoundary } from './lazy-route';
import {
  EMPTY_LAUNCHER_GLOBAL_PATHS,
  type AppBarItem,
  type LauncherGlobalPaths,
  type NavItem,
} from './navigation-types';
import type { AppSidebarConfig } from './sidebar-types';
import {
  EMPTY_FEATURE_GUIDE_TOOL_IDS,
  type FeatureGuideToolIds,
} from './ai-feature-guides';
import type {
  AppBarNotificationPanelComponent,
  AppBarNotificationUnreadCountLoader,
} from '@/src/components/layout/app-bar-model';
import {
  resolveAppLaunchDestination,
  translateAppLaunchContext,
  translateAppLaunchLabel,
  type AppLaunchDestinationResolver,
} from './app-launch-destination';

export type ShellProviderComponent = ComponentType<{ children: ReactNode }>;
export type ShellRealtimeProviderComponent = ComponentType<{
  children: ReactNode;
  token: string | null;
}>;

const getNoopAppModuleManifest = () => null;
const getNoopAppSidebarConfig = () => null;

function NoopShellRealtimeProvider({
  children,
}: {
  children: ReactNode;
  token: string | null;
}) {
  return children;
}

function ExecutionScopeIndicator({ label }: { label: string }) {
  const { t } = useTranslation('shell');
  return (
    <div className="border-b border-app-border px-3 py-3">
      <div className="app-text-overline text-app-ink/55">
        {t('workspaceContext.executionScopeLabel')}
      </div>
      <div className="app-text-body-sm mt-1.5 rounded-lg border border-app-border bg-app-bg px-3 py-2 text-app-ink">
        {label}
      </div>
    </div>
  );
}

export interface WorkspaceAppScope {
  appIds: readonly WorkspaceAppId[];
}

export interface AppContentRuntimeConfig {
  adminLandingRoute?: ShellStaticRouteDefinition;
  adminRedirectRoutes?: readonly ShellStaticRouteDefinition[];
  adminSectionRoutes?: readonly ShellAdminSectionRouteDefinition[];
  appGlobalRoutes?: readonly ShellStaticRouteDefinition[];
  appBarFixedAppIds?: readonly string[];
  appBarItems?: readonly AppBarItem[];
  appBarPinnedByDefaultAppIds?: readonly string[];
  backgroundWorkSources?: readonly BackgroundWorkSource[];
  featureGuideToolIds?: FeatureGuideToolIds;
  getDefaultAdminPath?: DefaultAdminPathResolver;
  getAppModuleManifest?: (appId: string) => unknown | null;
  getAppSidebarConfig?: (appId: string) => AppSidebarConfig | null;
  hasAdminSectionAccess?: AdminSectionAccessResolver;
  hasAnyAdminReadPermission?: (systemRoles: readonly string[]) => boolean;
  helpRoutes?: readonly ShellStaticRouteDefinition[];
  launcherGlobalPaths?: LauncherGlobalPaths;
  navItems?: readonly NavItem[];
  notificationIssueAppId?: string | null;
  notificationPanel?: AppBarNotificationPanelComponent | null;
  notificationRealtimeEventTypes?: ReadonlySet<string>;
  notificationUnreadCountLoader?: AppBarNotificationUnreadCountLoader | null;
  personalWidgetHost?: ElementType | null;
  personalWidgetsEnabled?: boolean;
  realtimeEnabled?: boolean;
  realtimeProvider?: ShellRealtimeProviderComponent | null;
  resolveShellStateForPath?: ShellStateResolver;
  shellProviders?: readonly ShellProviderComponent[];
  workspaceSettingsRoute?: ShellStaticRouteDefinition | null;
  workspaceRoutes?: readonly ShellWorkspaceRouteDefinition[];
  workspaceAiToolAppIds?: readonly string[];
}

export interface AppContentProps extends AppContentRuntimeConfig {
  workspaceAppScope?: WorkspaceAppScope;
}

function isScopedNavItemVisible({
  appIds,
  item,
}: {
  appIds: ReadonlySet<string>;
  item: WorkspaceBootstrapNavItem;
}): boolean {
  return appIds.has(item.app_id);
}

function scopeWorkspaceBootstrapData(
  data: WorkspaceBootstrapResponse | null,
  scope: WorkspaceAppScope | undefined,
): WorkspaceBootstrapResponse | null {
  if (!data || !scope) {
    return data;
  }

  const appIds = new Set<string>(scope.appIds);
  const nav = data.nav.filter((item) =>
    isScopedNavItemVisible({ appIds, item }),
  );
  const apps = data.apps
    .filter((app) => appIds.has(app.app_id))
    .map((app) => ({
      ...app,
      nav_items: app.nav_items.filter((item) =>
        isScopedNavItemVisible({ appIds, item }),
      ),
    }));
  const app_bar_categories = (data.app_bar_categories ?? [])
    .map((category) => ({
      ...category,
      items: category.items.filter((item) => appIds.has(item.app_id)),
    }))
    .filter((category) => category.items.length > 0);

  return {
    ...data,
    app_bar_categories,
    apps,
    chatbot_app_ids: data.chatbot_app_ids?.filter((appId) => appIds.has(appId)),
    nav,
  };
}

function MobileNavigationDrawer({
  activeAppId,
  appBarFixedAppIds,
  appBarItems,
  currentPathname,
  currentUser,
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
  appBarCategories,
  onOpenChange,
  open,
  resolveAppDestination,
  workspaceApps,
}: {
  activeAppId: string;
  appBarFixedAppIds: readonly string[];
  appBarItems: readonly AppBarItem[];
  currentPathname: string;
  currentUser: AuthUser;
  getDefaultAdminPath: DefaultAdminPathResolver;
  hasAnyAdminReadPermission: (systemRoles: readonly string[]) => boolean;
  appBarCategories: readonly WorkspaceBootstrapAppBarCategory[];
  onOpenChange: (open: boolean) => void;
  open: boolean;
  resolveAppDestination: AppLaunchDestinationResolver;
  workspaceApps: WorkspaceBootstrapApp[];
}) {
  const { t } = useTranslation(['common', 'shell']);
  const close = () => onOpenChange(false);
  const appBarItemById = useMemo(
    () => new Map(appBarItems.map((item) => [item.id, item])),
    [appBarItems],
  );
  const visibleItems = projectMobileNavigationItems({
    appBarCategories,
    fixedAppIds: appBarFixedAppIds,
    appBarItems,
    workspaceApps,
  }).map((item) => ({
    ...item,
    destination: resolveAppDestination(item.linkAppId),
    title:
      item.type === 'app'
        ? t(`shell:apps.${item.id}`, { defaultValue: item.title })
        : item.title,
  }));
  const navigationActiveAppId =
    getWorkspaceAppIdFromPath(currentPathname) ?? activeAppId;
  const settingsItem = appBarItemById.get('settings');
  const canShowSettings =
    hasAdminConsoleAccess(currentUser) ||
    hasAnyAdminReadPermission(currentUser.system_roles);

  return (
    <DetailDrawer
      closeLabel={t('shell:mobileNavigation.close')}
      contentClassName="border-app-border bg-app-bg"
      description={t('shell:mobileNavigation.description')}
      onOpenChange={onOpenChange}
      open={open}
      side="left"
      title={t('shell:mobileNavigation.title')}
    >
      <div
        onClickCapture={(event) => {
          if (event.target instanceof Element && event.target.closest('a')) {
            close();
          }
        }}
      >
        <section className="border-b border-app-border px-3 py-4">
          <div className="app-text-overline px-2 text-app-ink/50">
            {t('common:labels.apps')}
          </div>
          <div className="mt-2 space-y-1">
            <Link
              className={cn(
                'flex items-center gap-3 rounded-xl px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover',
                currentPathname === '/' && 'bg-app-surface text-app-accent',
              )}
              to="/"
            >
              <LayoutGrid size={18} className="shrink-0" />
              <span className="app-text-body-sm min-w-0 flex-1 truncate">
                {t('shell:launcher.title')}
              </span>
              {currentPathname === '/' ? (
                <Check size={15} className="shrink-0" />
              ) : null}
            </Link>
            {visibleItems.map((item) => (
              <Link
                aria-label={translateAppLaunchLabel(
                  item.title,
                  item.destination,
                  t,
                )}
                key={item.id}
                to={item.destination.href}
                className={cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover',
                  item.activeAppIds.includes(
                    navigationActiveAppId as WorkspaceAppId,
                  ) && 'bg-app-surface text-app-accent',
                )}
              >
                <item.icon size={18} className="shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="app-text-body-sm block truncate">
                    {item.title}
                  </span>
                  <span className="app-text-micro block truncate text-app-ink/50">
                    {translateAppLaunchContext(item.destination, t)}
                  </span>
                </span>
                {item.activeAppIds.includes(
                  navigationActiveAppId as WorkspaceAppId,
                ) ? (
                  <Check size={15} className="shrink-0" />
                ) : null}
              </Link>
            ))}

            {canShowSettings && settingsItem ? (
              <Link
                to={getDefaultAdminPath(currentUser.system_roles)}
                className={cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover',
                  activeAppId === 'settings' &&
                    'bg-app-surface text-app-accent',
                )}
              >
                <settingsItem.icon size={18} className="shrink-0" />
                <span className="app-text-body-sm min-w-0 flex-1 truncate">
                  {t('shell:apps.settings')}
                </span>
                {activeAppId === 'settings' ? (
                  <Check size={15} className="shrink-0" />
                ) : null}
              </Link>
            ) : null}
          </div>
        </section>
      </div>
    </DetailDrawer>
  );
}

function MobileAppMenuDrawer({
  activeAppId,
  activeDisplayAppId,
  activeNavItemId,
  appBarItems,
  currentWorkspaceSlug,
  enabledWorkspaceAppIds,
  getAppModuleManifest,
  getAppSidebarConfig,
  hasAdminSectionAccess,
  headerSlot,
  launcherGlobalPaths,
  navItems,
  onOpenChange,
  open,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeDisplayAppId: string;
  activeNavItemId: string;
  appBarItems: readonly AppBarItem[];
  currentWorkspaceSlug: string | null;
  enabledWorkspaceAppIds: readonly string[];
  getAppModuleManifest: (appId: string) => unknown | null;
  getAppSidebarConfig: (appId: string) => AppSidebarConfig | null;
  hasAdminSectionAccess: AdminSectionAccessResolver;
  headerSlot?: ReactNode;
  launcherGlobalPaths: LauncherGlobalPaths;
  navItems: readonly NavItem[];
  onOpenChange: (open: boolean) => void;
  open: boolean;
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) {
  const close = () => onOpenChange(false);
  const { t } = useTranslation('shell');
  const activeAppTitle =
    activeDisplayAppId === 'settings'
      ? t('apps.settings')
      : (workspaceApps.find((item) => item.app_id === activeDisplayAppId)
          ?.title ??
        t(`apps.${activeDisplayAppId}`, {
          defaultValue:
            appBarItems.find((item) => item.id === activeDisplayAppId)?.title ??
            activeDisplayAppId,
        }) ??
        'Menu');

  return (
    <DetailDrawer
      closeLabel={t('mobileAppMenu.close', { title: activeAppTitle })}
      contentClassName="border-app-border bg-app-bg"
      description={t('mobileAppMenu.description')}
      onOpenChange={onOpenChange}
      open={open}
      side="left"
      title={t('mobileAppMenu.title', { title: activeAppTitle })}
    >
      <div className="h-[min(680px,78vh)] border-t border-app-border">
        <AppSubSidebar
          activeAppId={activeAppId}
          activeNavItemId={activeNavItemId}
          appBarItems={appBarItems}
          currentWorkspaceSlug={currentWorkspaceSlug}
          enabledWorkspaceAppIds={enabledWorkspaceAppIds}
          getAppModuleManifest={getAppModuleManifest}
          getAppSidebarConfig={getAppSidebarConfig}
          hasAdminSectionAccess={hasAdminSectionAccess}
          headerSlot={headerSlot}
          launcherGlobalPaths={launcherGlobalPaths}
          navItems={navItems}
          onNavigate={close}
          variant="mobile"
          workspaceApps={workspaceApps}
          workspaceNavItems={workspaceNavItems}
        />
      </div>
    </DetailDrawer>
  );
}

function ReleaseNoteAnnouncementModal({
  dismissing,
  error,
  item,
  locale,
  onClose,
  onDismiss,
  onOpenHistory,
}: {
  dismissing: boolean;
  error: string | null;
  item: ReleaseNoteItem;
  locale: string;
  onClose: () => void;
  onDismiss: () => void;
  onOpenHistory: () => void;
}) {
  const { t } = useTranslation(['common', 'shell']);
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label={t('common:actions.close')}
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <section className="relative z-10 flex max-h-[min(720px,92vh)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-app-border bg-app-bg shadow-2xl">
        <div className="shrink-0 border-b border-app-border px-6 py-5">
          <p className="app-text-caption font-medium text-app-accent">
            {t('shell:releaseNotes.eyebrow')}
          </p>
          <h2 className="app-text-title-lg mt-2 text-app-ink">{item.title}</h2>
          <p className="app-text-caption mt-1 text-app-ink/50">
            {formatReleaseNoteDate(item.published_at, locale)}
          </p>
          {item.summary ? (
            <p className="app-text-body mt-4 text-app-ink/70">{item.summary}</p>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 custom-scrollbar">
          <ReleaseNoteBody body={item.body} />
        </div>
        {error ? (
          <p className="app-text-caption shrink-0 border-t border-app-border px-6 py-3 text-app-danger">
            {error}
          </p>
        ) : null}
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-app-border px-6 py-4">
          <button
            type="button"
            className="app-text-control rounded-md px-3 py-2 text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            onClick={onClose}
          >
            {t('shell:releaseNotes.later')}
          </button>
          <button
            type="button"
            className="app-text-control rounded-md px-3 py-2 text-app-ink/70 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            onClick={onOpenHistory}
            disabled={dismissing}
          >
            {t('shell:releaseNotes.viewHistory')}
          </button>
          <button
            type="button"
            className="app-text-control rounded-md bg-app-accent px-3 py-2 font-medium text-app-accent-fg transition-opacity hover:opacity-90 disabled:opacity-60"
            onClick={onDismiss}
            disabled={dismissing}
          >
            {dismissing
              ? t('common:actions.saving')
              : t('shell:releaseNotes.doNotShowAgain')}
          </button>
        </div>
      </section>
    </div>
  );
}

function AuthenticatedShell({
  adminLandingRoute,
  adminRedirectRoutes,
  adminSectionRoutes,
  appGlobalRoutes,
  appBarFixedAppIds,
  appBarItems,
  appBarPinnedByDefaultAppIds,
  backgroundWorkSources,
  featureGuideToolIds,
  getDefaultAdminPath,
  getAppModuleManifest,
  getAppSidebarConfig,
  hasAdminSectionAccess,
  hasAnyAdminReadPermission,
  helpRoutes,
  launcherGlobalPaths,
  navItems,
  notificationIssueAppId,
  notificationPanel,
  notificationRealtimeEventTypes,
  notificationUnreadCountLoader,
  personalWidgetHost: PersonalWidgetHost,
  personalWidgetsEnabled,
  realtimeEnabled,
  realtimeProvider: ShellRealtimeProvider,
  resolveShellStateForPath,
  workspaceSettingsRoute,
  workspaceRoutes,
  workspaceAppScope,
  workspaceAiToolAppIds,
}: {
  adminLandingRoute: ShellStaticRouteDefinition | undefined;
  adminRedirectRoutes: readonly ShellStaticRouteDefinition[] | undefined;
  adminSectionRoutes: readonly ShellAdminSectionRouteDefinition[] | undefined;
  appGlobalRoutes: readonly ShellStaticRouteDefinition[] | undefined;
  appBarFixedAppIds: readonly string[];
  appBarItems: readonly AppBarItem[];
  appBarPinnedByDefaultAppIds: readonly string[];
  backgroundWorkSources: readonly BackgroundWorkSource[];
  featureGuideToolIds: FeatureGuideToolIds;
  getDefaultAdminPath: DefaultAdminPathResolver;
  getAppModuleManifest: (appId: string) => unknown | null;
  getAppSidebarConfig: (appId: string) => AppSidebarConfig | null;
  hasAdminSectionAccess: AdminSectionAccessResolver;
  hasAnyAdminReadPermission: (systemRoles: readonly string[]) => boolean;
  helpRoutes: readonly ShellStaticRouteDefinition[] | undefined;
  launcherGlobalPaths: LauncherGlobalPaths;
  navItems: readonly NavItem[];
  notificationIssueAppId: string | null;
  notificationPanel: AppBarNotificationPanelComponent | null;
  notificationRealtimeEventTypes: ReadonlySet<string> | undefined;
  notificationUnreadCountLoader:
    | AppBarNotificationUnreadCountLoader
    | null
    | undefined;
  personalWidgetHost: ElementType | null;
  personalWidgetsEnabled: boolean;
  realtimeEnabled: boolean;
  realtimeProvider: ShellRealtimeProviderComponent;
  resolveShellStateForPath: ShellStateResolver | undefined;
  workspaceSettingsRoute: ShellStaticRouteDefinition | null | undefined;
  workspaceRoutes: readonly ShellWorkspaceRouteDefinition[] | undefined;
  workspaceAppScope: WorkspaceAppScope | undefined;
  workspaceAiToolAppIds: readonly string[];
}) {
  const auth = useAuth();
  const { pathname: locationPathname, search: locationSearch } = useLocation();
  const { t, i18n } = useTranslation('shell');
  const prefersReducedMotion = useReducedMotion();
  const systemDarkMode = useSyncExternalStore(
    subscribeSystemDarkMode,
    getSystemDarkModeSnapshot,
    () => false,
  );
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileInitialTab, setProfileInitialTab] =
    useState<SettingsSection>('profile');
  const [helpOpen, setHelpOpen] = useState(false);
  const [currentReleaseNote, setCurrentReleaseNote] =
    useState<ReleaseNoteItem | null>(null);
  const [releaseNoteDismissError, setReleaseNoteDismissError] = useState<
    string | null
  >(null);
  const [releaseNoteDismissing, setReleaseNoteDismissing] = useState(false);
  const currentUser = auth.user;
  const currentUserId = currentUser?.id ?? null;
  const appRouteContext = useMemo(
    () => resolveAppRouteContext(locationPathname),
    [locationPathname],
  );
  const routeWorkspaceSlug =
    appRouteContext.kind === 'workspace' ? appRouteContext.workspaceSlug : null;
  const shellWorkspaceSlug = routeWorkspaceSlug;
  const openProfile = useCallback((section: SettingsSection = 'profile') => {
    setProfileInitialTab(section);
    setProfileOpen(true);
  }, []);
  const mobileShellRouteKey = createMobileShellRouteKey(
    locationPathname,
    locationSearch,
  );
  const [mobileShellMenu, setMobileShellMenu] = useState(() =>
    createClosedMobileShellMenuState(mobileShellRouteKey),
  );
  useEffect(() => {
    setMobileShellMenu((current) => {
      if (current.routeKey === mobileShellRouteKey) {
        return current;
      }
      return createClosedMobileShellMenuState(mobileShellRouteKey);
    });
  }, [mobileShellRouteKey]);
  const activeMobileShellMenu = resolveActiveMobileShellMenuState(
    mobileShellMenu,
    mobileShellRouteKey,
  );
  const setMobileNavOpen = useCallback(
    (nextOpen: boolean) => {
      setMobileShellMenu((current) => {
        return applyMobileNavOpenChange(current, mobileShellRouteKey, nextOpen);
      });
    },
    [mobileShellRouteKey],
  );
  const setMobileAppMenuOpen = useCallback(
    (nextOpen: boolean) => {
      setMobileShellMenu((current) => {
        return applyMobileAppMenuOpenChange(
          current,
          mobileShellRouteKey,
          nextOpen,
        );
      });
    },
    [mobileShellRouteKey],
  );
  const { navOpen: mobileNavOpen, appMenuOpen: mobileAppMenuOpen } =
    activeMobileShellMenu;
  const themePreference = currentUser?.theme_preference ?? 'system';
  const resolvedTheme = resolveThemePreference(themePreference, systemDarkMode);
  const appsBootstrap = useAppsBootstrap(auth.token, currentUserId);
  const isRouteWorkspaceMember = Boolean(
    routeWorkspaceSlug &&
      currentUser?.workspaces.some(
        (workspace) => workspace.slug === routeWorkspaceSlug,
      ),
  );
  const workspaceBootstrap = useWorkspaceBootstrap(
    auth.token,
    currentUserId,
    isRouteWorkspaceMember ? routeWorkspaceSlug : null,
  );
  const scopedWorkspaceBootstrapData = useMemo(
    () =>
      scopeWorkspaceBootstrapData(workspaceBootstrap.data, workspaceAppScope),
    [workspaceAppScope, workspaceBootstrap.data],
  );
  const scopedWorkspaceBootstrap = useMemo<WorkspaceBootstrapContextValue>(
    () => ({
      data: scopedWorkspaceBootstrapData,
      error: workspaceBootstrap.error,
      loading: workspaceBootstrap.loading,
      reload: workspaceBootstrap.reload,
    }),
    [
      scopedWorkspaceBootstrapData,
      workspaceBootstrap.error,
      workspaceBootstrap.loading,
      workspaceBootstrap.reload,
    ],
  );
  const enabledWorkspaceAppIds = useMemo(() => {
    if (!scopedWorkspaceBootstrapData) {
      return null;
    }
    return scopedWorkspaceBootstrapData.apps.flatMap((app) =>
      app.enabled ? [app.app_id] : [],
    );
  }, [scopedWorkspaceBootstrapData]);
  const currentWorkspace = useMemo(() => {
    if (!routeWorkspaceSlug) {
      return null;
    }
    const workspace =
      scopedWorkspaceBootstrapData?.workspace ??
      currentUser?.workspaces.find(
        (candidate) => candidate.slug === routeWorkspaceSlug,
      ) ??
      null;
    return workspace
      ? {
          id: workspace.id,
          name: workspace.name,
          slug: workspace.slug,
        }
      : null;
  }, [
    currentUser?.workspaces,
    routeWorkspaceSlug,
    scopedWorkspaceBootstrapData?.workspace,
  ]);
  const currentWorkspaceAppIdSet = useMemo(
    () =>
      routeWorkspaceSlug && enabledWorkspaceAppIds
        ? new Set(enabledWorkspaceAppIds)
        : null,
    [enabledWorkspaceAppIds, routeWorkspaceSlug],
  );
  const launchAppById = useMemo(
    () =>
      new Map((appsBootstrap.data?.apps ?? []).map((app) => [app.app_id, app])),
    [appsBootstrap.data?.apps],
  );
  const resolveAppDestination = useCallback<AppLaunchDestinationResolver>(
    (appId) =>
      resolveAppLaunchDestination({
        app: launchAppById.get(appId) ?? null,
        appId,
        currentWorkspace,
        currentWorkspaceAppIds: currentWorkspaceAppIdSet,
        launcherGlobalPaths,
      }),
    [
      currentWorkspace,
      currentWorkspaceAppIdSet,
      launchAppById,
      launcherGlobalPaths,
    ],
  );
  const activeWorkspaceContext =
    appRouteContext.kind === 'workspace' &&
    enabledWorkspaceAppIds?.includes(appRouteContext.appId)
      ? appRouteContext
      : null;
  const shellAppsBootstrap = useMemo(
    () =>
      projectShellAppsBootstrap({
        globalBootstrap: appsBootstrap.data,
        personalToolsScope: t('appBar.personalToolsScope'),
        personalToolsTitle: t('appBar.personalTools'),
      }),
    [appsBootstrap.data, t],
  );
  const enabledGlobalAppIds = shellAppsBootstrap.globalRouteAppIds;
  const enabledRouteAppIds = routeWorkspaceSlug
    ? enabledWorkspaceAppIds
    : enabledGlobalAppIds;
  const enabledBackgroundWorkSources = useMemo(() => {
    const bootstrap = scopedWorkspaceBootstrapData;
    if (!bootstrap) {
      return [];
    }
    return filterBackgroundWorkSourcesForWorkspace(backgroundWorkSources, {
      enabledAppIds: [
        ...bootstrap.apps.filter((app) => app.enabled).map((app) => app.app_id),
      ],
      enabledNavItemIds: bootstrap.nav.map((item) => item.id),
    });
  }, [backgroundWorkSources, scopedWorkspaceBootstrapData]);
  const shellChromeState = useMemo(
    () =>
      resolveShellChromeState({
        appGlobalRoutes,
        enabledWorkspaceAppIds: enabledRouteAppIds,
        pathname: locationPathname,
        resolveShellStateForPath,
        search: locationSearch,
        user: currentUser,
        workspaceRoutes,
      }),
    [
      appGlobalRoutes,
      currentUser,
      locationPathname,
      locationSearch,
      resolveShellStateForPath,
      enabledRouteAppIds,
      workspaceRoutes,
    ],
  );
  const {
    activeAppId,
    activeNavItemId,
    canOpenMobileAppMenu,
    mainClassName,
    showSubSidebar,
  } = shellChromeState;
  const activeDisplayAppId = resolveShellDisplayAppId({
    activeAppId,
    pathname: locationPathname,
  });
  const activeDisplayScope = resolveAppDisplayScope(
    activeDisplayAppId as WorkspaceAppId,
  );
  const currentWorkspaceName = currentWorkspace?.name ?? routeWorkspaceSlug;
  const activeContextLabel =
    activeDisplayScope === 'workspace'
      ? currentWorkspaceName
      : activeDisplayScope === 'personal'
        ? t('shell:launcher.personalScope')
        : activeDisplayScope === 'company'
          ? t('shell:launcher.companyScope')
          : null;
  const canRenderDesktopSubSidebar =
    showSubSidebar && activeAppId !== 'profile';
  const subSidebarCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const lastUsageOpenEventRef = useRef<string | null>(null);
  const desktopAppBarMenuWasOpenRef = useRef(false);
  const restorePreviewAfterDesktopAppBarMenuRef = useRef(false);
  const [subSidebarPinned, setSubSidebarPinned] = useState<boolean>(() => {
    if (typeof window === 'undefined') {
      return true;
    }
    return restoreSubSidebarPinned(
      window.sessionStorage.getItem(SUB_SIDEBAR_PINNED_STORAGE_KEY),
    );
  });
  const [subSidebarPreviewOpen, setSubSidebarPreviewOpen] = useState(false);
  const [desktopAppBarMenuOpen, setDesktopAppBarMenuOpen] = useState(false);
  const desktopSubSidebarOpen =
    canRenderDesktopSubSidebar && (subSidebarPinned || subSidebarPreviewOpen);
  const clearSubSidebarCloseTimer = useCallback(() => {
    if (subSidebarCloseTimerRef.current === null) {
      return;
    }
    clearTimeout(subSidebarCloseTimerRef.current);
    subSidebarCloseTimerRef.current = null;
  }, []);
  const openSubSidebarPreview = useCallback(() => {
    if (
      !canRenderDesktopSubSidebar ||
      desktopAppBarMenuOpen ||
      subSidebarPinned
    ) {
      return;
    }
    clearSubSidebarCloseTimer();
    setSubSidebarPreviewOpen(true);
  }, [
    canRenderDesktopSubSidebar,
    clearSubSidebarCloseTimer,
    desktopAppBarMenuOpen,
    subSidebarPinned,
  ]);
  const scheduleSubSidebarPreviewClose = useCallback(() => {
    if (subSidebarPinned) {
      return;
    }
    clearSubSidebarCloseTimer();
    subSidebarCloseTimerRef.current = setTimeout(() => {
      setSubSidebarPreviewOpen(false);
      subSidebarCloseTimerRef.current = null;
    }, 180);
  }, [clearSubSidebarCloseTimer, subSidebarPinned]);
  const handleSubSidebarPinnedChange = useCallback(
    (nextPinned: boolean) => {
      clearSubSidebarCloseTimer();
      setSubSidebarPinned(nextPinned);
      setSubSidebarPreviewOpen(resolveSubSidebarPreviewOpenAfterPinnedChange());
    },
    [clearSubSidebarCloseTimer],
  );
  const documentTitleWorkspace =
    scopedWorkspaceBootstrap.data?.workspace ??
    (routeWorkspaceSlug
      ? (currentUser?.workspaces.find(
          (workspace) => workspace.slug === routeWorkspaceSlug,
        ) ?? null)
      : null);
  const documentTitle = resolveShellDocumentTitle({
    activeAppId,
    appBarItems,
    routeWorkspaceSlug,
    t,
    workspace: documentTitleWorkspace,
    workspaceApps: scopedWorkspaceBootstrap.data?.apps ?? [],
  });
  const usageRoutePath = useMemo(
    () => normalizeUsageRoutePath(locationPathname),
    [locationPathname],
  );
  const usageEventAppId = useMemo(
    () =>
      resolveUsageEventAppId({
        activeAppId,
        activeNavItemId,
        navItems: scopedWorkspaceBootstrap.data?.nav ?? null,
      }),
    [activeAppId, activeNavItemId, scopedWorkspaceBootstrap.data?.nav],
  );

  useEffect(() => {
    syncLocale(currentUser?.locale);
  }, [currentUser?.locale]);

  useEffect(() => {
    syncDateFormatPreference(currentUser?.date_format);
  }, [currentUser?.date_format]);

  useEffect(() => {
    if (resolvedTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [resolvedTheme]);

  useEffect(() => {
    document.title = documentTitle;
  }, [documentTitle]);

  useEffect(() => {
    trackMatomoPageView({
      appId: activeNavItemId
        ? `${activeAppId}:${activeNavItemId}`
        : activeAppId,
      appRoute: usageRoutePath,
    });
  }, [activeAppId, activeNavItemId, documentTitle, usageRoutePath]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    window.sessionStorage.setItem(
      SUB_SIDEBAR_PINNED_STORAGE_KEY,
      serializeSubSidebarPinned(subSidebarPinned),
    );
  }, [subSidebarPinned]);

  useEffect(() => {
    return () => clearSubSidebarCloseTimer();
  }, [clearSubSidebarCloseTimer]);

  useEffect(() => {
    const wasOpen = desktopAppBarMenuWasOpenRef.current;
    desktopAppBarMenuWasOpenRef.current = desktopAppBarMenuOpen;

    if (desktopAppBarMenuOpen && !wasOpen) {
      restorePreviewAfterDesktopAppBarMenuRef.current = subSidebarPreviewOpen;
      if (!subSidebarPinned) {
        clearSubSidebarCloseTimer();
        setSubSidebarPreviewOpen(false);
      }
      return;
    }

    if (!desktopAppBarMenuOpen && wasOpen) {
      const shouldRestorePreview =
        restorePreviewAfterDesktopAppBarMenuRef.current &&
        canRenderDesktopSubSidebar &&
        !subSidebarPinned;
      restorePreviewAfterDesktopAppBarMenuRef.current = false;
      if (shouldRestorePreview) {
        clearSubSidebarCloseTimer();
        setSubSidebarPreviewOpen(true);
      }
    }
  }, [
    canRenderDesktopSubSidebar,
    clearSubSidebarCloseTimer,
    desktopAppBarMenuOpen,
    subSidebarPinned,
    subSidebarPreviewOpen,
  ]);

  useEffect(() => {
    if (canRenderDesktopSubSidebar) {
      return;
    }
    clearSubSidebarCloseTimer();
    setSubSidebarPreviewOpen(false);
  }, [canRenderDesktopSubSidebar, clearSubSidebarCloseTimer]);

  useEffect(() => {
    if (!auth.token || !currentUserId) {
      return;
    }
    if (
      activeAppId === 'home' ||
      activeAppId === 'launcher' ||
      activeAppId === 'profile'
    ) {
      return;
    }
    if (
      routeWorkspaceSlug &&
      activeNavItemId &&
      !scopedWorkspaceBootstrap.data &&
      !scopedWorkspaceBootstrap.error
    ) {
      return;
    }
    const eventKey = `${currentUserId}:${usageEventAppId}:${activeNavItemId}:${usageRoutePath}`;
    if (lastUsageOpenEventRef.current === eventKey) {
      return;
    }
    lastUsageOpenEventRef.current = eventKey;
    const source = activeNavItemId
      ? `shell.nav.${activeNavItemId}`.slice(0, 120)
      : 'shell.app';
    void recordUsageEvent(auth.token, {
      app_id: usageEventAppId,
      event_type: 'app.open',
      route_path: usageRoutePath,
      source,
      metadata: {
        has_workspace_route: Boolean(routeWorkspaceSlug),
      },
      dedupe_minutes: 30,
    }).catch(() => undefined);
  }, [
    activeAppId,
    activeNavItemId,
    auth.token,
    currentUserId,
    routeWorkspaceSlug,
    scopedWorkspaceBootstrap.data,
    scopedWorkspaceBootstrap.error,
    usageEventAppId,
    usageRoutePath,
  ]);

  useEffect(() => {
    if (!auth.token || !currentUserId) {
      setCurrentReleaseNote(null);
      return;
    }
    let cancelled = false;
    setReleaseNoteDismissError(null);
    getCurrentReleaseNote(auth.token)
      .then((response) => {
        if (!cancelled) {
          setCurrentReleaseNote(response.item);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentReleaseNote(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth.token, currentUserId]);

  const dismissCurrentReleaseNote = useCallback(async () => {
    if (!auth.token || !currentReleaseNote) {
      return;
    }
    setReleaseNoteDismissing(true);
    setReleaseNoteDismissError(null);
    try {
      await dismissReleaseNote(auth.token, currentReleaseNote.id);
      setCurrentReleaseNote(null);
    } catch (caughtError) {
      setReleaseNoteDismissError(
        caughtError instanceof Error
          ? caughtError.message
          : t('shell:releaseNotes.dismissFailed'),
      );
    } finally {
      setReleaseNoteDismissing(false);
    }
  }, [auth.token, currentReleaseNote, t]);

  const openReleaseNotesHistory = useCallback(() => {
    if (auth.token && currentReleaseNote) {
      setReleaseNoteDismissing(true);
      dismissReleaseNote(auth.token, currentReleaseNote.id)
        .catch(() => undefined)
        .finally(() => {
          setReleaseNoteDismissing(false);
        });
    }
    setCurrentReleaseNote(null);
    openProfile('releaseNotes');
  }, [auth.token, currentReleaseNote, openProfile]);

  if (!currentUser) {
    return <Navigate replace to="/login" />;
  }

  return (
    <ShellRealtimeProvider token={realtimeEnabled ? auth.token : null}>
      <AccessRefreshBoundary
        accessProjectionKey={createAccessProjectionKey(
          currentUser,
          appsBootstrap.data,
        )}
        refreshApps={appsBootstrap.refresh}
        refreshUser={auth.refreshAccessUser}
        refreshWorkspace={workspaceBootstrap.refresh}
        workspaceSlug={routeWorkspaceSlug}
      >
        <WorkspaceBootstrapProvider
          value={{
            ...scopedWorkspaceBootstrap,
            aiToolAppIds: workspaceAiToolAppIds,
            globalApps: appsBootstrap.data,
            reloadGlobalApps: appsBootstrap.reload,
          }}
        >
          <div className="flex h-screen flex-col overflow-hidden bg-app-surface-sidebar text-app-ink transition-colors lg:flex-row">
            <AppBar
              activeAppId={activeDisplayAppId}
              activeContextLabel={activeContextLabel}
              appBarFixedAppIds={appBarFixedAppIds}
              appBarItems={appBarItems}
              appBarPinnedByDefaultAppIds={appBarPinnedByDefaultAppIds}
              canOpenMobileAppMenu={canOpenMobileAppMenu}
              currentUser={currentUser}
              currentPathname={locationPathname}
              currentWorkspaceName={currentWorkspaceName}
              launcherGlobalPaths={launcherGlobalPaths}
              notificationIssueAppId={notificationIssueAppId}
              onDesktopMenuOpenChange={setDesktopAppBarMenuOpen}
              onDesktopRailMouseEnter={openSubSidebarPreview}
              onDesktopRailMouseLeave={scheduleSubSidebarPreviewClose}
              onOpenHelp={() => setHelpOpen(true)}
              onOpenMobileAppMenu={() => setMobileAppMenuOpen(true)}
              onOpenMobileNavigation={() => setMobileNavOpen(true)}
              resolveAppDestination={resolveAppDestination}
              shellWorkspaceSlug={shellWorkspaceSlug}
              workspaceApps={shellAppsBootstrap.apps}
              workspaceAppBarCategories={shellAppsBootstrap.appBarCategories}
              canOpenWorkspaceSearch={Boolean(
                scopedWorkspaceBootstrapData?.keyword_search?.entity_types
                  .length,
              )}
              notificationPanel={notificationPanel}
              notificationRealtimeEventTypes={notificationRealtimeEventTypes}
              notificationUnreadCountLoader={notificationUnreadCountLoader}
              notificationsEnabled={Boolean(notificationPanel)}
              onOpenAccount={() => openProfile('profile')}
            />

            <div className="relative flex flex-1 overflow-hidden">
              <LazyMotion features={domAnimation}>
                <AnimatePresence initial={false}>
                  {desktopSubSidebarOpen ? (
                    <m.div
                      animate={{ opacity: 1, x: 0 }}
                      className={cn(
                        subSidebarPinned
                          ? 'hidden h-full shrink-0 lg:flex'
                          : 'absolute inset-y-0 left-0 z-30 hidden lg:flex',
                      )}
                      exit={
                        subSidebarPinned
                          ? undefined
                          : { opacity: 0, x: '-100%' }
                      }
                      initial={
                        subSidebarPinned ? false : { opacity: 0, x: '-100%' }
                      }
                      transition={
                        prefersReducedMotion
                          ? { duration: 0 }
                          : {
                              duration: 0.22,
                              ease: [0.22, 1, 0.36, 1],
                            }
                      }
                      onBlurCapture={(event) => {
                        const nextTarget = event.relatedTarget;
                        if (
                          nextTarget instanceof Node &&
                          event.currentTarget.contains(nextTarget)
                        ) {
                          return;
                        }
                        scheduleSubSidebarPreviewClose();
                      }}
                      onFocusCapture={openSubSidebarPreview}
                      onMouseEnter={openSubSidebarPreview}
                      onMouseLeave={scheduleSubSidebarPreviewClose}
                    >
                      <AppSubSidebar
                        activeAppId={activeAppId}
                        activeNavItemId={activeNavItemId}
                        appBarItems={appBarItems}
                        currentWorkspaceSlug={routeWorkspaceSlug}
                        enabledWorkspaceAppIds={enabledWorkspaceAppIds ?? []}
                        getAppModuleManifest={getAppModuleManifest}
                        getAppSidebarConfig={getAppSidebarConfig}
                        hasAdminSectionAccess={hasAdminSectionAccess}
                        headerSlot={
                          activeWorkspaceContext ? (
                            <WorkspaceContextSelector
                              appId={activeWorkspaceContext.appId}
                              onPreferenceChanged={appsBootstrap.reload}
                              workspaceSlug={
                                activeWorkspaceContext.workspaceSlug
                              }
                            />
                          ) : activeContextLabel &&
                            (activeDisplayScope === 'company' ||
                              activeDisplayScope === 'personal') ? (
                            <ExecutionScopeIndicator
                              label={activeContextLabel}
                            />
                          ) : undefined
                        }
                        launcherGlobalPaths={launcherGlobalPaths}
                        navItems={navItems}
                        onPinnedChange={handleSubSidebarPinnedChange}
                        overlay={!subSidebarPinned}
                        pinned={subSidebarPinned}
                        variant="desktop"
                        workspaceApps={
                          scopedWorkspaceBootstrap.data?.apps ?? []
                        }
                        workspaceNavItems={
                          scopedWorkspaceBootstrap.data?.nav ?? []
                        }
                      />
                    </m.div>
                  ) : null}
                </AnimatePresence>
              </LazyMotion>

              <div className="flex-1 min-w-0 flex flex-col overflow-hidden bg-app-bg transition-colors">
                <main className={mainClassName}>
                  <Routes>
                    <Route
                      path="/"
                      element={
                        <AppLauncherView
                          data={appsBootstrap.data}
                          error={appsBootstrap.error}
                          loading={appsBootstrap.loading}
                        />
                      }
                    />
                    <Route
                      path="/apps/:appId"
                      element={
                        <AppEntryRoute
                          bootstrap={appsBootstrap.data}
                          error={appsBootstrap.error}
                          loading={appsBootstrap.loading}
                          reload={appsBootstrap.reload}
                        />
                      }
                    />
                    {WorkspaceRouteElements({
                      bootstrapAppIds: enabledWorkspaceAppIds,
                      bootstrapError: workspaceBootstrap.error,
                      bootstrapLoading: workspaceBootstrap.loading,
                      workspaceRoutes,
                    })}
                    {StaticRouteElements({
                      adminLandingRoute,
                      adminRedirectRoutes,
                      adminSectionRoutes,
                      appGlobalRoutes,
                      bootstrapError: appsBootstrap.error,
                      bootstrapLoading: appsBootstrap.loading,
                      enabledAppIds: appsBootstrap.data
                        ? appsBootstrap.data.global_route_app_ids
                        : null,
                      featureGuideToolIds,
                      getDefaultAdminPath,
                      hasAdminSectionAccess,
                      helpRoutes,
                      workspaceSettingsRoute,
                    })}
                    <Route path="*" element={<NotFoundView />} />
                  </Routes>
                </main>
              </div>

              {personalWidgetsEnabled && PersonalWidgetHost ? (
                <LazyRouteErrorBoundary
                  resetKey={`${locationPathname}${locationSearch}`}
                >
                  <Suspense
                    fallback={
                      <div className="h-full w-10 shrink-0 border-l border-app-border bg-app-bg" />
                    }
                  >
                    <PersonalWidgetHost key={currentUserId} />
                  </Suspense>
                </LazyRouteErrorBoundary>
              ) : null}
            </div>

            <MobileNavigationDrawer
              activeAppId={activeAppId}
              appBarFixedAppIds={appBarFixedAppIds}
              appBarCategories={shellAppsBootstrap.appBarCategories}
              appBarItems={appBarItems}
              currentPathname={locationPathname}
              currentUser={currentUser}
              getDefaultAdminPath={getDefaultAdminPath}
              hasAnyAdminReadPermission={hasAnyAdminReadPermission}
              onOpenChange={setMobileNavOpen}
              open={mobileNavOpen}
              resolveAppDestination={resolveAppDestination}
              workspaceApps={shellAppsBootstrap.apps}
            />

            {canOpenMobileAppMenu ? (
              <MobileAppMenuDrawer
                activeAppId={activeAppId}
                activeDisplayAppId={activeDisplayAppId}
                activeNavItemId={activeNavItemId}
                appBarItems={appBarItems}
                currentWorkspaceSlug={routeWorkspaceSlug}
                enabledWorkspaceAppIds={enabledWorkspaceAppIds ?? []}
                getAppModuleManifest={getAppModuleManifest}
                getAppSidebarConfig={getAppSidebarConfig}
                hasAdminSectionAccess={hasAdminSectionAccess}
                headerSlot={
                  activeWorkspaceContext ? (
                    <WorkspaceContextSelector
                      appId={activeWorkspaceContext.appId}
                      onNavigate={() => setMobileAppMenuOpen(false)}
                      onPreferenceChanged={appsBootstrap.reload}
                      workspaceSlug={activeWorkspaceContext.workspaceSlug}
                    />
                  ) : activeContextLabel &&
                    (activeDisplayScope === 'company' ||
                      activeDisplayScope === 'personal') ? (
                    <ExecutionScopeIndicator label={activeContextLabel} />
                  ) : undefined
                }
                launcherGlobalPaths={launcherGlobalPaths}
                navItems={navItems}
                onOpenChange={setMobileAppMenuOpen}
                open={mobileAppMenuOpen}
                workspaceApps={scopedWorkspaceBootstrap.data?.apps ?? []}
                workspaceNavItems={scopedWorkspaceBootstrap.data?.nav ?? []}
              />
            ) : null}

            {profileOpen && (
              <div className="fixed inset-0 z-50 flex items-center justify-center">
                <button
                  type="button"
                  aria-label={t('common:actions.close')}
                  className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
                  onClick={() => setProfileOpen(false)}
                />
                <div className="relative z-10 h-[calc(100vh-1rem)] w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-app-border bg-app-bg shadow-2xl sm:h-[85vh] sm:max-w-4xl sm:rounded-2xl">
                  <button
                    type="button"
                    aria-label={t('common:actions.close')}
                    onClick={() => setProfileOpen(false)}
                    className="absolute top-4 right-4 z-20 flex size-8 items-center justify-center rounded-lg text-app-ink/50 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                  >
                    <X aria-hidden size={16} />
                  </button>
                  <div className="h-full overflow-y-auto">
                    <ProfilePage initialTab={profileInitialTab} />
                  </div>
                </div>
              </div>
            )}
            {currentReleaseNote ? (
              <ReleaseNoteAnnouncementModal
                dismissing={releaseNoteDismissing}
                error={releaseNoteDismissError}
                item={currentReleaseNote}
                locale={i18n.language}
                onClose={() => {
                  setCurrentReleaseNote(null);
                  setReleaseNoteDismissError(null);
                }}
                onDismiss={() => {
                  void dismissCurrentReleaseNote();
                }}
                onOpenHistory={openReleaseNotesHistory}
              />
            ) : null}
            {helpOpen ? (
              <HelpCenterModal
                closeLabel={t('common:actions.close')}
                onClose={() => setHelpOpen(false)}
              />
            ) : null}
            <BackgroundWorkProvider
              sources={enabledBackgroundWorkSources}
              workspaceSlug={routeWorkspaceSlug}
            />
          </div>
        </WorkspaceBootstrapProvider>
      </AccessRefreshBoundary>
    </ShellRealtimeProvider>
  );
}

function ShellProviderStack({
  children,
  providers,
}: {
  children: ReactNode;
  providers: readonly ShellProviderComponent[];
}) {
  return providers.reduceRight(
    (content, Provider) => <Provider>{content}</Provider>,
    children,
  );
}

export function AppContent({
  adminLandingRoute,
  adminRedirectRoutes,
  adminSectionRoutes,
  appGlobalRoutes,
  appBarFixedAppIds = [],
  appBarItems = [],
  appBarPinnedByDefaultAppIds = [],
  backgroundWorkSources = [],
  featureGuideToolIds = EMPTY_FEATURE_GUIDE_TOOL_IDS,
  getDefaultAdminPath = getPlatformDefaultAdminPath,
  getAppModuleManifest = getNoopAppModuleManifest,
  getAppSidebarConfig = getNoopAppSidebarConfig,
  hasAdminSectionAccess = hasConfiguredAdminSectionAccess,
  hasAnyAdminReadPermission = hasAnyPlatformAdminReadPermission,
  helpRoutes,
  launcherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
  navItems = [],
  notificationIssueAppId = null,
  notificationPanel = null,
  notificationRealtimeEventTypes,
  notificationUnreadCountLoader = null,
  personalWidgetHost = null,
  personalWidgetsEnabled = true,
  realtimeEnabled = true,
  realtimeProvider = NoopShellRealtimeProvider,
  resolveShellStateForPath,
  shellProviders = [],
  workspaceSettingsRoute,
  workspaceRoutes,
  workspaceAppScope,
  workspaceAiToolAppIds = [],
}: AppContentProps) {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route
          path="*"
          element={
            <RequireAuth>
              <ShellProviderStack providers={shellProviders}>
                <AuthenticatedShell
                  adminLandingRoute={adminLandingRoute}
                  adminRedirectRoutes={adminRedirectRoutes}
                  adminSectionRoutes={adminSectionRoutes}
                  appGlobalRoutes={appGlobalRoutes}
                  appBarFixedAppIds={appBarFixedAppIds}
                  appBarItems={appBarItems}
                  appBarPinnedByDefaultAppIds={appBarPinnedByDefaultAppIds}
                  backgroundWorkSources={backgroundWorkSources}
                  featureGuideToolIds={featureGuideToolIds}
                  getDefaultAdminPath={getDefaultAdminPath}
                  getAppModuleManifest={getAppModuleManifest}
                  getAppSidebarConfig={getAppSidebarConfig}
                  hasAdminSectionAccess={hasAdminSectionAccess}
                  hasAnyAdminReadPermission={hasAnyAdminReadPermission}
                  helpRoutes={helpRoutes}
                  launcherGlobalPaths={launcherGlobalPaths}
                  navItems={navItems}
                  notificationIssueAppId={notificationIssueAppId}
                  notificationPanel={notificationPanel}
                  notificationRealtimeEventTypes={
                    notificationRealtimeEventTypes
                  }
                  notificationUnreadCountLoader={notificationUnreadCountLoader}
                  personalWidgetHost={personalWidgetHost}
                  personalWidgetsEnabled={personalWidgetsEnabled}
                  realtimeEnabled={realtimeEnabled}
                  realtimeProvider={
                    realtimeProvider ?? NoopShellRealtimeProvider
                  }
                  resolveShellStateForPath={resolveShellStateForPath}
                  workspaceSettingsRoute={workspaceSettingsRoute}
                  workspaceRoutes={workspaceRoutes}
                  workspaceAppScope={workspaceAppScope}
                  workspaceAiToolAppIds={workspaceAiToolAppIds}
                />
              </ShellProviderStack>
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
