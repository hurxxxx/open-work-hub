import type { AuthUser } from './auth-api';
import {
  AppShell,
  Button,
  SidebarNav,
  SplitPane,
  StatusBadge,
  ToastProvider,
  ToastViewport,
  Topbar,
} from '@aidoo/ui';
import { useEffect, useState } from 'react';

import {
  AUTH_TOKEN_STORAGE_KEY,
  getBootstrapStatus,
  login,
  logout,
  me,
  setupFirstUser,
} from './auth-api';
import { AuthScreen } from './auth-screen';

import { SearchWorkbench } from '../domains/documents/search-workbench';
import { DraftPreview } from '../domains/drafts/draft-preview';
import { PlmPreview } from '../domains/plm/plm-preview';
import { WikiPmsPreview } from '../domains/wiki-pms/wiki-pms-preview';

type AuthPhase = 'loading' | 'login' | 'setup' | 'authenticated';

interface PortalWorkspaceProps {
  user: AuthUser;
  onLogout: () => Promise<void>;
}

function PortalWorkspace({ user, onLogout }: PortalWorkspaceProps) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <ToastProvider>
      <AppShell
        mobileSidebar={{
          open: mobileSidebarOpen,
          onOpenChange: setMobileSidebarOpen,
          label: '업무 메뉴',
        }}
        sidebar={
          <SidebarNav
            brand={{ eyebrow: '두원공조', title: '아이두' }}
            launcher={{ label: '아이두 통합검색', hint: '⌘K' }}
            sections={[
              {
                id: 'knowledge',
                label: 'Knowledge',
                items: [
                  { id: 'documents', label: 'Documents', active: true },
                  { id: 'plm', label: 'PLM' },
                  { id: 'drafts', label: 'Drafts' },
                  { id: 'wiki-pms', label: 'Wiki / PMS' },
                  { id: 'citations', label: 'Citations' },
                ],
              },
              {
                id: 'execution',
                label: 'Execution',
                items: [
                  { id: 'jobs', label: 'Jobs' },
                  { id: 'audit-logs', label: 'Audit logs' },
                ],
              },
              {
                id: 'pinned',
                label: 'Pinned',
                items: [
                  { id: 'specs', label: 'Latest specs' },
                  { id: 'exports', label: 'Export queue' },
                  { id: 'issues', label: 'Open issues' },
                ],
              },
            ]}
            footerBadges={['Engineering', 'RBAC preview']}
          />
        }
        header={
          <Topbar
            breadcrumb="Workspace / Documents / Grounded search"
            title="아이두 AI 업무 포털"
            description="두원공조 업무 문서와 지식 자산에서 근거를 찾고, 필요한 항목은 초안 작성 흐름으로 바로 넘기는 검색 중심 작업면입니다."
            actions={
              <>
                <StatusBadge>{user.full_name}</StatusBadge>
                <Button className="max-[980px]:hidden" variant="secondary">
                  Sync docs
                </Button>
                <Button className="max-[980px]:hidden" variant="secondary">
                  Saved views
                </Button>
                <Button className="max-[980px]:hidden" variant="primary">
                  New draft
                </Button>
                <StatusBadge className="max-[980px]:hidden">아이두 포털</StatusBadge>
                <Button variant="secondary" onClick={() => void onLogout()}>
                  로그아웃
                </Button>
              </>
            }
          />
        }
      >
        <SplitPane
          main={<SearchWorkbench />}
          mobileAsideLabel="보조 작업 패널 보기"
          aside={
            <>
              <PlmPreview />
              <DraftPreview />
              <WikiPmsPreview />
            </>
          }
        />
      </AppShell>
      <ToastViewport />
    </ToastProvider>
  );
}

export function App() {
  const [phase, setPhase] = useState<AuthPhase>('loading');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      try {
        const status = await getBootstrapStatus();
        if (!active) {
          return;
        }

        if (status.requires_setup) {
          localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
          setToken(null);
          setCurrentUser(null);
          setPhase('setup');
          return;
        }

        const savedToken = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
        if (!savedToken) {
          setPhase('login');
          return;
        }

        try {
          const user = await me(savedToken);
          if (!active) {
            return;
          }
          setToken(savedToken);
          setCurrentUser(user);
          setPhase('authenticated');
        } catch {
          localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
          setToken(null);
          setCurrentUser(null);
          setPhase('login');
        }
      } catch (caughtError) {
        if (!active) {
          return;
        }
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : '인증 서버에 연결하지 못했습니다.',
        );
        setPhase('login');
      }
    }

    void bootstrap();

    return () => {
      active = false;
    };
  }, []);

  async function handleSetup(payload: {
    fullName: string;
    email: string;
    password: string;
  }) {
    setBusy(true);
    setError(null);
    try {
      const session = await setupFirstUser(payload);
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, session.token);
      setToken(session.token);
      setCurrentUser(session.user);
      setPhase('authenticated');
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '계정 생성에 실패했습니다.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(payload: { email: string; password: string }) {
    setBusy(true);
    setError(null);
    try {
      const session = await login(payload);
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, session.token);
      setToken(session.token);
      setCurrentUser(session.user);
      setPhase('authenticated');
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '로그인에 실패했습니다.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    if (token) {
      try {
        await logout(token);
      } catch {
        // Best-effort revoke; local state still needs to clear.
      }
    }

    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    setToken(null);
    setCurrentUser(null);
    setError(null);
    setPhase('login');
  }

  if (phase !== 'authenticated' || currentUser === null) {
    return (
      <AuthScreen
        busy={busy}
        error={error}
        mode={phase === 'authenticated' ? 'loading' : phase}
        onLogin={handleLogin}
        onSetup={handleSetup}
      />
    );
  }

  return <PortalWorkspace onLogout={handleLogout} user={currentUser} />;
}

export default App;
