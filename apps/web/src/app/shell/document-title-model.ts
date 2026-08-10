import type { WorkspaceBootstrapApp } from '@/src/platform/workspaces/workspaces-api';

import type { AppBarItem } from './navigation-types';

type ShellDocumentTitleTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

type ShellDocumentTitleWorkspace =
  | {
      name: string;
    }
  | null
  | undefined;

export interface ResolveShellDocumentTitleInput {
  activeAppId: string;
  appBarItems?: readonly Pick<AppBarItem, 'id' | 'title'>[];
  pathname: string;
  routeWorkspaceSlug: string | null;
  t: ShellDocumentTitleTranslator;
  workspace: ShellDocumentTitleWorkspace;
  workspaceApps: readonly Pick<WorkspaceBootstrapApp, 'app_id' | 'title'>[];
}

function resolveDocumentAppTitle({
  activeAppId,
  appBarItems = [],
  pathname,
  t,
  workspaceApps,
}: Pick<
  ResolveShellDocumentTitleInput,
  'activeAppId' | 'appBarItems' | 'pathname' | 't' | 'workspaceApps'
>): string {
  if (/^\/w\/[^/]+\/settings(?:\/|$)/.test(pathname)) {
    return t('workspaceSwitcher.manage');
  }
  if (activeAppId === 'profile') {
    return t('documentTitle.profile');
  }
  if (activeAppId === 'settings') {
    return t('apps.settings');
  }
  if (activeAppId === 'search') {
    return t('search.title');
  }
  return t(`apps.${activeAppId}`, {
    defaultValue:
      workspaceApps.find((item) => item.app_id === activeAppId)?.title ??
      appBarItems.find((item) => item.id === activeAppId)?.title ??
      activeAppId,
  });
}

export function resolveShellDocumentTitle({
  activeAppId,
  appBarItems,
  pathname,
  routeWorkspaceSlug,
  t,
  workspace,
  workspaceApps,
}: ResolveShellDocumentTitleInput): string {
  const app = resolveDocumentAppTitle({
    activeAppId,
    appBarItems,
    pathname,
    t,
    workspaceApps,
  });
  if (workspace && (routeWorkspaceSlug || pathname.startsWith('/tool/'))) {
    return t('documentTitle.workspaceApp', {
      app,
      workspace: workspace.name,
    });
  }
  return t('documentTitle.app', { app });
}
