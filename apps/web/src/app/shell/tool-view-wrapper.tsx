import { Navigate, useLocation, useParams } from 'react-router-dom';

import { getNavItem } from '@/src/app/shell/app-registry';
import { RagSearchView } from '@/src/app-modules/ai';
import { DocsView } from '@/src/app-modules/docs';
import { PMSView } from '@/src/app-modules/pms';
import { hasWorkspaceMembership } from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import {
  canUseWorkspaceSearchTool,
  isWorkspaceAppEnabled,
} from '@/src/domains/rag/rag-ui-access';
import { useWorkspaceBootstrapContext } from '@/src/domains/workspaces/workspace-bootstrap-context';
import {
  getToolWorkspaceSlugFromSearch,
  resolveDefaultWorkspaceAppPath,
  resolveShellWorkspaceSlug,
} from '@/src/domains/workspaces/workspace-utils';
import { ComingSoonView } from './tool-views/ComingSoonView';
import { ToolView } from './tool-views/ToolView';

export function ToolViewWrapper() {
  const auth = useAuth();
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
        <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
      );
    }
    return <PMSView />;
  }

  const item = toolId ? getNavItem(toolId) : null;
  if (!item) {
    return <div className="p-8 text-gray-500">Tool not found</div>;
  }

  if (item.appId !== 'home' && !hasWorkspaceMembership(auth.user)) {
    return (
      <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
    );
  }

  if (item.appId === 'ai') {
    if (!hasWorkspaceMembership(auth.user, toolWorkspaceSlug)) {
      return (
        <AccessDeniedView description="현재 계정에는 이 도구가 속한 워크스페이스 접근 권한이 없습니다." />
      );
    }
    if (workspaceBootstrap.loading || enabledBootstrapApps === null) {
      return (
        <div className="p-8 text-gray-500">
          워크스페이스 구성을 불러오는 중입니다.
        </div>
      );
    }
    if (workspaceBootstrap.error) {
      return <AccessDeniedView description={workspaceBootstrap.error} />;
    }
    if (!isWorkspaceAppEnabled(enabledBootstrapApps, 'ai')) {
      return (
        <AccessDeniedView description="현재 workspace에서는 AI 앱이 활성화되어 있지 않습니다." />
      );
    }
  }

  if (item.appId === 'pms') {
    return <PMSView />;
  }

  if (item.appId === 'docs') {
    return <DocsView />;
  }

  if (toolId === 'search') {
    if (!canUseWorkspaceSearchTool(enabledBootstrapApps)) {
      return (
        <AccessDeniedView description="현재 workspace에서는 통합검색을 사용할 수 없습니다." />
      );
    }
    return <RagSearchView />;
  }

  if (item.comingSoon) {
    return <ComingSoonView item={item} />;
  }

  return <ToolView item={item} />;
}
