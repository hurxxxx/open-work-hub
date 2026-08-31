import {
  APP_CONTRACT_BY_ID,
  type AppId,
  type AppRouteId,
} from '@open-work-hub/contracts/app-contracts';
import { matchAppRoute } from '@open-work-hub/contracts/app-routes';

export type AppRouteContext =
  | { kind: 'launcher'; appId: null; workspaceSlug: null }
  | { kind: 'shell'; appId: null; workspaceSlug: null }
  | { kind: 'entry'; appId: AppId; workspaceSlug: null }
  | {
      kind: 'global';
      appId: AppId;
      routeId: AppRouteId;
      workspaceSlug: null;
    }
  | {
      kind: 'workspace';
      appId: AppId;
      routeId: AppRouteId;
      workspaceSlug: string;
    };

export function resolveAppRouteContext(pathname: string): AppRouteContext {
  if (pathname === '/') {
    return { kind: 'launcher', appId: null, workspaceSlug: null };
  }
  const matched = matchAppRoute(pathname);
  if (matched?.contextScope === 'workspace' && matched.workspaceSlug) {
    return {
      kind: 'workspace',
      appId: matched.appId,
      routeId: matched.routeId,
      workspaceSlug: matched.workspaceSlug,
    };
  }
  if (matched) {
    return {
      kind: 'global',
      appId: matched.appId,
      routeId: matched.routeId,
      workspaceSlug: null,
    };
  }
  const entry = Array.from(APP_CONTRACT_BY_ID.values()).find(
    (app) => app.route_base === pathname,
  );
  if (entry) {
    return { kind: 'entry', appId: entry.app_id, workspaceSlug: null };
  }
  return { kind: 'shell', appId: null, workspaceSlug: null };
}
