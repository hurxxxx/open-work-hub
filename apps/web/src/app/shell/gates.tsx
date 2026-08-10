import type { ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import {
  hasConfiguredAdminSectionAccess,
  type AdminSection,
  type AdminSectionAccessResolver,
} from '@/src/platform/admin/admin-permissions';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { workspaceAppIconForKey } from '@/src/platform/workspaces/workspace-app-icons';
import {
  resolveWorkspaceAppGate,
  type WorkspaceAppGateResult,
} from '@/src/platform/workspaces/workspace-app-access';
import type { AppModuleId, NavItem } from './navigation-types';
import { ComingSoonView } from './tool-views/ComingSoonView';

function renderWorkspaceGateContent({
  children,
  gate,
  t,
}: {
  children: ReactNode;
  gate: WorkspaceAppGateResult;
  t: (key: string) => string;
}) {
  switch (gate.status) {
    case 'workspace_denied':
      return <AccessDeniedView description={t('gates.workspaceAppDenied')} />;
    case 'loading':
      return (
        <div className="p-8 text-app-ink/55">{t('gates.workspaceLoading')}</div>
      );
    case 'bootstrap_error':
      return <AccessDeniedView description={gate.error} />;
    case 'app_disabled':
      return <AccessDeniedView description={t('gates.appDisabled')} />;
    case 'allowed':
      return children;
  }
}

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
  const gate = resolveWorkspaceAppGate({
    appId,
    bootstrapAppIds,
    bootstrapError,
    bootstrapLoading,
    user: auth.user,
    workspaceSlug,
  });

  return renderWorkspaceGateContent({ children, gate, t });
}

export function workspaceBootstrapEnabledAppIds(
  data: ReturnType<typeof useWorkspaceBootstrapContext>['data'],
): string[] | null {
  if (!data) {
    return null;
  }
  return data.apps.flatMap((app) => (app.enabled ? [app.app_id] : []));
}

export function workspaceFeatureComingSoonItem(
  data: ReturnType<typeof useWorkspaceBootstrapContext>['data'],
  appId: string,
): NavItem | null {
  const item = data?.apps.find((candidate) => candidate.app_id === appId);
  if (!item?.coming_soon) {
    return null;
  }
  return {
    id: item.app_id,
    title: item.title,
    icon: workspaceAppIconForKey(item.icon_key),
    category: '',
    appId: item.app_id as AppModuleId,
    pathSuffix: item.route_base,
    comingSoon: true,
  };
}

export function WorkspaceFeatureAppGate({
  children,
  appId,
}: {
  children: ReactNode;
  appId: string;
}) {
  const auth = useAuth();
  const { t } = useTranslation('shell');
  const { workspaceSlug } = useParams();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const gate = resolveWorkspaceAppGate({
    appId,
    bootstrapAppIds: workspaceBootstrapEnabledAppIds(workspaceBootstrap.data),
    bootstrapError: workspaceBootstrap.error,
    bootstrapLoading: workspaceBootstrap.loading,
    user: auth.user,
    workspaceSlug,
  });

  const comingSoonItem =
    gate.status === 'allowed'
      ? workspaceFeatureComingSoonItem(workspaceBootstrap.data, appId)
      : null;
  if (comingSoonItem) {
    return <ComingSoonView item={comingSoonItem} />;
  }

  return renderWorkspaceGateContent({ children, gate, t });
}

export function AdminGate({
  section,
  children,
  hasAdminSectionAccess:
    canAccessAdminSection = hasConfiguredAdminSectionAccess,
}: {
  section: AdminSection | string;
  children: ReactNode;
  hasAdminSectionAccess?: AdminSectionAccessResolver;
}) {
  const auth = useAuth();
  const { t } = useTranslation('shell');
  if (
    !hasAdminConsoleAccess(auth.user) ||
    !canAccessAdminSection(auth.user?.system_roles ?? [], section)
  ) {
    return <AccessDeniedView description={t('gates.adminSectionDenied')} />;
  }

  return children;
}
