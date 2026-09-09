import type { BootstrapApp } from '@/src/platform/apps/apps-api';

import type { AppBarItem } from './navigation-types';

type ShellDocumentTitleTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export interface ResolveShellDocumentTitleInput {
  activeAppId: string;
  appBarItems?: readonly Pick<AppBarItem, 'id' | 'title'>[];

  t: ShellDocumentTitleTranslator;
  apps: readonly Pick<BootstrapApp, 'app_id' | 'title'>[];
}

function resolveDocumentAppTitle({
  activeAppId,
  appBarItems = [],
  t,
  apps,
}: Pick<
  ResolveShellDocumentTitleInput,
  'activeAppId' | 'appBarItems' | 't' | 'apps'
>): string {
  if (activeAppId === 'profile') {
    return t('documentTitle.profile');
  }
  if (activeAppId === 'launcher') {
    return t('launcher.title');
  }
  if (activeAppId === 'settings') {
    return t('apps.settings');
  }
  if (activeAppId === 'search') {
    return t('search.title');
  }
  return t(`apps.${activeAppId}`, {
    defaultValue:
      apps.find((item) => item.app_id === activeAppId)?.title ??
      appBarItems.find((item) => item.id === activeAppId)?.title ??
      activeAppId,
  });
}

export function resolveShellDocumentTitle({
  activeAppId,
  appBarItems,
  t,
  apps,
}: ResolveShellDocumentTitleInput): string {
  const app = resolveDocumentAppTitle({
    activeAppId,
    appBarItems,
    t,
    apps,
  });
  return t('documentTitle.app', { app });
}
