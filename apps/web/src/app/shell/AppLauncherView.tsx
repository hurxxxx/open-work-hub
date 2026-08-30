import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { AppId } from '@open-work-hub/contracts/app-contracts';
import { buildAppEntryHref } from '@open-work-hub/contracts/app-routes';

import { workspaceAppIconForKey } from '@/src/platform/workspaces/workspace-app-icons';
import type { AppsBootstrapResponse } from '@/src/platform/workspaces/workspaces-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';

export function AppLauncherView({
  data,
  error,
  loading,
}: {
  data: AppsBootstrapResponse | null;
  error: string | null;
  loading: boolean;
}) {
  const { t } = useTranslation('shell');
  const { user } = useAuth();
  const hasNoWorkspace = user?.workspaces.length === 0;
  const isPlatformAdmin = hasAdminConsoleAccess(user);
  const hasNoApps = Boolean(data && data.apps.length === 0);
  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8">
      <p className="app-text-overline text-app-accent">
        {t('launcher.eyebrow')}
      </p>
      <h1 className="app-text-title-xl mt-2 text-app-ink">
        {t('launcher.title')}
      </h1>
      <p className="app-text-body mt-2 max-w-2xl text-app-ink/60">
        {t('launcher.description')}
      </p>

      {loading && !data ? (
        <div className="mt-8 h-40 animate-pulse rounded-2xl bg-app-surface" />
      ) : null}
      {error ? (
        <p className="app-text-body mt-8 rounded-xl border border-app-danger/25 bg-app-danger/10 p-4 text-app-danger">
          {error}
        </p>
      ) : null}
      {hasNoWorkspace && !loading ? (
        <section className="mt-8 rounded-2xl border border-app-accent/25 bg-app-accent/8 p-5">
          <h2 className="app-text-title-md text-app-ink">
            {t('launcher.noWorkspaceTitle')}
          </h2>
          <p className="app-text-body mt-2 max-w-3xl text-app-ink/65">
            {t('launcher.noWorkspaceDescription')}
          </p>
          {isPlatformAdmin ? (
            <Link
              className="app-text-body-sm mt-4 inline-flex rounded-xl bg-app-accent px-4 py-2.5 font-semibold text-app-accent-fg"
              to="/admin/workspaces"
            >
              {t('launcher.manageWorkspaces')}
            </Link>
          ) : null}
        </section>
      ) : null}
      {hasNoApps && !error ? (
        <section className="mt-8 rounded-2xl border border-app-border bg-app-surface p-6 text-center">
          <h2 className="app-text-title-md text-app-ink">
            {t('launcher.noAppsTitle')}
          </h2>
          <p className="app-text-body mt-2 text-app-ink/60">
            {t('launcher.noAppsDescription')}
          </p>
        </section>
      ) : null}
      <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {(data?.apps ?? []).map((app) => {
          const Icon = workspaceAppIconForKey(app.icon_key);
          return (
            <Link
              className="group rounded-2xl border border-app-border bg-app-surface p-4 transition hover:-translate-y-0.5 hover:border-app-accent/40 hover:shadow-lg"
              key={app.app_id}
              to={buildAppEntryHref(app.app_id as AppId)}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="flex size-11 items-center justify-center rounded-xl bg-app-accent/12 text-app-accent">
                  <Icon size={21} />
                </span>
                <span className="app-text-caption rounded-full bg-app-bg px-2 py-1 text-app-ink/55">
                  {app.availability_scope === 'workspace'
                    ? t('launcher.workspaceApp')
                    : app.execution_context_kind === 'personal'
                      ? t('launcher.personalApp')
                      : t('launcher.companyApp')}
                </span>
              </div>
              <h2 className="app-text-title-sm mt-4 text-app-ink">
                {t(`apps.${app.app_id}`, { defaultValue: app.title })}
              </h2>
              {app.availability_scope === 'workspace' ? (
                <p className="app-text-caption mt-1 text-app-ink/55">
                  {t('launcher.availableWorkspaceCount', {
                    count: app.eligible_workspace_count,
                  })}
                </p>
              ) : null}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
