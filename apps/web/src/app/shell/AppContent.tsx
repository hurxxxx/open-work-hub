import { useEffect, useMemo, useState } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { AppBar } from '@/src/components/layout/AppBar';
import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from '@/src/platform/auth/auth-provider';
import type { ThemePreference } from '@/src/platform/auth/auth-api';
import {
  NotFoundView,
  ProfilePage,
} from '@/src/platform/auth/settings-pages';
import {
  getWorkspaceAppIdFromPath,
  getWorkspaceSlugFromPath,
  persistLastWorkspaceAppId,
  persistLastWorkspaceSlug,
  resolveBootstrapWorkspaceSlug,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import { useWorkspaceBootstrap } from '@/src/platform/workspaces/workspaces-api';
import {
  WorkspaceBootstrapProvider,
} from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellState, type ShellAppId } from '@/src/app-shell';
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

function resolveThemePreference(themePreference: ThemePreference, systemDarkMode: boolean) {
  if (themePreference === 'system') {
    return systemDarkMode ? 'dark' : 'light';
  }

  return themePreference;
}

function isWhiteboardDetailPath(pathname: string): boolean {
  return /^\/w\/[^/]+\/whiteboard\/[^/]+\/?$/.test(pathname);
}

function AuthenticatedShell() {
  const auth = useAuth();
  const location = useLocation();
  const [activeAppId, setActiveAppId] = useState<ShellAppId>('home');
  const [activeNavItemId, setActiveNavItemId] = useState('');
  const [systemDarkMode, setSystemDarkMode] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
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

  if (!currentUser) {
    return <Navigate replace to="/login" />;
  }

  return (
    <WorkspaceBootstrapProvider value={workspaceBootstrap}>
      <div className="flex h-screen bg-app-surface-sidebar text-app-ink overflow-hidden transition-colors">
        <AppBar
          activeAppId={activeAppId}
          currentUser={currentUser}
          currentPathname={location.pathname}
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

        {profileOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div
              className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
              onClick={() => setProfileOpen(false)}
            />
            <div className="relative z-10 w-full max-w-4xl h-[85vh] bg-app-bg border border-app-border rounded-2xl shadow-2xl overflow-hidden">
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
