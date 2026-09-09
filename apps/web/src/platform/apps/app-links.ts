import type { NavItem } from '@/src/app/shell/navigation-types';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import {
  buildAppHref,
  matchAppRoute,
} from '@open-work-hub/contracts/app-routes';

export type ShellAppId = string;

export function getAppIdFromPath(pathname: string): ShellAppId | null {
  return matchAppRoute(pathname)?.appId ?? null;
}

export function buildAppPath(appId: ShellAppId): string {
  const app = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!app) throw new Error(`Unknown app: ${appId}`);
  return buildAppHref({ routeId: app.entry_route_id });
}

export const buildAppEntryPath = buildAppPath;

export function resolveAppInvocationHref(item: NavItem): string {
  if (item.absolutePath) return item.absolutePath;
  const appId = item.linkAppId ?? item.appId;
  const app = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!app) return '/';
  const parsed = new URL(item.pathSuffix || '/', 'https://app.invalid');
  const route =
    parsed.pathname === '/'
      ? app.routes.find(
          (candidate) => candidate.route_id === app.entry_route_id,
        )
      : app.routes.find(
          (candidate) =>
            candidate.suffix === parsed.pathname &&
            !candidate.suffix.includes(':'),
        );
  if (!route) return '/';
  const queryParams: Record<string, string | string[]> = {};
  for (const key of new Set(parsed.searchParams.keys())) {
    const values = parsed.searchParams.getAll(key);
    queryParams[key] = values.length === 1 ? values[0] : values;
  }
  return buildAppHref({
    routeId: route.route_id,
    queryParams,
    fragment: parsed.hash || undefined,
  });
}

export const resolveNavItemHref = resolveAppInvocationHref;
