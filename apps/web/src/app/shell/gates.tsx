import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import {
  hasConfiguredAdminSectionAccess,
  type AdminSection,
  type AdminSectionAccessResolver,
} from '@/src/platform/admin/admin-permissions';
import {
  resolveAppGate,
  type AppGateResult,
} from '@/src/platform/apps/app-access';
import { useAppBootstrapContext } from '@/src/platform/apps/app-bootstrap-context';
import { appIconForKey } from '@/src/platform/apps/app-icons';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import type { AppModuleId, NavItem } from './navigation-types';
import { ComingSoonView } from './tool-views/ComingSoonView';

function renderAppGateContent({
  children,
  gate,
  t,
}: {
  children: ReactNode;
  gate: AppGateResult;
  t: (key: string) => string;
}) {
  switch (gate.status) {
    case 'principal_denied':
      return <AccessDeniedView description={t('gates.appDisabled')} />;
    case 'loading':
      return (
        <div className="p-8 text-app-ink/55">{t('appBootstrap.loading')}</div>
      );
    case 'bootstrap_error':
      return <AccessDeniedView description={gate.error} />;
    case 'app_disabled':
      return <AccessDeniedView description={t('gates.appDisabled')} />;
    case 'allowed':
      return children;
  }
}

export function AppGate({
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
  const gate = resolveAppGate({
    appId,
    bootstrapAppIds,
    bootstrapError,
    bootstrapLoading,
    user: auth.user,
  });

  return renderAppGateContent({ children, gate, t });
}

export function bootstrapEnabledAppIds(
  data: ReturnType<typeof useAppBootstrapContext>['data'],
): string[] | null {
  if (!data) {
    return null;
  }
  return data.apps.flatMap((app) => (app.enabled ? [app.app_id] : []));
}

export function featureComingSoonItem(
  data: ReturnType<typeof useAppBootstrapContext>['data'],
  appId: string,
): NavItem | null {
  const item = data?.apps.find((candidate) => candidate.app_id === appId);
  if (!item?.coming_soon) {
    return null;
  }
  return {
    id: item.app_id,
    title: item.title,
    icon: appIconForKey(item.icon_key),
    category: '',
    appId: item.app_id as AppModuleId,
    absolutePath: item.route_base,
    comingSoon: true,
  };
}

export function FeatureAppGate({
  children,
  appId,
}: {
  children: ReactNode;
  appId: string;
}) {
  const auth = useAuth();
  const { t } = useTranslation('shell');
  const appBootstrap = useAppBootstrapContext();
  const gate = resolveAppGate({
    appId,
    bootstrapAppIds: bootstrapEnabledAppIds(appBootstrap.data),
    bootstrapError: appBootstrap.error,
    bootstrapLoading: appBootstrap.loading,
    user: auth.user,
  });

  const comingSoonItem =
    gate.status === 'allowed'
      ? featureComingSoonItem(appBootstrap.data, appId)
      : null;
  if (comingSoonItem) {
    return <ComingSoonView item={comingSoonItem} />;
  }

  return renderAppGateContent({ children, gate, t });
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
