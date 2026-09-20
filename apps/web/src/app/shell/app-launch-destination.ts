import type { AppsBootstrapApp } from '@/src/platform/apps/apps-api';
import { createCodexConsoleSessionLink } from '@/src/platform/auth/auth-api';
import { readStoredAuthToken } from '@/src/platform/auth/auth-storage';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import type { LauncherGlobalPaths } from './navigation-types';

export type AppLaunchDestination =
  | { displayScope: null; href: '/'; kind: 'unavailable' }
  | {
      displayScope: 'company' | 'personal';
      href: string;
      kind: 'app' | 'external';
    };
export type AppLaunchDestinationResolver = (
  appId: string,
) => AppLaunchDestination;
export type AppLaunchTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function resolveAppLaunchDestination({
  app,
  appId,
  launcherGlobalPaths,
}: {
  app: AppsBootstrapApp | null;
  appId: string;
  launcherGlobalPaths: LauncherGlobalPaths;
}): AppLaunchDestination {
  const contract = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!app?.enabled || !contract)
    return { displayScope: null, href: '/', kind: 'unavailable' };
  if ('url_setting' in contract.launcher) {
    const url = app.launch_url;
    if (!url || !safeLaunchUrl(url))
      return { displayScope: null, href: '/', kind: 'unavailable' };
    return {
      displayScope: contract.execution_context_kind,
      href: url,
      kind: 'external',
    };
  }
  return {
    displayScope: contract.execution_context_kind,
    href:
      launcherGlobalPaths.get(appId) ??
      buildAppHref({ routeId: contract.entry_route_id }),
    kind: 'app',
  };
}

export function translateAppLaunchContext(
  destination: AppLaunchDestination,
  t: AppLaunchTranslator,
): string {
  if (destination.kind === 'unavailable')
    return t('shell:launcher.appUnavailable');
  if (destination.kind === 'external') return t('shell:launcher.opensInNewTab');
  return t(
    destination.displayScope === 'personal'
      ? 'shell:launcher.personalScope'
      : 'shell:launcher.companyScope',
  );
}

export function translateAppLaunchLabel(
  appTitle: string,
  destination: AppLaunchDestination,
  t: AppLaunchTranslator,
): string {
  if (destination.kind === 'unavailable')
    return t('shell:launcher.unavailableAppLabel', { app: appTitle });
  if (destination.kind === 'external')
    return t('shell:launcher.openAppInNewTab', { app: appTitle });
  return t(
    destination.displayScope === 'personal'
      ? 'shell:launcher.openPersonalApp'
      : 'shell:launcher.openCompanyApp',
    { app: appTitle },
  );
}

export function appLaunchLinkProps(
  appId: string,
  href?: string,
  onBeforeLaunch?: () => void,
) {
  const contract = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!contract || !('url_setting' in contract.launcher))
    return onBeforeLaunch ? { onClick: onBeforeLaunch } : {};
  return {
    target: '_blank' as const,
    rel: 'noopener noreferrer',
    ...(appId === 'codex-console' && href
      ? {
          onClick: (event: { preventDefault: () => void }) => {
            event.preventDefault();
            onBeforeLaunch?.();
            void launchCodexConsole(href);
          },
        }
      : onBeforeLaunch
        ? { onClick: onBeforeLaunch }
        : {}),
  };
}

async function launchCodexConsole(href: string): Promise<void> {
  const popup = window.open('about:blank', '_blank');
  if (popup) popup.opener = null;
  const navigate = (destination: string) => {
    if (popup === null) {
      window.location.assign(destination);
      return;
    }
    if (!popup.closed) popup.location.replace(destination);
  };
  const token = readStoredAuthToken();
  if (!token) {
    navigate(href);
    return;
  }
  try {
    const link = await createCodexConsoleSessionLink(token);
    const destination = new URL(href, window.location.origin);
    destination.hash = new URLSearchParams({
      owh_issuer: window.location.origin,
      owh_code: link.code,
    }).toString();
    navigate(destination.toString());
  } catch {
    navigate(href);
  }
}

function safeLaunchUrl(value: string): boolean {
  if (
    /[\\\s]/.test(value) ||
    Array.from(value).some((character) => character.charCodeAt(0) < 32)
  )
    return false;
  if (value.startsWith('/')) return !value.startsWith('//');
  try {
    const url = new URL(value);
    return (
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash &&
      (url.protocol === 'https:' ||
        (url.protocol === 'http:' &&
          ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))
    );
  } catch {
    return false;
  }
}
