import {
  coreRoutePathMatchesPathname,
  getCoreShellPathname,
  getCoreShellSearchParams,
  getCoreWorkspaceAppRelativePath,
  resolveCoreGlobalRouteAppId,
  resolveCoreManifestNavItemId,
  resolveCoreWorkspaceRouteAppId,
} from '@open-alm/core-web/shell-navigation';

import type {
  AppModuleId,
  AppModuleManifest,
  NavItem,
} from './app/shell/navigation-types';

export const getShellPathname = getCoreShellPathname;
export const getShellSearchParams = getCoreShellSearchParams;
export const getWorkspaceAppRelativePath = getCoreWorkspaceAppRelativePath;
export const routePathMatchesPathname = coreRoutePathMatchesPathname;

export function resolveManifestNavItemId({
  appId,
  fallbackNavItemId,
  navItems,
  path,
}: {
  appId: string;
  fallbackNavItemId: string;
  navItems: readonly NavItem[];
  path: string;
}): string {
  const pathname = getCoreShellPathname(path);
  const linkedNavItemId = resolveLinkedManifestNavItemId({
    appId,
    navItems,
    path,
    pathname,
  });
  if (linkedNavItemId) {
    return linkedNavItemId;
  }
  const orderedAbsoluteNavItems = navItems
    .filter(
      (item) =>
        item.appId === appId &&
        typeof item.absolutePath === 'string' &&
        item.absolutePath.length > 0,
    )
    .sort(
      (left, right) =>
        (right.absolutePath ?? '').length - (left.absolutePath ?? '').length,
    );
  for (const item of orderedAbsoluteNavItems) {
    const absolutePath = item.absolutePath ?? '';
    if (
      pathname === absolutePath ||
      pathname.startsWith(`${absolutePath.replace(/\/+$/, '')}/`)
    ) {
      return item.id;
    }
  }

  return resolveCoreManifestNavItemId({
    appId,
    fallbackNavItemId,
    navItems,
    path,
  });
}

function resolveLinkedManifestNavItemId({
  appId,
  navItems,
  path,
  pathname,
}: {
  appId: string;
  navItems: readonly NavItem[];
  path: string;
  pathname: string;
}): string | null {
  const orderedLinkedNavItems = navItems
    .filter((item) => item.appId === appId && item.linkAppId)
    .sort(
      (left, right) =>
        (right.pathSuffix ?? '').length - (left.pathSuffix ?? '').length,
    );
  for (const item of orderedLinkedNavItems) {
    if (linkedNavItemMatchesPath({ item, path, pathname })) {
      return item.id;
    }
  }
  return null;
}

function linkedNavItemMatchesPath({
  item,
  path,
  pathname,
}: {
  item: NavItem;
  path: string;
  pathname: string;
}): boolean {
  const targetAppId = item.linkAppId;
  if (!targetAppId) {
    return false;
  }
  const appRelativePath = getCoreWorkspaceAppRelativePath(pathname, targetAppId);
  if (appRelativePath === null) {
    return false;
  }
  const suffix = item.pathSuffix ?? '';
  if (!suffix) {
    return true;
  }
  if (suffix.startsWith('?')) {
    return querySuffixMatches(path, suffix);
  }
  if (suffix.startsWith('/')) {
    return (
      appRelativePath === suffix || appRelativePath.startsWith(`${suffix}/`)
    );
  }
  return false;
}

function querySuffixMatches(path: string, suffix: string): boolean {
  const expected = new URLSearchParams(suffix.slice(1));
  if ([...expected.keys()].length === 0) {
    return false;
  }
  const actual = getCoreShellSearchParams(path);
  for (const [key, value] of expected) {
    if (actual.get(key) !== value) {
      return false;
    }
  }
  return true;
}

export function resolveWorkspaceRouteAppId({
  manifests,
  pathname,
}: {
  manifests: readonly AppModuleManifest[];
  pathname: string;
}): AppModuleId | null {
  return resolveCoreWorkspaceRouteAppId({ manifests, pathname });
}

export function resolveGlobalRouteAppId({
  manifests,
  pathname,
}: {
  manifests: readonly AppModuleManifest[];
  pathname: string;
}): AppModuleId | null {
  return resolveCoreGlobalRouteAppId({ manifests, pathname });
}
