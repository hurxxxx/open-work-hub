import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@open-work-hub/ui';

import {
  listAdminUsers,
  listAuditLogs,
  listTeams,
  listWorkspaces,
} from './admin-api';
import { AiSecuritySection } from './admin-ai-security-section';
import { AppsSection, type AdminAppsPage } from './admin-apps-section';
import { AuditSection } from './admin-audit-section';
import { CommunitySection } from './admin-community-section';
import { AdminDocumentProcessingSection } from './admin-document-processing-section';
import { AdminLlmManagementSection } from './admin-llm-management-section';
import { AdminModelRuntimeStatusSection } from './admin-model-runtime-status-section';
import { SurfaceCard, getErrorMessage, isAdminUser } from './admin-shared';
import {
  hasAnyAdminReadPermission,
  type AdminSection,
} from './admin-permissions';
import { UsageSection } from './admin-usage-section';
import { WorkspacesSection } from './admin-workspaces-section';

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
  apps: {
    titleKey: 'admin.console.sections.apps.title',
    descriptionKey: 'admin.console.sections.apps.description',
  },
  llm: {
    titleKey: 'admin.console.sections.llm.title',
    descriptionKey: 'admin.console.sections.llm.description',
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
  workspaces: {
    titleKey: 'admin.console.sections.workspaces.title',
    descriptionKey: 'admin.console.sections.workspaces.description',
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

function GeneralSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const auth = useAuth();
  const [summary, setSummary] = useState({
    userCount: null as number | null,
    adminCount: null as number | null,
    workspaceCount: null as number | null,
    teamCount: null as number | null,
    auditCount: null as number | null,
  });
  const [error, setError] = useState<string | null>(null);
  const canReadUsers = auth.hasPermission('user.read');
  const canReadWorkspaces = auth.hasPermission('workspace.read');
  const canReadTeams = auth.hasPermission('team.read');
  const canReadAudit = auth.hasPermission('audit.read');

  function formatCount(value: number | null) {
    return value ?? t('admin.console.general.restricted');
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [users, workspaces, teams, audits] = await Promise.all([
          canReadUsers
            ? listAdminUsers(token, { page_size: 100 })
            : Promise.resolve(null),
          canReadWorkspaces ? listWorkspaces(token) : Promise.resolve(null),
          canReadTeams ? listTeams(token) : Promise.resolve(null),
          canReadAudit ? listAuditLogs(token) : Promise.resolve(null),
        ]);
        if (cancelled) {
          return;
        }
        setSummary({
          userCount: users?.total ?? null,
          adminCount:
            users?.items.filter((item) => isAdminUser(item)).length ?? null,
          workspaceCount: workspaces?.length ?? null,
          teamCount: teams?.length ?? null,
          auditCount: audits?.total ?? null,
        });
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            getErrorMessage(
              caughtError,
              t('admin.console.general.summaryLoadFailed'),
            ),
          );
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [canReadAudit, canReadTeams, canReadUsers, canReadWorkspaces, t, token]);

  return (
    <div className="space-y-6">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SurfaceCard
          title={t('admin.console.general.operatingModelTitle')}
          description={t('admin.console.general.operatingModelDescription')}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              <div className="app-text-title-md text-app-ink">
                {t('admin.console.general.identityTitle')}
              </div>
              <div className="app-text-body mt-3 space-y-2 text-app-ink/55">
                <div>
                  {t('admin.console.general.userCount', {
                    count: formatCount(summary.userCount),
                    suffix:
                      summary.userCount !== null
                        ? t('admin.console.units.count')
                        : '',
                  })}
                </div>
                <div>
                  {t('admin.console.general.adminCount', {
                    count: formatCount(summary.adminCount),
                    suffix:
                      summary.adminCount !== null
                        ? t('admin.console.units.people')
                        : '',
                  })}
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              <div className="app-text-title-md text-app-ink">
                {t('admin.console.general.workModelTitle')}
              </div>
              <div className="app-text-body mt-3 space-y-2 text-app-ink/55">
                <div>
                  {t('admin.console.general.workspaceCount', {
                    count: formatCount(summary.workspaceCount),
                    suffix:
                      summary.workspaceCount !== null
                        ? t('admin.console.units.count')
                        : '',
                  })}
                </div>
                <div>
                  {t('admin.console.general.teamCount', {
                    count: formatCount(summary.teamCount),
                    suffix:
                      summary.teamCount !== null
                        ? t('admin.console.units.count')
                        : '',
                  })}
                </div>
              </div>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard
          title={t('admin.console.general.notesTitle')}
          description={t('admin.console.general.notesDescription')}
        >
          <div className="app-text-body space-y-3 text-app-ink/55">
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              {t('admin.console.general.noteProfile')}
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              {t('admin.console.general.noteNavigation')}
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              {t('admin.console.general.noteAudit')}
            </div>
          </div>
        </SurfaceCard>
      </div>
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
      content = <GeneralSection token={token} />;
      break;
    case 'apps':
      content = <AppsSection page={appsPage ?? 'platform'} token={token} />;
      break;
    case 'llm':
      content = <AdminLlmManagementSection token={token} />;
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
    case 'workspaces':
      content = <WorkspacesSection token={token} />;
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
