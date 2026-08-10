import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router-dom';

import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  buildWorkspaceAppPath,
  getWorkspaceBySlug,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';

export function WorkspaceRootRedirect({
  defaultWorkspaceAppId = 'home',
}: {
  defaultWorkspaceAppId?: WorkspaceAppId;
}) {
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

  return (
    <Navigate
      replace
      to={buildWorkspaceAppPath(workspaceSlug, defaultWorkspaceAppId)}
    />
  );
}
