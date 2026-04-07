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
  useNavigate,
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
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from './domains/auth/auth-provider';
import type { ThemePreference } from './domains/auth/auth-api';
import {
  AccessDeniedView,
  AccountSettingsView,
  SecuritySettingsView,
} from './domains/auth/settings-pages';

const FEATURE_BY_APP_ID: Partial<Record<'home' | 'ai' | 'pms' | 'docs' | 'planner', string>> = {
  ai: 'nav.ai',
  docs: 'nav.docs',
  pms: 'nav.pms',
  planner: 'nav.planner',
};

const ADMIN_SECTION_PERMISSIONS = {
  users: 'user.read',
  groups: 'group.read',
  workspaces: 'workspace.read',
  teams: 'team.read',
  'feature-access': 'feature_policy.read',
  audit: 'audit.read',
} as const;

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
  section: keyof typeof ADMIN_SECTION_PERMISSIONS;
  children: React.ReactNode;
}) {
  const auth = useAuth();
  if (!auth.hasPermission('admin.access') && !auth.hasPermission(ADMIN_SECTION_PERMISSIONS[section])) {
    return <AccessDeniedView description="현재 계정에는 이 관리자 섹션을 볼 권한이 없습니다." />;
  }

  return <>{children}</>;
}

const ToolViewWrapper = () => {
  const auth = useAuth();
  const { toolId } = useParams();
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
  const navigate = useNavigate();
  const [activeAppId, setActiveAppId] = useState<'home' | 'ai' | 'pms' | 'docs' | 'planner'>('home');
  const [activeNavItemId, setActiveNavItemId] = useState('');
  const [systemDarkMode, setSystemDarkMode] = useState(false);

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  const themePreference = auth.user.theme_preference;
  const resolvedTheme = resolveThemePreference(themePreference, systemDarkMode);
  const showAdminConsole = [
    'admin.access',
    'user.read',
    'group.read',
    'workspace.read',
    'team.read',
    'feature_policy.read',
    'audit.read',
  ].some((permission) => auth.hasPermission(permission));

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

    if (path.startsWith('/tool/')) {
      const toolId = path.split('/')[2];
      const item = NAV_ITEMS.find((entry) => entry.id === toolId);
      if (item) {
        setActiveAppId(item.appId);
        setActiveNavItemId(item.id);
      }
    }
  }, [location]);

  return (
    <div className="flex h-screen bg-clickup-sidebar text-clickup-text overflow-hidden transition-colors">
      <AppBar
        activeAppId={activeAppId}
        currentThemePreference={themePreference}
        currentUser={auth.user}
        onLogout={auth.logout}
        onOpenAccount={() => navigate('/settings/account')}
        onOpenSecurity={() => navigate('/settings/security')}
        onOpenAdmin={showAdminConsole ? () => navigate('/admin/users') : undefined}
        onThemePreferenceChange={(value) => {
          void auth.updatePreferences({ theme_preference: value });
        }}
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
            <Route path="/settings/account" element={<AccountSettingsView />} />
            <Route path="/settings/security" element={<SecuritySettingsView />} />
            <Route
              path="/admin/users"
              element={(
                <AdminGate section="users">
                  <AdminConsoleView section="users" />
                </AdminGate>
              )}
            />
            <Route
              path="/admin/groups"
              element={(
                <AdminGate section="groups">
                  <AdminConsoleView section="groups" />
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
              path="/admin/teams"
              element={(
                <AdminGate section="teams">
                  <AdminConsoleView section="teams" />
                </AdminGate>
              )}
            />
            <Route
              path="/admin/feature-access"
              element={(
                <AdminGate section="feature-access">
                  <AdminConsoleView section="feature-access" />
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
