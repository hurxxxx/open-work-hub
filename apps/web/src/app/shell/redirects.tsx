import { Navigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { getDefaultAdminPath } from '@/src/platform/admin/admin-permissions';
import {
  hasWorkspaceMembership,
} from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  buildWorkspaceAppPath,
  getWorkspaceBySlug,
  resolveRootEntryPath,
} from '@/src/platform/workspaces/workspace-utils';

export function AdminLandingRedirect() {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  return <Navigate replace to={getDefaultAdminPath(auth.user.system_roles)} />;
}

export function HomeRootRedirect() {
  const auth = useAuth();
  const { t } = useTranslation('shell');

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  const targetPath = resolveRootEntryPath(auth.user);
  if (!targetPath) {
    return (
      <AccessDeniedView description={t('gates.noAccessibleWorkspace')} />
    );
  }

  return <Navigate replace to={targetPath} />;
}

export function WorkspaceRootRedirect() {
  const auth = useAuth();
  const { t } = useTranslation('shell');
  const { workspaceSlug } = useParams();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  if (!workspaceSlug || !getWorkspaceBySlug(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description={t('gates.workspaceDenied')} />
    );
  }

  if (!hasWorkspaceMembership(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description={t('gates.workspaceDenied')} />
    );
  }

  return <Navigate replace to={buildWorkspaceAppPath(workspaceSlug, 'home')} />;
}
