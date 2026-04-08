/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useState } from 'react';
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
import { HomeView } from './components/views/HomeView';
import { PlannerView } from './components/views/PlannerView';
import { PMSView } from './components/views/PMSView/PMSView';
import { ToolView } from './components/views/ToolView';
import { NAV_ITEMS } from './constants';
import { AdminConsoleView } from './domains/admin/admin-console';
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
import type { ThemePreference } from './domains/auth/auth-api';
import {
  AccessDeniedView,
  ProfilePage,
} from './domains/auth/settings-pages';

const FEATURE_BY_APP_ID: Partial<Record<'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'settings', string>> = {
  ai: 'nav.ai',
  docs: 'nav.docs',
  pms: 'nav.pms',
  planner: 'nav.planner',
  settings: 'nav.admin',
};

function resolveThemePreference(themePreference: ThemePreference, systemDarkMode: boolean) {
  if (themePreference === 'system') {
    return systemDarkMode ? 'dark' : 'light';
  }

  return themePreference;
}

function WorkspaceGate({
  featureCode,
  children,
}: {
  featureCode?: string;
  children: React.ReactNode;
}) {
  const auth = useAuth();

  if (featureCode && !auth.hasFeature(featureCode)) {
    return (
      <AccessDeniedView description="현재 계정에는 이 워크스페이스에 대한 노출 권한이 없습니다." />
    );
  }

  return <>{children}</>;
}

function AdminGate({
  section,
  children,
}: {
  section: 'general' | 'people' | 'teams' | 'workspaces' | 'security' | 'audit';
  children: React.ReactNode;
}) {
  const auth = useAuth();
  if (!hasAdminSectionAccess(auth.user?.permissions ?? [], section)) {
    return <AccessDeniedView description="현재 계정에는 이 관리자 섹션을 볼 권한이 없습니다." />;
  }

  return <>{children}</>;
}

function AdminLandingRedirect() {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  return <Navigate replace to={getDefaultAdminPath(auth.user.permissions)} />;
}

const ToolViewWrapper = () => {
  const auth = useAuth();
  const location = useLocation();
  const { toolId } = useParams();

  if (toolId?.startsWith('pms-project-')) {
    const listId = toolId.replace('pms-project-', '');
    return <Navigate replace to={{ pathname: `/tool/pms-list-${listId}`, search: location.search }} />;
  }

  if (toolId?.startsWith('pms-list-') || /^pms-space-.+/.test(toolId ?? '')) {
    const featureCode = FEATURE_BY_APP_ID['pms'];
    if (featureCode && !auth.hasFeature(featureCode)) {
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

  const featureCode = FEATURE_BY_APP_ID[item.appId];
  if (featureCode && !auth.hasFeature(featureCode)) {
    return (
      <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
    );
  }

  if (item.appId === 'pms') {
    return <PMSView />;
  }

  if (item.appId === 'docs') {
    return <DocsView />;
  }

  return <ToolView item={item} />;
};

const AppContent = () => {
  const auth = useAuth();
  const location = useLocation();
  const [activeAppId, setActiveAppId] = useState<'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'settings' | 'profile'>('home');
  const [activeNavItemId, setActiveNavItemId] = useState('');
  const [systemDarkMode, setSystemDarkMode] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const currentUser = auth.user;
  const themePreference = currentUser?.theme_preference ?? 'system';
  const resolvedTheme = resolveThemePreference(themePreference, systemDarkMode);

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
    const path = location.pathname;
    if (path === '/') {
      setActiveAppId('home');
      setActiveNavItemId('');
      return;
    }

    if (path === '/ai') {
      setActiveAppId('ai');
      setActiveNavItemId('');
      return;
    }

    if (path === '/pms') {
      setActiveAppId('pms');
      setActiveNavItemId('');
      return;
    }

    if (path === '/docs' || path.startsWith('/docs/')) {
      setActiveAppId('docs');
      setActiveNavItemId('');
      return;
    }

    if (path === '/planner') {
      setActiveAppId('planner');
      setActiveNavItemId('');
      return;
    }

    if (path === '/admin' || path.startsWith('/admin/')) {
      setActiveAppId('settings');
      if (path === '/admin' || path === '/admin/') {
        setActiveNavItemId('settings-people');
        return;
      }
      const slug = path.split('/')[2];
      const mappedId = `settings-${slug === 'users' ? 'people' : slug === 'groups' || slug === 'feature-access' ? 'security' : slug}`;      
      setActiveNavItemId(mappedId);
      return;
    }

    if (path.startsWith('/tool/')) {
      const toolId = path.split('/')[2];
      if (
        toolId?.startsWith('pms-project-')
        || toolId?.startsWith('pms-list-')
        || /^pms-space-.+/.test(toolId ?? '')
      ) {
        setActiveAppId('pms');
        setActiveNavItemId(toolId.startsWith('pms-project-') ? toolId.replace('pms-project-', 'pms-list-') : toolId);
        return;
      }
      const item = NAV_ITEMS.find((entry) => entry.id === toolId);
      if (item) {
        setActiveAppId(item.appId);
        setActiveNavItemId(item.id);
      }
    }
  }, [location]);

  if (!currentUser) {
    return <Navigate replace to="/login" />;
  }

  return (
    <div className="flex h-screen bg-clickup-sidebar text-clickup-text overflow-hidden transition-colors">
      <AppBar
        activeAppId={activeAppId}
        currentUser={currentUser}
        onOpenAccount={() => setProfileOpen(true)}
      />

      <div className="flex-1 flex overflow-hidden">
        <SubSidebar
          activeAppId={activeAppId}
          activeNavItemId={activeNavItemId}
        />

        <main className="flex-1 bg-clickup-bg overflow-y-auto relative transition-colors">
          <Routes>
            <Route path="/" element={<HomeView />} />
            <Route
              path="/ai"
              element={(
                <WorkspaceGate featureCode="nav.ai">
                  <AIView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/pms"
              element={(
                <WorkspaceGate featureCode="nav.pms">
                  <PMSView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/docs"
              element={(
                <WorkspaceGate featureCode="nav.docs">
                  <DocsView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/docs/:docId"
              element={(
                <WorkspaceGate featureCode="nav.docs">
                  <DocsView />
                </WorkspaceGate>
              )}
            />
            <Route
              path="/planner"
              element={(
                <WorkspaceGate featureCode="nav.planner">
                  <PlannerView />
                </WorkspaceGate>
              )}
            />
            <Route path="/tool/:toolId" element={<ToolViewWrapper />} />
            <Route path="/tool/:toolId/:docId" element={<ToolViewWrapper />} />
            <Route path="/admin" element={<AdminLandingRedirect />} />
            <Route path="/admin/users" element={<Navigate replace to="/admin/people" />} />
            <Route path="/admin/groups" element={<Navigate replace to="/admin/security" />} />
            <Route path="/admin/feature-access" element={<Navigate replace to="/admin/security" />} />
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
              path="/admin/teams"
              element={(
                <AdminGate section="teams">
                  <AdminConsoleView section="teams" />
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
          </Routes>
        </main>
      </div>

      {/* Profile modal overlay — renders on top of current page, no route change */}
      {profileOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
            onClick={() => setProfileOpen(false)}
          />
          <div className="relative z-10 w-full max-w-4xl h-[85vh] bg-clickup-bg border border-clickup-border rounded-2xl shadow-2xl overflow-hidden">
            <button
              onClick={() => setProfileOpen(false)}
              className="absolute top-4 right-4 z-20 w-8 h-8 flex items-center justify-center rounded-lg text-clickup-text/50 hover:text-clickup-text hover:bg-clickup-hover transition-colors"
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
