import { NAV_ITEMS } from './app/shell/app-registry';
import {
  hasAdminConsoleAccess,
  hasWorkspaceMembership,
  type AuthUser,
} from './platform/auth/auth-api';
import { getWorkspaceSlugFromPath } from './platform/workspaces/workspace-utils';

export type ShellAppId =
  | 'home'
  | 'ai'
  | 'pms'
  | 'docs'
  | 'whiteboard'
  | 'planner'
  | 'meeting'
  | 'recording'
  | 'learning'
  | 'settings'
  | 'profile';

export type ShellState = {
  activeAppId: ShellAppId;
  activeNavItemId: string;
};

const HOME_SHELL_STATE: ShellState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

function getPathname(path: string): string {
  const end = path.search(/[?#]/);
  return end >= 0 ? path.slice(0, end) || '/' : path;
}

function getSearchParams(path: string): URLSearchParams {
  const start = path.indexOf('?');
  if (start < 0) {
    return new URLSearchParams();
  }
  const end = path.indexOf('#', start);
  return new URLSearchParams(path.slice(start + 1, end >= 0 ? end : undefined));
}

function resolveRecordingNavItemId(path: string): string {
  const params = getSearchParams(path);
  const view = params.get('view');
  const category = params.get('category');

  if (view === 'archived') return 'recording-archived';
  if (view === 'failed') return 'recording-failed';
  if (view === 'processing') return 'recording-processing';
  if (category === 'meeting') return 'recording-meeting';
  if (category === 'task') return 'recording-task';
  if (category === 'unlinked') return 'recording-unlinked';
  if (view === 'mine' || view === 'needs_review') return 'recording-mine';
  return 'recording-quick';
}

function canShowAppChrome(
  user: AuthUser | null | undefined,
  appId: 'ai' | 'pms' | 'docs' | 'whiteboard' | 'planner' | 'meeting' | 'recording' | 'learning' | 'settings',
  workspaceSlug?: string | null,
  enabledWorkspaceAppIds?: readonly string[],
): boolean {
  if (appId === 'settings') {
    return hasAdminConsoleAccess(user);
  }
  if (enabledWorkspaceAppIds && !enabledWorkspaceAppIds.includes(appId)) {
    return false;
  }
  return hasWorkspaceMembership(user, workspaceSlug);
}

function resolvePmsToolState(
  toolId: string,
  user: AuthUser | null | undefined,
  enabledWorkspaceAppIds?: readonly string[],
): ShellState {
  if (!canShowAppChrome(user, 'pms', undefined, enabledWorkspaceAppIds)) {
    return HOME_SHELL_STATE;
  }

  if (toolId === 'pms-space-team') {
    return {
      activeAppId: 'pms',
      activeNavItemId: '',
    };
  }

  return {
    activeAppId: 'pms',
    activeNavItemId: toolId,
  };
}

export function resolveShellState(
  path: string,
  user: AuthUser | null | undefined,
  enabledWorkspaceAppIds?: readonly string[],
): ShellState {
  const pathname = getPathname(path);
  const workspaceSlug = getWorkspaceSlugFromPath(pathname);

  if (pathname === '/') {
    return HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/home(?:\/|$)/.test(pathname)) {
    return HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/ai(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'ai', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'ai', activeNavItemId: 'chatbot' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms\/assigned(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'pms', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'pms', activeNavItemId: 'pms-tasks-assigned' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms\/today(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'pms', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'pms', activeNavItemId: 'pms-tasks-today' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms\/personal(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'pms', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'pms', activeNavItemId: 'pms-tasks-personal' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'pms', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'pms', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (pathname.startsWith('/docs/shared/')) {
    return canShowAppChrome(user, 'docs')
      ? { activeAppId: 'docs', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (pathname.startsWith('/whiteboard/shared/')) {
    return canShowAppChrome(user, 'whiteboard')
      ? { activeAppId: 'whiteboard', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/docs(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'docs', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'docs', activeNavItemId: 'docs-all' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/whiteboard(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'whiteboard', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'whiteboard', activeNavItemId: 'whiteboard-all' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/planner(?:\/|$)/.test(pathname)) {
    const params = getSearchParams(path);
    return canShowAppChrome(user, 'planner', workspaceSlug, enabledWorkspaceAppIds)
      ? {
          activeAppId: 'planner',
          activeNavItemId:
            params.get('view') === 'timeline'
              ? 'planner-timeline'
              : 'planner-calendar',
        }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/meeting(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'meeting', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'meeting', activeNavItemId: 'meeting-upcoming' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/recording(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'recording', workspaceSlug, enabledWorkspaceAppIds)
      ? {
          activeAppId: 'recording',
          activeNavItemId: resolveRecordingNavItemId(path),
        }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/learning(?:\/|$)/.test(pathname)) {
    return canShowAppChrome(user, 'learning', workspaceSlug, enabledWorkspaceAppIds)
      ? { activeAppId: 'learning', activeNavItemId: 'learning-home' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/settings(?:\/|$)/.test(pathname)) {
    return HOME_SHELL_STATE;
  }

  if (pathname === '/admin' || pathname.startsWith('/admin/')) {
    if (!canShowAppChrome(user, 'settings')) {
      return HOME_SHELL_STATE;
    }

    if (pathname === '/admin' || pathname === '/admin/') {
      return {
        activeAppId: 'settings',
        activeNavItemId: 'settings-people',
      };
    }

    const slug = pathname.split('/')[2];
    return {
      activeAppId: 'settings',
      activeNavItemId: `settings-${slug === 'users' ? 'people' : slug === 'groups' || slug === 'feature-access' ? 'security' : slug}`,
    };
  }

  if (!pathname.startsWith('/tool/')) {
    return HOME_SHELL_STATE;
  }

  const toolId = pathname.split('/')[2] ?? '';
  if (
    toolId === 'pms-space-team'
    || toolId.startsWith('pms-list-')
    || /^pms-space-.+/.test(toolId)
  ) {
    return resolvePmsToolState(toolId, user, enabledWorkspaceAppIds);
  }

  const item = NAV_ITEMS.find((entry) => entry.id === toolId);
  if (!item) {
    return HOME_SHELL_STATE;
  }

  if (item.appId !== 'home' && !canShowAppChrome(user, item.appId, undefined, enabledWorkspaceAppIds)) {
    return HOME_SHELL_STATE;
  }

  return {
    activeAppId: item.appId,
    activeNavItemId: item.id,
  };
}
