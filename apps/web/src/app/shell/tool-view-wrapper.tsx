import { Navigate, useLocation, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { getNavItem } from '@/src/app/shell/app-registry';
import { ragSearchToolElement } from '@/src/app-modules/ai/routes';
import { docsToolElement } from '@/src/app-modules/docs/routes';
import { pmsToolElement } from '@/src/app-modules/pms/routes';
import { whiteboardToolElement } from '@/src/app-modules/whiteboard/routes';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  canUseWorkspaceSearchTool,
  isWorkspaceAppEnabled,
} from '@/src/platform/rag/rag-ui-access';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  getToolWorkspaceSlugFromSearch,
  resolveDefaultWorkspaceAppPath,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import { ComingSoonView } from './tool-views/ComingSoonView';
import { ToolView } from './tool-views/ToolView';

export function ToolViewWrapper() {
  const auth = useAuth();
  const { t } = useTranslation(['apps', 'shell']);
  const location = useLocation();
  const { toolId } = useParams();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const pmsRoot = resolveDefaultWorkspaceAppPath(auth.user, 'pms');
  const toolWorkspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    getToolWorkspaceSlugFromSearch(
      auth.user,
      location.pathname,
      location.search,
    ) ??
    resolveShellWorkspaceSlug(auth.user, null);
  const enabledBootstrapApps = workspaceBootstrap.data?.apps ?? null;

  if (toolId === 'pms-space-team') {
    return (
      <Navigate replace to={{ pathname: pmsRoot, search: location.search }} />
    );
  }

  if (toolId?.startsWith('pms-list-') || /^pms-space-.+/.test(toolId ?? '')) {
    if (!hasWorkspaceMembership(auth.user)) {
      return (
        <AccessDeniedView description={t('shell:gates.toolWorkspaceDenied')} />
      );
    }
    return pmsToolElement;
  }

  const item = toolId ? getNavItem(toolId) : null;
  if (!item) {
    return <div className="p-8 text-gray-500">{t('apps:toolView.toolNotFound')}</div>;
  }

  if (item.appId !== 'home' && !hasWorkspaceMembership(auth.user)) {
    return (
      <AccessDeniedView description={t('shell:gates.toolWorkspaceDenied')} />
    );
  }

  if (item.appId === 'ai') {
    if (!hasWorkspaceMembership(auth.user, toolWorkspaceSlug)) {
      return (
        <AccessDeniedView description={t('shell:gates.toolWorkspaceDenied')} />
      );
    }
    if (workspaceBootstrap.loading || enabledBootstrapApps === null) {
      return (
        <div className="p-8 text-gray-500">
          {t('shell:gates.workspaceLoading')}
        </div>
      );
    }
    if (workspaceBootstrap.error) {
      return <AccessDeniedView description={workspaceBootstrap.error} />;
    }
    if (!isWorkspaceAppEnabled(enabledBootstrapApps, 'ai')) {
      return (
        <AccessDeniedView description={t('shell:gates.appDisabled')} />
      );
    }
  }

  if (item.appId === 'pms') {
    return pmsToolElement;
  }

  if (item.appId === 'docs') {
    return docsToolElement;
  }

  if (item.appId === 'whiteboard') {
    return whiteboardToolElement;
  }

  if (toolId === 'search') {
    if (!canUseWorkspaceSearchTool(enabledBootstrapApps)) {
      return (
        <AccessDeniedView description={t('shell:gates.workspaceSearchDisabled')} />
      );
    }
    return ragSearchToolElement;
  }

  if (item.comingSoon) {
    return <ComingSoonView item={item} />;
  }

  return <ToolView item={item} />;
}
