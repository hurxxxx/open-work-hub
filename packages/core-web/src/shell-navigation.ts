export interface CoreShellNavigationNavItem<TAppId extends string = string> {
  appId: TAppId;
  id: string;
  pathSuffix?: string;
}

export interface CoreShellNavigationManifest<TAppId extends string = string> {
  appBarItem: {
    id: TAppId;
  };
  globalRoutePaths?: readonly string[];
  staticGlobalRoutePaths?: readonly string[];
  workspaceRoutePaths: readonly string[];
}

export function getCoreShellPathname(path: string): string {
  const end = path.search(/[?#]/);
  return end >= 0 ? path.slice(0, end) || '/' : path;
}

export function getCoreShellSearchParams(path: string): URLSearchParams {
  const start = path.indexOf('?');
  if (start < 0) {
    return new URLSearchParams();
  }
  const end = path.indexOf('#', start);
  return new URLSearchParams(path.slice(start + 1, end >= 0 ? end : undefined));
}

export function resolveCoreManifestNavItemId<
  TAppId extends string,
  TNavItem extends CoreShellNavigationNavItem<TAppId>,
>({
  appId,
  fallbackNavItemId,
  navItems,
  path,
}: {
  appId: TAppId | string;
  fallbackNavItemId: string;
  navItems: readonly TNavItem[];
  path: string;
}): string {
  const pathname = getCoreShellPathname(path);
  const orderedNavItems = navItems
    .filter(
      (item) =>
        item.appId === appId &&
        typeof item.pathSuffix === 'string' &&
        item.pathSuffix.length > 0,
    )
    .sort(
      (left, right) =>
        (right.pathSuffix ?? '').length - (left.pathSuffix ?? '').length,
    );
  for (const item of orderedNavItems) {
    if (
      item.pathSuffix &&
      manifestPathSuffixMatches({
        appId,
        path,
        pathname,
        suffix: item.pathSuffix,
      })
    ) {
      return item.id;
    }
  }
  return fallbackNavItemId;
}

export function resolveCoreWorkspaceRouteAppId<
  TAppId extends string,
  TManifest extends CoreShellNavigationManifest<TAppId>,
>({
  manifests,
  pathname,
}: {
  manifests: readonly TManifest[];
  pathname: string;
}): TAppId | null {
  const candidates: Array<{ appId: TAppId; prefixLength: number }> = [];
  for (const manifest of manifests) {
    const appId = manifest.appBarItem.id;
    for (const routePath of manifest.workspaceRoutePaths) {
      const prefix = workspaceRouteAppPrefix(routePath);
      if (!prefix) {
        continue;
      }
      if (getCoreWorkspaceAppRelativePath(pathname, prefix) !== null) {
        candidates.push({ appId, prefixLength: prefix.length });
      }
    }
  }
  candidates.sort((left, right) => right.prefixLength - left.prefixLength);
  return candidates[0]?.appId ?? null;
}

export function resolveCoreGlobalRouteAppId<
  TAppId extends string,
  TManifest extends CoreShellNavigationManifest<TAppId>,
>({
  manifests,
  pathname,
}: {
  manifests: readonly TManifest[];
  pathname: string;
}): TAppId | null {
  for (const manifest of manifests) {
    const routePaths = [
      ...(manifest.globalRoutePaths ?? []),
      ...(manifest.staticGlobalRoutePaths ?? []),
    ];
    if (
      routePaths.some((routePath) =>
        coreRoutePathMatchesPathname(routePath, pathname),
      )
    ) {
      return manifest.appBarItem.id;
    }
  }
  return null;
}

export function getCoreWorkspaceAppRelativePath(
  pathname: string,
  appId: string,
): string | null {
  const match = new RegExp(
    `^/apps/${escapeRegExp(appId)}/workspaces/[^/]+(?=$|/)`,
  ).exec(pathname);
  if (!match) {
    return null;
  }
  return pathname.slice(match[0].length);
}

export function coreRoutePathMatchesPathname(
  routePath: string,
  pathname: string,
): boolean {
  const routeSegments = normalizeRoutePath(routePath).split('/').slice(1);
  const pathSegments = normalizeRoutePath(pathname).split('/').slice(1);
  const wildcardIndex = routeSegments.indexOf('*');
  if (wildcardIndex >= 0) {
    return (
      wildcardIndex === routeSegments.length - 1 &&
      pathSegments.length >= wildcardIndex &&
      routeSegments
        .slice(0, wildcardIndex)
        .every((segment, index) =>
          routeSegmentMatchesPathSegment(segment, pathSegments[index]),
        )
    );
  }
  if (routeSegments.length !== pathSegments.length) {
    return false;
  }
  return routeSegments.every((segment, index) =>
    routeSegmentMatchesPathSegment(segment, pathSegments[index]),
  );
}

function workspaceRouteAppPrefix(routePath: string): string | null {
  const match = /^\/apps\/([^/:]+)\/workspaces\/:workspaceSlug/.exec(routePath);
  return match?.[1] ?? null;
}

function normalizeRoutePath(path: string): string {
  const normalized = path.replace(/\/+$/, '');
  return normalized || '/';
}

function routeSegmentMatchesPathSegment(
  routeSegment: string,
  pathSegment: string | undefined,
): boolean {
  if (pathSegment == null) {
    return false;
  }
  if (routeSegment.startsWith(':')) {
    return pathSegment.length > 0;
  }
  return routeSegment === pathSegment;
}

function manifestPathSuffixMatches({
  appId,
  path,
  pathname,
  suffix,
}: {
  appId: string;
  path: string;
  pathname: string;
  suffix: string;
}): boolean {
  if (suffix.startsWith('?')) {
    return querySuffixMatches(path, suffix);
  }
  if (suffix.startsWith('/')) {
    const queryStart = suffix.indexOf('?');
    if (queryStart >= 0) {
      return (
        workspaceAppPathSuffixMatches({
          appId,
          pathname,
          suffix: suffix.slice(0, queryStart),
        }) && querySuffixMatches(path, suffix.slice(queryStart))
      );
    }
    return workspaceAppPathSuffixMatches({ appId, pathname, suffix });
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

function workspaceAppPathSuffixMatches({
  appId,
  pathname,
  suffix,
}: {
  appId: string;
  pathname: string;
  suffix: string;
}): boolean {
  const appRelativePath = getCoreWorkspaceAppRelativePath(pathname, appId);
  if (appRelativePath === null) {
    return false;
  }
  return appRelativePath === suffix || appRelativePath.startsWith(`${suffix}/`);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
