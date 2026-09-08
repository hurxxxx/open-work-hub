import { DetailDrawer } from '@open-work-hub/ui';
import { Check, LayoutGrid, X } from 'lucide-react';
import {
  AnimatePresence,
  LazyMotion,
  domAnimation,
  m,
  useReducedMotion,
} from 'motion/react';
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ComponentType,
  type ElementType,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { AppBar } from '@/src/components/layout/AppBar';
import type {
  AppBarNotificationPanelComponent,
  AppBarNotificationUnreadCountLoader,
} from '@/src/components/layout/app-bar-model';
import {
  SUB_SIDEBAR_PINNED_STORAGE_KEY,
  resolveSubSidebarPreviewOpenAfterPinnedChange,
  restoreSubSidebarPinned,
  serializeSubSidebarPinned,
} from '@/src/components/layout/sub-sidebar-frame-model';
import { cn } from '@/src/lib/utils';
import {
  getDefaultAdminPath as getPlatformDefaultAdminPath,
  hasAnyAdminReadPermission as hasAnyPlatformAdminReadPermission,
  hasConfiguredAdminSectionAccess,
  type AdminSectionAccessResolver,
  type DefaultAdminPathResolver,
} from '@/src/platform/admin/admin-permissions';
import { trackMatomoPageView } from '@/src/platform/analytics/matomo';
import {
  AppBootstrapProvider,
  type AppBootstrapContextValue,
} from '@/src/platform/apps/app-bootstrap-context';
import {
  getAppIdFromPath,
  type ShellAppId,
} from '@/src/platform/apps/app-links';
import {
  useAppsBootstrap,
  type AppsBootstrapResponse,
  type BootstrapApp,
  type BootstrapAppBarCategory,
  type BootstrapNavItem,
} from '@/src/platform/apps/apps-api';
import {
  ReleaseNoteBody,
  formatReleaseNoteDate,
} from '@/src/platform/auth/ReleaseNotesSettingsSection';
import {
  hasAdminConsoleAccess,
  type AuthUser,
} from '@/src/platform/auth/auth-api';
import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from '@/src/platform/auth/auth-provider';
import type { SettingsSection } from '@/src/platform/auth/settings-page-model';
import { NotFoundView, ProfilePage } from '@/src/platform/auth/settings-pages';
import { BackgroundWorkProvider } from '@/src/platform/background-work/background-work-provider';
import {
  filterBackgroundWorkSourcesForApps,
  type BackgroundWorkSource,
} from '@/src/platform/background-work/background-work-session';
import { syncLocale } from '@/src/platform/i18n';
import {
  dismissReleaseNote,
  getCurrentReleaseNote,
  type ReleaseNoteItem,
} from '@/src/platform/release-notes/release-notes-api';
import { syncDateFormatPreference } from '@/src/platform/time/time-utils';
import { recordUsageEvent } from '@/src/platform/usage/usage-api';
import {
  normalizeUsageRoutePath,
  resolveUsageEventAppId,
} from '@/src/platform/usage/usage-route';
import { AccessRefreshBoundary } from './AccessRefreshBoundary';
import { AppLauncherView } from './AppLauncherView';
import { AppSubSidebar } from './AppSubSidebar';
import { HelpCenterModal } from './HelpCenterPage';
import { createAccessProjectionKey } from './access-projection-key';
import {
  EMPTY_FEATURE_GUIDE_TOOL_IDS,
  type FeatureGuideToolIds,
} from './ai-feature-guides';
import {
  resolveAppLaunchDestination,
  translateAppLaunchContext,
  translateAppLaunchLabel,
  type AppLaunchDestinationResolver,
} from './app-launch-destination';
import {
  AppRouteElements,
  type ShellAppRouteDefinition,
} from './app-route-registry';
import { projectShellAppsBootstrap } from './apps-bootstrap-model';
import { resolveShellDocumentTitle } from './document-title-model';
import { LazyRouteErrorBoundary } from './lazy-route';
import { projectMobileNavigationItems } from './mobile-navigation-model';
import {
  applyMobileAppMenuOpenChange,
  applyMobileNavOpenChange,
  createClosedMobileShellMenuState,
  createMobileShellRouteKey,
  resolveActiveMobileShellMenuState,
} from './mobile-shell-menu-model';
import {
  EMPTY_LAUNCHER_GLOBAL_PATHS,
  type AppBarItem,
  type LauncherGlobalPaths,
  type NavItem,
} from './navigation-types';
import {
  resolveShellChromeState,
  type ShellStateResolver,
} from './shell-chrome-model';
import { resolveShellDisplayAppId } from './shell-display-app-model';
import {
  getSystemDarkModeSnapshot,
  resolveThemePreference,
  subscribeSystemDarkMode,
} from './shell-ui-model';
import type { AppSidebarConfig } from './sidebar-types';
import {
  StaticRouteElements,
  type ShellAdminSectionRouteDefinition,
  type ShellStaticRouteDefinition,
} from './static-route-elements';

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

export interface AppScope {
  appIds: readonly ShellAppId[];
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

  appRoutes?: readonly ShellAppRouteDefinition[];
  aiToolAppIds?: readonly string[];
}

export interface AppContentProps extends AppContentRuntimeConfig {
  appScope?: AppScope;
}

function isScopedNavItemVisible({
  appIds,
  item,
}: {
  appIds: ReadonlySet<string>;
  item: BootstrapNavItem;
}): boolean {
  return appIds.has(item.app_id);
}

function scopeBootstrapData(
  data: AppsBootstrapResponse | null,
  scope: AppScope | undefined,
): AppsBootstrapResponse | null {
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
  apps,
}: {
  activeAppId: string;
  appBarFixedAppIds: readonly string[];
  appBarItems: readonly AppBarItem[];
  currentPathname: string;
  currentUser: AuthUser;
  getDefaultAdminPath: DefaultAdminPathResolver;
  hasAnyAdminReadPermission: (systemRoles: readonly string[]) => boolean;
  appBarCategories: readonly BootstrapAppBarCategory[];
  onOpenChange: (open: boolean) => void;
  open: boolean;
  resolveAppDestination: AppLaunchDestinationResolver;
  apps: BootstrapApp[];
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
    apps,
  }).map((item) => ({
    ...item,
    destination: resolveAppDestination(item.linkAppId),
    title:
      item.type === 'app'
        ? t(`shell:apps.${item.id}`, { defaultValue: item.title })
        : item.title,
  }));
  const navigationActiveAppId =
    getAppIdFromPath(currentPathname) ?? activeAppId;
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
                    navigationActiveAppId as ShellAppId,
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
                  navigationActiveAppId as ShellAppId,
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
  enabledShellAppIds,
  getAppModuleManifest,
  getAppSidebarConfig,
  hasAdminSectionAccess,
  headerSlot,
  launcherGlobalPaths,
  navItems,
  onOpenChange,
  open,
  apps,
  appNavItems,
}: {
  activeAppId: string;
  activeDisplayAppId: string;
  activeNavItemId: string;
  appBarItems: readonly AppBarItem[];

  enabledShellAppIds: readonly string[];
  getAppModuleManifest: (appId: string) => unknown | null;
  getAppSidebarConfig: (appId: string) => AppSidebarConfig | null;
  hasAdminSectionAccess: AdminSectionAccessResolver;
  headerSlot?: ReactNode;
  launcherGlobalPaths: LauncherGlobalPaths;
  navItems: readonly NavItem[];
  onOpenChange: (open: boolean) => void;
  open: boolean;
  apps: BootstrapApp[];
  appNavItems: BootstrapNavItem[];
}) {
  const close = () => onOpenChange(false);
  const { t } = useTranslation('shell');
  const activeAppTitle =
    activeDisplayAppId === 'settings'
      ? t('apps.settings')
      : (apps.find((item) => item.app_id === activeDisplayAppId)?.title ??
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
          enabledShellAppIds={enabledShellAppIds}
          getAppModuleManifest={getAppModuleManifest}
          getAppSidebarConfig={getAppSidebarConfig}
          hasAdminSectionAccess={hasAdminSectionAccess}
          headerSlot={headerSlot}
          launcherGlobalPaths={launcherGlobalPaths}
          navItems={navItems}
          onNavigate={close}
          variant="mobile"
          apps={apps}
          appNavItems={appNavItems}
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
  appRoutes,
  appScope,
  aiToolAppIds,
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

  appRoutes: readonly ShellAppRouteDefinition[] | undefined;
  appScope: AppScope | undefined;
  aiToolAppIds: readonly string[];
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
  const scopedBootstrapData = useMemo(
    () => scopeBootstrapData(appsBootstrap.data, appScope),
    [appsBootstrap.data, appScope],
  );
  const scopedBootstrap = useMemo<AppBootstrapContextValue>(
    () => ({
      data: scopedBootstrapData,
      error: appsBootstrap.error,
      loading: appsBootstrap.loading,
      reload: appsBootstrap.reload,
    }),
    [
      scopedBootstrapData,
      appsBootstrap.error,
      appsBootstrap.loading,
      appsBootstrap.reload,
    ],
  );
  const enabledShellAppIds = useMemo(
    () =>
      scopedBootstrapData?.apps
        .filter((app) => app.enabled)
        .map((app) => app.app_id) ?? null,
    [scopedBootstrapData],
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
        launcherGlobalPaths,
      }),
    [launchAppById, launcherGlobalPaths],
  );
  const shellAppsBootstrap = useMemo(
    () =>
      projectShellAppsBootstrap({
        globalBootstrap: appsBootstrap.data,
        personalToolsScope: t('appBar.personalToolsScope'),
        personalToolsTitle: t('appBar.personalTools'),
      }),
    [appsBootstrap.data, t],
  );
  const enabledRouteAppIds = enabledShellAppIds;
  const enabledBackgroundWorkSources = useMemo(() => {
    const bootstrap = scopedBootstrapData;
    if (!bootstrap) {
      return [];
    }
    return filterBackgroundWorkSourcesForApps(backgroundWorkSources, {
      enabledAppIds: [
        ...bootstrap.apps.filter((app) => app.enabled).map((app) => app.app_id),
      ],
      enabledNavItemIds: bootstrap.nav.map((item) => item.id),
    });
  }, [backgroundWorkSources, scopedBootstrapData]);
  const shellChromeState = useMemo(
    () =>
      resolveShellChromeState({
        appGlobalRoutes,
        enabledShellAppIds: enabledRouteAppIds,
        pathname: locationPathname,
        resolveShellStateForPath,
        search: locationSearch,
        user: currentUser,
        appRoutes,
      }),
    [
      appGlobalRoutes,
      currentUser,
      locationPathname,
      locationSearch,
      resolveShellStateForPath,
      enabledRouteAppIds,
      appRoutes,
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
  const documentTitle = resolveShellDocumentTitle({
    activeAppId,
    appBarItems,
    t,
    apps: scopedBootstrap.data?.apps ?? [],
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
        navItems: scopedBootstrap.data?.nav ?? null,
      }),
    [activeAppId, activeNavItemId, scopedBootstrap.data?.nav],
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
    if (activeNavItemId && !scopedBootstrap.data && !scopedBootstrap.error) {
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
      metadata: {},
      dedupe_minutes: 30,
    }).catch(() => undefined);
  }, [
    activeAppId,
    activeNavItemId,
    auth.token,
    currentUserId,
    scopedBootstrap.data,
    scopedBootstrap.error,
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
      >
        <AppBootstrapProvider
          value={{
            ...scopedBootstrap,
            aiToolAppIds: aiToolAppIds,
          }}
        >
          <div className="flex h-screen flex-col overflow-hidden bg-app-surface-sidebar text-app-ink transition-colors lg:flex-row">
            <AppBar
              activeAppId={activeDisplayAppId}
              appBarFixedAppIds={appBarFixedAppIds}
              appBarItems={appBarItems}
              appBarPinnedByDefaultAppIds={appBarPinnedByDefaultAppIds}
              canOpenMobileAppMenu={canOpenMobileAppMenu}
              currentUser={currentUser}
              currentPathname={locationPathname}
              currentCompanyLabel={null}
              launcherGlobalPaths={launcherGlobalPaths}
              notificationIssueAppId={notificationIssueAppId}
              onDesktopMenuOpenChange={setDesktopAppBarMenuOpen}
              onDesktopRailMouseEnter={openSubSidebarPreview}
              onDesktopRailMouseLeave={scheduleSubSidebarPreviewClose}
              onOpenHelp={() => setHelpOpen(true)}
              onOpenMobileAppMenu={() => setMobileAppMenuOpen(true)}
              onOpenMobileNavigation={() => setMobileNavOpen(true)}
              resolveAppDestination={resolveAppDestination}
              apps={shellAppsBootstrap.apps}
              appBarCategories={shellAppsBootstrap.appBarCategories}
              canOpenSearch={Boolean(
                scopedBootstrapData?.keyword_search?.entity_types?.length,
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
                        enabledShellAppIds={enabledShellAppIds ?? []}
                        getAppModuleManifest={getAppModuleManifest}
                        getAppSidebarConfig={getAppSidebarConfig}
                        hasAdminSectionAccess={hasAdminSectionAccess}
                        launcherGlobalPaths={launcherGlobalPaths}
                        navItems={navItems}
                        onPinnedChange={handleSubSidebarPinnedChange}
                        overlay={!subSidebarPinned}
                        pinned={subSidebarPinned}
                        variant="desktop"
                        apps={scopedBootstrap.data?.apps ?? []}
                        appNavItems={scopedBootstrap.data?.nav ?? []}
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
                    {AppRouteElements({
                      bootstrapAppIds: enabledShellAppIds,
                      bootstrapError: appsBootstrap.error,
                      bootstrapLoading: appsBootstrap.loading,
                      appRoutes,
                    })}
                    {StaticRouteElements({
                      adminLandingRoute,
                      adminRedirectRoutes,
                      adminSectionRoutes,
                      appGlobalRoutes,
                      bootstrapError: appsBootstrap.error,
                      bootstrapLoading: appsBootstrap.loading,
                      enabledAppIds: appsBootstrap.data
                        ? appsBootstrap.data.apps
                            .filter((app) => app.enabled)
                            .map((app) => app.app_id)
                        : null,
                      featureGuideToolIds,
                      getDefaultAdminPath,
                      hasAdminSectionAccess,
                      helpRoutes,
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
              apps={shellAppsBootstrap.apps}
            />

            {canOpenMobileAppMenu ? (
              <MobileAppMenuDrawer
                activeAppId={activeAppId}
                activeDisplayAppId={activeDisplayAppId}
                activeNavItemId={activeNavItemId}
                appBarItems={appBarItems}
                enabledShellAppIds={enabledShellAppIds ?? []}
                getAppModuleManifest={getAppModuleManifest}
                getAppSidebarConfig={getAppSidebarConfig}
                hasAdminSectionAccess={hasAdminSectionAccess}
                launcherGlobalPaths={launcherGlobalPaths}
                navItems={navItems}
                onOpenChange={setMobileAppMenuOpen}
                open={mobileAppMenuOpen}
                apps={scopedBootstrap.data?.apps ?? []}
                appNavItems={scopedBootstrap.data?.nav ?? []}
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
            <BackgroundWorkProvider sources={enabledBackgroundWorkSources} />
          </div>
        </AppBootstrapProvider>
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
  appRoutes,
  appScope,
  aiToolAppIds = [],
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
                  appRoutes={appRoutes}
                  appScope={appScope}
                  aiToolAppIds={aiToolAppIds}
                />
              </ShellProviderStack>
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
