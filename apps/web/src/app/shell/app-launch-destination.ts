import type { AppsBootstrapApp } from '@/src/platform/apps/apps-api';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import type { LauncherGlobalPaths } from './navigation-types';

export type AppLaunchDestination =
  | { displayScope: null; href: '/'; kind: 'unavailable' }
  | { displayScope: 'company' | 'personal'; href: string; kind: 'app' };
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
  return t(
    destination.displayScope === 'personal'
      ? 'shell:launcher.openPersonalApp'
      : 'shell:launcher.openCompanyApp',
    { app: appTitle },
  );
}
