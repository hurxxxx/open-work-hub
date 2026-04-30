import { Navigate, useParams } from 'react-router-dom';

import { getDefaultAdminPath } from '@/src/domains/admin/admin-permissions';
import {
  hasWorkspaceMembership,
} from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import {
  buildWorkspaceAppPath,
  getWorkspaceBySlug,
  resolveRootEntryPath,
} from '@/src/domains/workspaces/workspace-utils';

export function AdminLandingRedirect() {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  return <Navigate replace to={getDefaultAdminPath(auth.user.system_roles)} />;
}

export function HomeRootRedirect() {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  const targetPath = resolveRootEntryPath(auth.user);
  if (!targetPath) {
    return (
      <AccessDeniedView description="접근 가능한 워크스페이스가 없습니다. 관리자에게 문의해주세요." />
    );
  }

  return <Navigate replace to={targetPath} />;
}

export function WorkspaceRootRedirect() {
  const auth = useAuth();
  const { workspaceSlug } = useParams();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  if (!workspaceSlug || !getWorkspaceBySlug(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description="현재 계정은 이 workspace에 접근할 수 없습니다." />
    );
  }

  if (!hasWorkspaceMembership(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description="현재 계정은 이 workspace에 접근할 수 없습니다." />
    );
  }

  return <Navigate replace to={buildWorkspaceAppPath(workspaceSlug, 'home')} />;
}
