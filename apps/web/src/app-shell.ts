import { NAV_ITEMS } from './constants';
import { hasFeatureAccess, type AuthUser } from './domains/auth/auth-api';

export type ShellAppId = 'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'settings' | 'profile';

export type ShellState = {
  activeAppId: ShellAppId;
  activeNavItemId: string;
};

export const FEATURE_BY_APP_ID: Partial<Record<'ai' | 'pms' | 'docs' | 'planner' | 'settings', string>> = {
  ai: 'nav.ai',
  docs: 'nav.docs',
  pms: 'nav.pms',
  planner: 'nav.planner',
  settings: 'nav.admin',
};

const HOME_SHELL_STATE: ShellState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

function canShowAppChrome(
  user: AuthUser | null | undefined,
  appId: 'ai' | 'pms' | 'docs' | 'planner' | 'settings',
): boolean {
  const featureCode = FEATURE_BY_APP_ID[appId];
  return featureCode ? hasFeatureAccess(user, featureCode) : true;
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
    activeNavItemId: toolId.startsWith('pms-project-')
      ? toolId.replace('pms-project-', 'pms-list-')
      : toolId,
  };
}

export function resolveShellState(
  path: string,
  user: AuthUser | null | undefined,
): ShellState {
  if (path === '/') {
    return HOME_SHELL_STATE;
  }

  if (path === '/ai') {
    return canShowAppChrome(user, 'ai')
      ? { activeAppId: 'ai', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (path === '/pms') {
    return canShowAppChrome(user, 'pms')
      ? { activeAppId: 'pms', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (path === '/docs' || path.startsWith('/docs/')) {
    if (path.startsWith('/docs/shared/')) {
      return canShowAppChrome(user, 'docs')
        ? { activeAppId: 'docs', activeNavItemId: '' }
        : HOME_SHELL_STATE;
    }
    return canShowAppChrome(user, 'docs')
      ? { activeAppId: 'docs', activeNavItemId: '' }
      : HOME_SHELL_STATE;
  }

  if (path === '/planner') {
    return canShowAppChrome(user, 'planner')
      ? { activeAppId: 'planner', activeNavItemId: '' }
      : HOME_SHELL_STATE;
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
    || toolId.startsWith('pms-project-')
    || toolId.startsWith('pms-list-')
    || /^pms-space-.+/.test(toolId)
  ) {
    return resolvePmsToolState(toolId, user);
  }

  const item = NAV_ITEMS.find((entry) => entry.id === toolId);
  if (!item) {
    return HOME_SHELL_STATE;
  }

  if (!canShowAppChrome(user, item.appId)) {
    return HOME_SHELL_STATE;
  }

  return {
    activeAppId: item.appId,
    activeNavItemId: item.id,
  };
}
