import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Link } from 'react-router-dom';
import { AiSecuritySection } from './admin-ai-security-section';
import { AppsSection, type AdminAppsPage } from './admin-apps-section';
import { AuditSection } from './admin-audit-section';
import { CommunitySection } from './admin-community-section';
import { AdminDocumentProcessingSection } from './admin-document-processing-section';
import { GroupsSection } from './admin-groups-section';
import { AdminHermesToolsSection } from './admin-hermes-tools-section';
import { AdminLlmManagementSection } from './admin-llm-management-section';
import { AdminModelRuntimeStatusSection } from './admin-model-runtime-status-section';
import { AdminOrganizationSection } from './admin-organization-section';
import { PeopleSection } from './admin-people-section';
import {
  hasAnyAdminReadPermission,
  type AdminSection,
} from './admin-permissions';
import { AdminPlatformApiKeysSection } from './admin-platform-api-keys-section';
import { UsageSection } from './admin-usage-section';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';

const sectionMeta: Record<
  AdminSection,
  { titleKey: string; descriptionKey?: string }
> = {
  general: {
    titleKey: 'admin.console.sections.general.title',
    descriptionKey: 'admin.console.sections.general.description',
  },
  people: {
    titleKey: 'admin.console.sections.people.title',
    descriptionKey: 'admin.console.sections.people.description',
  },
  organization: {
    titleKey: 'admin.console.sections.organization.title',
    descriptionKey: 'admin.console.sections.organization.description',
  },
  'api-integrations': {
    titleKey: 'admin.console.sections.apiIntegrations.title',
    descriptionKey: 'admin.console.sections.apiIntegrations.description',
  },
  apps: {
    titleKey: 'admin.console.sections.apps.title',
    descriptionKey: 'admin.console.sections.apps.description',
  },
  llm: {
    titleKey: 'admin.console.sections.llm.title',
    descriptionKey: 'admin.console.sections.llm.description',
  },
  'ai-tools': {
    titleKey: 'admin.console.sections.aiTools.title',
    descriptionKey: 'admin.console.sections.aiTools.description',
  },
  'model-monitoring': {
    titleKey: 'admin.console.sections.modelMonitoring.title',
    descriptionKey: 'admin.console.sections.modelMonitoring.description',
  },
  'document-processing': {
    titleKey: 'admin.console.sections.documentProcessing.title',
    descriptionKey: 'admin.console.sections.documentProcessing.description',
  },
  'ai-security': {
    titleKey: 'admin.console.sections.aiSecurity.title',
    descriptionKey: 'admin.console.sections.aiSecurity.description',
  },
  groups: {
    titleKey: 'shell:companyGroups.title',
    descriptionKey: 'shell:companyGroups.policy',
  },
  community: {
    titleKey: 'admin.console.sections.community.title',
    descriptionKey: 'admin.console.sections.community.description',
  },
  usage: {
    titleKey: 'admin.console.sections.usage.title',
    descriptionKey: 'admin.console.sections.usage.description',
  },
  audit: {
    titleKey: 'admin.console.sections.audit.title',
    descriptionKey: 'admin.console.sections.audit.description',
  },
};

function SettingsShell({
  section,
  appsPage,
  children,
  actions,
}: {
  section: AdminSection;
  appsPage?: AdminAppsPage;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const { t } = useTranslation('apps');
  const meta =
    section === 'apps' && appsPage
      ? {
          titleKey: `admin.console.sections.apps.${appsPage}.title`,
          descriptionKey: `admin.console.sections.apps.${appsPage}.description`,
        }
      : sectionMeta[section];
  const description = meta.descriptionKey ? t(meta.descriptionKey) : '';

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="w-full space-y-6">
        <header className="flex flex-col gap-2 border-b border-app-border pb-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="app-text-title text-app-ink">
                {t(meta.titleKey)}
              </h1>
            </div>
            {description ? (
              <p className="app-text-body max-w-3xl text-app-ink/55">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 items-center gap-3">{actions}</div>
          ) : null}
        </header>
        {children}
      </div>
    </div>
  );
}

function GeneralSection() {
  const { t } = useTranslation('shell');
  return (
    <div className="space-y-4">
      <p className="app-text-body text-app-ink/70">
        {t('companyAccess.platformRule')}
      </p>
      <nav className="flex flex-wrap gap-4">
        <Link to="/admin/people" className="text-app-accent">
          {t('companyAccess.users')}
        </Link>
        <Link to="/admin/organization" className="text-app-accent">
          {t('companyGroups.organization')}
        </Link>
        <Link to="/admin/groups" className="text-app-accent">
          {t('companyGroups.title')}
        </Link>
        <Link to="/admin/apps/access" className="text-app-accent">
          {t('companyAccess.title')}
        </Link>
      </nav>
    </div>
  );
}

export function AdminConsoleView({
  section,
  appsPage,
}: {
  section: AdminSection;
  appsPage?: AdminAppsPage;
}) {
  const { t } = useTranslation('apps');
  const auth = useAuth();
  const token = auth.token;
  const hasAdminReadPermission = useMemo(
    () => hasAnyAdminReadPermission(auth.user?.system_roles ?? []),
    [auth.user],
  );

  if (!token) {
    return null;
  }

  if (!hasAdminReadPermission) {
    return <AccessDeniedView description={t('admin.console.accessDenied')} />;
  }

  let content: React.ReactNode;
  let actions: React.ReactNode;

  switch (section) {
    case 'general':
      content = <GeneralSection />;
      break;
    case 'people':
      content = <PeopleSection token={token} />;
      break;
    case 'organization':
      content = <AdminOrganizationSection token={token} />;
      break;
    case 'api-integrations':
      content = <AdminPlatformApiKeysSection token={token} />;
      break;
    case 'apps':
      content = <AppsSection page={appsPage ?? 'access'} token={token} />;
      break;
    case 'llm':
      content = <AdminLlmManagementSection token={token} />;
      break;
    case 'ai-tools':
      content = <AdminHermesToolsSection token={token} />;
      break;
    case 'model-monitoring':
      content = <AdminModelRuntimeStatusSection token={token} />;
      break;
    case 'document-processing':
      content = <AdminDocumentProcessingSection token={token} />;
      break;
    case 'ai-security':
      content = <AiSecuritySection token={token} />;
      break;
    case 'groups':
      content = <GroupsSection token={token} />;
      break;
    case 'community':
      content = <CommunitySection token={token} />;
      break;
    case 'usage':
      content = <UsageSection token={token} />;
      break;
    case 'audit':
      content = <AuditSection token={token} />;
      break;
    default:
      content = null;
  }

  return (
    <SettingsShell actions={actions} appsPage={appsPage} section={section}>
      {content}
    </SettingsShell>
  );
}
