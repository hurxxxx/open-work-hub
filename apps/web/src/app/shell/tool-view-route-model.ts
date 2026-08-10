import type { AppModuleId } from './navigation-types';
import { isWorkspaceNavItemEnabled } from '@/src/platform/rag/rag-ui-access';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import { isWorkspaceAppEnabled } from '@/src/platform/workspaces/workspace-app-access';
import type {
  ToolViewAccessDeniedReason,
  ToolViewRouteGate,
  ToolViewRouteMatch,
} from './route-types';

export type ToolViewRouteItem = {
  appId: AppModuleId;
  comingSoon?: boolean | null;
  linkAppId?: AppModuleId;
};

export type ToolViewRouteDecision =
  | { type: 'redirect_app_root'; appId: ToolViewRouteMatch['appId'] }
  | { type: 'access_denied'; reason: ToolViewAccessDeniedReason }
  | { type: 'access_denied_message'; message: string }
  | { type: 'loading' }
  | {
      type: 'tool_element';
      routeId: string;
    }
  | { type: 'coming_soon' }
  | { type: 'tool_view' }
  | { type: 'not_found' };

type ToolViewGateDecision = Extract<
  ToolViewRouteDecision,
  { type: 'access_denied' | 'access_denied_message' | 'loading' }
>;

export type ToolViewBootstrapApp = {
  app_id: string;
  enabled: boolean;
};

export type ToolViewBootstrapNavItem = {
  id: string;
};

export type ToolViewKeywordSearchEntityType = {
  value: string;
};

export function resolveToolRedirectAppRootPath({
  appId,
  toolWorkspaceSlug,
  user,
}: {
  appId: ToolViewRouteMatch['appId'];
  toolWorkspaceSlug: string | null;
  user: Parameters<typeof resolveDefaultWorkspaceAppPath>[0];
}): string {
  return toolWorkspaceSlug
    ? buildWorkspaceAppPath(toolWorkspaceSlug, appId)
    : resolveDefaultWorkspaceAppPath(user, appId);
}

export function resolveToolViewRouteDecision({
  enabledBootstrapApps,
  enabledBootstrapNav,
  hasAnyWorkspaceMembership,
  hasRequestedWorkspaceMembership,
  hasToolWorkspaceMembership,
  item,
  matchedToolRoute,
  requestedToolWorkspaceSlug,
  workspaceBootstrapError,
  workspaceBootstrapLoading,
  workspaceKeywordSearchEntityTypes = [],
}: {
  enabledBootstrapApps: readonly ToolViewBootstrapApp[] | null;
  enabledBootstrapNav: readonly ToolViewBootstrapNavItem[] | null;
  hasAnyWorkspaceMembership: boolean;
  hasRequestedWorkspaceMembership: boolean;
  hasToolWorkspaceMembership: boolean;
  item: ToolViewRouteItem | null;
  matchedToolRoute: ToolViewRouteMatch | null;
  requestedToolWorkspaceSlug: string | null;
  toolId: string | null | undefined;
  workspaceBootstrapError: string | null;
  workspaceBootstrapLoading: boolean;
  workspaceKeywordSearchEntityTypes?: readonly ToolViewKeywordSearchEntityType[];
}): ToolViewRouteDecision {
  if (requestedToolWorkspaceSlug && !hasRequestedWorkspaceMembership) {
    return { type: 'access_denied', reason: 'tool_workspace_denied' };
  }

  if (matchedToolRoute) {
    const hasWorkspaceSearchGate =
      matchedToolRoute.type === 'element' &&
      matchedToolRoute.gates?.some((gate) => gate.type === 'workspace_search');
    const appGate = hasWorkspaceSearchGate
      ? resolveWorkspaceToolContextGate({
          enabledBootstrapApps,
          hasAnyWorkspaceMembership,
          hasToolWorkspaceMembership,
          workspaceBootstrapError,
          workspaceBootstrapLoading,
        })
      : resolveWorkspaceAppToolGate({
          appId: matchedToolRoute.bootstrapAppId ?? matchedToolRoute.appId,
          enabledBootstrapApps,
          hasAnyWorkspaceMembership,
          hasToolWorkspaceMembership,
          workspaceBootstrapError,
          workspaceBootstrapLoading,
        });
    if (appGate) {
      return appGate;
    }

    if (matchedToolRoute.type === 'redirect_app_root') {
      return {
        appId: matchedToolRoute.bootstrapAppId ?? matchedToolRoute.appId,
        type: 'redirect_app_root',
      };
    }

    for (const gate of matchedToolRoute.gates ?? []) {
      const gateDecision = resolveToolViewRouteGate({
        enabledBootstrapNav,
        gate,
        workspaceKeywordSearchEntityTypes,
      });
      if (gateDecision) {
        return gateDecision;
      }
    }

    return { routeId: matchedToolRoute.id, type: 'tool_element' };
  }

  if (!item) {
    return { type: 'not_found' };
  }

  if (item.appId !== 'home' && !hasAnyWorkspaceMembership) {
    return { type: 'access_denied', reason: 'tool_workspace_denied' };
  }

  const appGate = resolveWorkspaceAppToolGate({
    appId: item.linkAppId ?? item.appId,
    enabledBootstrapApps,
    hasAnyWorkspaceMembership,
    hasToolWorkspaceMembership,
    workspaceBootstrapError,
    workspaceBootstrapLoading,
  });
  if (appGate) {
    return appGate;
  }

  if (item.comingSoon) {
    return { type: 'coming_soon' };
  }

  return { type: 'tool_view' };
}

function resolveWorkspaceAppToolGate({
  appId,
  enabledBootstrapApps,
  hasAnyWorkspaceMembership,
  hasToolWorkspaceMembership,
  workspaceBootstrapError,
  workspaceBootstrapLoading,
}: {
  appId: AppModuleId;
  enabledBootstrapApps: readonly ToolViewBootstrapApp[] | null;
  hasAnyWorkspaceMembership: boolean;
  hasToolWorkspaceMembership: boolean;
  workspaceBootstrapError: string | null;
  workspaceBootstrapLoading: boolean;
}): ToolViewGateDecision | null {
  if (appId === 'home' || appId === 'settings') {
    return null;
  }
  const contextGate = resolveWorkspaceToolContextGate({
    enabledBootstrapApps,
    hasAnyWorkspaceMembership,
    hasToolWorkspaceMembership,
    workspaceBootstrapError,
    workspaceBootstrapLoading,
  });
  if (contextGate) {
    return contextGate;
  }
  if (!isWorkspaceAppEnabled(enabledBootstrapApps, appId)) {
    return { type: 'access_denied', reason: 'app_disabled' };
  }
  return null;
}

function resolveWorkspaceToolContextGate({
  enabledBootstrapApps,
  hasAnyWorkspaceMembership,
  hasToolWorkspaceMembership,
  workspaceBootstrapError,
  workspaceBootstrapLoading,
}: {
  enabledBootstrapApps: readonly ToolViewBootstrapApp[] | null;
  hasAnyWorkspaceMembership: boolean;
  hasToolWorkspaceMembership: boolean;
  workspaceBootstrapError: string | null;
  workspaceBootstrapLoading: boolean;
}): ToolViewGateDecision | null {
  if (!hasAnyWorkspaceMembership || !hasToolWorkspaceMembership) {
    return { type: 'access_denied', reason: 'tool_workspace_denied' };
  }
  if (workspaceBootstrapLoading || enabledBootstrapApps === null) {
    return { type: 'loading' };
  }
  if (workspaceBootstrapError) {
    return {
      type: 'access_denied_message',
      message: workspaceBootstrapError,
    };
  }
  return null;
}

function resolveToolViewRouteGate({
  enabledBootstrapNav,
  gate,
  workspaceKeywordSearchEntityTypes,
}: {
  enabledBootstrapNav: readonly ToolViewBootstrapNavItem[] | null;
  gate: ToolViewRouteGate;
  workspaceKeywordSearchEntityTypes: readonly ToolViewKeywordSearchEntityType[];
}): ToolViewGateDecision | null {
  if (
    gate.type === 'workspace_search' &&
    workspaceKeywordSearchEntityTypes.length === 0
  ) {
    return {
      type: 'access_denied',
      reason: gate.deniedReason ?? 'workspace_search_disabled',
    };
  }
  if (
    gate.type === 'bootstrap_nav_item' &&
    !isWorkspaceNavItemEnabled(enabledBootstrapNav, gate.navItemId)
  ) {
    return { type: 'access_denied', reason: gate.deniedReason };
  }
  return null;
}
