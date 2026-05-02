import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Check } from 'lucide-react';
import { DetailDrawer } from '@aidoo/ui';

import { AppBar } from '@/src/components/layout/AppBar';
import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from '@/src/platform/auth/auth-provider';
import {
  hasAdminConsoleAccess,
  type AuthUser,
  type ThemePreference,
} from '@/src/platform/auth/auth-api';
import {
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
} from '@/src/platform/admin/admin-permissions';
import {
  NotFoundView,
  ProfilePage,
} from '@/src/platform/auth/settings-pages';
import {
  buildWorkspaceAppPath,
  getPreferredWorkspace,
  getWorkspaceAppIdFromPath,
  getWorkspaceSlugFromPath,
  persistLastWorkspaceAppId,
  persistLastWorkspaceSlug,
  resolveBootstrapWorkspaceSlug,
  resolveShellWorkspaceSlug,
  resolveWorkspaceSwitchPath,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';
import {
  useWorkspaceBootstrap,
  type WorkspaceBootstrapApp,
  type WorkspaceBootstrapNavItem,
} from '@/src/platform/workspaces/workspaces-api';
import {
  WorkspaceBootstrapProvider,
} from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellState, type ShellAppId } from '@/src/app-shell';
import { cn } from '@/src/lib/utils';
import {
  AdminLandingRedirect,
  HomeRootRedirect,
  WorkspaceRootRedirect,
} from './redirects';
import {
  StaticRouteElements,
  WorkspaceRouteElements,
} from './workspace-route-registry';
import { ToolViewWrapper } from './tool-view-wrapper';
import { AppSubSidebar } from './AppSubSidebar';
import { APP_BAR_ITEMS } from './app-registry';

function resolveThemePreference(themePreference: ThemePreference, systemDarkMode: boolean) {
  if (themePreference === 'system') {
    return systemDarkMode ? 'dark' : 'light';
  }

  return themePreference;
}

function isWhiteboardDetailPath(pathname: string): boolean {
  return /^\/w\/[^/]+\/whiteboard\/[^/]+\/?$/.test(pathname);
}

function getInitials(label: string, fallback: string): string {
  const initials = label
    .trim()
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return initials || fallback;
}

function buildMobileAppLink(
  appId: WorkspaceAppId,
  currentUser: AuthUser,
  shellWorkspaceSlug: string | null,
): string {
  const selectedWorkspace = (
    shellWorkspaceSlug
      ? currentUser.workspaces.find((workspace) => workspace.slug === shellWorkspaceSlug) ?? null
      : null
  ) ?? getPreferredWorkspace(currentUser, appId);

  return selectedWorkspace ? buildWorkspaceAppPath(selectedWorkspace.slug, appId) : '/';
}

function MobileNavigationDrawer({
  activeAppId,
  activeNavItemId,
  currentPathname,
  currentUser,
  currentWorkspaceSlug,
  hideSubSidebar,
  onOpenChange,
  onShellWorkspaceChange,
  open,
  shellWorkspaceSlug,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: ShellAppId;
  activeNavItemId: string;
  currentPathname: string;
  currentUser: AuthUser;
  currentWorkspaceSlug: string | null;
  hideSubSidebar: boolean;
  onOpenChange: (open: boolean) => void;
  onShellWorkspaceChange: (workspaceSlug: string | null) => void;
  open: boolean;
  shellWorkspaceSlug: string | null;
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) {
  const navigate = useNavigate();
  const close = () => onOpenChange(false);
  const appBarItemById = useMemo(
    () => new Map(APP_BAR_ITEMS.map((item) => [item.id, item])),
    [],
  );
  const visibleItems = workspaceApps
    .filter((item) => item.enabled)
    .map((item) => {
      const localItem = appBarItemById.get(item.app_id as WorkspaceAppId);
      if (!localItem) {
        return null;
      }
      return {
        id: item.app_id as WorkspaceAppId,
        title: item.title,
        icon: localItem.icon,
      };
    })
    .filter((item): item is { id: WorkspaceAppId; title: string; icon: (typeof APP_BAR_ITEMS)[number]['icon'] } => Boolean(item));
  const currentWorkspace = currentUser.workspaces.find((workspace) => workspace.slug === shellWorkspaceSlug) ?? null;
  const otherWorkspaces = currentUser.workspaces
    .filter((workspace) => workspace.slug !== currentWorkspace?.slug)
    .sort((left, right) => left.name.localeCompare(right.name, 'ko'));
  const settingsItem = appBarItemById.get('settings');
  const canShowSettings = (
    hasAdminConsoleAccess(currentUser)
    || hasAnyAdminReadPermission(currentUser.system_roles)
  );

  const handleWorkspaceSelect = (nextWorkspaceSlug: string) => {
    if (nextWorkspaceSlug !== shellWorkspaceSlug) {
      persistLastWorkspaceSlug(nextWorkspaceSlug);
      onShellWorkspaceChange(nextWorkspaceSlug);
      navigate(resolveWorkspaceSwitchPath(currentUser, currentPathname, nextWorkspaceSlug));
    }
    close();
  };

  return (
    <DetailDrawer
      closeLabel="메뉴 닫기"
      contentClassName="border-app-border bg-app-bg"
      description="앱과 워크스페이스를 전환합니다."
      onOpenChange={onOpenChange}
      open={open}
      side="left"
      title="메뉴"
    >
      <div
        onClickCapture={(event) => {
          if (event.target instanceof Element && event.target.closest('a')) {
            close();
          }
        }}
      >
        <section className="border-b border-app-border px-3 py-4">
          <div className="app-text-overline px-2 text-app-ink/50">Workspace</div>
          <div className="mt-2 space-y-1">
            {currentWorkspace ? (
              <button
                className="flex w-full items-center gap-3 rounded-xl bg-app-surface px-3 py-2 text-left text-app-ink"
                onClick={() => handleWorkspaceSelect(currentWorkspace.slug)}
                type="button"
              >
                <span className="app-text-body-sm flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-bg font-semibold">
                  {getInitials(currentWorkspace.name, 'WS')}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="app-text-body-sm block truncate font-semibold">
                    {currentWorkspace.name}
                  </span>
                  <span className="app-text-caption block truncate text-app-ink/50">
                    {currentWorkspace.slug}
                  </span>
                </span>
                <Check size={15} className="text-app-accent" />
              </button>
            ) : null}

            {otherWorkspaces.map((workspace) => (
              <button
                key={workspace.id}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                onClick={() => handleWorkspaceSelect(workspace.slug)}
                type="button"
              >
                <span className="app-text-body-sm flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-bg font-semibold">
                  {getInitials(workspace.name, 'WS')}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="app-text-body-sm block truncate">
                    {workspace.name}
                  </span>
                  <span className="app-text-caption block truncate text-app-ink/50">
                    {workspace.slug}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="border-b border-app-border px-3 py-4">
          <div className="app-text-overline px-2 text-app-ink/50">Apps</div>
          <div className="mt-2 space-y-1">
            {visibleItems.map((item) => (
              <Link
                key={item.id}
                to={buildMobileAppLink(item.id, currentUser, shellWorkspaceSlug)}
                className={cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover',
                  activeAppId === item.id && 'bg-app-surface text-app-accent',
                )}
              >
                <item.icon size={18} className="shrink-0" />
                <span className="app-text-body-sm min-w-0 flex-1 truncate">
                  {item.title}
                </span>
                {activeAppId === item.id ? <Check size={15} className="shrink-0" /> : null}
              </Link>
            ))}

            {canShowSettings && settingsItem ? (
              <Link
                to={getDefaultAdminPath(currentUser.system_roles)}
                className={cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover',
                  activeAppId === 'settings' && 'bg-app-surface text-app-accent',
                )}
              >
                <settingsItem.icon size={18} className="shrink-0" />
                <span className="app-text-body-sm min-w-0 flex-1 truncate">
                  Settings
                </span>
                {activeAppId === 'settings' ? <Check size={15} className="shrink-0" /> : null}
              </Link>
            ) : null}
          </div>
        </section>

        {!hideSubSidebar && activeAppId !== 'home' && activeAppId !== 'profile' ? (
          <div className="h-[min(520px,60vh)] border-b border-app-border">
            <AppSubSidebar
              activeAppId={activeAppId}
              activeNavItemId={activeNavItemId}
              currentWorkspaceSlug={currentWorkspaceSlug}
              onNavigate={close}
              variant="mobile"
              workspaceApps={workspaceApps}
              workspaceNavItems={workspaceNavItems}
            />
          </div>
        ) : null}
      </div>
    </DetailDrawer>
  );
}

function AuthenticatedShell() {
  const auth = useAuth();
  const location = useLocation();
  const [activeAppId, setActiveAppId] = useState<ShellAppId>('home');
  const [activeNavItemId, setActiveNavItemId] = useState('');
  const [systemDarkMode, setSystemDarkMode] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const currentUser = auth.user;
  const routeWorkspaceSlug = getWorkspaceSlugFromPath(location.pathname);
  const routeWorkspaceAppId = getWorkspaceAppIdFromPath(location.pathname);
  const [shellWorkspaceSlug, setShellWorkspaceSlug] = useState<string | null>(null);
  const themePreference = currentUser?.theme_preference ?? 'system';
  const resolvedTheme = resolveThemePreference(themePreference, systemDarkMode);
  const bootstrapWorkspaceSlug = resolveBootstrapWorkspaceSlug(
    currentUser,
    location.pathname,
    location.search,
    shellWorkspaceSlug,
  );
  const workspaceBootstrap = useWorkspaceBootstrap(auth.token, bootstrapWorkspaceSlug);
  const hideSubSidebar = isWhiteboardDetailPath(location.pathname);
  const enabledWorkspaceAppIds = useMemo(
    () => workspaceBootstrap.data
      ? workspaceBootstrap.data.apps
          .filter((app) => app.enabled)
          .map((app) => app.app_id)
      : null,
    [workspaceBootstrap.data],
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => setSystemDarkMode(mediaQuery.matches);
    apply();
    mediaQuery.addEventListener('change', apply);

    return () => {
      mediaQuery.removeEventListener('change', apply);
    };
  }, []);

  useEffect(() => {
    if (resolvedTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [resolvedTheme]);

  useEffect(() => {
    const nextState = resolveShellState(
      location.pathname,
      currentUser,
      enabledWorkspaceAppIds ?? undefined,
    );
    setActiveAppId(nextState.activeAppId);
    setActiveNavItemId(nextState.activeNavItemId);
  }, [currentUser, enabledWorkspaceAppIds, location.pathname]);

  useEffect(() => {
    if (!currentUser) {
      setShellWorkspaceSlug(null);
      return;
    }

    if (routeWorkspaceSlug) {
      setShellWorkspaceSlug(resolveShellWorkspaceSlug(currentUser, routeWorkspaceSlug));
      return;
    }

    setShellWorkspaceSlug((current) => {
      if (currentUser.workspaces.some((workspace) => workspace.slug === current)) {
        return current;
      }

      return resolveShellWorkspaceSlug(currentUser, null);
    });
  }, [currentUser, routeWorkspaceSlug]);

  useEffect(() => {
    if (!routeWorkspaceSlug || !routeWorkspaceAppId) {
      return;
    }

    persistLastWorkspaceSlug(routeWorkspaceSlug);
    persistLastWorkspaceAppId(routeWorkspaceAppId);
  }, [routeWorkspaceAppId, routeWorkspaceSlug]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  if (!currentUser) {
    return <Navigate replace to="/login" />;
  }

  return (
    <WorkspaceBootstrapProvider value={workspaceBootstrap}>
      <div className="flex h-screen flex-col overflow-hidden bg-app-surface-sidebar text-app-ink transition-colors lg:flex-row">
        <AppBar
          activeAppId={activeAppId}
          currentUser={currentUser}
          currentPathname={location.pathname}
          onOpenMobileNavigation={() => setMobileNavOpen(true)}
          onShellWorkspaceChange={setShellWorkspaceSlug}
          shellWorkspaceSlug={shellWorkspaceSlug}
          workspaceApps={workspaceBootstrap.data?.apps ?? []}
          onOpenAccount={() => setProfileOpen(true)}
        />

        <div className="flex-1 flex overflow-hidden">
          {!hideSubSidebar ? (
            <AppSubSidebar
              activeAppId={activeAppId}
              activeNavItemId={activeNavItemId}
              currentWorkspaceSlug={bootstrapWorkspaceSlug}
              variant="desktop"
              workspaceApps={workspaceBootstrap.data?.apps ?? []}
              workspaceNavItems={workspaceBootstrap.data?.nav ?? []}
            />
          ) : null}

          <div className="flex-1 flex flex-col overflow-hidden bg-app-bg transition-colors">
            <main className={hideSubSidebar ? 'flex-1 overflow-hidden relative' : 'flex-1 overflow-y-auto relative'}>
              <Routes>
                <Route path="/" element={<HomeRootRedirect />} />
                <Route path="/w/:workspaceSlug" element={<WorkspaceRootRedirect />} />
                {WorkspaceRouteElements({
                  bootstrapAppIds: enabledWorkspaceAppIds,
                  bootstrapError: workspaceBootstrap.error,
                  bootstrapLoading: workspaceBootstrap.loading,
                })}
                {StaticRouteElements()}
                <Route path="/tool/:toolId" element={<ToolViewWrapper />} />
                <Route path="/tool/:toolId/:docId" element={<ToolViewWrapper />} />
                <Route path="/admin" element={<AdminLandingRedirect />} />
                <Route path="*" element={<NotFoundView />} />
              </Routes>
            </main>
          </div>
        </div>

        <MobileNavigationDrawer
          activeAppId={activeAppId}
          activeNavItemId={activeNavItemId}
          currentPathname={location.pathname}
          currentUser={currentUser}
          currentWorkspaceSlug={bootstrapWorkspaceSlug}
          hideSubSidebar={hideSubSidebar}
          onOpenChange={setMobileNavOpen}
          onShellWorkspaceChange={setShellWorkspaceSlug}
          open={mobileNavOpen}
          shellWorkspaceSlug={shellWorkspaceSlug}
          workspaceApps={workspaceBootstrap.data?.apps ?? []}
          workspaceNavItems={workspaceBootstrap.data?.nav ?? []}
        />

        {profileOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div
              className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
              onClick={() => setProfileOpen(false)}
            />
            <div className="relative z-10 h-[calc(100vh-1rem)] w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-app-border bg-app-bg shadow-2xl sm:h-[85vh] sm:max-w-4xl sm:rounded-2xl">
              <button
                onClick={() => setProfileOpen(false)}
                className="absolute top-4 right-4 z-20 w-8 h-8 flex items-center justify-center rounded-lg text-app-ink/50 hover:text-app-ink hover:bg-app-surface-hover transition-colors"
              >
                x
              </button>
              <div className="h-full overflow-y-auto">
                <ProfilePage initialTab="profile" />
              </div>
            </div>
          </div>
        )}
      </div>
    </WorkspaceBootstrapProvider>
  );
}

export function AppContent() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route
          path="*"
          element={(
            <RequireAuth>
              <AuthenticatedShell />
            </RequireAuth>
          )}
        />
      </Routes>
    </AuthProvider>
  );
}
