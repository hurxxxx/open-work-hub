/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  BrowserRouter as Router,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
} from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import { ToastProvider, ToastViewport } from '@aidoo/ui';

import { AppBar } from './components/layout/AppBar';
import { SubSidebar } from './components/layout/SubSidebar';
import { AIView } from './components/views/AIView';
import { DocsView } from './components/views/DocsView';
import { WorkspaceHomeView } from './components/views/WorkspaceHomeView/WorkspaceHomeView';
import { MeetingView } from './components/views/MeetingView/MeetingView';
import { MeetingWorkspaceView } from './components/views/MeetingView/MeetingWorkspaceView';
import { PlannerView } from './components/views/PlannerView';
import { PMSView } from './components/views/PMSView/PMSView';
import { AssignedToMeView } from './components/views/PMSView/AssignedToMeView';
import { TodayOverdueView } from './components/views/PMSView/TodayOverdueView';
import { PersonalListView } from './components/views/PMSView/PersonalListView';
import { LearningView } from './components/views/LearningView';
import { LearningCourseView } from './components/views/LearningCourseView';
import { RagSearchView } from './components/views/RagSearchView';
import { ToolView } from './components/views/ToolView';
import { ComingSoonView } from './components/views/ComingSoonView';
import { NAV_ITEMS } from './constants';
import { AdminConsoleView } from './domains/admin/admin-console';
import { canUseWorkspaceSearchTool, isWorkspaceAppEnabled } from './domains/rag/rag-ui-access';
import {
  getDefaultAdminPath,
  hasAdminSectionAccess,
} from './domains/admin/admin-permissions';
import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from './domains/auth/auth-provider';
import {
  hasAdminConsoleAccess,
  hasWorkspaceMembership,
  type ThemePreference,
} from './domains/auth/auth-api';
import {
  buildWorkspaceAppPath,
  getWorkspaceAppIdFromPath,
  getWorkspaceBySlug,
  getWorkspaceSlugFromPath,
  getToolWorkspaceSlugFromSearch,
  persistLastWorkspaceAppId,
  persistLastWorkspaceSlug,
  resolveBootstrapWorkspaceSlug,
  resolveRootEntryPath,
  resolveShellWorkspaceSlug,
  resolveDefaultWorkspaceAppPath,
} from './domains/workspaces/workspace-utils';
import { useWorkspaceBootstrap } from './domains/workspaces/workspaces-api';
import {
  useWorkspaceBootstrapContext,
  WorkspaceBootstrapProvider,
} from './domains/workspaces/workspace-bootstrap-context';
import { WorkspaceSettingsView } from './domains/workspaces/WorkspaceSettingsView';
import {
  AccessDeniedView,
  NotFoundView,
  ProfilePage,
} from './domains/auth/settings-pages';
import { resolveShellState, type ShellAppId } from './app-shell';

function resolveThemePreference(themePreference: ThemePreference, systemDarkMode: boolean) {
  if (themePreference === 'system') {
    return systemDarkMode ? 'dark' : 'light';
  }

  return themePreference;
}

function WorkspaceGate({
  children,
  appId,
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
}: {
  children: ReactNode;
  appId: string;
  bootstrapAppIds: string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
}) {
  const auth = useAuth();
  const { workspaceSlug } = useParams();

  if (!hasWorkspaceMembership(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description="현재 계정은 이 workspace에서 해당 앱을 사용할 수 없습니다." />
    );
  }

  if (workspaceSlug) {
    if (bootstrapLoading || bootstrapAppIds === null) {
      return <div className="p-8 text-gray-500">워크스페이스 구성을 불러오는 중입니다.</div>;
    }
    if (bootstrapError) {
      return <AccessDeniedView description={bootstrapError} />;
    }
    if (!bootstrapAppIds.includes(appId)) {
      return (
        <AccessDeniedView description="현재 workspace에서는 이 앱이 활성화되어 있지 않습니다." />
      );
    }
  }

  return <>{children}</>;
}

function AdminGate({
  section,
  children,
}: {
  section: 'general' | 'people' | 'workspaces' | 'security' | 'audit';
  children: ReactNode;
}) {
  const auth = useAuth();
  if (!hasAdminConsoleAccess(auth.user) || !hasAdminSectionAccess(auth.user?.system_roles ?? [], section)) {
    return <AccessDeniedView description="현재 계정에는 이 관리자 섹션을 볼 권한이 없습니다." />;
  }

  return <>{children}</>;
}

function AdminLandingRedirect() {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  return <Navigate replace to={getDefaultAdminPath(auth.user.system_roles)} />;
}

function HomeRootRedirect() {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  const targetPath = resolveRootEntryPath(auth.user);
  if (!targetPath) {
    return (
      <AccessDeniedView description="접근 가능한 워크스페이스가 없습니다. 관리자에게 문의해주세요." />
    );
  }

  return <Navigate replace to={targetPath} />;
}

function WorkspaceRootRedirect() {
  const auth = useAuth();
  const { workspaceSlug } = useParams();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  if (!workspaceSlug || !getWorkspaceBySlug(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description="현재 계정은 이 workspace에 접근할 수 없습니다." />
    );
  }

  return <Navigate replace to={buildWorkspaceAppPath(workspaceSlug, 'home')} />;
}

const ToolViewWrapper = () => {
  const auth = useAuth();
  const location = useLocation();
  const { toolId } = useParams();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const pmsRoot = resolveDefaultWorkspaceAppPath(auth.user, 'pms');
  const toolWorkspaceSlug = workspaceBootstrap.data?.workspace.slug
    ?? getToolWorkspaceSlugFromSearch(auth.user, location.pathname, location.search)
    ?? resolveShellWorkspaceSlug(auth.user, null);
  const enabledBootstrapApps = workspaceBootstrap.data?.apps ?? null;

  if (toolId === 'pms-space-team') {
    return <Navigate replace to={{ pathname: pmsRoot, search: location.search }} />;
  }

  if (toolId?.startsWith('pms-list-') || /^pms-space-.+/.test(toolId ?? '')) {
    if (!hasWorkspaceMembership(auth.user)) {
      return (
        <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
      );
    }
    return <PMSView />;
  }

  const item = NAV_ITEMS.find((entry) => entry.id === toolId);
  if (!item) {
    return <div className="p-8 text-gray-500">Tool not found</div>;
  }

  if (item.appId !== 'home' && !hasWorkspaceMembership(auth.user)) {
    return (
      <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
    );
  }

  if (item.appId === 'ai') {
    if (!hasWorkspaceMembership(auth.user, toolWorkspaceSlug)) {
      return (
        <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
      );
    }
    if (workspaceBootstrap.loading || enabledBootstrapApps === null) {
      return <div className="p-8 text-gray-500">워크스페이스 구성을 불러오는 중입니다.</div>;
    }
    if (workspaceBootstrap.error) {
      return <AccessDeniedView description={workspaceBootstrap.error} />;
    }
    if (!isWorkspaceAppEnabled(enabledBootstrapApps, 'ai')) {
      return (
        <AccessDeniedView description="현재 workspace에서는 AI 앱이 활성화되어 있지 않습니다." />
      );
    }
  }

  if (item.appId === 'pms') {
    return <PMSView />;
  }

  if (item.appId === 'docs') {
    return <DocsView />;
  }

  if (toolId === 'search') {
    if (!canUseWorkspaceSearchTool(enabledBootstrapApps)) {
      return (
        <AccessDeniedView description="현재 workspace에서는 통합검색을 사용할 수 없습니다." />
      );
    }
    return <RagSearchView />;
  }

  if (item.comingSoon) {
    return <ComingSoonView item={item} />;
  }

  return <ToolView item={item} />;
};

const AppContent = () => {
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
        <SubSidebar
          activeAppId={activeAppId}
          activeNavItemId={activeNavItemId}
          currentWorkspaceSlug={bootstrapWorkspaceSlug}
          workspaceApps={workspaceBootstrap.data?.apps ?? []}
          workspaceNavItems={workspaceBootstrap.data?.nav ?? []}
        />

        <div className="flex-1 flex flex-col overflow-hidden bg-app-bg transition-colors">
          <main className="flex-1 overflow-y-auto relative">
            <Routes>
            <Route path="/" element={<HomeRootRedirect />} />
            <Route path="/docs/shared/:shareToken" element={<DocsView />} />
            <Route path="/w/:workspaceSlug" element={<WorkspaceRootRedirect />} />
            <Route
              path="/w/:workspaceSlug/home"
              element={(
                <WorkspaceGate
                  appId="home"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <WorkspaceHomeView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/ai"
              element={(
                <WorkspaceGate
                  appId="ai"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <AIView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/pms"
              element={(
                <WorkspaceGate
                  appId="pms"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <PMSView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/pms/assigned"
              element={(
                <WorkspaceGate
                  appId="pms"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <AssignedToMeView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/pms/today"
              element={(
                <WorkspaceGate
                  appId="pms"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <TodayOverdueView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/pms/personal"
              element={(
                <WorkspaceGate
                  appId="pms"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <PersonalListView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/docs"
              element={(
                <WorkspaceGate
                  appId="docs"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <DocsView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/docs/:docId"
              element={(
                <WorkspaceGate
                  appId="docs"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <DocsView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/planner"
              element={(
                <WorkspaceGate
                  appId="planner"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <PlannerView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/meeting"
              element={(
                <WorkspaceGate
                  appId="meeting"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <MeetingView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/meeting/:meetingId"
              element={(
                <WorkspaceGate
                  appId="meeting"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <MeetingWorkspaceView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/learning"
              element={(
                <WorkspaceGate
                  appId="learning"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <LearningView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/learning/:courseSlug"
              element={(
                <WorkspaceGate
                  appId="learning"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <LearningCourseView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/w/:workspaceSlug/learning/:courseSlug/:lessonSlug"
              element={(
                <WorkspaceGate
                  appId="learning"
                  bootstrapAppIds={enabledWorkspaceAppIds}
                  bootstrapError={workspaceBootstrap.error}
                  bootstrapLoading={workspaceBootstrap.loading}
                >
                  <LearningCourseView />
                </WorkspaceGate>
              )}
            />
            <Route path="/w/:workspaceSlug/settings" element={<WorkspaceSettingsView />} />
            <Route path="/tool/:toolId" element={<ToolViewWrapper />} />
            <Route path="/tool/:toolId/:docId" element={<ToolViewWrapper />} />
            <Route path="/admin" element={<AdminLandingRedirect />} />
            <Route path="/admin/users" element={<Navigate replace to="/admin/people" />} />
            <Route path="/admin/groups" element={<Navigate replace to="/admin/security" />} />
            <Route path="/admin/feature-access" element={<Navigate replace to="/admin/security" />} />
            <Route path="/admin/teams" element={<Navigate replace to="/admin/workspaces" />} />
            <Route
              path="/admin/general"
              element={(
                <AdminGate section="general">
                  <AdminConsoleView section="general" />
                </AdminGate>
              )}
            />
            <Route
              path="/admin/people"
              element={(
                <AdminGate section="people">
                  <AdminConsoleView section="people" />
                </AdminGate>
              )}
            />
            <Route
              path="/admin/workspaces"
              element={(
                <AdminGate section="workspaces">
                  <AdminConsoleView section="workspaces" />
                </AdminGate>
              )}
            />
            <Route
              path="/admin/security"
              element={(
                <AdminGate section="security">
                  <AdminConsoleView section="security" />
                </AdminGate>
              )}
            />
            <Route
              path="/admin/audit"
              element={(
                <AdminGate section="audit">
                  <AdminConsoleView section="audit" />
                </AdminGate>
              )}
            />
            <Route path="*" element={<NotFoundView />} />
            </Routes>
          </main>
        </div>
      </div>

      {/* Profile modal overlay — renders on top of current page, no route change */}
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
              ✕
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
};

export default function App() {
  return (
    <MantineProvider defaultColorScheme="auto">
      <ToastProvider>
        <Router>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginRoute />} />
              <Route
                path="*"
                element={(
                  <RequireAuth>
                    <AppContent />
                  </RequireAuth>
                )}
              />
            </Routes>
          </AuthProvider>
        </Router>
        <ToastViewport />
      </ToastProvider>
    </MantineProvider>
  );
}
