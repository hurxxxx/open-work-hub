import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Bell,
  Check,
  ChevronDown,
  Plus,
  Search,
  Settings as SettingsIcon,
} from 'lucide-react';
import { AnimatePresence } from 'motion/react';

import { APP_BAR_ITEMS } from '@/src/constants';
import {
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
} from '@/src/domains/admin/admin-permissions';
import {
  hasFeatureAccess,
  type AuthUser,
  workspaceRoleAllows,
} from '@/src/domains/auth/auth-api';
import {
  buildWorkspaceAppPath,
  getPreferredWorkspace,
  hasWorkspaceApp,
  persistLastWorkspaceSlug,
  resolveWorkspaceSwitchPath,
  type WorkspaceAppId,
} from '@/src/domains/workspaces/workspace-utils';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { getUnreadNotificationCount } from '@/src/domains/pms/pms-api';
import { cn } from '@/src/lib/utils';
import { NotificationPanel } from './NotificationPanel';

function getInitials(label: string, fallback: string): string {
  const initials = label
    .trim()
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return initials || fallback;
}

export function AppBar({
  activeAppId,
  currentPathname,
  currentUser,
  onShellWorkspaceChange,
  shellWorkspaceSlug,
  onOpenAccount,
}: {
  activeAppId: string;
  currentPathname: string;
  currentUser: AuthUser;
  onShellWorkspaceChange: (workspaceSlug: string | null) => void;
  shellWorkspaceSlug: string | null;
  onOpenAccount: () => void;
}) {
  const { hasPermission, token } = useAuth();
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [workspaceSwitcherOpen, setWorkspaceSwitcherOpen] = useState(false);
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const workspaceSwitcherRef = useRef<HTMLDivElement>(null);
  const currentWorkspace = currentUser.workspaces.find((workspace) => workspace.slug === shellWorkspaceSlug) ?? null;
  const canCreateWorkspace = hasPermission('workspace.write');
  const canManageCurrentWorkspace = workspaceRoleAllows(currentWorkspace?.role, 'admin');
  const normalizedWorkspaceQuery = workspaceQuery.trim().toLowerCase();
  const matchingWorkspaces = currentUser.workspaces.filter((workspace) => {
    if (!normalizedWorkspaceQuery) {
      return true;
    }

    const haystack = `${workspace.name} ${workspace.slug}`.toLowerCase();
    return haystack.includes(normalizedWorkspaceQuery);
  });
  const pinnedWorkspace = currentWorkspace && matchingWorkspaces.some((workspace) => workspace.id === currentWorkspace.id)
    ? currentWorkspace
    : null;
  const otherWorkspaces = matchingWorkspaces
    .filter((workspace) => workspace.id !== currentWorkspace?.id)
    .sort((left, right) => left.name.localeCompare(right.name, 'ko'));

  useEffect(() => {
    if (!token) {
      setUnreadCount(0);
      return;
    }

    let active = true;

    const syncUnreadCount = async () => {
      try {
        const res = await getUnreadNotificationCount(token);
        if (active) {
          setUnreadCount(res.count);
        }
      } catch {
        return;
      }
    };

    void syncUnreadCount();
    const interval = window.setInterval(() => {
      void syncUnreadCount();
    }, 30000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [token]);

  useEffect(() => {
    if (!workspaceSwitcherOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (workspaceSwitcherRef.current && !workspaceSwitcherRef.current.contains(event.target as Node)) {
        setWorkspaceSwitcherOpen(false);
      }
    }

    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, [workspaceSwitcherOpen]);

  useEffect(() => {
    setWorkspaceSwitcherOpen(false);
    setWorkspaceQuery('');
  }, [currentPathname, shellWorkspaceSlug]);

  const handleCountChange = useCallback((delta: number) => {
    setUnreadCount(prev => Math.max(0, prev + delta));
  }, []);

  const handleNavigateToIssue = useCallback((issueId: string) => {
    const pmsPath = buildAppLink('pms', currentUser, shellWorkspaceSlug);
    if (pmsPath === '/') {
      return;
    }
    navigate(`${pmsPath}?issue=${encodeURIComponent(issueId)}`);
  }, [currentUser, navigate, shellWorkspaceSlug]);

  const handleWorkspaceSelect = useCallback((nextWorkspaceSlug: string) => {
    if (nextWorkspaceSlug === shellWorkspaceSlug) {
      setWorkspaceSwitcherOpen(false);
      return;
    }

    persistLastWorkspaceSlug(nextWorkspaceSlug);
    onShellWorkspaceChange(nextWorkspaceSlug);
    navigate(resolveWorkspaceSwitchPath(currentUser, currentPathname, nextWorkspaceSlug));
  }, [currentPathname, currentUser, navigate, onShellWorkspaceChange, shellWorkspaceSlug]);

  const visibleItems = APP_BAR_ITEMS.filter((item) => {
    if (item.id === 'home') {
      return true;
    }

    if (item.id === 'settings') {
      return (
        hasFeatureAccess(currentUser, 'nav.admin')
        || hasAnyAdminReadPermission(currentUser.system_roles)
      );
    }

    return shellWorkspaceSlug
      ? hasWorkspaceApp(currentUser, shellWorkspaceSlug, item.id as WorkspaceAppId)
      : false;
  });

  return (
    <div className="w-16 h-full bg-app-bg-strong border-r border-app-border flex flex-col items-center py-4 gap-4 z-20">
      <div ref={workspaceSwitcherRef} className="relative mb-2">
        <button
          aria-expanded={workspaceSwitcherOpen}
          aria-haspopup="dialog"
          aria-label="워크스페이스 전환"
          className="group flex h-11 w-11 flex-col items-center justify-center rounded-xl border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-surface-hover"
          onClick={() => setWorkspaceSwitcherOpen((open) => !open)}
          title={currentWorkspace ? `${currentWorkspace.name} workspace` : '워크스페이스 선택'}
          type="button"
        >
          <span className="app-text-body-sm font-semibold leading-none">
            {getInitials(currentWorkspace?.name ?? 'Workspace', 'WS')}
          </span>
          <ChevronDown
            size={12}
            className={cn(
              'mt-1 text-gray-500 transition-transform',
              workspaceSwitcherOpen && 'rotate-180',
            )}
          />
        </button>

        {workspaceSwitcherOpen ? (
          <div
            className="absolute left-full top-0 ml-3 w-80 rounded-2xl border border-app-border bg-app-surface p-3 shadow-2xl"
            role="dialog"
          >
            <div className="px-1 pb-2">
              <div className="app-text-overline text-gray-500">Workspaces</div>
            </div>

            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                className="app-text-body-sm w-full rounded-xl border border-app-border bg-app-bg py-2 pl-9 pr-3 text-app-ink outline-none transition-colors focus:border-app-accent"
                onChange={(event) => setWorkspaceQuery(event.currentTarget.value)}
                placeholder="워크스페이스 검색"
                type="text"
                value={workspaceQuery}
              />
            </div>

            <div className="mt-3 max-h-80 overflow-y-auto">
              {pinnedWorkspace ? (
                <WorkspaceRow
                  isCurrent
                  onClick={() => handleWorkspaceSelect(pinnedWorkspace.slug)}
                  workspace={pinnedWorkspace}
                />
              ) : null}

              {pinnedWorkspace && otherWorkspaces.length > 0 ? (
                <div className="my-2 border-t border-app-border" />
              ) : null}

              {otherWorkspaces.map((workspace) => (
                <WorkspaceRow
                  key={workspace.id}
                  onClick={() => handleWorkspaceSelect(workspace.slug)}
                  workspace={workspace}
                />
              ))}

              {!pinnedWorkspace && otherWorkspaces.length === 0 ? (
                <div className="rounded-xl border border-dashed border-app-border px-3 py-5 text-center">
                  <div className="app-text-body-sm text-app-ink">검색 결과가 없습니다.</div>
                  <div className="app-text-caption mt-1 text-gray-500">이름 또는 slug 로 다시 검색하세요.</div>
                </div>
              ) : null}
            </div>

            {canCreateWorkspace || canManageCurrentWorkspace ? (
              <div className="mt-3 border-t border-app-border pt-2">
                {canCreateWorkspace ? (
                  <button
                    className="app-text-body-sm flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                    onClick={() => navigate('/admin/workspaces')}
                    type="button"
                  >
                    <Plus size={14} className="text-gray-500" />
                    <span>새 워크스페이스</span>
                  </button>
                ) : null}

                {canManageCurrentWorkspace && currentWorkspace ? (
                  <button
                    className="app-text-body-sm flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                    onClick={() => navigate(`/w/${encodeURIComponent(currentWorkspace.slug)}/settings`)}
                    type="button"
                  >
                    <SettingsIcon size={14} className="text-gray-500" />
                    <span>워크스페이스 설정</span>
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {visibleItems.map((item) => (
        <Link
          key={item.id}
          to={item.id === 'settings'
            ? getDefaultAdminPath(currentUser.system_roles)
            : buildAppLink(item.id as WorkspaceAppId, currentUser, shellWorkspaceSlug)}
          className={cn(
            'p-3 rounded-xl transition-all group relative',
            activeAppId === item.id
              ? 'bg-app-surface-sidebar text-app-accent shadow-inner'
              : 'text-gray-500 hover:text-gray-300 hover:bg-app-surface-hover',
          )}
        >
          <item.icon size={22} />
          <div className="app-text-micro absolute left-full ml-2 rounded bg-black px-2 py-1 text-white opacity-0 pointer-events-none whitespace-nowrap z-50 group-hover:opacity-100">
            {item.title}
          </div>
          {activeAppId === item.id ? (
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-app-accent rounded-r-full" />
          ) : null}
        </Link>
      ))}

      <div className="mt-auto flex flex-col items-center gap-3 relative">
        <button
          aria-label="알림"
          className="relative p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-app-surface-hover transition-all"
          onClick={() => setNotifOpen(prev => !prev)}
          type="button"
        >
          <Bell size={20} />
          {unreadCount > 0 && (
            <span className="app-text-micro absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 font-bold text-white">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        <AnimatePresence>
          {notifOpen && (
            <NotificationPanel
              onClose={() => setNotifOpen(false)}
              onNavigateToIssue={handleNavigateToIssue}
              onCountChange={handleCountChange}
            />
          )}
        </AnimatePresence>

        <button
          aria-label="마이페이지"
          className="app-text-body-sm flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-gradient-to-br from-app-accent to-purple-500 font-bold text-white shadow-md shadow-app-accent/20 outline-none ring-2 ring-transparent transition-all hover:ring-app-accent/40"
          onClick={onOpenAccount}
          title={`${currentUser.display_name || currentUser.full_name} · 마이페이지`}
          type="button"
        >
          {getInitials(currentUser.display_name || currentUser.full_name, 'ID')}
        </button>
      </div>
    </div>
  );
}

function WorkspaceRow({
  isCurrent = false,
  onClick,
  workspace,
}: {
  isCurrent?: boolean;
  onClick: () => void;
  workspace: AuthUser['workspaces'][number];
}) {
  return (
    <button
      className={cn(
        'flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left transition-colors hover:bg-app-surface-hover',
        isCurrent && 'bg-app-bg',
      )}
      onClick={onClick}
      type="button"
    >
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-bg text-app-ink">
        <span className="app-text-body-sm font-semibold">{getInitials(workspace.name, 'WS')}</span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="app-text-body-sm truncate text-app-ink">{workspace.name}</span>
          {isCurrent ? <Check size={14} className="shrink-0 text-app-accent" /> : null}
        </div>
        <div className="app-text-caption mt-0.5 truncate text-gray-500">
          {workspace.slug} · {workspace.enabled_apps.length}앱
        </div>
      </div>
    </button>
  );
}

function buildAppLink(
  appId: WorkspaceAppId,
  currentUser: AuthUser,
  shellWorkspaceSlug: string | null,
): string {
  const selectedWorkspace = (
    shellWorkspaceSlug
      ? currentUser.workspaces.find(
        (workspace) => workspace.slug === shellWorkspaceSlug && workspace.enabled_apps.includes(appId),
      ) ?? null
      : null
  ) ?? getPreferredWorkspace(currentUser, appId);

  return selectedWorkspace ? buildWorkspaceAppPath(selectedWorkspace.slug, appId) : '/';
}
