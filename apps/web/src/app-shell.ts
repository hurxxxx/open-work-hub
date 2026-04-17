import { NAV_ITEMS } from './constants';
import {
  hasAdminConsoleAccess,
  hasWorkspaceMembership,
  type AuthUser,
} from './domains/auth/auth-api';
import { getWorkspaceSlugFromPath } from './domains/workspaces/workspace-utils';

export type ShellAppId = 'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'meeting' | 'settings' | 'profile';

export type ShellState = {
  activeAppId: ShellAppId;
  activeNavItemId: string;
};

const HOME_SHELL_STATE: ShellState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

function canShowAppChrome(
  user: AuthUser | null | undefined,
  appId: 'ai' | 'pms' | 'docs' | 'planner' | 'meeting' | 'settings',
  workspaceSlug?: string | null,
): boolean {
  if (appId === 'settings') {
    return hasAdminConsoleAccess(user);
  }
  return hasWorkspaceMembership(user, workspaceSlug);
}

function resolvePmsToolState(
  toolId: string,
  user: AuthUser | null | undefined,
): ShellState {
  if (!canShowAppChrome(user, 'pms')) {
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
): ShellState {
  const workspaceSlug = getWorkspaceSlugFromPath(path);

  if (path === '/') {
    return HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/home(?:\/|$)/.test(path)) {
    return HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/ai(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'ai', workspaceSlug)
      ? { activeAppId: 'ai', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms\/assigned(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'pms', workspaceSlug)
      ? { activeAppId: 'pms', activeNavItemId: 'pms-tasks-assigned' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms\/today(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'pms', workspaceSlug)
      ? { activeAppId: 'pms', activeNavItemId: 'pms-tasks-today' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms\/personal(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'pms', workspaceSlug)
      ? { activeAppId: 'pms', activeNavItemId: 'pms-tasks-personal' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/pms(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'pms', workspaceSlug)
      ? { activeAppId: 'pms', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (path.startsWith('/docs/shared/')) {
    return canShowAppChrome(user, 'docs')
      ? { activeAppId: 'docs', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/docs(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'docs', workspaceSlug)
      ? { activeAppId: 'docs', activeNavItemId: 'docs-all' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/planner(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'planner', workspaceSlug)
      ? { activeAppId: 'planner', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/meeting(?:\/|$)/.test(path)) {
    return canShowAppChrome(user, 'meeting', workspaceSlug)
      ? { activeAppId: 'meeting', activeNavItemId: 'meeting-upcoming' }
      : HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/settings(?:\/|$)/.test(path)) {
    return HOME_SHELL_STATE;
  }

  if (path === '/admin' || path.startsWith('/admin/')) {
    if (!canShowAppChrome(user, 'settings')) {
      return HOME_SHELL_STATE;
    }

    if (path === '/admin' || path === '/admin/') {
      return {
        activeAppId: 'settings',
        activeNavItemId: 'settings-people',
      };
    }

    const slug = path.split('/')[2];
    return {
      activeAppId: 'settings',
      activeNavItemId: `settings-${slug === 'users' ? 'people' : slug === 'groups' || slug === 'feature-access' ? 'security' : slug}`,
    };
  }

  if (!path.startsWith('/tool/')) {
    return HOME_SHELL_STATE;
  }

  const toolId = path.split('/')[2] ?? '';
  if (
    toolId === 'pms-space-team'
    || toolId.startsWith('pms-list-')
    || /^pms-space-.+/.test(toolId)
  ) {
    return resolvePmsToolState(toolId, user);
  }

  const item = NAV_ITEMS.find((entry) => entry.id === toolId);
  if (!item) {
    return HOME_SHELL_STATE;
  }

  if (item.appId !== 'home' && !canShowAppChrome(user, item.appId)) {
    return HOME_SHELL_STATE;
  }

  return {
    activeAppId: item.appId,
    activeNavItemId: item.id,
  };
}
