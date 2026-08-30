import { describe, expect, it } from 'vitest';

import type { AppsBootstrapApp } from '@/src/platform/workspaces/workspaces-api';
import { EMPTY_LAUNCHER_GLOBAL_PATHS } from './navigation-types';
import { resolveAppLaunchDestination } from './app-launch-destination';

function workspaceApp(
  overrides: Partial<AppsBootstrapApp> = {},
): AppsBootstrapApp {
  return {
    app_id: 'docs',
    availability_scope: 'workspace',
    coming_soon: false,
    eligible_workspace_count: 2,
    entry_route_id: 'docs.root',
    execution_context_kind: 'workspace',
    icon_key: 'copy',
    preferred_workspace: {
      id: 'workspace-administrator',
      name: 'Administrator',
      slug: 'administrator',
    },
    resource_scope: 'workspace',
    route_base: '/apps/docs',
    single_eligible_workspace: null,
    title: 'Docs',
    ...overrides,
  } as AppsBootstrapApp;
}

describe('app launch destination', () => {
  it('keeps an eligible current workspace ahead of the app preference', () => {
    expect(
      resolveAppLaunchDestination({
        app: workspaceApp(),
        appId: 'docs',
        currentWorkspace: {
          id: 'workspace-general',
          name: 'General',
          slug: 'general',
        },
        currentWorkspaceAppIds: new Set(['docs']),
        launcherGlobalPaths: EMPTY_LAUNCHER_GLOBAL_PATHS,
      }),
    ).toMatchObject({
      href: '/apps/docs/workspaces/general',
      kind: 'current-workspace',
      workspace: { name: 'General' },
    });
  });

  it('uses the app entry and previews the preference when current scope is ineligible', () => {
    expect(
      resolveAppLaunchDestination({
        app: workspaceApp(),
        appId: 'docs',
        currentWorkspace: {
          id: 'workspace-general',
          name: 'General',
          slug: 'general',
        },
        currentWorkspaceAppIds: new Set(['pms']),
        launcherGlobalPaths: EMPTY_LAUNCHER_GLOBAL_PATHS,
      }),
    ).toMatchObject({
      href: '/apps/docs',
      kind: 'app-entry',
      workspace: { name: 'Administrator' },
    });
  });

  it('fails closed to the app entry while current-workspace availability is unknown', () => {
    expect(
      resolveAppLaunchDestination({
        app: workspaceApp({ preferred_workspace: null }),
        appId: 'docs',
        currentWorkspace: {
          id: 'workspace-general',
          name: 'General',
          slug: 'general',
        },
        currentWorkspaceAppIds: null,
        launcherGlobalPaths: EMPTY_LAUNCHER_GLOBAL_PATHS,
      }),
    ).toMatchObject({ href: '/apps/docs', kind: 'app-entry', workspace: null });
  });

  it('never carries workspace context into personal or company apps', () => {
    const mail = {
      ...workspaceApp(),
      app_id: 'mail',
      availability_scope: 'platform',
      eligible_workspace_count: 0,
      entry_route_id: 'mail.root',
      execution_context_kind: 'personal',
      preferred_workspace: null,
      resource_scope: 'personal',
      route_base: '/apps/mail',
    } as AppsBootstrapApp;

    expect(
      resolveAppLaunchDestination({
        app: mail,
        appId: 'mail',
        currentWorkspace: {
          id: 'workspace-general',
          name: 'General',
          slug: 'general',
        },
        currentWorkspaceAppIds: new Set(['mail']),
        launcherGlobalPaths: new Map([['mail', '/apps/mail']]),
      }),
    ).toMatchObject({
      displayScope: 'personal',
      href: '/apps/mail',
      kind: 'global',
      workspace: null,
    });
  });
});
