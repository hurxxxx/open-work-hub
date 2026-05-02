import type { ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import {
  hasAdminSectionAccess,
  type AdminSection,
} from '@/src/platform/admin/admin-permissions';
import {
  hasAdminConsoleAccess,
  hasWorkspaceMembership,
} from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';

export function WorkspaceGate({
  children,
  appId,
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
}: {
  children: ReactNode;
  appId: string;
  bootstrapAppIds: string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
}) {
  const auth = useAuth();
  const { t } = useTranslation('shell');
  const { workspaceSlug } = useParams();

  if (!hasWorkspaceMembership(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description={t('gates.workspaceAppDenied')} />
    );
  }

  if (workspaceSlug) {
    if (bootstrapLoading || bootstrapAppIds === null) {
      return <div className="p-8 text-gray-500">{t('gates.workspaceLoading')}</div>;
    }
    if (bootstrapError) {
      return <AccessDeniedView description={bootstrapError} />;
    }
    if (!bootstrapAppIds.includes(appId)) {
      return (
        <AccessDeniedView description={t('gates.appDisabled')} />
      );
    }
  }

  return children;
}

export function AdminGate({
  section,
  children,
}: {
  section: AdminSection;
  children: ReactNode;
}) {
  const auth = useAuth();
  const { t } = useTranslation('shell');
  if (!hasAdminConsoleAccess(auth.user) || !hasAdminSectionAccess(auth.user?.system_roles ?? [], section)) {
    return <AccessDeniedView description={t('gates.adminSectionDenied')} />;
  }

  return children;
}
