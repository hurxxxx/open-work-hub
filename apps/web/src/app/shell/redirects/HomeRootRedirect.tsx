import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  resolveRootEntryPath,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';

export function HomeRootRedirect({
  defaultWorkspaceAppId,
}: {
  defaultWorkspaceAppId?: WorkspaceAppId;
}) {
  const auth = useAuth();
  const { t } = useTranslation('shell');

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  const targetPath = resolveRootEntryPath(auth.user, defaultWorkspaceAppId);
  if (!targetPath) {
    return (
      <AccessDeniedView description={t('gates.noAccessibleWorkspace')} />
    );
  }

  return <Navigate replace to={targetPath} />;
}
