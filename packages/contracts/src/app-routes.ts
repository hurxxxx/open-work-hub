import {
  APP_CONTRACT_BY_ID,
  APP_ROUTE_BY_ID,
  type AppId,
  type AppRouteContract,
  type AppRouteId,
} from './app-contracts.generated.js';

export type InternalAppLocation = {
  routeId: AppRouteId;
  workspaceSlug?: string;
  pathParams?: Readonly<Record<string, string>>;
  queryParams?: Readonly<
    Record<string, string | readonly string[] | null | undefined>
  >;
  fragment?: string;
};

export type MatchedAppRoute = {
  appId: AppId;
  routeId: AppRouteId;
  contextScope: 'global' | 'workspace';
  workspaceSlug: string | null;
  pathParams: Readonly<Record<string, string>>;
};

const PATH_PARAM = /:([A-Za-z][A-Za-z0-9_]*)/g;

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}

function renderTemplate(
  template: string,
  params: Readonly<Record<string, string>>,
): string {
  const expectedKeys = new Set(
    Array.from(template.matchAll(PATH_PARAM), (match) => match[1]),
  );
  for (const key of Object.keys(params)) {
    if (!expectedKeys.has(key)) {
      throw new Error(`Unexpected route parameter: ${key}`);
    }
  }
  return template.replace(PATH_PARAM, (_match, key: string) => {
    const value = params[key];
    if (!value) throw new Error(`Missing route parameter: ${key}`);
    return encodePathSegment(value);
  });
}

export function getAppRoutePattern(routeId: AppRouteId): string {
  const route = APP_ROUTE_BY_ID.get(routeId);
  if (!route) throw new Error(`Unknown app route: ${routeId}`);
  return route.context_scope === 'workspace'
    ? `${route.route_base}/workspaces/:workspaceSlug${route.suffix}`
    : `${route.route_base}${route.suffix}`;
}

export function getAppRouteChrome(
  routeId: AppRouteId,
): AppRouteContract['chrome'] {
  const route = APP_ROUTE_BY_ID.get(routeId);
  if (!route) throw new Error(`Unknown app route: ${routeId}`);
  return route.chrome;
}

export function buildAppHref(location: InternalAppLocation): string {
  const route = APP_ROUTE_BY_ID.get(location.routeId);
  if (!route) throw new Error(`Unknown app route: ${location.routeId}`);
  const params = { ...(location.pathParams ?? {}) };
  if (route.context_scope === 'workspace') {
    if (!location.workspaceSlug) {
      throw new Error(
        `Workspace route requires workspaceSlug: ${location.routeId}`,
      );
    }
    params.workspaceSlug = location.workspaceSlug;
  } else if (location.workspaceSlug) {
    throw new Error(
      `Global route cannot carry workspaceSlug: ${location.routeId}`,
    );
  }

  const pathname = renderTemplate(getAppRoutePattern(location.routeId), params);
  const query = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(location.queryParams ?? {}).sort(
    ([a], [b]) => a.localeCompare(b),
  )) {
    if (rawValue === null || rawValue === undefined) continue;
    for (const value of Array.isArray(rawValue) ? rawValue : [rawValue]) {
      query.append(key, value);
    }
  }
  const search = query.size ? `?${query.toString()}` : '';
  const hash = location.fragment
    ? `#${encodeURIComponent(location.fragment.replace(/^#/, ''))}`
    : '';
  return `${pathname}${search}${hash}`;
}

function compilePattern(pattern: string): { regex: RegExp; keys: string[] } {
  const keys: string[] = [];
  const escaped = pattern
    .split('/')
    .map((segment) => {
      if (!segment.startsWith(':')) {
        return segment.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      }
      keys.push(segment.slice(1));
      return '([^/]+)';
    })
    .join('/');
  return { regex: new RegExp(`^${escaped}/?$`), keys };
}

const MATCHERS = Array.from(APP_ROUTE_BY_ID.entries())
  .map(([routeId, route]) => ({
    routeId,
    route,
    ...compilePattern(getAppRoutePattern(routeId)),
  }))
  .sort((left, right) => right.regex.source.length - left.regex.source.length);

export function matchAppRoute(pathname: string): MatchedAppRoute | null {
  for (const matcher of MATCHERS) {
    const match = matcher.regex.exec(pathname);
    if (!match) continue;
    const values = matcher.keys.map(
      (key, index) => [key, decodeURIComponent(match[index + 1])] as const,
    );
    const params = Object.fromEntries(values);
    const workspaceSlug = params.workspaceSlug ?? null;
    delete params.workspaceSlug;
    return {
      appId: matcher.route.app_id,
      routeId: matcher.routeId,
      contextScope: matcher.route.context_scope,
      workspaceSlug,
      pathParams: params,
    };
  }
  return null;
}

export function buildAppEntryHref(appId: AppId): string {
  const app = APP_CONTRACT_BY_ID.get(appId);
  if (!app) throw new Error(`Unknown app: ${appId}`);
  return app.route_base;
}
