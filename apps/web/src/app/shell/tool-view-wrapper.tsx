import { Navigate, useLocation, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  getRequestedToolWorkspaceSlugFromSearch,
  getToolWorkspaceSlugFromSearch,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import {
  resolveToolRedirectAppRootPath,
  resolveToolViewRouteDecision,
} from './tool-view-route-model';
import type {
  ToolViewAccessDeniedReason,
  ToolViewRouteDefinition,
} from './route-types';
import type { NavItem } from './navigation-types';
import { ComingSoonView } from './tool-views/ComingSoonView';
import { ToolGuideLauncher } from './tool-views/ToolGuideLauncher';
import { ToolView } from './tool-views/ToolView';
import {
  EMPTY_FEATURE_GUIDE_TOOL_IDS,
  type FeatureGuideToolIds,
} from './ai-feature-guides';

const ACCESS_DENIED_DESCRIPTION_KEYS: Record<
  ToolViewAccessDeniedReason,
  string
> = {
  app_disabled: 'shell:gates.appDisabled',
  tool_workspace_denied: 'shell:gates.toolWorkspaceDenied',
  workspace_search_disabled: 'shell:gates.workspaceSearchDisabled',
};

const getNoopNavItem = () => null;
const getNoopToolViewRoute = () => null;

export interface ToolViewWrapperProps {
  featureGuideToolIds?: FeatureGuideToolIds;
  getNavItem?: (itemId: string) => NavItem | null;
  getToolViewRoute?: ({
    item,
    toolId,
  }: {
    item: NavItem | null;
    toolId: string;
  }) => ToolViewRouteDefinition | null;
}

export function ToolViewWrapper({
  featureGuideToolIds = EMPTY_FEATURE_GUIDE_TOOL_IDS,
  getNavItem = getNoopNavItem,
  getToolViewRoute = getNoopToolViewRoute,
}: ToolViewWrapperProps = {}) {
  const auth = useAuth();
  const { t } = useTranslation(['apps', 'shell']);
  const location = useLocation();
  const { toolId } = useParams();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const requestedToolWorkspaceSlug = getRequestedToolWorkspaceSlugFromSearch(
    location.pathname,
    location.search,
  );
  const toolWorkspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    getToolWorkspaceSlugFromSearch(
      auth.user,
      location.pathname,
      location.search,
    ) ??
    (requestedToolWorkspaceSlug
      ? null
      : resolveShellWorkspaceSlug(auth.user, null));
  const enabledBootstrapApps = workspaceBootstrap.data
    ? workspaceBootstrap.data.apps
    : null;
  const enabledBootstrapNav = workspaceBootstrap.data?.nav ?? null;
  const item = toolId ? getNavItem(toolId) : null;
  const matchedToolRoute = toolId ? getToolViewRoute({ item, toolId }) : null;
  const decision = resolveToolViewRouteDecision({
    enabledBootstrapApps,
    enabledBootstrapNav,
    hasAnyWorkspaceMembership: hasWorkspaceMembership(auth.user),
    hasRequestedWorkspaceMembership: hasWorkspaceMembership(
      auth.user,
      requestedToolWorkspaceSlug,
    ),
    hasToolWorkspaceMembership: hasWorkspaceMembership(
      auth.user,
      toolWorkspaceSlug,
    ),
    item,
    matchedToolRoute,
    requestedToolWorkspaceSlug,
    toolId,
    workspaceBootstrapError: workspaceBootstrap.error,
    workspaceBootstrapLoading: workspaceBootstrap.loading,
    workspaceKeywordSearchEntityTypes:
      workspaceBootstrap.data?.keyword_search?.entity_types ?? [],
  });

  if (decision.type === 'redirect_app_root') {
    return (
      <Navigate
        replace
        to={{
          pathname: resolveToolRedirectAppRootPath({
            appId: decision.appId,
            toolWorkspaceSlug,
            user: auth.user,
          }),
          search: location.search,
        }}
      />
    );
  }

  if (decision.type === 'not_found') {
    return (
      <div className="p-8 text-app-ink/55">
        {t('apps:toolView.toolNotFound')}
      </div>
    );
  }

  if (decision.type === 'access_denied') {
    return (
      <AccessDeniedView
        description={t(ACCESS_DENIED_DESCRIPTION_KEYS[decision.reason])}
      />
    );
  }

  if (decision.type === 'access_denied_message') {
    return <AccessDeniedView description={decision.message} />;
  }

  if (decision.type === 'loading') {
    return (
      <div className="p-8 text-app-ink/55">
        {t('shell:gates.workspaceLoading')}
      </div>
    );
  }

  if (decision.type === 'tool_element') {
    const element =
      matchedToolRoute?.id === decision.routeId &&
      matchedToolRoute.type === 'element'
        ? matchedToolRoute.element
        : null;
    if (element && toolId) {
      return (
        <ToolGuideLauncher
          featureGuideToolIds={featureGuideToolIds}
          toolId={toolId}
        >
          {element}
        </ToolGuideLauncher>
      );
    }
    return element;
  }

  if (decision.type === 'coming_soon' && item) {
    return <ComingSoonView item={item} />;
  }

  return item ? <ToolView item={item} /> : null;
}
