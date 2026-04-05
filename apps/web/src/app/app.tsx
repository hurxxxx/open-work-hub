import type { AuthUser } from './auth-api';
import {
  AppShell,
  Button,
  EmptyState,
  Panel,
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
type PortalRouteId =
  | 'documents'
  | 'plm'
  | 'drafts'
  | 'wiki-pms'
  | 'citations'
  | 'jobs'
  | 'audit-logs'
  | 'latest-specs'
  | 'export-queue'
  | 'open-issues';

interface PortalRoute {
  id: PortalRouteId;
  path: string;
  label: string;
  breadcrumb: string;
  title: string;
  description: string;
}

const PORTAL_ROUTES: PortalRoute[] = [
  {
    id: 'documents',
    path: '/documents',
    label: 'Documents',
    breadcrumb: 'Workspace / Documents / Grounded search',
    title: '아이두 AI 업무 포털',
    description:
      '두원공조 업무 문서와 지식 자산에서 근거를 찾고, 필요한 항목은 초안 작성 흐름으로 바로 넘기는 검색 중심 작업면입니다.',
  },
  {
    id: 'plm',
    path: '/plm',
    label: 'PLM',
    breadcrumb: 'Workspace / PLM / Approved queries',
    title: 'PLM 조회 작업면',
    description:
      '승인된 PLM 조회 템플릿과 결과 미리보기를 검토하고, 이후 읽기 전용 조회 흐름으로 확장할 수 있는 화면입니다.',
  },
  {
    id: 'drafts',
    path: '/drafts',
    label: 'Drafts',
    breadcrumb: 'Workspace / Drafts / Citation queues',
    title: '초안 작업면',
    description:
      '근거 블록이 준비된 초안 큐와 템플릿 상태를 검토하고, 다음 단계의 draft-generation 흐름으로 이어집니다.',
  },
  {
    id: 'wiki-pms',
    path: '/wiki-pms',
    label: 'Wiki / PMS',
    breadcrumb: 'Workspace / Wiki / PMS / Preview',
    title: 'Wiki / PMS 작업면',
    description:
      '위키, 작업, 릴리즈 노트에 연결될 구조화 프리뷰 화면입니다.',
  },
  {
    id: 'citations',
    path: '/citations',
    label: 'Citations',
    breadcrumb: 'Workspace / Citations / Bundles',
    title: 'Citation 번들',
    description:
      '문서 근거를 묶어서 초안 생성이나 검토 흐름으로 넘기기 위한 보조 작업 영역입니다.',
  },
  {
    id: 'jobs',
    path: '/jobs',
    label: 'Jobs',
    breadcrumb: 'Workspace / Execution / Jobs',
    title: '실행 작업 큐',
    description:
      '배치 작업과 비동기 처리 큐의 상태를 확인하는 운영 화면입니다.',
  },
  {
    id: 'audit-logs',
    path: '/audit-logs',
    label: 'Audit logs',
    breadcrumb: 'Workspace / Execution / Audit logs',
    title: '감사 로그',
    description:
      '권한, 근거, 실행 이력을 확인하기 위한 감사 로그 작업면입니다.',
  },
  {
    id: 'latest-specs',
    path: '/latest-specs',
    label: 'Latest specs',
    breadcrumb: 'Workspace / Pinned / Latest specs',
    title: '최신 규격 문서',
    description:
      '자주 참조하는 최신 규격 문서를 빠르게 여는 고정 진입점입니다.',
  },
  {
    id: 'export-queue',
    path: '/export-queue',
    label: 'Export queue',
    breadcrumb: 'Workspace / Pinned / Export queue',
    title: '내보내기 큐',
    description:
      '생성된 초안과 보고서 산출물의 내보내기 상태를 확인하는 화면입니다.',
  },
  {
    id: 'open-issues',
    path: '/open-issues',
    label: 'Open issues',
    breadcrumb: 'Workspace / Pinned / Open issues',
    title: '열린 이슈',
    description:
      '최근 작업 중 아직 닫히지 않은 이슈와 후속 조치 목록을 모아 보는 화면입니다.',
  },
];

const DEFAULT_PORTAL_PATH = '/documents';

interface PortalWorkspaceProps {
  user: AuthUser;
  token: string;
  onLogout: () => Promise<void>;
}

function normalizePortalPath(pathname: string): string {
  const normalized =
    pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;

  if (!normalized || normalized === '/') {
    return DEFAULT_PORTAL_PATH;
  }

  return PORTAL_ROUTES.find((route) => route.path === normalized)?.path ?? DEFAULT_PORTAL_PATH;
}

function PlaceholderPage({
  eyebrow,
  title,
  description,
  actionLabel,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actionLabel?: string;
}) {
  return (
    <Panel eyebrow={eyebrow} title={title} description={description}>
      <EmptyState
        title={`${title} 연결 준비 중`}
        description={description}
        action={actionLabel ? { label: actionLabel } : undefined}
      />
    </Panel>
  );
}

function renderWorkspaceContent(routeId: PortalRouteId, token: string) {
  switch (routeId) {
    case 'documents':
      return (
        <SplitPane
          main={<SearchWorkbench token={token} />}
          mobileAsideLabel="보조 작업 패널 보기"
          aside={
            <>
              <PlmPreview />
              <DraftPreview />
              <WikiPmsPreview />
            </>
          }
        />
      );
    case 'plm':
      return (
        <div className="grid gap-5">
          <PlmPreview />
          <PlaceholderPage
            actionLabel="읽기 전용 조회 확장 예정"
            description="승인된 조회 템플릿을 실제 PLM 검색 실행 흐름에 연결하는 다음 단계 작업면입니다."
            eyebrow="PLM"
            title="실행 쿼리 미리보기"
          />
        </div>
      );
    case 'drafts':
      return (
        <div className="grid gap-5">
          <DraftPreview />
          <PlaceholderPage
            actionLabel="초안 생성 흐름 준비 중"
            description="근거 묶음과 템플릿 필드를 실제 draft-generation 경로로 연결할 예정입니다."
            eyebrow="Drafts"
            title="초안 상세 편집"
          />
        </div>
      );
    case 'wiki-pms':
      return <WikiPmsPreview />;
    case 'citations':
      return (
        <PlaceholderPage
          actionLabel="Documents에서 근거 선택"
          description="문서 검색에서 선택한 citation을 묶어 초안 또는 검토 흐름으로 넘기는 번들 공간입니다."
          eyebrow="Citations"
          title="Citation bundle"
        />
      );
    case 'jobs':
      return (
        <PlaceholderPage
          description="비동기 배치와 후처리 작업 상태를 추적하는 화면입니다."
          eyebrow="Execution"
          title="작업 큐"
        />
      );
    case 'audit-logs':
      return (
        <PlaceholderPage
          description="권한, 근거, 라우팅, 생성 기록을 확인하는 감사 로그 화면입니다."
          eyebrow="Execution"
          title="Audit logs"
        />
      );
    case 'latest-specs':
      return (
        <PlaceholderPage
          actionLabel="Documents에서 최신 규격 열기"
          description="가장 최근에 사용한 규격 문서 모음을 고정 진입점으로 제공하는 화면입니다."
          eyebrow="Pinned"
          title="Latest specs"
        />
      );
    case 'export-queue':
      return (
        <PlaceholderPage
          description="초안과 리포트 내보내기 상태를 추적하는 큐 화면입니다."
          eyebrow="Pinned"
          title="Export queue"
        />
      );
    case 'open-issues':
      return (
        <PlaceholderPage
          description="현재 열려 있는 운영 이슈와 후속 조치 항목을 모아보는 화면입니다."
          eyebrow="Pinned"
          title="Open issues"
        />
      );
  }
}

function PortalWorkspace({ user, token, onLogout }: PortalWorkspaceProps) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState(() =>
    normalizePortalPath(window.location.pathname),
  );

  useEffect(() => {
    const syncedPath = normalizePortalPath(window.location.pathname);
    if (window.location.pathname !== syncedPath) {
      window.history.replaceState({}, '', syncedPath);
    }
    setCurrentPath(syncedPath);

    function handlePopState() {
      setCurrentPath(normalizePortalPath(window.location.pathname));
    }

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [currentPath]);

  const currentRoute =
    PORTAL_ROUTES.find((route) => route.path === currentPath) ?? PORTAL_ROUTES[0];

  function navigateTo(path: string) {
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
    setCurrentPath(path);
  }

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
            launcher={{
              label: '아이두 통합검색',
              hint: '⌘K',
              onSelect: () => navigateTo('/documents'),
            }}
            sections={[
              {
                id: 'knowledge',
                label: 'Knowledge',
                items: [
                  {
                    id: 'documents',
                    label: 'Documents',
                    active: currentRoute.id === 'documents',
                    onSelect: () => navigateTo('/documents'),
                  },
                  {
                    id: 'plm',
                    label: 'PLM',
                    active: currentRoute.id === 'plm',
                    onSelect: () => navigateTo('/plm'),
                  },
                  {
                    id: 'drafts',
                    label: 'Drafts',
                    active: currentRoute.id === 'drafts',
                    onSelect: () => navigateTo('/drafts'),
                  },
                  {
                    id: 'wiki-pms',
                    label: 'Wiki / PMS',
                    active: currentRoute.id === 'wiki-pms',
                    onSelect: () => navigateTo('/wiki-pms'),
                  },
                  {
                    id: 'citations',
                    label: 'Citations',
                    active: currentRoute.id === 'citations',
                    onSelect: () => navigateTo('/citations'),
                  },
                ],
              },
              {
                id: 'execution',
                label: 'Execution',
                items: [
                  {
                    id: 'jobs',
                    label: 'Jobs',
                    active: currentRoute.id === 'jobs',
                    onSelect: () => navigateTo('/jobs'),
                  },
                  {
                    id: 'audit-logs',
                    label: 'Audit logs',
                    active: currentRoute.id === 'audit-logs',
                    onSelect: () => navigateTo('/audit-logs'),
                  },
                ],
              },
              {
                id: 'pinned',
                label: 'Pinned',
                items: [
                  {
                    id: 'specs',
                    label: 'Latest specs',
                    active: currentRoute.id === 'latest-specs',
                    onSelect: () => navigateTo('/latest-specs'),
                  },
                  {
                    id: 'exports',
                    label: 'Export queue',
                    active: currentRoute.id === 'export-queue',
                    onSelect: () => navigateTo('/export-queue'),
                  },
                  {
                    id: 'issues',
                    label: 'Open issues',
                    active: currentRoute.id === 'open-issues',
                    onSelect: () => navigateTo('/open-issues'),
                  },
                ],
              },
            ]}
            footerBadges={['Engineering', 'RBAC preview']}
          />
        }
        header={
          <Topbar
            breadcrumb={currentRoute.breadcrumb}
            title={currentRoute.title}
            description={currentRoute.description}
            actions={
              <>
                <StatusBadge>{user.full_name}</StatusBadge>
                {currentRoute.id === 'documents' ? (
                  <>
                    <Button className="max-[980px]:hidden" variant="secondary">
                      Sync docs
                    </Button>
                    <Button className="max-[980px]:hidden" variant="secondary">
                      Saved views
                    </Button>
                    <Button className="max-[980px]:hidden" variant="primary">
                      New draft
                    </Button>
                  </>
                ) : null}
                <StatusBadge className="max-[980px]:hidden">{currentRoute.label}</StatusBadge>
                <Button variant="secondary" onClick={() => void onLogout()}>
                  로그아웃
                </Button>
              </>
            }
          />
        }
      >
        {renderWorkspaceContent(currentRoute.id, token)}
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

  return <PortalWorkspace onLogout={handleLogout} token={token ?? ''} user={currentUser} />;
}

export default App;
