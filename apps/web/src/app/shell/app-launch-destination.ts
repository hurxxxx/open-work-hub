import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import {
  buildAppEntryHref,
  buildAppHref,
} from '@open-work-hub/contracts/app-routes';

import type { LauncherGlobalPaths } from './navigation-types';
import type {
  AppsBootstrapApp,
  EligibleWorkspace,
} from '@/src/platform/workspaces/workspaces-api';

export type AppLaunchDestination =
  | {
      displayScope: null;
      href: '/';
      kind: 'unavailable';
      workspace: null;
    }
  | {
      displayScope: 'company' | 'personal';
      href: string;
      kind: 'global';
      workspace: null;
    }
  | {
      displayScope: 'workspace';
      href: string;
      kind: 'current-workspace';
      workspace: EligibleWorkspace;
    }
  | {
      displayScope: 'workspace';
      href: string;
      kind: 'app-entry';
      workspace: EligibleWorkspace | null;
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
  currentWorkspace,
  currentWorkspaceAppIds,
  launcherGlobalPaths,
}: {
  app: AppsBootstrapApp | null;
  appId: string;
  currentWorkspace: EligibleWorkspace | null;
  currentWorkspaceAppIds: ReadonlySet<string> | null;
  launcherGlobalPaths: LauncherGlobalPaths;
}): AppLaunchDestination {
  const contract = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!app || !contract) {
    return {
      displayScope: null,
      href: '/',
      kind: 'unavailable',
      workspace: null,
    };
  }

  if (contract.availability_scope === 'platform') {
    return {
      displayScope:
        contract.execution_context_kind === 'personal' ? 'personal' : 'company',
      href:
        launcherGlobalPaths.get(appId) ?? buildAppEntryHref(contract.app_id),
      kind: 'global',
      workspace: null,
    };
  }

  if (app.eligible_workspace_count < 1) {
    return {
      displayScope: null,
      href: '/',
      kind: 'unavailable',
      workspace: null,
    };
  }

  if (currentWorkspace && currentWorkspaceAppIds?.has(appId)) {
    return {
      displayScope: 'workspace',
      href: buildAppHref({
        routeId: contract.entry_route_id,
        workspaceSlug: currentWorkspace.slug,
      }),
      kind: 'current-workspace',
      workspace: currentWorkspace,
    };
  }

  return {
    displayScope: 'workspace',
    href: buildAppEntryHref(contract.app_id),
    kind: 'app-entry',
    workspace: app.preferred_workspace ?? app.single_eligible_workspace ?? null,
  };
}

export function translateAppLaunchContext(
  destination: AppLaunchDestination,
  t: AppLaunchTranslator,
): string {
  switch (destination.kind) {
    case 'current-workspace':
    case 'app-entry':
      return destination.workspace
        ? t('shell:launcher.opensInWorkspace', {
            workspace: destination.workspace.name,
          })
        : t('shell:launcher.workspaceSelectionRequired');
    case 'global':
      return destination.displayScope === 'personal'
        ? t('shell:launcher.personalScope')
        : t('shell:launcher.companyScope');
    case 'unavailable':
      return t('shell:launcher.appUnavailable');
  }
}

export function translateAppLaunchLabel(
  appTitle: string,
  destination: AppLaunchDestination,
  t: AppLaunchTranslator,
): string {
  switch (destination.kind) {
    case 'current-workspace':
    case 'app-entry':
      return destination.workspace
        ? t('shell:launcher.openWorkspaceApp', {
            app: appTitle,
            workspace: destination.workspace.name,
          })
        : t('shell:launcher.chooseWorkspaceForApp', { app: appTitle });
    case 'global':
      return destination.displayScope === 'personal'
        ? t('shell:launcher.openPersonalApp', { app: appTitle })
        : t('shell:launcher.openCompanyApp', { app: appTitle });
    case 'unavailable':
      return t('shell:launcher.unavailableAppLabel', { app: appTitle });
  }
}
